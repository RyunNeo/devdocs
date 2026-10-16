import json
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import defer

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.rag.embeddings import DIMENSIONS, MODEL
from app.services.indexing_service import fingerprint


@dataclass
class RetrievedSource:
    number: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    filename: str
    content: str
    metadata: dict
    similarity: float
    index_fingerprint: str


def eligible_documents(db, user_id, kb_id):
    rows = db.execute(
        select(
            Document.id, Document.filename, Document.index_fingerprint, Document.content_hash
        ).where(
            Document.user_id == user_id,
            Document.knowledge_base_id == kb_id,
            Document.status == "parsed",
            Document.index_status == "completed",
            Document.chunk_count > 0,
        )
    )
    return {row.id: row for row in rows if row.index_fingerprint == fingerprint(row.content_hash)}


def has_sources(db, user_id, kb_id):
    documents = eligible_documents(db, user_id, kb_id)
    if not documents:
        return False
    return (
        db.scalar(
            select(DocumentChunk.id)
            .where(
                DocumentChunk.document_id.in_(documents),
                DocumentChunk.user_id == user_id,
                DocumentChunk.knowledge_base_id == kb_id,
                DocumentChunk.embedding_model == MODEL,
                DocumentChunk.embedding_dimension == DIMENSIONS,
            )
            .limit(1)
        )
        is not None
    )


def budget_sources(sources, budget=12000):
    result = []
    for source in sources:
        source.metadata = {
            str(key)[:64]: value[:512] if isinstance(value, str) else value
            for key, value in list(source.metadata.items())[:16]
            if type(value) in {str, int, float, bool}
        }
        source.number = len(result) + 1
        encoded = json.dumps(
            [source_data(s) for s in [*result, source]], ensure_ascii=False
        ).encode()
        if len(encoded) > budget:
            continue
        result.append(source)
    return result


def source_data(source):
    return {
        "number": source.number,
        "filename": source.filename,
        "metadata": source.metadata,
        "content": source.content,
    }


def retrieve_sources(db, user_id, kb_id, vector, settings):
    documents = eligible_documents(db, user_id, kb_id)
    if not documents:
        return []
    owned = (
        DocumentChunk.document_id.in_(documents),
        DocumentChunk.user_id == user_id,
        DocumentChunk.knowledge_base_id == kb_id,
        DocumentChunk.embedding_model == MODEL,
        DocumentChunk.embedding_dimension == DIMENSIONS,
    )
    if db.bind.dialect.name == "postgresql":
        distance = DocumentChunk.embedding.cosine_distance(vector)
        rows = db.execute(
            select(DocumentChunk, (1 - distance).label("similarity"))
            .options(defer(DocumentChunk.embedding))
            .where(*owned, (1 - distance) >= settings.retrieval_min_similarity)
            .order_by(distance, DocumentChunk.id)
            .limit(settings.retrieval_top_k)
        ).all()
    else:
        rows = []
        for chunk in db.scalars(select(DocumentChunk).where(*owned)):
            norm = math.hypot(*chunk.embedding) * math.hypot(*vector)
            score = (
                sum(a * b for a, b in zip(chunk.embedding, vector, strict=True)) / norm
                if norm
                else -1
            )
            if score >= settings.retrieval_min_similarity:
                rows.append((chunk, score))
        rows.sort(key=lambda row: (-row[1], str(row[0].id)))
        rows = rows[: settings.retrieval_top_k]
    return budget_sources(
        [
            RetrievedSource(
                i + 1,
                chunk.document_id,
                chunk.id,
                chunk.chunk_index,
                documents[chunk.document_id].filename,
                chunk.content,
                chunk.source_metadata,
                float(score),
                documents[chunk.document_id].index_fingerprint,
            )
            for i, (chunk, score) in enumerate(rows)
        ]
    )
