"""Documents and durable private-file deletion tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0004_documents"
down_revision = "0003_name_whitespace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(8), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("knowledge_base_id", "content_hash", name="uq_documents_kb_hash"),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint(
            "status IN ('pending','processing','parsed','failed')", name="ck_documents_status"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size"),
    )
    op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_table(
        "storage_cleanup_tasks",
        sa.Column("storage_key", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("storage_key"),
    )


def downgrade():
    # Downgrade removes metadata, not original files. Back up both before reverting.
    op.drop_table("storage_cleanup_tasks")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_index("ix_documents_knowledge_base_id", table_name="documents")
    op.drop_table("documents")
