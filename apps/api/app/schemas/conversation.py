from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    content: str
    status: str
    run_id: UUID | None
    sequence: int
    citations: list[dict]
    model: str | None
    usage: dict | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    knowledge_base_id: UUID
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]
    has_older: bool


class ConversationSummary(ConversationRead):
    title: str
    last_question: str
    latest_status: str | None


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    total: int
    limit: int
    offset: int
