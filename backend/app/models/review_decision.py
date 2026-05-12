"""ReviewDecision domain model for compliance case review outcomes."""

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, relationship

from app.db import Base
from app.models.base import BaseModel
from app.models.enums import ReviewDecisionType


class ReviewDecision(Base, BaseModel):
    """Domain model for human review decisions on compliance cases.

    Immutable audit records capturing review outcomes with timestamps and notes.
    Supports multiple decisions per case to maintain full decision history.

    Phase 2 (Current):
    - reviewer_name is free-text string
    - Acceptable for single-user MVP

    Phase 3 (Planned):
    - reviewer_name will be replaced with user_id (FK to users table)
    - Must be authenticated user from Phase 3 auth system
    - Audit trail will record: users.id → decision
    """

    __tablename__ = "review_decisions"

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
    reviewer_name: Mapped = Column(  # type: ignore[assignment]
        String(255),
        nullable=False,
    )
    decision: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(
            ReviewDecisionType,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    notes = Column(Text, nullable=True)

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="review_decisions",
        foreign_keys=[case_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_review_decisions_case_id_created_at", "case_id", "created_at"),
        Index("ix_review_decisions_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ReviewDecision(id={self.id}, case_id={self.case_id}, "
            f"decision={self.decision})>"
        )
