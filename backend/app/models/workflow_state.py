"""WorkflowStateCheckpoint domain model for compliance-workflow state persistence (Task 52).

Persists a durable snapshot of the compliance workflow's ``WorkflowState`` after each step so a run
can be recovered after a failure/interruption and so the trail of snapshots forms an audit record of
how a case was processed (Phase 6, Task 52).

One row == one checkpoint == the state captured after a single workflow node completed. Rows are
grouped by ``run_id`` (a per-run identifier -- a case may be reprocessed into several runs) and linked
to their ``case_id`` for the audit trail. ``state_snapshot`` holds the JSON-serialized ``WorkflowState``
(see ``app.workflows.state_persistence.serialize_state``); ``status`` records whether the step
completed, is in progress, or failed, and a failed step carries the sanitized ``error``/``error_type``.

NOTE on naming: the class is ``WorkflowStateCheckpoint`` (table ``workflow_state_checkpoints``) to
avoid colliding with the ``WorkflowState`` ``TypedDict`` in ``app.workflows.langgraph_setup`` -- one is
the in-memory graph state, the other is its persisted checkpoint row.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel
from app.models.enums import WorkflowStepStatus


class WorkflowStateCheckpoint(Base, BaseModel):
    """Domain model for a single compliance-workflow state checkpoint.

    Attributes:
        id: Primary key (UUID).
        run_id: Groups all checkpoints of one workflow run (distinct from ``case_id`` so a
            reprocessed case yields separate, distinguishable runs).
        case_id: Foreign key to the parent compliance case (audit link + recovery scoping).
        step: Name of the workflow node just completed (``ingest`` ... ``route_review``).
        status: ``in_progress`` | ``completed`` | ``failed`` for this step.
        state_snapshot: The JSON-serialized ``WorkflowState`` after this step.
        error: Sanitized error message when the run failed at this step (nullable).
        error_type: The failing step's error type (``retrieval``/``risk``/...); nullable.
        created_at / updated_at: Timestamps (inherited from ``BaseModel``) -- the audit timeline.
    """

    __tablename__ = "workflow_state_checkpoints"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    run_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    case_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step: Mapped = Column(  # type: ignore[assignment]
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(
            WorkflowStepStatus,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    state_snapshot = Column(
        JSONB,
        nullable=False,
    )
    error = Column(Text, nullable=True)
    error_type = Column(String(64), nullable=True)
    created_at: Mapped = Column(  # type: ignore[assignment]
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    compliance_case = relationship(
        "ComplianceCase",
        foreign_keys=[case_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_workflow_state_checkpoints_run_id_created_at", "run_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<WorkflowStateCheckpoint(id={self.id}, run_id={self.run_id}, "
            f"case_id={self.case_id}, step={self.step}, status={self.status})>"
        )
