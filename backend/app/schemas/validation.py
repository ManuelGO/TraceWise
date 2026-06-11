"""Validation schemas for entity extraction quality checks.

This module defines Pydantic models for validation results, tracking
validation failures, and computed validation scores for extracted entities.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ValidationRuleType(StrEnum):
    """Enumeration of validation rule categories."""

    COMPLETENESS = "completeness"
    DATE_LOGIC = "date_logic"
    PORT_VALIDATION = "port_validation"
    COUNTRY_CODE = "country_code"
    HS_CODE_FORMAT = "hs_code_format"
    TRACKING_FORMAT = "tracking_format"


class SeverityLevel(StrEnum):
    """Enumeration of failure severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationFailure(BaseModel):
    """Represents a single validation failure.

    Attributes:
        rule: The validation rule that failed
        field: The field path that triggered the failure (e.g., "supplier.name")
        message: Human-readable description of the failure (max 500 chars)
        severity: Severity level (info, warning, error, critical)
    """

    model_config = ConfigDict(extra="forbid")

    rule: ValidationRuleType
    field: str
    message: str = Field(max_length=500)
    severity: SeverityLevel


class ValidationResult(BaseModel):
    """Result of validation check for an extracted entity.

    Attributes:
        is_valid: Whether the entity passed all validation rules
        failures: List of validation failures (empty if valid)
        validation_score: Computed score 0-100 based on passed checks
        checked_at: When validation was performed
    """

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    failures: list[ValidationFailure] = Field(default_factory=list)
    validation_score: float = Field(ge=0.0, le=100.0)
    checked_at: datetime


class ValidatedExtractionResult(BaseModel):
    """Complete result combining extraction and validation.

    Attributes:
        extraction_id: UUID of the original extraction
        entity_type: Type of entity (supplier, product, location, shipment)
        validation: Validation result details
        retry_count: Number of retries attempted
        validated_at: When validation completed
        extraction_data: Original extraction result (for consistency checking)
    """

    model_config = ConfigDict(extra="forbid")

    extraction_id: UUID
    entity_type: str = Field(pattern="^(supplier|product|location|shipment|result)$")
    validation: ValidationResult
    retry_count: int = Field(ge=0, le=10)
    validated_at: datetime
    extraction_data: dict | None = Field(None, description="Original extraction result data")


# Helper functions for common validations


def is_valid_date_pair(shipment_date: str | None, arrival_date: str | None) -> bool:
    """Check if shipment date is before or equal to arrival date.

    Args:
        shipment_date: ISO date string or None
        arrival_date: ISO date string or None

    Returns:
        True if dates are valid, False otherwise
    """
    if not shipment_date or not arrival_date:
        return True

    try:
        from datetime import datetime as dt

        ship = dt.fromisoformat(shipment_date)
        arrival = dt.fromisoformat(arrival_date)
        return ship <= arrival
    except (ValueError, TypeError):
        return False


def is_valid_country_code(code: str | None) -> bool:
    """Check if code is valid ISO 3166-1 alpha-2.

    Args:
        code: Two-letter country code or None

    Returns:
        True if valid ISO code, False otherwise
    """
    if not code:
        return True

    # Full ISO 3166-1 alpha-2 country codes (249 entries)
    valid_codes = {
        "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR",
        "AS", "AT", "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE",
        "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ",
        "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD",
        "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR",
        "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
        "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI",
        "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF",
        "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS",
        "GT", "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU",
        "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT",
        "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
        "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK",
        "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME",
        "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ",
        "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA",
        "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU",
        "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
        "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS",
        "RU", "RW", "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI",
        "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV",
        "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK",
        "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ", "UA",
        "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
        "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
    }

    return code.upper() in valid_codes


def is_valid_hs_code(code: str | None) -> bool:
    """Check if HS code has valid format.

    Args:
        code: HS code string or None

    Returns:
        True if valid format (6-10 digits), False otherwise
    """
    if not code:
        return True

    cleaned = code.replace(" ", "").replace("-", "")
    return cleaned.isdigit() and 6 <= len(cleaned) <= 10


def is_valid_tracking_number(tracking: str | None) -> bool:
    """Check if tracking number has reasonable format.

    Args:
        tracking: Tracking number string or None

    Returns:
        True if tracking is non-empty, False otherwise
    """
    if not tracking:
        return True

    return bool(tracking.strip()) and len(tracking.strip()) >= 3
