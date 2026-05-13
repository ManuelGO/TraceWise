"""Create extracted_evidences table

Revision ID: 004
Revises: 003
Create Date: 2026-05-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create extracted_evidences table."""
    op.create_table(
        "extracted_evidences",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("country_of_origin", sa.String(length=100), nullable=True),
        sa.Column("shipment_date", sa.Date(), nullable=True),
        sa.Column("coordinates_present", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=True),
        sa.Column("raw_extraction", sa.JSON(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_extracted_evidences_id"), "extracted_evidences", ["id"], unique=False)
    op.create_index(
        op.f("ix_extracted_evidences_document_id"), "extracted_evidences", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_extracted_evidences_extracted_at"), "extracted_evidences", ["extracted_at"], unique=False
    )
    op.create_index(
        "ix_extracted_evidences_document_id_extracted_at",
        "extracted_evidences",
        ["document_id", "extracted_at"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_extracted_evidences_confidence_score_range",
        "extracted_evidences",
        "confidence_score >= 0.0 AND confidence_score <= 1.0",
    )


def downgrade() -> None:
    """Drop extracted_evidences table."""
    op.drop_constraint(
        "ck_extracted_evidences_confidence_score_range", "extracted_evidences"
    )
    op.drop_index("ix_extracted_evidences_document_id_extracted_at", table_name="extracted_evidences")
    op.drop_index(op.f("ix_extracted_evidences_extracted_at"), table_name="extracted_evidences")
    op.drop_index(op.f("ix_extracted_evidences_document_id"), table_name="extracted_evidences")
    op.drop_index(op.f("ix_extracted_evidences_id"), table_name="extracted_evidences")
    op.drop_table("extracted_evidences")
