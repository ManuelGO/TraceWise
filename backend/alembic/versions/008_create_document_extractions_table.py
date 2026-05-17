"""Create document_extractions table for extracted text and semantic chunks.

Revision ID: 008
Revises: 007
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create document_extractions table."""
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("chunks", sa.JSON(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "extraction_status",
            sa.String(50),
            nullable=False,
            server_default="extracted",
        ),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_extractions_document_id"),
        "document_extractions",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_extractions_idempotency_key"),
        "document_extractions",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_document_extractions_extraction_status"),
        "document_extractions",
        ["extraction_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_extractions_created_at"),
        "document_extractions",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop document_extractions table."""
    op.drop_index(
        op.f("ix_document_extractions_created_at"), table_name="document_extractions"
    )
    op.drop_index(
        op.f("ix_document_extractions_extraction_status"),
        table_name="document_extractions",
    )
    op.drop_index(
        op.f("ix_document_extractions_idempotency_key"),
        table_name="document_extractions",
    )
    op.drop_index(
        op.f("ix_document_extractions_document_id"), table_name="document_extractions"
    )
    op.drop_table("document_extractions")
