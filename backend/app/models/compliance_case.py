"""ComplianceCase domain model for tracking compliance audits."""

from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, relationship

from app.db import Base
from app.models.base import BaseModel


class CaseStatus(str, Enum):
    """Valid statuses for a compliance case."""

    DRAFT = "draft"
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    """Risk classification levels for compliance cases."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceCase(Base, BaseModel):
    """Domain model for compliance cases."""

    __tablename__ = "compliance_cases"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    title = Column(String(255), nullable=False, unique=True, index=True)
    supplier_name = Column(String(255), nullable=False)
    product_type = Column(String(100), nullable=False)
    country_of_origin = Column(String(100), nullable=False)
    status: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(CaseStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=CaseStatus.DRAFT,
        nullable=False,
        index=True,
    )
    risk_level: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(RiskLevel, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    documents = relationship(
        "Document",
        back_populates="compliance_case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<ComplianceCase(id={self.id}, title={self.title}, status={self.status})>"
