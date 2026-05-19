"""Add idempotency keys for task deduplication.

This migration:
- Adds idempotency_key column to document_extractions for deduplication
- Creates unique index to prevent concurrent duplicate inserts
- Column is nullable for backward compatibility with existing extractions

Revision ID: 010
Revises: 009
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add idempotency_key column and unique index to document_extractions."""
    # Add idempotency_key column (nullable for existing records)
    op.add_column(
        "document_extractions",
        sa.Column("idempotency_key", sa.String(64), nullable=True, default=None),
    )

    # Create unique index to prevent concurrent duplicate inserts
    # Allows multiple NULL values (PostgreSQL behavior)
    op.create_index(
        "ix_document_extractions_idempotency_key_unique",
        "document_extractions",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    """Remove idempotency_key column and index from document_extractions."""
    # Remove unique index
    op.drop_index("ix_document_extractions_idempotency_key_unique", "document_extractions")

    # Remove idempotency_key column
    op.drop_column("document_extractions", "idempotency_key")
