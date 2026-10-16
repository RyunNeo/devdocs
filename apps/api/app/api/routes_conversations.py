from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, Database
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationRead,
)
from app.services.conversation_service import (
    create_conversation,
    list_conversations,
    read_conversation,
)

router = APIRouter(tags=["conversations"])


@router.post(
    "/knowledge-bases/{kb_id}/conversations", response_model=ConversationRead, status_code=201
)
def create(kb_id: UUID, data: ConversationCreate, user: CurrentUser, db: Database):
    return create_conversation(db, user.id, kb_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def read(
    conversation_id: UUID,
    user: CurrentUser,
    db: Database,
    before_sequence: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
):
    return read_conversation(db, user.id, conversation_id, before_sequence, limit)


@router.get("/knowledge-bases/{kb_id}/conversations", response_model=ConversationList)
def list_all(
    kb_id: UUID,
    user: CurrentUser,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_conversations(db, user.id, kb_id, limit, offset)
