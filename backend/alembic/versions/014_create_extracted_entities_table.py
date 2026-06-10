"""Create extracted_entities table for validated extraction results.

Revision ID: 014
Revises: 013
Create Date: 2026-06-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create extracted_entities table."""
    op.create_table(
        "extracted_entities",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_extraction_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False, server_default="result"),
        sa.Column("entity_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("model_used", sa.String(255), nullable=False),
        sa.Column("validation_status", sa.String(20), nullable=False),
        sa.Column("validation_score", sa.Float(), nullable=False),
        sa.Column("validation_failures", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_extraction_id"],
            ["document_extractions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Create indexes
    op.create_index(
        "idx_extracted_entities_document_extraction_id",
        "extracted_entities",
        ["document_extraction_id"],
        unique=False,
    )
    op.create_index(
        "idx_extracted_entities_validation_status",
        "extracted_entities",
        ["validation_status"],
        unique=False,
    )
    op.create_index(
        "idx_extracted_entities_created_at",
        "extracted_entities",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop extracted_entities table."""
    op.drop_index(
        "idx_extracted_entities_created_at",
        table_name="extracted_entities",
    )
    op.drop_index(
        "idx_extracted_entities_validation_status",
        table_name="extracted_entities",
    )
    op.drop_index(
        "idx_extracted_entities_document_extraction_id",
        table_name="extracted_entities",
    )
    op.drop_table("extracted_entities")
