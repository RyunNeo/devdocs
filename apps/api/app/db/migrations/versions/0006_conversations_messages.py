"""Owned conversations and recoverable answer messages."""

import sqlalchemy as sa
from alembic import op

revision = "0006_conversations_messages"
down_revision = "0005_document_chunks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "knowledge_base_id",
            sa.Uuid(),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("active_run_id", sa.Uuid()),
        sa.Column("active_started_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ["user_id", "knowledge_base_id"]:
        op.create_index(f"ix_conversations_{column}", "conversations", [column])
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("usage", sa.JSON()),
        sa.Column("error_code", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_messages_sequence"),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_messages_role"),
        sa.CheckConstraint(
            "status IN ('streaming','completed','failed','cancelled')", name="ck_messages_status"
        ),
    )
    for column in ["conversation_id", "run_id"]:
        op.create_index(f"ix_messages_{column}", "messages", [column])


def downgrade():
    op.drop_table("messages")
    op.drop_table("conversations")
