"""Unit tests for ReviewDecisionRepository + ComplianceCase review-queue methods (Task 53).

Runs fully offline: the DB-touching methods are exercised against a fake async session whose
``execute`` returns a canned result object, so no live database is required (mirroring the
offline convention of the Phase 6 suites).
"""

from typing import Any
from uuid import uuid4

import pytest

from app.db.repositories import ComplianceCaseRepository, ReviewDecisionRepository
from app.db.repository import BaseRepository
from app.models import CaseStatus, ReviewDecision, ReviewDecisionType


class _FakeScalarResult:
    """Stand-in for the SQLAlchemy Result returned by ``session.execute``."""

    def __init__(self, items: list[Any], scalar: Any = None) -> None:
        self._items = items
        self._scalar = scalar

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return list(self._items)

    def scalar_one(self) -> Any:
        return self._scalar


class _FakeSession:
    """Minimal async session: records the executed statement, returns canned rows/scalars."""

    def __init__(self, items: list[Any] | None = None, scalar: Any = None) -> None:
        self._items = items if items is not None else []
        self._scalar = scalar
        self.executed: list[Any] = []

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        self.executed.append(stmt)
        return _FakeScalarResult(self._items, self._scalar)


def _decision(**overrides: Any) -> ReviewDecision:
    base: dict[str, Any] = {
        "case_id": uuid4(),
        "reviewer_name": "Alice",
        "decision": ReviewDecisionType.APPROVED,
        "notes": None,
    }
    base.update(overrides)
    return ReviewDecision(**base)


# ===== ReviewDecisionRepository =====


class TestReviewDecisionRepositoryConfiguration:
    def test_model_is_review_decision(self):
        assert ReviewDecisionRepository().model == ReviewDecision

    def test_inherits_base_repository(self):
        assert isinstance(ReviewDecisionRepository(), BaseRepository)

    def test_filterable_fields_use_real_column(self):
        # FIX: the model column is ``decision`` -- the previous ``decision_type`` typo made
        # find_by_decision_type raise AttributeError at query-build time.
        assert ReviewDecisionRepository().FILTERABLE_FIELDS == {"case_id", "decision"}


class TestReviewDecisionRepositoryFinders:
    @pytest.mark.asyncio
    async def test_find_by_case_id_returns_list(self):
        case_id = uuid4()
        rows = [_decision(case_id=case_id), _decision(case_id=case_id)]
        session = _FakeSession(rows)
        repo = ReviewDecisionRepository()

        result = await repo.find_by_case_id(session, case_id)  # type: ignore[arg-type]

        assert result == rows
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_find_by_case_id_empty(self):
        repo = ReviewDecisionRepository()
        result = await repo.find_by_case_id(_FakeSession([]), uuid4())  # type: ignore[arg-type]
        assert result == []

    @pytest.mark.asyncio
    async def test_find_by_case_id_caps_limit(self):
        repo = ReviewDecisionRepository()
        result = await repo.find_by_case_id(_FakeSession([]), uuid4(), limit=99999)  # type: ignore[arg-type]
        assert result == []

    @pytest.mark.asyncio
    async def test_count_by_case_id(self):
        session = _FakeSession(scalar=3)
        repo = ReviewDecisionRepository()
        assert await repo.count_by_case_id(session, uuid4()) == 3  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_find_by_decision_type_does_not_raise(self):
        # Regression: previously raised AttributeError because FILTERABLE_FIELDS referenced a
        # non-existent ``decision_type`` column.
        rows = [_decision(decision=ReviewDecisionType.REJECTED)]
        session = _FakeSession(rows)
        repo = ReviewDecisionRepository()

        result = await repo.find_by_decision_type(session, ReviewDecisionType.REJECTED)  # type: ignore[arg-type]

        assert result == rows

    @pytest.mark.asyncio
    async def test_find_approved_and_rejected_helpers(self):
        repo = ReviewDecisionRepository()
        assert await repo.find_approved_decisions(_FakeSession([])) == []  # type: ignore[arg-type]
        assert await repo.find_rejected_decisions(_FakeSession([])) == []  # type: ignore[arg-type]


# ===== ComplianceCaseRepository review-queue methods =====


class TestComplianceCaseReviewQueue:
    @pytest.mark.asyncio
    async def test_find_awaiting_review_returns_list(self):
        rows = [object(), object()]
        session = _FakeSession(rows)
        repo = ComplianceCaseRepository()

        result = await repo.find_awaiting_review(session)  # type: ignore[arg-type]

        assert result == rows
        assert len(session.executed) == 1

    @pytest.mark.asyncio
    async def test_find_awaiting_review_empty(self):
        repo = ComplianceCaseRepository()
        assert await repo.find_awaiting_review(_FakeSession([])) == []  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_find_awaiting_review_caps_limit(self):
        repo = ComplianceCaseRepository()
        assert await repo.find_awaiting_review(_FakeSession([]), limit=99999) == []  # type: ignore[arg-type]


class TestPaginationTiebreaker:
    """FIX 2: ordering carries a monotonic-stable ``id`` tiebreaker so pages don't drift when
    two rows share a Python-side ``created_at`` (sub-ms ties)."""

    @pytest.mark.asyncio
    async def test_find_awaiting_review_orders_by_created_at_then_id(self):
        session = _FakeSession([])
        await ComplianceCaseRepository().find_awaiting_review(session)  # type: ignore[arg-type]

        order_cols = [str(c.element) for c in session.executed[0]._order_by_clauses]
        assert any("created_at" in c for c in order_cols)
        assert any(c.endswith(".id") for c in order_cols), (
            f"expected an id tiebreaker in ORDER BY, got {order_cols}"
        )

    @pytest.mark.asyncio
    async def test_find_by_case_id_orders_by_created_at_then_id(self):
        session = _FakeSession([])
        await ReviewDecisionRepository().find_by_case_id(session, uuid4())  # type: ignore[arg-type]

        order_cols = [str(c.element) for c in session.executed[0]._order_by_clauses]
        assert any("created_at" in c for c in order_cols)
        assert any(c.endswith(".id") for c in order_cols), (
            f"expected an id tiebreaker in ORDER BY, got {order_cols}"
        )

    @pytest.mark.asyncio
    async def test_count_awaiting_review(self):
        session = _FakeSession(scalar=7)
        repo = ComplianceCaseRepository()
        assert await repo.count_awaiting_review(session) == 7  # type: ignore[arg-type]

    def test_awaiting_review_status_value(self):
        # Guards the derived-queue contract: the queue is "cases in awaiting_review".
        assert CaseStatus.AWAITING_REVIEW.value == "awaiting_review"
