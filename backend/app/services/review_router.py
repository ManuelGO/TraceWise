"""Human-review routing service (Task 53).

Turns the compliance workflow's ``needs_human_review`` signal into a concrete case-status
transition, and applies a reviewer's decision back onto the case status. The review *queue* is
derived from case status (a case is queued iff its status is ``awaiting_review``), so routing is
simply a status change -- there is no separate queue table.

Stateless and session-injected: callers own the session/transaction lifecycle (the API commits
once at the endpoint boundary), mirroring the rest of ``app/services``.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CaseStatus, ComplianceCase, ReviewDecisionType

logger = logging.getLogger(__name__)


class CaseNotFoundError(Exception):
    """Raised when a routing/decision target case does not exist.

    The API layer maps this to a 404 response.
    """


class InvalidCaseTransitionError(Exception):
    """Raised when a routing/decision would move a case along a forbidden status edge.

    The API layer maps this to a 409 Conflict response. Guards the review state machine:
    only ``draft -> awaiting_review`` (routing) and ``awaiting_review -> {approved, rejected,
    draft}`` (decisions) are allowed; terminal states (``approved``/``rejected``/``completed``)
    do not transition, and a decision cannot be recorded against a case that never entered the
    queue -- which would otherwise pollute the immutable audit trail.
    """


# Decision -> resulting case status (coordinator-confirmed Option A, 2026-07-11).
# ``approved``/``override`` are terminal accept; ``rejected`` is terminal reject;
# ``needs_more_evidence`` drops back to ``draft`` for asynchronous re-work (keeps the queue clean).
_DECISION_STATUS: dict[ReviewDecisionType, CaseStatus] = {
    ReviewDecisionType.APPROVED: CaseStatus.APPROVED,
    ReviewDecisionType.OVERRIDE: CaseStatus.APPROVED,
    ReviewDecisionType.REJECTED: CaseStatus.REJECTED,
    ReviewDecisionType.NEEDS_MORE_EVIDENCE: CaseStatus.DRAFT,
}


async def _get_case(session: AsyncSession, case_id: UUID) -> ComplianceCase:
    """Load a case or raise ``CaseNotFoundError``."""
    result = await session.execute(select(ComplianceCase).where(ComplianceCase.id == case_id))
    case = result.scalar_one_or_none()
    if case is None:
        raise CaseNotFoundError(str(case_id))
    return case


async def route_to_review(session: AsyncSession, case_id: UUID) -> ComplianceCase:
    """Route a case into the human-review queue by setting ``status=awaiting_review``.

    Only a ``draft`` case may be routed. Routing an already-queued case is a true no-op
    (short-circuits without a write, so ``updated_at`` is not churned); routing a terminal
    case (``approved``/``rejected``/``completed``) or one still ``processing`` is rejected.
    Does NOT commit -- the caller owns the transaction.

    Args:
        session: AsyncSession instance.
        case_id: The compliance case to route.

    Returns:
        The updated (in-session) ComplianceCase.

    Raises:
        CaseNotFoundError: If no case with ``case_id`` exists.
        InvalidCaseTransitionError: If the case's status forbids routing to review.
    """
    case = await _get_case(session, case_id)
    if case.status == CaseStatus.AWAITING_REVIEW:
        # True idempotent no-op: already queued, nothing to write.
        return case
    if case.status != CaseStatus.DRAFT:
        raise InvalidCaseTransitionError(
            f"Cannot route case in status {case.status.value!r} to review; "
            "only draft cases may be routed."
        )
    case.status = CaseStatus.AWAITING_REVIEW
    session.add(case)
    await session.flush()
    logger.info("Routed case %s to human review (awaiting_review)", case_id)
    return case


def resolve_decision_status(decision: ReviewDecisionType) -> CaseStatus:
    """Map a review decision to the resulting case status (the transition table).

    Args:
        decision: The reviewer's decision.

    Returns:
        The case status the decision transitions the case to.

    Raises:
        ValueError: If the decision is not a known ``ReviewDecisionType`` (defensive; the API
            schema already constrains the input to the four valid values).
    """
    try:
        return _DECISION_STATUS[decision]
    except KeyError as exc:  # pragma: no cover - guarded by the schema Literal upstream
        raise ValueError(f"Unknown review decision: {decision!r}") from exc


async def apply_decision_status(
    session: AsyncSession,
    case_id: UUID,
    decision: ReviewDecisionType,
) -> ComplianceCase:
    """Transition a case's status per a recorded review decision (Option A table).

    Does NOT commit -- the caller records the ``ReviewDecision`` and commits both the decision
    and this status change in one transaction so a case is never moved out of the queue without
    its decision persisted.

    Args:
        session: AsyncSession instance.
        case_id: The compliance case the decision applies to.
        decision: The reviewer's decision.

    Returns:
        The updated (in-session) ComplianceCase.

    Raises:
        CaseNotFoundError: If no case with ``case_id`` exists.
        InvalidCaseTransitionError: If the case is not in ``awaiting_review`` (a decision may
            only be recorded on a queued case; recording one otherwise would pollute the
            immutable audit trail with a review that never went through the queue).
        ValueError: If ``decision`` is not a known ReviewDecisionType.
    """
    new_status = resolve_decision_status(decision)
    case = await _get_case(session, case_id)
    if case.status != CaseStatus.AWAITING_REVIEW:
        raise InvalidCaseTransitionError(
            f"Cannot record a review decision on a case in status {case.status.value!r}; "
            "only cases awaiting review may be decided."
        )
    case.status = new_status
    session.add(case)
    await session.flush()
    logger.info(
        "Applied review decision %s to case %s -> status=%s",
        decision.value,
        case_id,
        new_status.value,
    )
    return case


__all__ = [
    "CaseNotFoundError",
    "InvalidCaseTransitionError",
    "apply_decision_status",
    "resolve_decision_status",
    "route_to_review",
]
