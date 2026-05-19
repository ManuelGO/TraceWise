"""Enhance document processing with granular status tracking and error tracking.

This migration:
- Adds processing_error column to documents table for error message persistence
- Updates processing_status enum values for granular pipeline tracking:
  OLD: pending, processing, completed, failed
  NEW: uploaded, validating, extracting, extracted, embedding, ready, failed

Semantic mapping for backward compatibility:
- pending → uploaded (document uploaded, not yet validated)
- processing → extracting (text extraction in progress)
- completed → extracted (text extraction complete)
- failed → failed (no change needed)

Revision ID: 009
Revises: 008
Create Date: 2026-05-18

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add processing_error column and map legacy processing_status values to new ones."""
    # Add processing_error column (nullable TEXT for error messages)
    op.add_column(
        "documents",
        sa.Column("processing_error", sa.Text(), nullable=True, default=None),
    )

    # Map all legacy enum values to new granular states
    # Order is important: update most specific values first
    op.execute(
        "UPDATE documents SET processing_status = 'extracting' "
        "WHERE processing_status = 'processing'"
    )
    op.execute(
        "UPDATE documents SET processing_status = 'extracted' "
        "WHERE processing_status = 'completed'"
    )
    op.execute(
        "UPDATE documents SET processing_status = 'uploaded' "
        "WHERE processing_status = 'pending'"
    )
    # 'failed' value already exists in new enum; no update needed


def downgrade() -> None:
    """Downgrade: revert status mappings and remove processing_error column."""
    # Reverse the mappings for rollback safety
    op.execute(
        "UPDATE documents SET processing_status = 'processing' "
        "WHERE processing_status = 'extracting'"
    )
    op.execute(
        "UPDATE documents SET processing_status = 'completed' "
        "WHERE processing_status = 'extracted'"
    )
    op.execute(
        "UPDATE documents SET processing_status = 'pending' "
        "WHERE processing_status = 'uploaded'"
    )

    # Remove processing_error column
    op.drop_column("documents", "processing_error")
