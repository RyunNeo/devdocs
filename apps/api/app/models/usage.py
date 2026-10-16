import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("operation", "operation_run_id", name="uq_usage_operation_run"),
        CheckConstraint("operation IN ('chat','index')", name="ck_usage_operation"),
        CheckConstraint(
            "status IN ('running','completed','local_completed',"
            "'failed','cancelled','interrupted')",
            name="ck_usage_status",
        ),
        Index("ix_usage_user_started", "user_id", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(36))
    operation: Mapped[str] = mapped_column(String(8))
    operation_run_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    quota_charged: Mapped[bool] = mapped_column(default=True)
    quota_day: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    durations_ms: Mapped[dict] = mapped_column(JSON, default=dict)
    models: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[dict] = mapped_column(JSON, default=dict)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DailyUsageCounter(Base):
    __tablename__ = "daily_usage_counters"
    __table_args__ = (
        UniqueConstraint("user_id", "quota_day", "operation", name="uq_daily_usage"),
        CheckConstraint("used_count >= 0", name="ck_daily_usage_nonnegative"),
        CheckConstraint("operation IN ('chat','index')", name="ck_daily_usage_operation"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    quota_day: Mapped[date] = mapped_column(Date)
    operation: Mapped[str] = mapped_column(String(8))
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
