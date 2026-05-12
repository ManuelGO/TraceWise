"""Document domain model for uploaded evidence artifacts."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, relationship

from app.db import Base
from app.models.base import BaseModel
from app.models.enums import DocumentType, ProcessingStatus


class Document(Base, BaseModel):
    """Domain model for uploaded evidence documents linked to compliance cases."""

    __tablename__ = "documents"

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
    filename = Column(String(255), nullable=False)
    document_type: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(DocumentType, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    storage_path = Column(String(512), nullable=False)
    processing_status: Mapped = Column(  # type: ignore[assignment]
        SQLEnum(
            ProcessingStatus,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    uploaded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)

    compliance_case = relationship(
        "ComplianceCase",
        back_populates="documents",
        foreign_keys=[case_id],
        lazy="joined",
    )

    def __repr__(self):
        return (
            f"<Document(id={self.id}, filename={self.filename}, "
            f"processing_status={self.processing_status})>"
        )
