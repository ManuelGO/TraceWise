"""Unit tests for the Task 53 review schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.compliance_case import ComplianceCaseRead
from app.schemas.review_decision import (
    ReviewCaseDetail,
    ReviewDecisionCreate,
    ReviewDecisionListResponse,
    ReviewDecisionRead,
    ReviewDecisionSubmit,
    ReviewQueueResponse,
)


def _case_read() -> ComplianceCaseRead:
    now = datetime.now(UTC)
    return ComplianceCaseRead(
        id=uuid4(),
        title="Case A",
        supplier_name="Acme",
        product_type="Coffee",
        country_of_origin="BR",
        status="awaiting_review",
        risk_level="medium",
        created_at=now,
        updated_at=now,
    )


def _decision_read() -> ReviewDecisionRead:
    now = datetime.now(UTC)
    return ReviewDecisionRead(
        id=uuid4(),
        case_id=uuid4(),
        reviewer_name="Alice",
        decision="approved",
        notes=None,
        created_at=now,
        updated_at=now,
    )


class TestReviewDecisionSubmit:
    def test_valid(self):
        s = ReviewDecisionSubmit(reviewer_name="Alice", decision="approved", notes="ok")
        assert s.reviewer_name == "Alice"
        assert s.decision == "approved"

    def test_case_id_not_a_field(self):
        # case_id comes from the URL path, not the body.
        assert "case_id" not in ReviewDecisionSubmit.model_fields

    def test_reviewer_name_trimmed(self):
        assert ReviewDecisionSubmit(reviewer_name="  Bob  ", decision="rejected").reviewer_name == "Bob"

    def test_blank_reviewer_name_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecisionSubmit(reviewer_name="   ", decision="approved")

    def test_invalid_decision_rejected(self):
        with pytest.raises(ValidationError):
            ReviewDecisionSubmit(reviewer_name="Alice", decision="maybe")  # type: ignore[arg-type]

    def test_notes_length_capped(self):
        with pytest.raises(ValidationError):
            ReviewDecisionSubmit(reviewer_name="Alice", decision="approved", notes="x" * 10_001)


class TestReviewDecisionCreateInheritance:
    """FIX 4: ReviewDecisionCreate extends ReviewDecisionSubmit (fields + validator live once)."""

    def test_create_extends_submit(self):
        assert issubclass(ReviewDecisionCreate, ReviewDecisionSubmit)

    def test_create_adds_case_id(self):
        assert "case_id" in ReviewDecisionCreate.model_fields
        assert "case_id" not in ReviewDecisionSubmit.model_fields

    def test_create_inherits_reviewer_name_validator(self):
        # The single validator on the base is enforced on the subclass too.
        with pytest.raises(ValidationError):
            ReviewDecisionCreate(case_id=uuid4(), reviewer_name="   ", decision="approved")

    def test_create_valid(self):
        c = ReviewDecisionCreate(case_id=uuid4(), reviewer_name="  Alice  ", decision="rejected")
        assert c.reviewer_name == "Alice"
        assert c.decision == "rejected"


class TestReviewResponses:
    def test_queue_response(self):
        resp = ReviewQueueResponse(items=[_case_read()], total=1, skip=0, limit=50)
        assert resp.total == 1
        assert resp.items[0].status == "awaiting_review"

    def test_queue_response_empty(self):
        resp = ReviewQueueResponse(items=[], total=0, skip=0, limit=50)
        assert resp.items == []

    def test_decision_list_response(self):
        resp = ReviewDecisionListResponse(items=[_decision_read()], total=1, skip=0, limit=100)
        assert resp.total == 1
        assert resp.items[0].decision == "approved"

    def test_case_detail(self):
        detail = ReviewCaseDetail(case=_case_read(), decisions=[_decision_read()])
        assert detail.case.title == "Case A"
        assert len(detail.decisions) == 1
