"""Extracted entity model for validated extraction results.

Stores validated extraction results from Task 39 (Extraction Validation & Retry).
Each extracted entity is tied to a document extraction and includes validation
status, score, and failure information.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel


class ExtractedEntity(Base, BaseModel):
    """Model for storing validated extraction results.

    Attributes:
        id: Primary key (UUID)
        document_extraction_id: Foreign key to document_extractions
        entity_type: Type of entity ('result' for full extraction)
        entity_data: Full extraction data as JSONB
        extraction_confidence: LLM confidence (0.0-1.0)
        model_used: LLM model identifier
        validation_status: Status after validation (valid, invalid, needs_improvement, failed)
        validation_score: Validation score (0-100)
        validation_failures: List of validation failures as JSONB
        retry_count: Number of retry attempts (0-3)
        last_retry_at: When last retry occurred
        created_at: When record was created (inherited)
        updated_at: When record was last updated (inherited)
    """

    __tablename__ = "extracted_entities"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )

    # Foreign key to document_extractions
    document_extraction_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Entity information
    entity_type = Column(
        String(20),
        nullable=False,
        default="result",
    )
    entity_data = Column(
        JSONB,
        nullable=False,
    )

    # Extraction metadata
    extraction_confidence = Column(
        Float,
        nullable=False,
    )
    model_used = Column(
        String(255),
        nullable=False,
    )

    # Validation information
    validation_status = Column(
        String(20),
        nullable=False,
    )
    validation_score = Column(
        Float,
        nullable=False,
    )
    validation_failures = Column(
        JSONB,
        nullable=True,
        default=None,
    )

    # Retry tracking
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
    )
    last_retry_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps (inherited from BaseModel)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    document_extraction = relationship(
        "DocumentExtraction",
        foreign_keys=[document_extraction_id],
        lazy="joined",
    )

    # Indexes for common queries
    __table_args__ = (
        Index("idx_extracted_entities_document_extraction_id", "document_extraction_id"),
        Index("idx_extracted_entities_validation_status", "validation_status"),
        Index("idx_extracted_entities_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ExtractedEntity(id={self.id}, "
            f"document_extraction_id={self.document_extraction_id}, "
            f"validation_status={self.validation_status}, "
            f"validation_score={self.validation_score:.1f})>"
        )
