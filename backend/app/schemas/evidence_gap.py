"""Pydantic schemas for evidence gap analysis (Task 44).

Defines the output schema for missing-evidence detection. A gap is a required
field (per document type) that was not present in the extracted entities.

Models:
- GapSeverity: severity classification for a gap (critical/high/medium/low)
- EvidenceGap: a single missing required field with an actionable suggestion
- EvidenceGapResult: aggregated gap report for one document, including a
  completeness_score consumed by Task 43 (ConfidenceScorer) as evidence_completeness
- EvidenceGapRequest: request body for the gap-analysis endpoint

This task is stateless (TASK_44_COORDINATOR_DECISION.md, Option 1): no ORM model,
no database persistence. The result is computed on demand and returned directly.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import ExtractionResult

# Default/fallback document-type key used when none is supplied or the supplied
# value is unrecognized. Lives in the schema layer (the public contract); the
# service imports it from here.
GENERAL_DOC_TYPE: str = "general"


class GapSeverity(StrEnum):
    """Severity of a missing-evidence gap.

    Extends the consistency module's high/medium/low tiers with `critical`,
    since a missing mandatory field can be a hard compliance blocker.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceGap(BaseModel):
    """A single missing required field detected during gap analysis.

    Attributes:
        document_type: Document type string the gap was evaluated under
        required_field: Human-readable label of the missing field (e.g. "Supplier name")
        entity_path: Dotted path into the extraction result (e.g. "supplier.name")
        severity: Gap severity classification
        suggested_action: Actionable remediation guidance for resolving the gap
    """

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(
        ..., min_length=1, max_length=100, description="Document type the gap applies to"
    )
    required_field: str = Field(
        ..., min_length=1, max_length=200, description="Human-readable required field label"
    )
    entity_path: str = Field(
        ..., min_length=1, max_length=200, description="Dotted entity path (e.g. supplier.name)"
    )
    severity: GapSeverity = Field(..., description="Gap severity classification")
    suggested_action: str = Field(
        ..., min_length=1, max_length=500, description="Actionable remediation suggestion"
    )


class EvidenceGapResult(BaseModel):
    """Aggregated evidence gap report for a single document.

    Attributes:
        document_id: UUID of the source document (from the ExtractionResult)
        document_type: Document type string the analysis was run under
        gaps: List of detected missing-evidence gaps (empty when complete)
        total_required: Total number of required fields for this document type
        required_found: Number of required fields that were present
        completeness_score: required_found / total_required (0.0-1.0); consumed by
            Task 43 ConfidenceScorer as evidence_completeness
        is_complete: True iff no gaps were detected
        generated_at: UTC timestamp of when the analysis ran
    """

    model_config = ConfigDict(extra="forbid")

    document_id: UUID = Field(..., description="Source document ID")
    document_type: str = Field(
        ..., min_length=1, max_length=100, description="Document type analyzed"
    )
    gaps: list[EvidenceGap] = Field(default_factory=list, description="Detected evidence gaps")
    total_required: int = Field(..., ge=0, description="Total required fields for this doc type")
    required_found: int = Field(..., ge=0, description="Required fields found present")
    completeness_score: float = Field(
        ..., ge=0.0, le=1.0, description="Fraction of required fields found (0.0-1.0)"
    )
    is_complete: bool = Field(..., description="True when no gaps were detected")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of analysis",
    )
    # NaN/inf are rejected by the ge=0.0/le=1.0 constraints above before any
    # field_validator would run (Pydantic v2), so no extra validator is needed.


class EvidenceGapRequest(BaseModel):
    """Request body for evidence gap analysis.

    Attributes:
        extraction: Task 38 ExtractionResult to analyze.
        document_type: Document type string. Recognized DocumentType values use their
            specific required-field catalogue; "general" or any unrecognized value
            falls back to the general baseline.
    """

    model_config = ConfigDict(extra="forbid")

    extraction: ExtractionResult = Field(..., description="Extraction result to analyze")
    document_type: str = Field(
        GENERAL_DOC_TYPE,
        min_length=1,
        max_length=100,
        description="Document type for the required-field catalogue",
    )
