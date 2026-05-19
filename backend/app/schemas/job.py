"""Pydantic schemas for Job model (internal serialization, not API endpoints)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import JobStatus, JobType


class JobCreate(BaseModel):
    """Schema for creating a new job.

    Status is server-enforced to always start as 'pending'.
    Metadata is optional and can store job-specific configuration.
    """

    case_id: UUID = Field(..., description="Parent compliance case ID")
    job_type: JobType = Field(..., description="Type of async job to execute")
    job_metadata: dict[str, Any] | None = Field(
        None, description="Job-specific metadata and configuration"
    )


class JobRead(BaseModel):
    """Schema for reading a job (ORM response).

    Exposes all job fields for inspection and serialization.
    """

    id: UUID
    case_id: UUID
    job_type: JobType
    status: JobStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    job_metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Schema for paginated job list response.

    Used by GET /cases/{case_id}/jobs endpoint.
    """

    items: list[JobRead] = Field(..., description="Array of job records")
    total: int = Field(..., ge=0, description="Total number of jobs for the case")
    skip: int = Field(..., ge=0, description="Number of records skipped")
    limit: int = Field(..., ge=1, description="Maximum records per page")
