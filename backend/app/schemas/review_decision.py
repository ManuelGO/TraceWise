"""Pydantic schemas for ReviewDecision API requests/responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReviewDecisionCreate(BaseModel):
    """Schema for creating a review decision on a compliance case."""

    case_id: UUID = Field(..., description="Parent compliance case ID")
    reviewer_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="[Phase 2] Name or identifier of the reviewer. Phase 3: Will be replaced with user_id FK.",
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
