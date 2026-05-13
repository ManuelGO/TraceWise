"""Create generated_reports table

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create generated_reports table."""
    op.create_table(
        "generated_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("report_content", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(length=255), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["compliance_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_reports_id"), "generated_reports", ["id"], unique=False)
    op.create_index(
        op.f("ix_generated_reports_case_id"), "generated_reports", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_generated_reports_generated_at"), "generated_reports", ["generated_at"], unique=False
    )
    op.create_index(
        "ix_generated_reports_case_id_generated_at",
        "generated_reports",
        ["case_id", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop generated_reports table."""
    op.drop_index("ix_generated_reports_case_id_generated_at", table_name="generated_reports")
    op.drop_index(op.f("ix_generated_reports_generated_at"), table_name="generated_reports")
    op.drop_index(op.f("ix_generated_reports_case_id"), table_name="generated_reports")
    op.drop_index(op.f("ix_generated_reports_id"), table_name="generated_reports")
    op.drop_table("generated_reports")
