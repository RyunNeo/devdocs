import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, defer, sessionmaker

from app.core.config import Settings
from app.core.logging import safe_log
from app.core.usage_context import UsageRecorder, bind_usage
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.rag import embeddings
from app.rag.splitter import SPLITTER_VERSION, ChunkLimitError, split_document
from app.services import document_service as documents
from app.services.usage_service import finish_operation, reserve_operation

logger = logging.getLogger(__name__)


def fingerprint(content_hash: str) -> str:
    return hashlib.sha256(
        f"{content_hash}:{embeddings.MODEL}:{embeddings.DIMENSIONS}:{SPLITTER_VERSION}".encode()
    ).hexdigest()


def _locked_document(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID):
    initial = documents.get_owned(db, user_id, doc_id)
    documents.lock_knowledge(db, user_id, initial.knowledge_base_id)
    return db.scalar(
        documents.owned_query(user_id)
        .where(Document.id == doc_id)
        .with_for_update(of=Document)
        .execution_options(populate_existing=True)
    )


def index_document(
    db: Session, settings: Settings, user_id: uuid.UUID, doc_id: uuid.UUID, request_id=None
):
    doc = _locked_document(db, user_id, doc_id)
    if doc is None:
        raise HTTPException(404, "文档不存在或无法访问")
    if doc.status != "parsed" or not doc.extracted_text:
        raise HTTPException(409, "请先成功解析文档，再建立索引")
    target = fingerprint(doc.content_hash)
    count = db.scalar(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    )
    if (
        doc.index_status == "completed"
        and doc.index_fingerprint == target
        and count == doc.chunk_count
        and count
    ):
        db.commit()
        return doc
    now = datetime.now(timezone.utc)
    started = doc.index_started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if (
        doc.index_status == "indexing"
        and started is not None
        and (now - started).total_seconds() < 300
    ):
        raise HTTPException(409, "文档正在建立索引，请稍后刷新查看")
    try:
        provider = embeddings.make_embeddings(settings)
    except embeddings.EmbeddingError as failure:
        raise HTTPException(503, str(failure)) from None
    run_id = uuid.uuid4()
    event = reserve_operation(
        db,
        user_id,
        "index",
        run_id,
        request_id or str(uuid.uuid4()),
        settings,
        knowledge_base_id=doc.knowledge_base_id,
        document_id=doc_id,
        now=now,
    )
    snapshot = {
        "text": doc.extracted_text,
        "file_type": doc.file_type,
        "source_metadata": doc.source_metadata,
    }
    doc.index_status = "indexing"
    doc.index_error = None
    doc.index_run_id = run_id
    doc.index_started_at = now
    db.commit()
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    recorder = UsageRecorder(factory, event.id)
    scope = bind_usage(recorder)
    scope.__enter__()
    outcome, error_code = "failed", None
    elapsed = time.monotonic()
    # External requests do not hold database row locks.
    try:
        chunks = split_document(
            snapshot["text"], snapshot["file_type"], snapshot["source_metadata"]
        )
        vectors = embeddings.validate_vectors(
            provider.embed_documents([chunk["content"] for chunk in chunks]), len(chunks)
        )
        db.expire_all()
        doc = _locked_document(db, user_id, doc_id)
        if doc is None or doc.index_run_id != run_id:
            raise HTTPException(409, "索引任务已失效，请刷新文档列表")
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        db.add_all(
            DocumentChunk(
                document_id=doc.id,
                knowledge_base_id=doc.knowledge_base_id,
                user_id=user_id,
                chunk_index=position,
                content=chunk["content"],
                source_metadata=chunk["metadata"],
                embedding_model=embeddings.MODEL,
                embedding_dimension=embeddings.DIMENSIONS,
                embedding=vector,
            )
            for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        )
        doc.index_status = "completed"
        doc.index_fingerprint = target
        doc.index_run_id = None
        doc.chunk_count = len(chunks)
        db.commit()
        outcome = "completed"
        safe_log(
            logger,
            "index_finished",
            request_id=event.request_id,
            document_id=str(doc_id),
            chunks=len(chunks),
            model=embeddings.MODEL,
            status=outcome,
        )
        return doc
    except HTTPException:
        db.rollback()
        error_code = "run_expired"
        raise
    except Exception as failure:
        db.rollback()
        error_code = "index_failed"
        message = (
            str(failure)
            if isinstance(failure, (embeddings.EmbeddingError, ChunkLimitError))
            else "索引建立失败，请稍后重试"
        )
        safe_log(
            logger,
            "index_finished",
            request_id=event.request_id,
            document_id=str(doc_id),
            error_type=type(failure).__name__,
            status="failed",
        )
        db.expire_all()
        doc = _locked_document(db, user_id, doc_id)
        if doc is None or doc.index_run_id != run_id:
            raise HTTPException(409, "索引任务已失效，请刷新文档列表")
        doc.index_status = "failed"
        doc.index_error = message
        doc.index_run_id = None
        db.commit()
        return doc
    finally:
        db.rollback()
        recorder.metrics.durations_ms["total"] = round((time.monotonic() - elapsed) * 1000)
        recorder.metrics.durations_ms["index_processing"] = (
            recorder.metrics.durations_ms["total"] if outcome == "completed" else None
        )
        try:
            finish_operation(factory, event.id, outcome, recorder.snapshot(), error_code)
        except Exception:
            safe_log(
                logger, "usage_storage_failed", request_id=event.request_id, document_id=str(doc_id)
            )
        scope.__exit__(None, None, None)


def list_chunks(db: Session, user_id: uuid.UUID, doc_id: uuid.UUID, limit: int, offset: int):
    documents.get_owned(db, user_id, doc_id)
    query = select(DocumentChunk).where(
        DocumentChunk.document_id == doc_id, DocumentChunk.user_id == user_id
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    chunks = db.scalars(
        query.options(defer(DocumentChunk.embedding))
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "metadata": chunk.source_metadata,
                "embedding_model": chunk.embedding_model,
                "embedding_dimension": chunk.embedding_dimension,
            }
            for chunk in chunks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
