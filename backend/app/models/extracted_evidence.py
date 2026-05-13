"""ExtractedEvidence domain model for structured entity extraction from documents."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel


class ExtractedEvidence(Base, BaseModel):
    """Domain model for structured entity extraction from documents.

    Captures ML extraction pipeline output with confidence scores and audit trail.
    Linked to Document records for reference to source material.
    """

    __tablename__ = "extracted_evidences"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    document_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_name: Mapped = Column(  # type: ignore[assignment]
        String(255), nullable=True
    )
    product: Mapped = Column(  # type: ignore[assignment]
        String(255), nullable=True
    )
    country_of_origin: Mapped = Column(  # type: ignore[assignment]
        String(100), nullable=True
    )
    shipment_date: Mapped = Column(  # type: ignore[assignment]
        Date, nullable=True
    )
    coordinates_present: Mapped = Column(  # type: ignore[assignment]
        Boolean,
        nullable=False,
        default=False,
    )
    confidence_score: Mapped = Column(  # type: ignore[assignment]
        Float,
        nullable=False,
        # Note: Database-level validation not enforced for flexibility
        # Pydantic schema enforces 0.0-1.0 range
    )
    missing_fields: Mapped = Column(  # type: ignore[assignment]
        JSON,
        nullable=True,
        # JSON list: ["field_name1", "field_name2", ...]
    )
    raw_extraction: Mapped = Column(  # type: ignore[assignment]
        JSON,
        nullable=True,
        # JSON object with full extraction pipeline output
    )
    extracted_at: Mapped = Column(  # type: ignore[assignment]
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    document = relationship(
        "Document",
        back_populates="extracted_evidences",
        foreign_keys=[document_id],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_extracted_evidences_document_id_extracted_at", "document_id", "extracted_at"),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_extracted_evidences_confidence_score_range",
        ),
    )

    def __repr__(self):
        return (
            f"<ExtractedEvidence(id={self.id}, document_id={self.document_id}, "
            f"confidence_score={self.confidence_score})>"
        )
