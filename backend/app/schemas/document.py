"""Pydantic schemas for Document API requests/responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DocumentCreate(BaseModel):
    """Schema for creating a new document.

    Processing status is server-enforced to always start as 'pending'.
    """

    case_id: UUID = Field(..., description="Parent compliance case ID")
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Original filename (e.g., invoice_2024.pdf)",
    )
    document_type: Literal[
        "supplier_declaration", "invoice", "shipment_note", "geojson", "certificate", "other"
    ] = Field(..., description="Type of document")
    storage_path: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Storage path (e.g., s3://bucket/cases/uuid/documents/filename.pdf)",
    )
    file_size: int = Field(..., ge=0, description="File size in bytes")
    mime_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="MIME type (e.g., application/pdf, image/png)",
    )

    @field_validator("filename", "storage_path", "mime_type")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        """Ensure string fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("String fields cannot be empty or whitespace-only")
        return v.strip()


class DocumentRead(BaseModel):
    """Schema for reading a document (ORM response)."""

    id: UUID
    case_id: UUID
    filename: str
    document_type: Literal[
        "supplier_declaration", "invoice", "shipment_note", "geojson", "certificate", "other"
    ]
    storage_path: str
    file_size: int
    mime_type: str
    processing_status: Literal["pending", "processing", "completed", "failed"]
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    """Schema for updating a document (partial updates allowed)."""

    document_type: (
        Literal[
            "supplier_declaration", "invoice", "shipment_note", "geojson", "certificate", "other"
        ]
        | None
    ) = Field(None, description="Type of document")
    processing_status: Literal["pending", "processing", "completed", "failed"] | None = Field(
        None, description="Processing status in extraction pipeline"
    )
