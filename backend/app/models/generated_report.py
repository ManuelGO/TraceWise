"""GeneratedReport domain model for final compliance reports."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, relationship

from app.db import Base
from app.models.base import BaseModel


class GeneratedReport(Base, BaseModel):
    """Domain model for generated compliance reports.

    Stores final reports linked to compliance cases. Supports multiple reports per case
    for audit trail and versioning. Latest report by generated_at is the current report.

    Phase 2 (Current):
    - generated_by is free-text (agent name or reviewer name)
    - Acceptable for single-user MVP

    Phase 3 (Planned):
    - generated_by will be replaced with user_id (FK to users table)
    - Must be authenticated user from Phase 3 auth system
    """

    __tablename__ = "generated_reports"

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
    report_content: Mapped = Column(  # type: ignore[assignment]
        Text,
        nullable=False,
        # Full report body (markdown or plain text, supports large documents)
    )
    generated_by = Column(String(255), nullable=True)
    # generated_by: agent name (e.g., "compliance-agent-v2") or reviewer name
    generated_at: Mapped = Column(  # type: ignore[assignment]
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="generated_reports",
        foreign_keys=[case_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_generated_reports_case_id_generated_at", "case_id", "generated_at"),
    )

    def __repr__(self):
        return (
            f"<GeneratedReport(id={self.id}, case_id={self.case_id}, "
            f"generated_at={self.generated_at})>"
        )
