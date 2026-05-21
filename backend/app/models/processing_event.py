"""ProcessingEvent domain model for audit trail and timeline."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped

from app.db.database import Base
from app.models.base import BaseModel


class ProcessingEvent(Base, BaseModel):
    """Domain model for processing events in audit trail."""

    __tablename__ = "processing_events"

    id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
        nullable=False,
    )
    case_id: Mapped = Column(  # type: ignore[assignment]
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    event_type = Column(String(100), nullable=False, index=True)
    timestamp: Mapped = Column(  # type: ignore[assignment]
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    event_metadata = Column("event_metadata", JSONB, nullable=False, default=lambda: {})

    # Composite index on (case_id, timestamp) for timeline queries
    __table_args__ = (
        Index("idx_processing_events_case_timestamp", "case_id", "timestamp"),
    )

    def __repr__(self):
        return f"<ProcessingEvent(id={self.id}, case_id={self.case_id}, event_type={self.event_type}, timestamp={self.timestamp})>"
