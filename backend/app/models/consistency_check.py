"""Consistency check model for storing validation results."""

from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel


class ConsistencyCheck(Base, BaseModel):
    """Model for storing consistency check results.

    Attributes:
        id: Primary key (UUID)
        case_id: Foreign key to compliance cases
        report_data: Full consistency report as JSONB
        conflicts_count: Total number of conflicts detected
        severity_distribution: Distribution of conflict severities as JSON
        created_at: When record was created (inherited from BaseModel)
        updated_at: When record was last updated (inherited from BaseModel)
    """

    __tablename__ = "consistency_checks"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )

    case_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("compliance_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Report data
    report_data = Column(
        JSONB,
        nullable=False,
    )

    # Metadata
    conflicts_count = Column(
        Integer,
        nullable=False,
        default=0,
    )

    severity_distribution = Column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Relationships
    case = relationship(
        "ComplianceCase",
        foreign_keys=[case_id],
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<ConsistencyCheck(id={self.id}, case_id={self.case_id}, "
            f"conflicts_count={self.conflicts_count}, created_at={self.created_at})>"
        )
