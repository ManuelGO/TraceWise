"""Confidence scoring service for compliance risk assessments.

Aggregates five quality factors from the Phase 5 pipeline into a single
confidence score (0.0-1.0) that reflects how reliable the overall risk
assessment is.

Confidence factors (coordinator-approved weights from DECISIONS_CONFIRMED.md):
  Extraction confidence   25%  — LLM confidence from Task 38
  Validation success      20%  — Validation pass rate from Task 39
  Consistency score       25%  — Cross-document agreement from Task 40
  Evidence completeness   15%  — Required fields found (caller-provided)
  Source quality          15%  — RetrievalService similarity (caller-provided)

Pipeline position:
  Task 38 → Task 39 → Task 40 → Task 41 → Task 42 → Task 43 (THIS) → Task 44
"""

import logging
import math
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.consistency import ConsistencyReport
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight constants (coordinator-approved, must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHT_EXTRACTION: float = 0.25
WEIGHT_VALIDATION: float = 0.20
WEIGHT_CONSISTENCY: float = 0.25
WEIGHT_COMPLETENESS: float = 0.15
WEIGHT_SOURCE_QUALITY: float = 0.15

_WEIGHTS_SUM = (
    WEIGHT_EXTRACTION
    + WEIGHT_VALIDATION
    + WEIGHT_CONSISTENCY
    + WEIGHT_COMPLETENESS
    + WEIGHT_SOURCE_QUALITY
)
assert abs(_WEIGHTS_SUM - 1.0) < 1e-9, f"Confidence weights must sum to 1.0, got {_WEIGHTS_SUM}"

# Default threshold for `threshold_met` flag
CONFIDENCE_THRESHOLD_DEFAULT: float = 0.70

# Confidence level boundaries (inclusive lower bound)
_LEVEL_THRESHOLDS: list[tuple[float, str]] = [
    (0.90, "very_high"),
    (0.75, "high"),
    (0.60, "medium"),
    (0.40, "low"),
    (0.00, "very_low"),
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ConfidenceFactors(BaseModel):
    """Breakdown of the five confidence factors contributing to the final score.

    Attributes:
        extraction_confidence: LLM confidence from entity extraction (0.0-1.0)
        validation_success_rate: Proportion of validation checks that passed (0.0-1.0)
        consistency_score: Cross-document agreement score (0.0-1.0)
        evidence_completeness: Proportion of required fields found (0.0-1.0)
        source_quality: Average similarity of retrieved source documents (0.0-1.0)
    """

    model_config = ConfigDict(extra="forbid")

    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="LLM extraction confidence (0.0-1.0)"
    )
    validation_success_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Proportion of validation checks passed (0.0-1.0)"
    )
    consistency_score: float = Field(
        ..., ge=0.0, le=1.0, description="Cross-document consistency score (0.0-1.0)"
    )
    evidence_completeness: float = Field(
        ..., ge=0.0, le=1.0, description="Required evidence fields found (0.0-1.0)"
    )
    source_quality: float = Field(
        ..., ge=0.0, le=1.0, description="Average source document similarity (0.0-1.0)"
    )

    @field_validator(
        "extraction_confidence",
        "validation_success_rate",
        "consistency_score",
        "evidence_completeness",
        "source_quality",
    )
    @classmethod
    def reject_nan_inf(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Confidence factor must be a finite number")
        return v


class ConfidenceResult(BaseModel):
    """Result of confidence scoring for a compliance risk assessment.

    Attributes:
        confidence_score: Final weighted confidence (0.0-1.0)
        factors: Breakdown of the five individual factors
        confidence_level: Human-readable level (very_low/low/medium/high/very_high)
        threshold_met: Whether confidence_score >= configured threshold
        computed_at: UTC timestamp of when scoring was performed
    """

    model_config = ConfigDict(extra="forbid")

    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Final weighted confidence score (0.0-1.0)"
    )
    factors: ConfidenceFactors = Field(..., description="Individual factor breakdown")
    confidence_level: str = Field(
        ...,
        pattern="^(very_low|low|medium|high|very_high)$",
        description="Confidence level classification",
    )
    threshold_met: bool = Field(..., description="Whether score meets the configured threshold")
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of computation",
    )

    @field_validator("confidence_score")
    @classmethod
    def reject_nan_inf(cls, v: float) -> float:
        if math.isnan(v) or math.isinf(v):
            raise ValueError("confidence_score must be a finite number")
        return v


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConfidenceScorer:
    """Pure-computation confidence scoring service.

    Aggregates five pipeline-quality factors into a single confidence score
    (0.0-1.0). No I/O, no database writes, no async — deterministic for
    identical inputs.

    Attributes:
        threshold: Minimum confidence score considered acceptable (default 0.70)
    """

    def __init__(self, threshold: float = CONFIDENCE_THRESHOLD_DEFAULT) -> None:
        """Initialize ConfidenceScorer.

        Args:
            threshold: Minimum acceptable confidence score (0.0-1.0, default 0.70)

        Raises:
            ValueError: If threshold is outside [0.0, 1.0] or is NaN/inf
        """
        self._validate_float("threshold", threshold)
        self.threshold = threshold

    def compute(
        self,
        entities: ExtractionResult,
        validation_result: ValidationResult | None = None,
        consistency_result: ConsistencyReport | None = None,
        evidence_completeness: float = 1.0,
        source_quality: float = 0.5,
    ) -> ConfidenceResult:
        """Compute the confidence score for a compliance risk assessment.

        Derives each factor from the provided inputs, applies coordinator-approved
        weights, and returns a ConfidenceResult with the aggregated score and
        full factor breakdown.

        Args:
            entities: ExtractionResult from Task 38 (required)
            validation_result: ValidationResult from Task 39 (optional)
            consistency_result: ConsistencyReport from Task 40 (optional)
            evidence_completeness: Fraction of required fields found (default 1.0)
            source_quality: Average source similarity score (default 0.5)

        Returns:
            ConfidenceResult with confidence_score, factors, level, and threshold flag

        Raises:
            ValueError: If entities is None or factor values are invalid
        """
        if entities is None:
            raise ValueError("ExtractionResult is required for confidence scoring")

        self._validate_float("evidence_completeness", evidence_completeness)
        self._validate_float("source_quality", source_quality)

        extraction = self._derive_extraction_factor(entities)
        validation = self._derive_validation_factor(validation_result)
        consistency = self._derive_consistency_factor(consistency_result)

        factors = ConfidenceFactors(
            extraction_confidence=extraction,
            validation_success_rate=validation,
            consistency_score=consistency,
            evidence_completeness=evidence_completeness,
            source_quality=source_quality,
        )

        score = self._aggregate(factors)
        level = self._classify_level(score)
        met = self._check_threshold(score)

        logger.info(
            f"Confidence scoring complete: score={score:.3f}, level={level}, "
            f"threshold_met={met} (threshold={self.threshold})"
        )

        return ConfidenceResult(
            confidence_score=score,
            factors=factors,
            confidence_level=level,
            threshold_met=met,
        )

    # ------------------------------------------------------------------
    # Factor derivation helpers
    # ------------------------------------------------------------------

    def _derive_extraction_factor(self, entities: ExtractionResult) -> float:
        """Read extraction_confidence directly from ExtractionResult.

        Args:
            entities: ExtractionResult from Task 38

        Returns:
            Extraction confidence clamped to [0.0, 1.0]
        """
        return max(0.0, min(1.0, entities.extraction_confidence))

    def _derive_validation_factor(self, validation_result: ValidationResult | None) -> float:
        """Derive validation success rate from ValidationResult.

        Maps validation_score (0-100) to a 0.0-1.0 fraction.
        If no ValidationResult is provided, returns 1.0 (no failures known).

        Args:
            validation_result: ValidationResult from Task 39 (optional)

        Returns:
            Validation success rate in [0.0, 1.0]
        """
        if validation_result is None:
            return 1.0
        rate = validation_result.validation_score / 100.0
        return max(0.0, min(1.0, rate))

    def _derive_consistency_factor(self, consistency_result: ConsistencyReport | None) -> float:
        """Derive consistency score from ConsistencyReport.

        Uses confidence_adjustment (0.0-0.3) as a penalty:
        consistency_score = 1.0 - confidence_adjustment

        If no ConsistencyReport is provided, returns 1.0 (no conflicts known).

        Args:
            consistency_result: ConsistencyReport from Task 40 (optional)

        Returns:
            Consistency score in [0.7, 1.0] when report present, 1.0 otherwise
        """
        if consistency_result is None:
            return 1.0
        score = 1.0 - consistency_result.confidence_adjustment
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Aggregation and classification
    # ------------------------------------------------------------------

    def _aggregate(self, factors: ConfidenceFactors) -> float:
        """Apply coordinator-approved weights to produce final confidence score.

        Args:
            factors: ConfidenceFactors with all five components

        Returns:
            Weighted sum clamped to [0.0, 1.0]
        """
        raw = (
            factors.extraction_confidence * WEIGHT_EXTRACTION
            + factors.validation_success_rate * WEIGHT_VALIDATION
            + factors.consistency_score * WEIGHT_CONSISTENCY
            + factors.evidence_completeness * WEIGHT_COMPLETENESS
            + factors.source_quality * WEIGHT_SOURCE_QUALITY
        )
        return max(0.0, min(1.0, raw))

    def _classify_level(self, score: float) -> str:
        """Map confidence score to a human-readable level.

        Thresholds: very_high ≥ 0.90, high ≥ 0.75, medium ≥ 0.60, low ≥ 0.40, else very_low

        Args:
            score: Confidence score in [0.0, 1.0]

        Returns:
            Level string: "very_low", "low", "medium", "high", or "very_high"
        """
        for bound, level in _LEVEL_THRESHOLDS:
            if score >= bound:
                return level
        return "very_low"  # unreachable but satisfies type checker

    def _check_threshold(self, score: float) -> bool:
        """Check whether confidence score meets the configured threshold.

        Args:
            score: Confidence score in [0.0, 1.0]

        Returns:
            True if score >= self.threshold, False otherwise
        """
        return score >= self.threshold

    # ------------------------------------------------------------------
    # Internal validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_float(name: str, value: float) -> None:
        """Validate a float argument is finite and in [0.0, 1.0].

        Args:
            name: Argument name for error messages
            value: Float value to check

        Raises:
            ValueError: If value is NaN, inf, or outside [0.0, 1.0]
        """
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{name} must be a finite number, got {value}")
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")
