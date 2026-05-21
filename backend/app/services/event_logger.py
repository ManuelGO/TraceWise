"""Event logger service for audit trail and timeline logging."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProcessingEvent

logger = logging.getLogger(__name__)

# Allowed event types for validation
ALLOWED_EVENT_TYPES = {
    "document_uploaded",
    "validation_started",
    "validation_completed",
    "validation_failed",
    "extraction_started",
    "extraction_completed",
    "extraction_failed",
    "retry_scheduled",
    "max_retries_exceeded",
}


async def log_event(
    session: AsyncSession,
    case_id: UUID,
    event_type: str,
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> ProcessingEvent:
    """Log a processing event to the audit trail.

    Args:
        session: AsyncSession instance for database access
        case_id: UUID of the compliance case
        event_type: Type of event (e.g., document_uploaded, validation_started)
        metadata: Optional event-specific context data (JSONB)
        timestamp: Optional explicit timestamp (defaults to UTC now); used for backfilling

    Returns:
        Created ProcessingEvent instance

    Raises:
        IntegrityError: If case_id doesn't exist or other FK/constraint violation
        Exception: If database serialization error occurs
    """
    # Validate event_type (log warning for unknown types but don't reject)
    if event_type not in ALLOWED_EVENT_TYPES:
        logger.info(f"[EVENT_LOG] Unknown event_type: {event_type} (case_id={case_id})")

    # Default metadata to empty dict; make defensive copy to avoid mutating caller's dict
    if metadata is None:
        metadata = {}
    else:
        metadata = metadata.copy()

    # Truncate error_message in metadata to 1000 chars if present
    if "error_message" in metadata and isinstance(metadata["error_message"], str):
        metadata["error_message"] = metadata["error_message"][:1000]

    # Set timestamp to provided value or UTC now
    event_timestamp = timestamp if timestamp is not None else datetime.now(UTC)

    # Create ProcessingEvent instance
    event = ProcessingEvent(
        case_id=case_id,
        event_type=event_type,
        event_metadata=metadata,
        timestamp=event_timestamp,
    )

    # Add to session and flush to database
    session.add(event)
    await session.flush()

    # Log event at INFO level for observability
    logger.info(
        f"[EVENT_LOG] case_id={case_id} event_type={event_type} timestamp={event_timestamp}"
    )

    return event


__all__ = ["ALLOWED_EVENT_TYPES", "log_event"]
