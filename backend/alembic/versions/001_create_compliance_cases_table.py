"""Create compliance_cases table

Revision ID: 001
Revises:
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create compliance_cases table."""
    op.create_table(
        "compliance_cases",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("product_type", sa.String(length=100), nullable=False),
        sa.Column("country_of_origin", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "processing",
                "awaiting_review",
                "approved",
                "rejected",
                "completed",
                name="casestatus",
                native_enum=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "risk_level",
            # native_enum=False — shared with risk_assessments table (migration 003)
            # IMPORTANT: do NOT change to True without coordinating with migration 003
            sa.Enum("low", "medium", "high", "critical", name="risklevel", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title"),
    )
    op.create_index(op.f("ix_compliance_cases_id"), "compliance_cases", ["id"], unique=False)
    op.create_index(
        op.f("ix_compliance_cases_status"), "compliance_cases", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_compliance_cases_risk_level"), "compliance_cases", ["risk_level"], unique=False
    )
    op.create_index(
        op.f("ix_compliance_cases_created_at"), "compliance_cases", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_compliance_cases_updated_at"), "compliance_cases", ["updated_at"], unique=False
    )


def downgrade() -> None:
    """Drop compliance_cases table."""
    op.drop_index(op.f("ix_compliance_cases_updated_at"), table_name="compliance_cases")
    op.drop_index(op.f("ix_compliance_cases_created_at"), table_name="compliance_cases")
    op.drop_index(op.f("ix_compliance_cases_risk_level"), table_name="compliance_cases")
    op.drop_index(op.f("ix_compliance_cases_status"), table_name="compliance_cases")
    op.drop_index(op.f("ix_compliance_cases_id"), table_name="compliance_cases")
    op.drop_table("compliance_cases")
