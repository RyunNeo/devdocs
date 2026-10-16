from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.document import Document, StorageCleanupTask
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services import document_storage


def normalize_name(name: str) -> str:
    return "".join(name.split()).casefold()


def assert_name_available(
    db: Session, user_id: UUID, name: str, exclude_id: UUID | None = None
) -> None:
    # Read display names too, so legacy spaced keys remain protected before migration.
    key = normalize_name(name)
    rows = db.execute(
        select(KnowledgeBase.id, KnowledgeBase.name).where(KnowledgeBase.user_id == user_id)
    )
    for identifier, existing_name in rows:
        if identifier != exclude_id and normalize_name(existing_name) == key:
            raise HTTPException(409, "你已有同名知识库，请换一个名称")


def commit_change(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        sqlite_duplicate = (
            "UNIQUE constraint failed: knowledge_bases.user_id, knowledge_bases.name_key"
            in str(error.orig)
        )
        if constraint == "uq_knowledge_bases_user_name" or sqlite_duplicate:
            raise HTTPException(409, "你已有同名知识库，请换一个名称") from None
        raise


def create_knowledge_base(db: Session, user_id: UUID, data: KnowledgeBaseCreate) -> KnowledgeBase:
    assert_name_available(db, user_id, data.name)
    knowledge_base = KnowledgeBase(
        user_id=user_id,
        name=data.name,
        name_key=normalize_name(data.name),
        description=data.description,
    )
    db.add(knowledge_base)
    commit_change(db)
    db.refresh(knowledge_base)
    return knowledge_base


def list_knowledge_bases(db: Session, user_id: UUID, limit: int, offset: int) -> dict:
    owned = KnowledgeBase.user_id == user_id
    total = db.scalar(select(func.count()).select_from(KnowledgeBase).where(owned))
    items = db.scalars(
        select(KnowledgeBase)
        .where(owned)
        .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_owned_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID) -> KnowledgeBase:
    knowledge_base = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user_id
        )
    )
    if knowledge_base is None:
        raise HTTPException(404, "知识库不存在或无法访问")
    return knowledge_base


def update_knowledge_base(
    db: Session, user_id: UUID, knowledge_base_id: UUID, data: KnowledgeBaseUpdate
) -> KnowledgeBase:
    knowledge_base = get_owned_knowledge_base(db, user_id, knowledge_base_id)
    if "name" in data.model_fields_set:
        assert_name_available(db, user_id, data.name, exclude_id=knowledge_base_id)
        knowledge_base.name = data.name
        knowledge_base.name_key = normalize_name(data.name)
    if "description" in data.model_fields_set:
        knowledge_base.description = data.description
    commit_change(db)
    db.refresh(knowledge_base)
    return knowledge_base


def delete_knowledge_base(db: Session, user_id: UUID, knowledge_base_id: UUID,
                          settings: Settings) -> None:
    knowledge_base = db.scalar(select(KnowledgeBase).where(
        KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user_id).with_for_update())
    if knowledge_base is None:
        raise HTTPException(404, "知识库不存在或无法访问")
    keys = list(db.scalars(select(Document.storage_key).where(
        Document.knowledge_base_id == knowledge_base_id)).all())
    # Match completion's conversation -> message lock order before cascading deletion.
    list(db.scalars(select(Conversation).where(Conversation.knowledge_base_id == knowledge_base_id)
                    .order_by(Conversation.id).with_for_update()))
    db.add_all(StorageCleanupTask(storage_key=key) for key in keys)
    db.execute(delete(Message).where(Message.conversation_id.in_(select(Conversation.id).where(
        Conversation.knowledge_base_id == knowledge_base_id))))
    db.execute(delete(Conversation).where(Conversation.knowledge_base_id == knowledge_base_id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.knowledge_base_id == knowledge_base_id))
    db.execute(delete(Document).where(Document.knowledge_base_id == knowledge_base_id))
    db.delete(knowledge_base)
    commit_change(db)
    document_storage.drain_cleanup(db, settings, keys)
