import logging
from pathlib import PurePosixPath
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from app.core.config import Settings
from app.core.logging import safe_log
from app.models.chunk import DocumentChunk
from app.models.document import Document, StorageCleanupTask
from app.models.knowledge_base import KnowledgeBase
from app.rag.loaders import TextParseError, extract_document
from app.schemas.document import DocumentRead
from app.services import document_storage as storage

logger = logging.getLogger(__name__)


def lock_knowledge(db: Session, user_id: UUID, kb_id: UUID) -> KnowledgeBase:
    kb = db.scalar(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
        .with_for_update()
    )
    if kb is None:
        raise HTTPException(404, "知识库不存在或无法访问")
    return kb


def owned_query(user_id: UUID):
    return (
        select(Document)
        .join(KnowledgeBase)
        .where(Document.user_id == user_id, KnowledgeBase.user_id == user_id)
    )


def get_owned(db: Session, user_id: UUID, doc_id: UUID) -> Document:
    doc = db.scalar(owned_query(user_id).where(Document.id == doc_id))
    if doc is None:
        raise HTTPException(404, "文档不存在或无法访问")
    return doc


def upload_document(
    db: Session, settings: Settings, user_id: UUID, kb_id: UUID, file: UploadFile
) -> Document:
    # All document writes lock the parent, including deletion, preventing orphan upload races.
    lock_knowledge(db, user_id, kb_id)
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise HTTPException(400, "文件名无效或过长")
    kind = PurePosixPath(name).suffix.lower().lstrip(".")
    if kind not in {"md", "txt", "pdf"}:
        raise HTTPException(400, "目前只支持 Markdown (.md)、TXT (.txt) 和文本 PDF (.pdf)")
    key, size, digest = storage.store_file(settings, file)
    try:
        if db.scalar(
            select(Document.id).where(
                Document.knowledge_base_id == kb_id, Document.content_hash == digest
            )
        ):
            raise HTTPException(409, "这个知识库中已有相同内容的文档")
        doc = Document(
            knowledge_base_id=kb_id,
            user_id=user_id,
            filename=name,
            file_type=kind,
            size_bytes=size,
            content_hash=digest,
            storage_key=key,
        )
        db.add(doc)
        db.commit()
    except Exception as failure:
        db.rollback()
        # The file survives a rolled-back insert until its independent cleanup task commits.
        db.add(StorageCleanupTask(storage_key=key))
        db.commit()
        storage.drain_cleanup(db, settings, [key])
        if isinstance(failure, IntegrityError):
            constraint = getattr(getattr(failure.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_documents_kb_hash" or (
                "UNIQUE constraint failed: documents.knowledge_base_id, documents.content_hash"
                in str(failure.orig)
            ):
                raise HTTPException(409, "这个知识库中已有相同内容的文档") from None
        raise
    return process_document(db, settings, user_id, doc.id)


def process_document(db: Session, settings: Settings, user_id: UUID, doc_id: UUID) -> Document:
    initial = get_owned(db, user_id, doc_id)
    lock_knowledge(db, user_id, initial.knowledge_base_id)
    doc = db.scalar(
        owned_query(user_id)
        .where(Document.id == doc_id)
        .with_for_update(of=Document)
        .execution_options(populate_existing=True)
    )
    if doc is None:
        raise HTTPException(404, "文档不存在或无法访问")
    if doc.status == "parsed":
        db.commit()
        return doc
    doc.status = "processing"
    doc.error_message = None
    doc.parse_warning = None
    doc.extracted_text = None
    doc.source_metadata = {}
    doc.character_count = 0
    try:
        with storage.file_path(settings, doc.storage_key).open("rb") as source:
            data = source.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise TextParseError("文件超过当前解析大小限制")
        doc.extracted_text, doc.source_metadata = extract_document(data, doc.file_type)
        empty_pages = doc.source_metadata.get("empty_pages", 0)
        if empty_pages:
            doc.parse_warning = f"有 {empty_pages} 页未提取到文本，索引仅包含有文本的页面"
        doc.character_count = len(doc.extracted_text)
        doc.status = "parsed"
    except TextParseError as failure:
        doc.status = "failed"
        doc.error_message = str(failure)
    except (OSError, ValueError):
        doc.status = "failed"
        doc.error_message = "无法读取原文件，请检查存储目录后重试"
        safe_log(logger, "storage_failed", document_id=str(doc.id))
    db.commit()
    safe_log(logger, "document_parsed", document_id=str(doc.id), status=doc.status)
    return doc


def list_documents(db: Session, user_id: UUID, kb_id: UUID, limit: int, offset: int) -> dict:
    kb = db.scalar(
        select(KnowledgeBase.id).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
    )
    if kb is None:
        raise HTTPException(404, "知识库不存在或无法访问")
    query = owned_query(user_id).where(Document.knowledge_base_id == kb_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.options(defer(Document.extracted_text), defer(Document.source_metadata))
        .order_by(Document.created_at.desc(), Document.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def detail(db: Session, user_id: UUID, doc_id: UUID) -> dict:
    doc = get_owned(db, user_id, doc_id)
    text = doc.extracted_text
    return {
        **DocumentRead.model_validate(doc).model_dump(),
        "text_preview": text[:20000] if text is not None else None,
        "preview_truncated": text is not None and len(text) > 20000,
    }


def delete_document(db: Session, settings: Settings, user_id: UUID, doc_id: UUID) -> None:
    initial = get_owned(db, user_id, doc_id)
    lock_knowledge(db, user_id, initial.knowledge_base_id)
    doc = get_owned(db, user_id, doc_id)
    key = doc.storage_key
    db.add(StorageCleanupTask(storage_key=key))
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    db.delete(doc)
    db.commit()
    storage.drain_cleanup(db, settings, [key])


def summary(db: Session, user_id: UUID) -> dict:
    return {"total": db.scalar(select(func.count()).select_from(owned_query(user_id).subquery()))}
