"""Timeline API for case processing events."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.db.repositories.compliance_case import ComplianceCaseRepository
from app.db.repositories.processing_event import ProcessingEventRepository
from app.schemas.timeline import ProcessingEventRead, TimelineResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["timeline"])


@router.get("/{case_id}/timeline", response_model=TimelineResponse)
async def get_case_timeline(
    case_id: UUID,
    skip: int = Query(0, ge=0, description="Number of events to skip"),
    limit: int = Query(100, ge=1, le=500, description="Number of events to return (max 500)"),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    """Get processing timeline (event history) for a compliance case.

    Args:
        case_id: UUID of the compliance case
        skip: Number of events to skip for pagination (default 0)
        limit: Maximum number of events to return (default 100, max 500)
        session: Database session

    Returns:
        TimelineResponse with events list and total count

    Raises:
        HTTPException 404: If case not found
    """
    # Verify case exists
    case_repo = ComplianceCaseRepository()
    case = await case_repo.read(session, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Get events for case
    event_repo = ProcessingEventRepository()
    events = await event_repo.find_by_case(session, case_id, skip=skip, limit=limit)
    total = await event_repo.count_by_case(session, case_id)

    logger.info(f"Timeline fetched for case {case_id}: {len(events)} events, total={total}")

    event_reads = [
        ProcessingEventRead.model_validate(event) for event in events
    ]

    return TimelineResponse(events=event_reads, total=total)


__all__ = ["router"]
