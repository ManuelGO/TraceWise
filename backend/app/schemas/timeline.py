"""Schemas for processing timeline API responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProcessingEventRead(BaseModel):
    """Processing event in timeline response."""

    id: UUID = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Type of event (e.g., document_uploaded)")
    timestamp: datetime = Field(..., description="When the event occurred (UTC)")
    event_metadata: dict = Field(
        default_factory=dict,
        description="Event-specific context data",
    )

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    """Response for GET /cases/{case_id}/timeline."""

    events: list[ProcessingEventRead] = Field(..., description="List of events in chronological order")
    total: int = Field(..., description="Total number of events for this case")


__all__ = ["ProcessingEventRead", "TimelineResponse"]
