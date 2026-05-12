"""Pydantic schemas for RiskAssessment API requests/responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RiskAssessmentCreate(BaseModel):
    """Schema for creating a new risk assessment."""

    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Risk classification level"
    )
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Risk score between 0.0 and 1.0",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    reasons: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of risk factors (1-100 items, each 1-1000 chars)",
    )

    @field_validator("reasons")
    @classmethod
    def validate_reasons(cls, v: list[str]) -> list[str]:
        """Ensure all reasons are non-empty, properly trimmed, and bounded."""
        if not v:
            raise ValueError("reasons list cannot be empty")
        for reason in v:
            if not reason or not reason.strip():
                raise ValueError("Each reason must be a non-empty string")
            if len(reason.strip()) > 1000:
                raise ValueError("Each reason must be ≤1000 characters")
        return [reason.strip() for reason in v]


class RiskAssessmentRead(BaseModel):
    """Schema for reading a risk assessment (ORM response)."""

    id: UUID
    case_id: UUID
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str]
    generated_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
