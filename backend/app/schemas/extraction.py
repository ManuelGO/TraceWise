"""Pydantic schemas for structured entity extraction from documents.

This module defines schemas for extracting and validating structured entities
(supplier, product, location, shipment information) from compliance documents
using LLM-guided extraction with Pydantic validation.

Entity Schemas:
- SupplierInfo: Company name, country, registration, business type, certification
- ProductInfo: Product name, HS code, category, origin, quantity
- LocationInfo: Country, region, risk profile, geolocation verification
- ShipmentInfo: Dates, ports, transport mode, tracking number

ExtractionResult: Combined result with all entities + confidence scoring
"""

import math
from datetime import UTC, date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_str(v: str | None) -> str | None:
    """Normalize string: strip whitespace, reject empty."""
    if v is None:
        return None
    stripped = v.strip()
    if not stripped:
        raise ValueError("String fields cannot be empty or whitespace-only")
    return stripped


class SupplierInfo(BaseModel):
    """Extracted supplier information from document.

    Attributes:
        name: Supplier company name (required)
        country_of_origin: ISO 3166-1 alpha-2 code or full country name (required)
        registration_number: Business/tax registration ID (optional)
        business_type: Type of business (e.g., manufacturer, importer, distributor)
        certification_status: Certification status (e.g., certified, pending, none)
        last_updated: When this information was last verified
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255, description="Supplier company name")
    country_of_origin: str = Field(
        ..., min_length=1, max_length=100, description="ISO code or full country name"
    )
    registration_number: str | None = Field(
        None, max_length=100, description="Business/tax registration number"
    )
    business_type: str | None = Field(
        None, max_length=100, description="Type of business (manufacturer, importer, etc)"
    )
    certification_status: str | None = Field(
        None, max_length=100, description="Certification status (certified, pending, none)"
    )
    last_updated: datetime | None = Field(None, description="When info was last verified")

    @field_validator("name", "country_of_origin", "registration_number", "business_type", "certification_status", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None) -> str | None:
        return _normalize_str(v)

    @field_validator("last_updated", mode="after")
    @classmethod
    def normalize_timezone(cls, v: datetime | None) -> datetime | None:
        """Normalize timezone for last_updated datetimes.

        If datetime is naive, add UTC timezone. If it has different timezone, convert to UTC.
        """
        if v is None:
            return v
        if v.tzinfo is None:
            # Only convert naive datetimes - keep them naive in the model
            # but mark that they should be treated as UTC
            return v
        # Convert non-UTC timezones to UTC
        if v.tzinfo != UTC:
            return v.astimezone(UTC)
        return v


class ProductInfo(BaseModel):
    """Extracted product information from document.

    Attributes:
        name: Product name or description (required)
        hs_code: Harmonized System code (8-10 digits, optional)
        category: Product category (e.g., agricultural, wood, minerals)
        origin_country: Where product originates (ISO code)
        quantity: Amount of goods
        unit: Unit of measurement (kg, units, liters, etc)
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=500, description="Product name or description")
    hs_code: str | None = Field(
        None, max_length=20, description="Harmonized System code (8-10 digits)"
    )
    category: str | None = Field(
        None, max_length=100, description="Product category (agricultural, wood, etc)"
    )
    origin_country: str | None = Field(
        None, max_length=100, description="ISO code or full country name"
    )
    quantity: float | None = Field(None, ge=0.0, description="Amount of goods")
    unit: str | None = Field(None, max_length=50, description="Unit (kg, units, liters, etc)")

    @field_validator("name", "hs_code", "category", "origin_country", "unit", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None) -> str | None:
        return _normalize_str(v)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float | None) -> float | None:
        """Reject NaN and infinity values in quantity."""
        if v is not None:
            if math.isnan(v) or math.isinf(v):
                raise ValueError("quantity must be a finite number")
        return v


class LocationInfo(BaseModel):
    """Extracted location/origin information from document.

    Attributes:
        country: ISO 3166-1 alpha-2 code or full country name (required)
        region: Province, state, or region (optional)
        risk_profile: Risk assessment for location (high-risk, medium, low)
        geolocation_verified: Whether location has been verified with coordinates
    """

    model_config = ConfigDict(extra="forbid")

    country: str = Field(..., min_length=1, max_length=100, description="ISO code or full country name")
    region: str | None = Field(None, max_length=100, description="Province, state, or region")
    risk_profile: str | None = Field(
        None, max_length=50, description="Risk profile (high-risk, medium, low, unknown)"
    )
    geolocation_verified: bool = Field(False, description="Whether location verified with coordinates")

    @field_validator("country", "region", "risk_profile", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None) -> str | None:
        return _normalize_str(v)


class ShipmentInfo(BaseModel):
    """Extracted shipment details from document.

    Attributes:
        shipment_date: Date goods were shipped
        arrival_date: Expected or actual arrival date
        origin_port: Port of loading (e.g., Singapore Port)
        destination_port: Port of discharge
        transport_mode: Mode of transportation (sea, air, rail, truck)
        tracking_number: Bill of lading, AWB, or reference number
    """

    model_config = ConfigDict(extra="forbid")

    shipment_date: date | None = Field(None, description="Date goods were shipped")
    arrival_date: date | None = Field(None, description="Expected or actual arrival date")
    origin_port: str | None = Field(None, max_length=255, description="Port of loading")
    destination_port: str | None = Field(None, max_length=255, description="Port of discharge")
    transport_mode: str | None = Field(None, max_length=50, description="Mode (sea, air, rail, truck)")
    tracking_number: str | None = Field(None, max_length=100, description="Bill of lading or AWB number")

    @field_validator("origin_port", "destination_port", "transport_mode", "tracking_number", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None) -> str | None:
        return _normalize_str(v)


class ExtractionResult(BaseModel):
    """Result of structured entity extraction from a document.

    Combines all extracted entities with metadata and confidence scoring.

    Attributes:
        document_id: UUID of the source document
        supplier: Extracted supplier information
        product: Extracted product information
        location: Extracted location/origin information
        shipment: Extracted shipment details
        extraction_confidence: LLM confidence in extraction (0.0-1.0)
        extracted_at: Timestamp of extraction
        model_used: Model identifier (e.g., openai/gpt-4o-mini)
    """

    model_config = ConfigDict(extra="forbid")

    document_id: UUID = Field(..., description="Parent document ID")
    supplier: SupplierInfo = Field(..., description="Extracted supplier information")
    product: ProductInfo = Field(..., description="Extracted product information")
    location: LocationInfo = Field(..., description="Extracted location information")
    shipment: ShipmentInfo = Field(..., description="Extracted shipment information")
    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="LLM confidence in extraction (0.0-1.0)"
    )
    extracted_at: datetime = Field(..., description="Timestamp of extraction")
    model_used: str = Field(..., max_length=255, description="Model identifier")

    @field_validator("extraction_confidence")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """Reject NaN and infinity values.

        Pydantic's ge/le don't reject float('nan') or float('inf').
        Storing NaN corrupts downstream aggregations.
        """
        if math.isnan(v) or math.isinf(v):
            raise ValueError("extraction_confidence must be finite between 0.0 and 1.0")
        return v
