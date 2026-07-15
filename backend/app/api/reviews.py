"""REST API endpoints for human review routing (Task 53).

Exposes the reviewer-facing surface on top of the compliance workflow's ``needs_human_review``
signal: the review queue (cases in ``awaiting_review``), routing a case into review, a reviewer's
case view, and recording decisions (which transition the case out of the queue).

The queue is *derived* from case status -- there is no separate queue table. Recording a decision
persists an immutable ``ReviewDecision`` AND transitions the case status in the SAME transaction,
so a case is never moved out of the queue without its decision persisted.

All routes require authentication (coordinator decision, 2026-07-11): the queue and decisions are
sensitive review data.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_auth
from app.db.repositories import ComplianceCaseRepository, ReviewDecisionRepository
from app.models import ReviewDecision, ReviewDecisionType
from app.schemas.compliance_case import ComplianceCaseRead
from app.schemas.review_decision import (
    ReviewCaseDetail,
    ReviewDecisionListResponse,
    ReviewDecisionRead,
    ReviewDecisionSubmit,
    ReviewQueueResponse,
)
from app.services.review_router import (
    CaseNotFoundError,
    InvalidCaseTransitionError,
    apply_decision_status,
    route_to_review,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_auth)],
)

_case_repo = ComplianceCaseRepository()
_decision_repo = ReviewDecisionRepository()


def _case_not_found(case_id: UUID) -> HTTPException:
    """Build the standard 404 for an absent case."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Case with id {case_id} not found",
    )


@router.get(
    "/queue",
    response_model=ReviewQueueResponse,
    summary="List cases awaiting human review (the review queue)",
)
async def list_review_queue(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    session: AsyncSession = Depends(get_session),
) -> ReviewQueueResponse:
    """List cases awaiting review, newest-first, paginated.

    The queue is derived from case status: every case in ``awaiting_review`` is queued.
    """
    cases = await _case_repo.find_awaiting_review(session, skip=skip, limit=limit)
    total = await _case_repo.count_awaiting_review(session)
    return ReviewQueueResponse(
        items=[ComplianceCaseRead.model_validate(c) for c in cases],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/cases/{case_id}/route",
    response_model=ComplianceCaseRead,
    summary="Route a case into the human-review queue",
)
async def route_case_to_review(
    case_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ComplianceCaseRead:
    """Set a case's status to ``awaiting_review`` so it appears in the queue.

    Only ``draft`` cases may be routed; routing a terminal or in-progress case is a 409.

    Raises:
        HTTPException: 404 if the case does not exist; 409 if its status forbids routing.
    """
    try:
        case = await route_to_review(session, case_id)
    except CaseNotFoundError:
        raise _case_not_found(case_id)
    except InvalidCaseTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    await session.commit()
    await session.refresh(case)
    return ComplianceCaseRead.model_validate(case)


@router.get(
    "/cases/{case_id}",
    response_model=ReviewCaseDetail,
    summary="Reviewer view of a case: the case plus its decision history",
)
async def get_review_case(
    case_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReviewCaseDetail:
    """Return a case and its full (newest-first) review-decision history.

    Raises:
        HTTPException: 404 if the case does not exist.
    """
    case = await _case_repo.read(session, case_id)
    if case is None:
        raise _case_not_found(case_id)
    decisions = await _decision_repo.find_by_case_id(session, case_id)
    return ReviewCaseDetail(
        case=ComplianceCaseRead.model_validate(case),
        decisions=[ReviewDecisionRead.model_validate(d) for d in decisions],
    )


@router.post(
    "/cases/{case_id}/decisions",
    response_model=ReviewDecisionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a review decision and transition the case out of the queue",
)
async def submit_review_decision(
    case_id: UUID,
    payload: ReviewDecisionSubmit,
    session: AsyncSession = Depends(get_session),
) -> ReviewDecisionRead:
    """Record an immutable decision and apply its case-status transition atomically.

    The decision row and the case-status change are committed in one transaction so the case is
    never moved out of the queue without its decision persisted. A decision may only be recorded
    on a case in ``awaiting_review`` -- otherwise the request is a 409 and no decision is written.

    Raises:
        HTTPException: 404 if the case does not exist; 409 if it is not awaiting review.
    """
    decision_type = ReviewDecisionType(payload.decision)

    try:
        # Transition the case first: this both fails fast on a missing/ineligible case AND
        # guarantees no ReviewDecision row is written unless the transition is valid.
        await apply_decision_status(session, case_id, decision_type)
    except CaseNotFoundError:
        raise _case_not_found(case_id)
    except InvalidCaseTransitionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    decision = ReviewDecision(
        case_id=case_id,
        reviewer_name=payload.reviewer_name,
        decision=decision_type,
        notes=payload.notes,
    )
    await _decision_repo.create(session, decision)
    await session.commit()
    await session.refresh(decision)
    logger.info("Recorded review decision for case %s", case_id)
    return ReviewDecisionRead.model_validate(decision)


@router.get(
    "/cases/{case_id}/decisions",
    response_model=ReviewDecisionListResponse,
    summary="List a case's review-decision history",
)
async def list_review_decisions(
    case_id: UUID,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    session: AsyncSession = Depends(get_session),
) -> ReviewDecisionListResponse:
    """List the review decisions recorded for a case, newest-first, paginated.

    Raises:
        HTTPException: 404 if the case does not exist.
    """
    if not await _case_repo.exists(session, case_id):
        raise _case_not_found(case_id)
    decisions = await _decision_repo.find_by_case_id(session, case_id, skip=skip, limit=limit)
    total = await _decision_repo.count_by_case_id(session, case_id)
    return ReviewDecisionListResponse(
        items=[ReviewDecisionRead.model_validate(d) for d in decisions],
        total=total,
        skip=skip,
        limit=limit,
    )
