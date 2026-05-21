"""Create processing_events table for audit trail and timeline.

This migration:
- Creates processing_events table with event-based audit log
- Adds composite index (case_id, timestamp) for timeline queries
- Adds foreign key constraint with CASCADE delete on compliance_cases
- Stores event-specific metadata as JSONB for flexibility

Revision ID: 011
Revises: 010
Create Date: 2026-05-21
Updated_at: 2026-05-21

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create processing_events table with indexes and FK constraint."""
    # Create processing_events table
    op.create_table(
        "processing_events",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "case_id",
            sa.Uuid(as_uuid=True),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "event_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["compliance_cases.id"],
            ondelete="CASCADE",
        ),
    )

    # Create composite index on (case_id, timestamp) for timeline queries
    op.create_index(
        "idx_processing_events_case_timestamp",
        "processing_events",
        ["case_id", "timestamp"],
    )


def downgrade() -> None:
    """Drop processing_events table and indexes."""
    # Drop composite index
    op.drop_index(
        "idx_processing_events_case_timestamp",
        "processing_events",
    )

    # Drop table (cascade will handle FK)
    op.drop_table("processing_events")
