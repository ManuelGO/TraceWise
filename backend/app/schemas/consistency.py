"""Pydantic schemas for evidence consistency checking and conflict detection.

This module defines schemas for tracking consistency conflicts across
extracted entities in compliance cases, including field agreement,
temporal consistency, and logical relationship validation.

Key Models:
- FieldConflict: Mismatch in field values across documents
- TemporalConflict: Inconsistencies in dates/temporal logic
- LogicalConflict: Violations of logical entity relationships
- ConsistencyReport: Aggregated results of consistency checks
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConflictSeverity(StrEnum):
    """Enumeration of conflict severity levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TemporalConflictType(StrEnum):
    """Enumeration of temporal conflict types."""

    DATE_ORDER_VIOLATION = "date_order_violation"
    OVERLAPPING_SHIPMENTS = "overlapping_shipments"
    FUTURE_DATE = "future_date"
    MISSING_DATE_PAIR = "missing_date_pair"


class LogicalConflictType(StrEnum):
    """Enumeration of logical conflict types."""

    LOCATION_SUPPLIER_MISMATCH = "location_supplier_mismatch"
    PRODUCT_ORIGIN_MISMATCH = "product_origin_mismatch"
    PORT_LOCATION_MISMATCH = "port_location_mismatch"
    SUPPLIER_PRODUCT_MISMATCH = "supplier_product_mismatch"


class FieldConflict(BaseModel):
    """Represents a conflict in field values across documents.

    Attributes:
        field: Field path (e.g., "supplier.country_of_origin")
        values: Dict mapping document IDs to conflicting values
        severity: Conflict severity (high, medium, low)
        resolved_value: Suggested resolution (e.g., majority vote)
    """

    model_config = ConfigDict(extra="forbid")

    field: str = Field(..., min_length=1, max_length=100, description="Field path (e.g., supplier.name)")
    values: dict[str, str | None] = Field(..., description="Document ID -> value mapping")
    severity: ConflictSeverity = Field(..., description="Conflict severity level")
    resolved_value: str | None = Field(None, max_length=500, description="Suggested resolution")


class TemporalConflict(BaseModel):
    """Represents a temporal inconsistency across documents.

    Attributes:
        conflict_type: Type of temporal violation
        dates_involved: Dict mapping document IDs to relevant dates
        severity: Conflict severity (high, medium, low)
        description: Human-readable explanation of the conflict
    """

    model_config = ConfigDict(extra="forbid")

    conflict_type: TemporalConflictType = Field(..., description="Type of temporal conflict")
    dates_involved: dict[str, dict[str, str | None]] = Field(
        ..., description="Document ID -> {field: date_string} mapping"
    )
    severity: ConflictSeverity = Field(..., description="Conflict severity level")
    description: str = Field(..., min_length=1, max_length=500, description="Human-readable explanation")


class LogicalConflict(BaseModel):
    """Represents a logical inconsistency between entity relationships.

    Attributes:
        conflict_type: Type of logical violation
        involved_fields: Dict mapping document IDs to involved field values
        severity: Conflict severity (high, medium, low)
        description: Human-readable explanation of the conflict
    """

    model_config = ConfigDict(extra="forbid")

    conflict_type: LogicalConflictType = Field(..., description="Type of logical conflict")
    involved_fields: dict[str, dict[str, str | None]] = Field(
        ..., description="Document ID -> {field: value} mapping"
    )
    severity: ConflictSeverity = Field(..., description="Conflict severity level")
    description: str = Field(..., min_length=1, max_length=500, description="Human-readable explanation")


class ConsistencyReport(BaseModel):
    """Aggregated consistency check results for a case.

    Attributes:
        case_id: Parent compliance case ID
        field_conflicts: List of detected field conflicts
        temporal_conflicts: List of detected temporal conflicts
        logical_conflicts: List of detected logical conflicts
        total_conflict_count: Total number of conflicts detected
        confidence_adjustment: Confidence score reduction (0.0-0.3)
        summary: Human-readable summary of findings
        timestamp: When report was generated
    """

    model_config = ConfigDict(extra="forbid")

    case_id: UUID = Field(..., description="Parent compliance case ID")
    field_conflicts: list[FieldConflict] = Field(default_factory=list, description="Field conflicts")
    temporal_conflicts: list[TemporalConflict] = Field(default_factory=list, description="Temporal conflicts")
    logical_conflicts: list[LogicalConflict] = Field(default_factory=list, description="Logical conflicts")
    total_conflict_count: int = Field(ge=0, description="Total number of conflicts")
    confidence_adjustment: float = Field(
        ge=0.0, le=0.3, description="Confidence reduction factor (0.0-0.3)"
    )
    summary: str = Field(..., min_length=1, max_length=1000, description="Summary of consistency findings")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Report generation time")
