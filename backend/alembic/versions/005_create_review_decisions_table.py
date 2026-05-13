"""Create review_decisions table

Revision ID: 005
Revises: 004
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create review_decisions table."""
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reviewer_name", sa.String(length=255), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "approved",
                "rejected",
                "needs_more_evidence",
                "override",
                name="reviewdecisiontype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["compliance_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_decisions_id"), "review_decisions", ["id"], unique=False)
    op.create_index(
        op.f("ix_review_decisions_case_id"), "review_decisions", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_decisions_created_at"), "review_decisions", ["created_at"], unique=False
    )
    op.create_index(
        "ix_review_decisions_case_id_created_at",
        "review_decisions",
        ["case_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop review_decisions table."""
    op.drop_index("ix_review_decisions_case_id_created_at", table_name="review_decisions")
    op.drop_index(op.f("ix_review_decisions_created_at"), table_name="review_decisions")
    op.drop_index(op.f("ix_review_decisions_case_id"), table_name="review_decisions")
    op.drop_index(op.f("ix_review_decisions_id"), table_name="review_decisions")
    op.drop_table("review_decisions")
