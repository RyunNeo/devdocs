"""Source locations, recoverable indexing state and 1024-dimensional dense chunks."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0005_document_chunks"
down_revision = "0004_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("parse_warning", sa.String(255), nullable=True))
    op.add_column(
        "documents",
        sa.Column("source_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "documents",
        sa.Column("index_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column("documents", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("index_run_id", sa.Uuid(), nullable=True))
    op.add_column(
        "documents", sa.Column("index_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("documents", sa.Column("index_fingerprint", sa.String(64), nullable=True))
    op.add_column(
        "documents", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")
    )
    with op.batch_alter_table("documents") as batch:
        batch.create_check_constraint(
            "ck_documents_index_status",
            "index_status IN ('pending','indexing','completed','failed')",
        )
        for column in ["source_metadata", "index_status", "chunk_count"]:
            batch.alter_column(column, server_default=None)
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
    )
    for column in ["document_id", "knowledge_base_id", "user_id"]:
        op.create_index(f"ix_document_chunks_{column}", "document_chunks", [column])


def downgrade():
    op.drop_table("document_chunks")
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("ck_documents_index_status", type_="check")
        for column in [
            "parse_warning",
            "chunk_count",
            "index_fingerprint",
            "index_started_at",
            "index_run_id",
            "index_error",
            "index_status",
            "source_metadata",
        ]:
            batch.drop_column(column)
