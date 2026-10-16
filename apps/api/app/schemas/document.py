from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    knowledge_base_id: UUID
    filename: str
    file_type: str
    size_bytes: int
    status: Literal["pending", "processing", "parsed", "failed"]
    error_message: str | None
    parse_warning: str | None
    character_count: int
    index_status: Literal["pending", "indexing", "completed", "failed"]
    index_error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentRead):
    text_preview: str | None
    preview_truncated: bool


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int
