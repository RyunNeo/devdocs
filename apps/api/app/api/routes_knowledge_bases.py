from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import CurrentUser, Database
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseList,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_base_service as service

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post("", response_model=KnowledgeBaseRead, status_code=201)
def create(data: KnowledgeBaseCreate, user: CurrentUser, db: Database):
    return service.create_knowledge_base(db, user.id, data)


@router.get("", response_model=KnowledgeBaseList)
def list_all(
    user: CurrentUser,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_knowledge_bases(db, user.id, limit, offset)


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def get(knowledge_base_id: UUID, user: CurrentUser, db: Database):
    return service.get_owned_knowledge_base(db, user.id, knowledge_base_id)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
def update(knowledge_base_id: UUID, data: KnowledgeBaseUpdate, user: CurrentUser, db: Database):
    return service.update_knowledge_base(db, user.id, knowledge_base_id, data)


@router.delete("/{knowledge_base_id}", status_code=204)
def delete(knowledge_base_id: UUID, request: Request, user: CurrentUser, db: Database):
    service.delete_knowledge_base(db, user.id, knowledge_base_id, request.app.state.settings)
    request.app.state.chat_runtime.cancel_kb(knowledge_base_id)
    return Response(status_code=204)
