"""Pydantic schemas for ComplianceCase API requests/responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ComplianceCaseCreate(BaseModel):
    """Schema for creating a new compliance case.

    Status is server-enforced to always start as 'draft'.
    """

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Case title (must be unique)",
    )
    supplier_name: str = Field(
        ..., min_length=1, max_length=255, description="Supplier/manufacturer name"
    )
    product_type: str = Field(
        ..., min_length=1, max_length=100, description="Type of product under review"
    )
    country_of_origin: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="ISO country code or name",
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Risk classification level"
    )

    @field_validator("title", "supplier_name", "product_type", "country_of_origin")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        """Ensure string fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("String fields cannot be empty or whitespace-only")
        return v.strip()


class ComplianceCaseRead(BaseModel):
    """Schema for reading a compliance case (ORM response)."""

    id: UUID
    title: str
    supplier_name: str
    product_type: str
    country_of_origin: str
    status: Literal[
        "draft",
        "processing",
        "awaiting_review",
        "approved",
        "rejected",
        "completed",
    ]
    risk_level: Literal["low", "medium", "high", "critical"]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplianceCaseUpdate(BaseModel):
    """Schema for updating a compliance case (partial updates allowed)."""

    title: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Case title (must be unique)",
    )
    supplier_name: str | None = Field(
        None, min_length=1, max_length=255, description="Supplier/manufacturer name"
    )
    product_type: str | None = Field(
        None, min_length=1, max_length=100, description="Type of product under review"
    )
    country_of_origin: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="ISO country code or name",
    )
    status: (
        Literal[
            "draft",
            "processing",
            "awaiting_review",
            "approved",
            "rejected",
            "completed",
        ]
        | None
    ) = Field(None, description="Case status")
    risk_level: Literal["low", "medium", "high", "critical"] | None = Field(
        None, description="Risk classification level"
    )

    @field_validator("title", "supplier_name", "product_type", "country_of_origin")
    @classmethod
    def validate_non_empty_strings(cls, v: str | None) -> str | None:
        """Ensure string fields are not empty or whitespace-only if provided."""
        if v is None:
            return None
        if not v or not v.strip():
            raise ValueError("String fields cannot be empty or whitespace-only")
        return v.strip()


class ComplianceCaseListResponse(BaseModel):
    """Schema for paginated compliance case list response."""

    items: list[ComplianceCaseRead]
    total: int = Field(..., description="Total number of items matching filters")
    skip: int = Field(..., ge=0, description="Number of items skipped")
    limit: int = Field(..., ge=1, le=1000, description="Maximum items per page")
