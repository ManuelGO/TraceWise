"""RiskAssessment domain model for AI-generated risk evaluations."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Index, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, relationship

from app.db import Base
from app.models.base import BaseModel
from app.models.enums import RiskLevel


class RiskAssessment(Base, BaseModel):
    """Domain model for AI-generated risk assessments."""

    __tablename__ = "risk_assessments"

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
    risk_level: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(
            RiskLevel,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    risk_score: Mapped = Column(  # type: ignore[assignment]
        Float,
        nullable=False,
    )
    confidence_score: Mapped = Column(  # type: ignore[assignment]
        Float,
        nullable=False,
    )
    reasons: Mapped = Column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
    )
    generated_at: Mapped = Column(  # type: ignore[assignment]
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="risk_assessments",
        lazy="joined",
    )

    __table_args__ = (Index("ix_risk_assessments_case_id_generated_at", "case_id", "generated_at"),)

    def __repr__(self):
        return (
            f"<RiskAssessment(id={self.id}, case_id={self.case_id}, risk_level={self.risk_level})>"
        )
