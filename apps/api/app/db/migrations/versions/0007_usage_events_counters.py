"""Persistent operation usage and atomic daily counters."""

import sqlalchemy as sa
from alembic import op

revision = "0007_usage_events_counters"
down_revision = "0006_conversations_messages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(8), nullable=False),
        sa.Column("operation_run_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid()),
        sa.Column("conversation_id", sa.Uuid()),
        sa.Column("document_id", sa.Uuid()),
        sa.Column("quota_charged", sa.Boolean(), nullable=False),
        sa.Column("quota_day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("durations_ms", sa.JSON(), nullable=False),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.Column("token_usage", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.UniqueConstraint("operation", "operation_run_id", name="uq_usage_operation_run"),
        sa.CheckConstraint("operation IN ('chat','index')", name="ck_usage_operation"),
        sa.CheckConstraint(
            "status IN ('running','completed','local_completed',"
            "'failed','cancelled','interrupted')",
            name="ck_usage_status",
        ),
    )
    op.create_index("ix_usage_user_started", "usage_events", ["user_id", "started_at"])
    op.create_table(
        "daily_usage_counters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("quota_day", sa.Date(), nullable=False),
        sa.Column("operation", sa.String(8), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "quota_day", "operation", name="uq_daily_usage"),
        sa.CheckConstraint("used_count >= 0", name="ck_daily_usage_nonnegative"),
        sa.CheckConstraint("operation IN ('chat','index')", name="ck_daily_usage_operation"),
    )


def downgrade():
    op.drop_table("daily_usage_counters")
    op.drop_table("usage_events")
