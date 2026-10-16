from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.usage import UsageEvent
from app.schemas.conversation import ConversationDetail, ConversationRead, MessageRead
from app.services.knowledge_base_service import get_owned_knowledge_base


def get_owned_conversation(db: Session, user_id: UUID, conversation_id: UUID, lock=False):
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    conversation = db.scalar(query)
    if conversation is None:
        raise HTTPException(404, "会话不存在或无法访问")
    return conversation


def expire_run(db: Session, conversation: Conversation):
    started = conversation.active_started_at
    if started is None:
        return
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - started).total_seconds() >= 180:
        db.execute(
            update(UsageEvent)
            .where(
                UsageEvent.operation == "chat",
                UsageEvent.operation_run_id == conversation.active_run_id,
                UsageEvent.user_id == conversation.user_id,
                UsageEvent.status == "running",
            )
            .values(
                status="interrupted",
                error_code="interrupted",
                finished_at=datetime.now(timezone.utc),
            )
        )
        db.execute(
            update(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.run_id == conversation.active_run_id,
                Message.status == "streaming",
            )
            .values(
                status="failed", error_code="interrupted", updated_at=datetime.now(timezone.utc)
            )
        )
        conversation.active_run_id = None
        conversation.active_started_at = None


def create_conversation(db: Session, user_id: UUID, kb_id: UUID):
    get_owned_knowledge_base(db, user_id, kb_id)
    conversation = Conversation(user_id=user_id, knowledge_base_id=kb_id)
    db.add(conversation)
    db.commit()
    return conversation


def refresh_citation_status(db, user_id, citations):
    result = []
    for citation in citations:
        snapshot = dict(citation)
        doc = db.execute(
            select(Document.id, Document.index_status, Document.index_fingerprint).where(
                Document.id == UUID(citation["document_id"]), Document.user_id == user_id
            )
        ).first()
        chunk = db.scalar(
            select(DocumentChunk.id).where(
                DocumentChunk.id == UUID(citation["chunk_id"]), DocumentChunk.user_id == user_id
            )
        )
        snapshot["source_status"] = (
            "deleted"
            if doc is None
            else "current"
            if (
                chunk is not None
                and doc.index_status == "completed"
                and doc.index_fingerprint == citation.get("index_fingerprint")
            )
            else "changed"
        )
        result.append(snapshot)
    return result


def list_conversations(db: Session, user_id: UUID, kb_id: UUID, limit: int, offset: int):
    get_owned_knowledge_base(db, user_id, kb_id)

    def user_question(length, descending=False):
        return (
            select(func.substr(Message.content, 1, length))
            .where(Message.conversation_id == Conversation.id, Message.role == "user")
            .order_by(Message.sequence.desc() if descending else Message.sequence.asc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )

    first = user_question(40)
    last = user_question(80, True)
    status = (
        select(Message.status)
        .where(Message.conversation_id == Conversation.id, Message.role == "assistant")
        .order_by(Message.sequence.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    owned = (
        Conversation.user_id == user_id,
        Conversation.knowledge_base_id == kb_id,
        first.is_not(None),
    )
    total = db.scalar(select(func.count()).select_from(Conversation).where(*owned))
    rows = db.execute(
        select(
            Conversation.id,
            Conversation.knowledge_base_id,
            Conversation.created_at,
            Conversation.updated_at,
            first.label("title"),
            last.label("last_question"),
            status.label("latest_status"),
        )
        .where(*owned)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [dict(row._mapping) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def read_conversation(
    db: Session,
    user_id: UUID,
    conversation_id: UUID,
    before_sequence: int | None = None,
    limit: int = 40,
):
    conversation = get_owned_conversation(db, user_id, conversation_id, lock=True)
    expire_run(db, conversation)
    db.commit()
    filters = [Message.conversation_id == conversation_id]
    if before_sequence is not None:
        filters.append(Message.sequence < before_sequence)
    messages = list(
        db.scalars(
            select(Message).where(*filters).order_by(Message.sequence.desc()).limit(limit + 1)
        )
    )
    reads = []
    for message in reversed(messages[:limit]):
        read = MessageRead.model_validate(message)
        if read.role == "assistant" and read.status != "completed":
            read.content = ""
            read.citations = []
        else:
            read.citations = refresh_citation_status(db, user_id, read.citations)
        reads.append(read)
    return ConversationDetail(
        **ConversationRead.model_validate(conversation).model_dump(),
        messages=reads,
        has_older=len(messages) > limit,
    )
