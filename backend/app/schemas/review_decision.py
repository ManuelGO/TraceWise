"""Pydantic schemas for ReviewDecision API requests/responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.compliance_case import ComplianceCaseRead


class ReviewDecisionSubmit(BaseModel):
    """Schema for submitting a review decision via the reviews API (Task 53).

    The ``case_id`` is NOT in the body -- it comes from the URL path so the two can never
    disagree. ``reviewer_name`` records who acted (Phase-2 assignment; Phase-3 will replace it
    with an authenticated user id). This is the shared field set; ``ReviewDecisionCreate`` extends
    it with ``case_id`` so the fields + validator live in exactly one place.
    """

    reviewer_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="[Phase 2] Name or identifier of the reviewer who made the decision.",
    )
    decision: Literal["approved", "rejected", "needs_more_evidence", "override"] = Field(
        ..., description="Decision outcome"
    )
    notes: str | None = Field(
        None,
        max_length=10_000,
        description="Reviewer notes or justification",
    )

    @field_validator("reviewer_name")
    @classmethod
    def validate_reviewer_name(cls, v: str) -> str:
        """Ensure reviewer_name is not empty or whitespace-only."""
        if not v.strip():
            raise ValueError("reviewer_name cannot be empty or whitespace-only")
        return v.strip()


class ReviewDecisionCreate(ReviewDecisionSubmit):
    """Schema for creating a review decision on a compliance case (includes ``case_id``)."""

    case_id: UUID = Field(..., description="Parent compliance case ID")


class ReviewDecisionRead(BaseModel):
    """Schema for reading a review decision (ORM response)."""

    id: UUID
    case_id: UUID
    reviewer_name: str
    decision: Literal["approved", "rejected", "needs_more_evidence", "override"]
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewDecisionListResponse(BaseModel):
    """Schema for a paginated list of review decisions (a case's decision history)."""

    items: list[ReviewDecisionRead]
    total: int = Field(..., description="Total number of decisions for the case")
    skip: int = Field(..., ge=0, description="Number of items skipped")
    limit: int = Field(..., ge=1, le=1000, description="Maximum items per page")


class ReviewQueueResponse(BaseModel):
    """Schema for the review queue -- cases awaiting human review (derived from case status).

    The queue is derived: an item is any ``ComplianceCase`` whose status is ``awaiting_review``.
    ``ComplianceCaseRead`` is reused verbatim as the queue-item shape.
    """

    items: list[ComplianceCaseRead]
    total: int = Field(..., description="Total number of cases awaiting review")
    skip: int = Field(..., ge=0, description="Number of items skipped")
    limit: int = Field(..., ge=1, le=1000, description="Maximum items per page")


class ReviewCaseDetail(BaseModel):
    """Schema for a reviewer's view of a case: the case plus its full decision history."""

    case: ComplianceCaseRead
    decisions: list[ReviewDecisionRead]
