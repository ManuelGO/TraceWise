"""Job domain model for tracking async job execution and status."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel
from app.models.enums import JobStatus, JobType


class Job(Base, BaseModel):
    """Domain model for tracking async job execution and status."""

    __tablename__ = "jobs"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    case_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_type: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(JobType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    status: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(JobStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    job_metadata = Column("job_metadata", JSONB, nullable=True, default=lambda: {})

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="jobs",
        foreign_keys=[case_id],
        lazy="joined",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.status is None:
            self.status = JobStatus.PENDING

    def _transition(
        self,
        forbidden: tuple[JobStatus, ...],
        target: JobStatus,
        error: str,
    ) -> None:
        """Validate and execute a state transition.

        Args:
            forbidden: Tuple of statuses that prevent this transition
            target: Target status to transition to
            error: Error message if transition is invalid

        Raises:
            ValueError: If current status is in forbidden tuple
        """
        if self.status in forbidden:
            raise ValueError(f"Cannot transition to {target.value}: {error}")
        self.status = target

    def mark_processing(self) -> None:
        """Transition job from pending to processing status.

        Sets started_at timestamp to current UTC time.

        Raises:
            ValueError: If current status is not 'pending'
        """
        self._transition(
            forbidden=(JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED),
            target=JobStatus.PROCESSING,
            error=f"job status is '{self.status}', expected 'pending'",
        )
        self.started_at = datetime.now(UTC)  # type: ignore[assignment]

    def mark_completed(self) -> None:
        """Transition job from processing to completed status.

        Sets completed_at timestamp to current UTC time.

        Raises:
            ValueError: If current status is not 'processing'
        """
        self._transition(
            forbidden=(JobStatus.PENDING, JobStatus.COMPLETED, JobStatus.FAILED),
            target=JobStatus.COMPLETED,
            error=f"job status is '{self.status}', expected 'processing'",
        )
        self.completed_at = datetime.now(UTC)  # type: ignore[assignment]

    def mark_failed(self, error_message: str) -> None:
        """Transition job to failed status with error details.

        Sets completed_at timestamp to current UTC time and stores error message.

        Called exclusively by internal workers on job failure.
        In Phase 3, this will be exposed via API with error_message size limits.

        Args:
            error_message: Descriptive error message explaining failure reason

        Raises:
            ValueError: If current status is 'completed' or 'failed'
        """
        self._transition(
            forbidden=(JobStatus.COMPLETED, JobStatus.FAILED),
            target=JobStatus.FAILED,
            error=f"job status is '{self.status}', cannot fail from completed or already-failed state",
        )
        self.error_message = error_message  # type: ignore[assignment]
        self.completed_at = datetime.now(UTC)  # type: ignore[assignment]

    def __repr__(self):
        return (
            f"<Job(id={self.id}, case_id={self.case_id}, "
            f"job_type={self.job_type}, status={self.status})>"
        )
