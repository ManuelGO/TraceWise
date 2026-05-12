"""Pydantic schemas for ExtractedEvidence API requests/responses."""

import json
import math
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ExtractedEvidenceCreate(BaseModel):
    """Schema for creating extracted evidence from document processing."""

    document_id: UUID = Field(..., description="Parent document ID")
    supplier_name: str | None = Field(
        None,
        max_length=255,
        description="Extracted supplier name",
    )
    product: str | None = Field(
        None,
        max_length=255,
        description="Extracted product name",
    )
    country_of_origin: str | None = Field(
        None,
        max_length=100,
        description="Country of origin (ISO code preferred)",
    )
    shipment_date: date | None = Field(
        None,
        description="Extracted shipment date",
    )
    coordinates_present: bool = Field(
        False,
        description="Whether GPS coordinates were found in document",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="ML model confidence score (0.0-1.0)",
    )
    missing_fields: list[str] | None = Field(
        None,
        description="List of field names not extracted",
    )
    raw_extraction: dict[str, Any] | None = Field(
        None,
        description="Full raw output from extraction pipeline",
    )

    @field_validator("supplier_name", "product", "country_of_origin")
    @classmethod
    def validate_non_empty_strings(cls, v: str | None) -> str | None:
        """Ensure string fields are not empty or whitespace-only."""
        if v is not None and isinstance(v, str):
            if not v.strip():
                raise ValueError("String fields cannot be empty or whitespace-only")
            return v.strip()
        return v

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Reject NaN and infinity values.

        Pydantic's ge/le don't reject float('nan') or float('inf').
        Storing NaN corrupts downstream aggregations.
        """
        if math.isnan(v) or math.isinf(v):
            raise ValueError("confidence_score must be finite between 0.0 and 1.0")
        return v

    @field_validator("missing_fields")
    @classmethod
    def validate_missing_fields(cls, v: list[str] | None) -> list[str] | None:
        """Ensure missing_fields is a list of non-empty strings."""
        if v is not None and any(not f.strip() for f in v):
            raise ValueError("missing_fields must contain non-empty strings")
        return v

    @field_validator("raw_extraction")
    @classmethod
    def validate_raw_extraction(cls, v: dict | None) -> dict | None:
        """Validate raw extraction doesn't exceed size limit.

        Prevents:
        - Stack overflow from deeply nested JSON
        - Memory exhaustion from huge payloads
        - Billion-laughs expansion attacks
        """
        if v is not None:
            serialised = json.dumps(v)
            if len(serialised) > 500_000:  # 500 KB
                raise ValueError("raw_extraction exceeds 500 KB size limit")
        return v


class ExtractedEvidenceRead(BaseModel):
    """Schema for reading extracted evidence (ORM response)."""

    id: UUID
    document_id: UUID
    supplier_name: str | None
    product: str | None
    country_of_origin: str | None
    shipment_date: date | None
    coordinates_present: bool
    confidence_score: float
    missing_fields: list[str] | None
    raw_extraction: dict[str, Any] | None
    extracted_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
