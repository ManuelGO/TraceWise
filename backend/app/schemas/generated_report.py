"""Pydantic schemas for GeneratedReport API requests/responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class GeneratedReportCreate(BaseModel):
    """Schema for creating a generated compliance report."""

    case_id: UUID = Field(..., description="Parent compliance case ID")
    report_content: str = Field(
        ...,
        min_length=1,
        max_length=1_000_000,
        description="Full report body (markdown or plain text). Will be rendered as PDF.",
    )
    generated_by: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="[Phase 2] Agent/reviewer name. Phase 3: Will be replaced with user_id FK.",
    )

    @field_validator("report_content")
    @classmethod
    def validate_report_content(cls, v: str) -> str:
        """Validate report content without mutating it.

        Check for empty/whitespace-only, but preserve intentional formatting.
        Whitespace is significant in Markdown and prose.
        """
        if not v or not v.strip():
            raise ValueError("report_content cannot be empty or whitespace-only")
        return v  # Preserve original formatting


class GeneratedReportRead(BaseModel):
    """Schema for reading a generated report (ORM response)."""

    id: UUID
    case_id: UUID
    report_content: str
    generated_by: str | None
    generated_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
