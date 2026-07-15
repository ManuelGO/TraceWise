"""Unit tests for the human-review routing service (Task 53).

Fully offline: a fake async session returns a canned case (or none), so no DB is touched. The
status transition table (coordinator Option A) and the not-found path are asserted directly.
"""

from typing import Any
from uuid import uuid4

import pytest

from app.models import CaseStatus, ReviewDecisionType
from app.services.review_router import (
    CaseNotFoundError,
    InvalidCaseTransitionError,
    apply_decision_status,
    resolve_decision_status,
    route_to_review,
)


class _FakeCase:
    def __init__(self, status: CaseStatus = CaseStatus.DRAFT) -> None:
        self.id = uuid4()
        self.status = status


class _FakeScalarResult:
    def __init__(self, case: Any) -> None:
        self._case = case

    def scalar_one_or_none(self) -> Any:
        return self._case


class _FakeSession:
    """Records add/flush and returns a canned case from execute()."""

    def __init__(self, case: Any = None) -> None:
        self._case = case
        self.added: list[Any] = []
        self.flushed = False

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        return _FakeScalarResult(self._case)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


# ===== resolve_decision_status (transition table) =====


class TestResolveDecisionStatus:
    def test_approved_to_approved(self):
        assert resolve_decision_status(ReviewDecisionType.APPROVED) == CaseStatus.APPROVED

    def test_override_to_approved(self):
        assert resolve_decision_status(ReviewDecisionType.OVERRIDE) == CaseStatus.APPROVED

    def test_rejected_to_rejected(self):
        assert resolve_decision_status(ReviewDecisionType.REJECTED) == CaseStatus.REJECTED

    def test_needs_more_evidence_to_draft(self):
        assert (
            resolve_decision_status(ReviewDecisionType.NEEDS_MORE_EVIDENCE) == CaseStatus.DRAFT
        )

    def test_all_decision_types_are_mapped(self):
        # Guards against a new ReviewDecisionType being added without a transition.
        for decision in ReviewDecisionType:
            assert isinstance(resolve_decision_status(decision), CaseStatus)


# ===== route_to_review =====


class TestRouteToReview:
    @pytest.mark.asyncio
    async def test_sets_awaiting_review(self):
        case = _FakeCase(status=CaseStatus.DRAFT)
        session = _FakeSession(case)

        result = await route_to_review(session, case.id)  # type: ignore[arg-type]

        assert result is case
        assert case.status == CaseStatus.AWAITING_REVIEW
        assert case in session.added
        assert session.flushed is True

    @pytest.mark.asyncio
    async def test_idempotent_on_already_queued_is_true_noop(self):
        # FIX 1: an already-queued case is a true no-op -- no write, so updated_at is not churned.
        case = _FakeCase(status=CaseStatus.AWAITING_REVIEW)
        session = _FakeSession(case)

        result = await route_to_review(session, case.id)  # type: ignore[arg-type]

        assert result is case
        assert case.status == CaseStatus.AWAITING_REVIEW
        assert session.flushed is False
        assert session.added == []

    @pytest.mark.asyncio
    async def test_missing_case_raises(self):
        session = _FakeSession(None)
        with pytest.raises(CaseNotFoundError):
            await route_to_review(session, uuid4())  # type: ignore[arg-type]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "source",
        [
            CaseStatus.PROCESSING,
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
            CaseStatus.COMPLETED,
        ],
    )
    async def test_route_from_non_draft_is_rejected(self, source):
        # FIX 1: only draft cases may be routed; terminal/in-progress states raise (409 upstream).
        case = _FakeCase(status=source)
        session = _FakeSession(case)

        with pytest.raises(InvalidCaseTransitionError):
            await route_to_review(session, case.id)  # type: ignore[arg-type]

        assert case.status == source  # unchanged
        assert session.flushed is False


# ===== apply_decision_status =====


class TestApplyDecisionStatus:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("decision", "expected"),
        [
            (ReviewDecisionType.APPROVED, CaseStatus.APPROVED),
            (ReviewDecisionType.OVERRIDE, CaseStatus.APPROVED),
            (ReviewDecisionType.REJECTED, CaseStatus.REJECTED),
            (ReviewDecisionType.NEEDS_MORE_EVIDENCE, CaseStatus.DRAFT),
        ],
    )
    async def test_transitions(self, decision, expected):
        case = _FakeCase(status=CaseStatus.AWAITING_REVIEW)
        session = _FakeSession(case)

        result = await apply_decision_status(session, case.id, decision)  # type: ignore[arg-type]

        assert result.status == expected
        assert session.flushed is True

    @pytest.mark.asyncio
    async def test_missing_case_raises(self):
        session = _FakeSession(None)
        with pytest.raises(CaseNotFoundError):
            await apply_decision_status(
                session, uuid4(), ReviewDecisionType.APPROVED  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "source",
        [
            CaseStatus.DRAFT,
            CaseStatus.PROCESSING,
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
            CaseStatus.COMPLETED,
        ],
    )
    async def test_decision_on_non_queued_case_is_rejected(self, source):
        # FIX 1: a decision may only be recorded on a case awaiting review -- deciding on any
        # other status raises (409 upstream) so the immutable audit trail is not polluted with a
        # review that never went through the queue, and no status write happens.
        case = _FakeCase(status=source)
        session = _FakeSession(case)

        with pytest.raises(InvalidCaseTransitionError):
            await apply_decision_status(
                session, case.id, ReviewDecisionType.APPROVED  # type: ignore[arg-type]
            )

        assert case.status == source  # unchanged
        assert session.flushed is False
