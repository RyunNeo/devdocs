from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

Operation = Literal["chat", "index"]
UsageStatus = Literal[
    "running", "completed", "local_completed", "failed", "cancelled", "interrupted"
]


class TokenUsage(BaseModel):
    known_tokens: int = 0
    complete: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    batches: int | None = None


class UsageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: str
    operation: Operation
    status: UsageStatus
    quota_charged: bool
    started_at: datetime
    finished_at: datetime | None
    durations_ms: dict[str, int | None]
    models: dict[str, str]
    attempts: dict[str, int]
    token_usage: dict[str, TokenUsage]
    error_code: str | None


class UsageEventList(BaseModel):
    items: list[UsageEventRead]
    total: int
    limit: int
    offset: int


class QuotaRead(BaseModel):
    limit: int
    used: int
    remaining: int


class RecentUsage(BaseModel):
    total: int
    ended: int
    running: int
    completed: int
    local_completed: int
    failed: int
    cancelled: int
    interrupted: int
    success_rate: float | None
    avg_duration_ms: float | None
    sample_count: int
    known_tokens: int
    unknown_usage_count: int


class UsageSummary(BaseModel):
    today: str
    reset_at: datetime
    quota: dict[Operation, QuotaRead]
    recording_started_at: datetime | None
    recent: RecentUsage
