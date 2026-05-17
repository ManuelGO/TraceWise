"""Document extraction model for extracted text and semantic chunks."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, relationship

from app.db.database import Base
from app.models.base import BaseModel


class DocumentExtraction(Base, BaseModel):
    """Domain model for extracted text and chunked content from documents."""

    __tablename__ = "document_extractions"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    document_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extracted_text = Column(Text, nullable=False)
    chunks = Column(JSONB, nullable=False)
    chunk_count = Column(Integer, nullable=False)
    extraction_status = Column(
        String(50),
        nullable=False,
        default="extracted",
        index=True,
    )
    pages = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    document = relationship(
        "Document",
        foreign_keys=[document_id],
        lazy="joined",
    )

    def __init__(self, **kwargs):
        if "extraction_status" not in kwargs:
            kwargs["extraction_status"] = "extracted"
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<DocumentExtraction(id={self.id}, document_id={self.document_id}, "
            f"extraction_status={self.extraction_status}, chunk_count={self.chunk_count})>"
        )
