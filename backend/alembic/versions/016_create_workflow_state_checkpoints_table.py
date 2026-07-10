"""Create workflow_state_checkpoints table for compliance-workflow state persistence (Task 52).

Revision ID: 016
Revises: 015
Create Date: 2026-07-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "016"
down_revision: str | None = "015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow_state_checkpoints table."""
    op.create_table(
        "workflow_state_checkpoints",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("step", sa.String(length=64), nullable=False),
        # ``status`` mirrors the WorkflowStepStatus StrEnum (non-native enum -> VARCHAR check).
        sa.Column(
            "status",
            sa.Enum(
                "in_progress",
                "completed",
                "failed",
                name="workflowstepstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
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
    op.create_index(
        "ix_workflow_state_checkpoints_id", "workflow_state_checkpoints", ["id"]
    )
    op.create_index(
        "ix_workflow_state_checkpoints_run_id", "workflow_state_checkpoints", ["run_id"]
    )
    op.create_index(
        "ix_workflow_state_checkpoints_case_id", "workflow_state_checkpoints", ["case_id"]
    )
    op.create_index(
        "ix_workflow_state_checkpoints_step", "workflow_state_checkpoints", ["step"]
    )
    op.create_index(
        "ix_workflow_state_checkpoints_status", "workflow_state_checkpoints", ["status"]
    )
    op.create_index(
        "ix_workflow_state_checkpoints_created_at",
        "workflow_state_checkpoints",
        ["created_at"],
    )
    op.create_index(
        "ix_workflow_state_checkpoints_run_id_created_at",
        "workflow_state_checkpoints",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    """Drop workflow_state_checkpoints table."""
    op.drop_index(
        "ix_workflow_state_checkpoints_run_id_created_at",
        table_name="workflow_state_checkpoints",
    )
    op.drop_index(
        "ix_workflow_state_checkpoints_created_at", table_name="workflow_state_checkpoints"
    )
    op.drop_index(
        "ix_workflow_state_checkpoints_status", table_name="workflow_state_checkpoints"
    )
    op.drop_index("ix_workflow_state_checkpoints_step", table_name="workflow_state_checkpoints")
    op.drop_index(
        "ix_workflow_state_checkpoints_case_id", table_name="workflow_state_checkpoints"
    )
    op.drop_index(
        "ix_workflow_state_checkpoints_run_id", table_name="workflow_state_checkpoints"
    )
    op.drop_index("ix_workflow_state_checkpoints_id", table_name="workflow_state_checkpoints")
    op.drop_table("workflow_state_checkpoints")
