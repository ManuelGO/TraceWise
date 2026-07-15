"""Tests for the human-review routing API (Task 53).

Fully offline: the endpoint functions are called directly with an AsyncMock session and the
module-level repositories / router-service functions patched (mirroring test_timeline_api.py).
No DB, network, or auth backend is exercised.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import reviews as reviews_api
from app.api.reviews import (
    get_review_case,
    list_review_decisions,
    list_review_queue,
    route_case_to_review,
    router,
    submit_review_decision,
)
from app.main import create_app
from app.models import CaseStatus, ReviewDecisionType
from app.schemas.review_decision import ReviewDecisionSubmit
from app.services.review_router import CaseNotFoundError, InvalidCaseTransitionError

# ===== Builders =====


def _case_obj(status: str = "awaiting_review"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        title="Case A",
        supplier_name="Acme",
        product_type="Coffee",
        country_of_origin="BR",
        status=status,
        risk_level="medium",
        created_at=now,
        updated_at=now,
    )


def _decision_obj(case_id=None, decision: str = "approved"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        case_id=case_id or uuid4(),
        reviewer_name="Alice",
        decision=decision,
        notes=None,
        created_at=now,
        updated_at=now,
    )


# ===== Router structure / registration =====


class TestReviewsRouterStructure:
    def test_router_prefix_and_routes(self):
        assert router.prefix == "/reviews"
        # queue, route, get-case, submit-decision, list-decisions
        assert len(router.routes) == 5

    def test_router_requires_auth(self):
        # The router-level dependency (require_auth) is attached.
        assert len(router.dependencies) == 1

    def test_app_includes_reviews_router(self):
        app = create_app()
        routes = [route.path for route in app.routes]
        assert any("/reviews" in route for route in routes)


# ===== GET /reviews/queue =====


class TestListReviewQueue:
    @pytest.mark.asyncio
    async def test_empty_queue(self):
        session = AsyncMock(spec=AsyncSession)
        with patch.object(
            reviews_api._case_repo, "find_awaiting_review", AsyncMock(return_value=[])
        ), patch.object(
            reviews_api._case_repo, "count_awaiting_review", AsyncMock(return_value=0)
        ):
            resp = await list_review_queue(skip=0, limit=50, session=session)

        assert resp.total == 0
        assert resp.items == []

    @pytest.mark.asyncio
    async def test_populated_queue(self):
        session = AsyncMock(spec=AsyncSession)
        cases = [_case_obj(), _case_obj()]
        with patch.object(
            reviews_api._case_repo, "find_awaiting_review", AsyncMock(return_value=cases)
        ), patch.object(
            reviews_api._case_repo, "count_awaiting_review", AsyncMock(return_value=2)
        ):
            resp = await list_review_queue(skip=0, limit=50, session=session)

        assert resp.total == 2
        assert len(resp.items) == 2
        assert all(item.status == "awaiting_review" for item in resp.items)


# ===== POST /reviews/cases/{id}/route =====


class TestRouteCaseToReview:
    @pytest.mark.asyncio
    async def test_route_success(self):
        session = AsyncMock(spec=AsyncSession)
        case = _case_obj(status="awaiting_review")
        with patch(
            "app.api.reviews.route_to_review", AsyncMock(return_value=case)
        ):
            resp = await route_case_to_review(case_id=case.id, session=session)

        assert resp.status == "awaiting_review"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_route_404(self):
        session = AsyncMock(spec=AsyncSession)
        with patch(
            "app.api.reviews.route_to_review",
            AsyncMock(side_effect=CaseNotFoundError("nope")),
        ):
            with pytest.raises(HTTPException) as exc:
                await route_case_to_review(case_id=uuid4(), session=session)

        assert exc.value.status_code == 404
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_409_on_invalid_transition(self):
        # FIX 1: routing a non-draft (e.g. terminal) case -> 409, nothing committed.
        session = AsyncMock(spec=AsyncSession)
        with patch(
            "app.api.reviews.route_to_review",
            AsyncMock(side_effect=InvalidCaseTransitionError("only draft may be routed")),
        ):
            with pytest.raises(HTTPException) as exc:
                await route_case_to_review(case_id=uuid4(), session=session)

        assert exc.value.status_code == 409
        session.commit.assert_not_awaited()


# ===== GET /reviews/cases/{id} =====


class TestGetReviewCase:
    @pytest.mark.asyncio
    async def test_get_case_success(self):
        session = AsyncMock(spec=AsyncSession)
        case = _case_obj()
        decisions = [_decision_obj(case_id=case.id)]
        with patch.object(
            reviews_api._case_repo, "read", AsyncMock(return_value=case)
        ), patch.object(
            reviews_api._decision_repo, "find_by_case_id", AsyncMock(return_value=decisions)
        ):
            resp = await get_review_case(case_id=case.id, session=session)

        assert resp.case.title == "Case A"
        assert len(resp.decisions) == 1

    @pytest.mark.asyncio
    async def test_get_case_404(self):
        session = AsyncMock(spec=AsyncSession)
        with patch.object(reviews_api._case_repo, "read", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await get_review_case(case_id=uuid4(), session=session)

        assert exc.value.status_code == 404


# ===== POST /reviews/cases/{id}/decisions =====


class TestSubmitReviewDecision:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("decision", "expected_status"),
        [
            ("approved", CaseStatus.APPROVED),
            ("override", CaseStatus.APPROVED),
            ("rejected", CaseStatus.REJECTED),
            ("needs_more_evidence", CaseStatus.DRAFT),
        ],
    )
    async def test_submit_each_decision(self, decision, expected_status):
        session = AsyncMock(spec=AsyncSession)
        case_id = uuid4()
        payload = ReviewDecisionSubmit(reviewer_name="Alice", decision=decision)

        apply_mock = AsyncMock(return_value=_case_obj(status=expected_status.value))

        # Simulate the DB flush + refresh the real create/commit would do: stamp the
        # server-generated id/timestamps on the ORM object the endpoint constructed.
        async def _stamp_create(_session, obj):
            now = datetime.now(UTC)
            obj.id = uuid4()
            obj.created_at = now
            obj.updated_at = now
            return obj

        create_mock = AsyncMock(side_effect=_stamp_create)
        with patch("app.api.reviews.apply_decision_status", apply_mock), patch.object(
            reviews_api._decision_repo, "create", create_mock
        ):
            resp = await submit_review_decision(
                case_id=case_id, payload=payload, session=session
            )

        # The status transition was applied for the right decision type...
        apply_mock.assert_awaited_once()
        assert apply_mock.await_args.args[2] == ReviewDecisionType(decision)
        # ...the decision was persisted and committed once (atomic with the transition).
        create_mock.assert_awaited_once()
        session.commit.assert_awaited_once()
        assert resp.decision == decision
        assert resp.case_id == case_id

    @pytest.mark.asyncio
    async def test_submit_404_does_not_create_decision(self):
        session = AsyncMock(spec=AsyncSession)
        payload = ReviewDecisionSubmit(reviewer_name="Alice", decision="approved")
        create_mock = AsyncMock()
        with patch(
            "app.api.reviews.apply_decision_status",
            AsyncMock(side_effect=CaseNotFoundError("nope")),
        ), patch.object(reviews_api._decision_repo, "create", create_mock):
            with pytest.raises(HTTPException) as exc:
                await submit_review_decision(
                    case_id=uuid4(), payload=payload, session=session
                )

        assert exc.value.status_code == 404
        # The case was missing -> no decision row written, nothing committed.
        create_mock.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_submit_409_on_invalid_transition_does_not_create_decision(self):
        # FIX 1: deciding on a case not awaiting review -> 409, and NO ReviewDecision row is
        # written (the guard runs before decision creation), so the audit trail stays clean.
        session = AsyncMock(spec=AsyncSession)
        payload = ReviewDecisionSubmit(reviewer_name="Alice", decision="approved")
        create_mock = AsyncMock()
        with patch(
            "app.api.reviews.apply_decision_status",
            AsyncMock(side_effect=InvalidCaseTransitionError("not awaiting review")),
        ), patch.object(reviews_api._decision_repo, "create", create_mock):
            with pytest.raises(HTTPException) as exc:
                await submit_review_decision(
                    case_id=uuid4(), payload=payload, session=session
                )

        assert exc.value.status_code == 409
        create_mock.assert_not_awaited()
        session.commit.assert_not_awaited()

    def test_invalid_decision_rejected_by_schema(self):
        # The Literal on ReviewDecisionSubmit rejects bad decisions before the endpoint runs
        # (FastAPI returns 422). Assert the schema guard directly.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ReviewDecisionSubmit(reviewer_name="Alice", decision="maybe")  # type: ignore[arg-type]


# ===== GET /reviews/cases/{id}/decisions =====


class TestListReviewDecisions:
    @pytest.mark.asyncio
    async def test_list_success(self):
        session = AsyncMock(spec=AsyncSession)
        case_id = uuid4()
        decisions = [_decision_obj(case_id=case_id), _decision_obj(case_id=case_id)]
        with patch.object(
            reviews_api._case_repo, "exists", AsyncMock(return_value=True)
        ), patch.object(
            reviews_api._decision_repo, "find_by_case_id", AsyncMock(return_value=decisions)
        ), patch.object(
            reviews_api._decision_repo, "count_by_case_id", AsyncMock(return_value=2)
        ):
            resp = await list_review_decisions(case_id=case_id, skip=0, limit=100, session=session)

        assert resp.total == 2
        assert len(resp.items) == 2

    @pytest.mark.asyncio
    async def test_list_404_when_case_absent(self):
        session = AsyncMock(spec=AsyncSession)
        with patch.object(reviews_api._case_repo, "exists", AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await list_review_decisions(
                    case_id=uuid4(), skip=0, limit=100, session=session
                )

        assert exc.value.status_code == 404
