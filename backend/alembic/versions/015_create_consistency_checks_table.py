"""Create consistency_checks table for storing validation results.

Revision ID: 015
Revises: 014
Create Date: 2026-06-10 19:55:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create consistency_checks table."""
    op.create_table(
        "consistency_checks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("report_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conflicts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "severity_distribution",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="'{}'",
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
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["compliance_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_consistency_checks_case_id", "consistency_checks", ["case_id"])


def downgrade() -> None:
    """Drop consistency_checks table."""
    op.drop_index("idx_consistency_checks_case_id", table_name="consistency_checks")
    op.drop_table("consistency_checks")
