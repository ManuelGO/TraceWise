"""Create risk_assessments table

Revision ID: 003
Revises: 002
Create Date: 2026-05-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create risk_assessments table."""
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "risk_level",
            # native_enum=False — shared with compliance_cases table (migration 001)
            # IMPORTANT: do NOT change to True without coordinating with migration 001
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="risklevel",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["compliance_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_assessments_id"), "risk_assessments", ["id"], unique=False)
    op.create_index(
        op.f("ix_risk_assessments_case_id"), "risk_assessments", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_risk_assessments_risk_level"), "risk_assessments", ["risk_level"], unique=False
    )
    op.create_index(
        op.f("ix_risk_assessments_generated_at"),
        "risk_assessments",
        ["generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_risk_assessments_case_id_generated_at",
        "risk_assessments",
        ["case_id", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop risk_assessments table."""
    op.drop_index(
        "ix_risk_assessments_case_id_generated_at",
        table_name="risk_assessments",
    )
    op.drop_index(op.f("ix_risk_assessments_generated_at"), table_name="risk_assessments")
    op.drop_index(op.f("ix_risk_assessments_risk_level"), table_name="risk_assessments")
    op.drop_index(op.f("ix_risk_assessments_case_id"), table_name="risk_assessments")
    op.drop_index(op.f("ix_risk_assessments_id"), table_name="risk_assessments")
    op.drop_table("risk_assessments")
