"""Unit tests for ConfidenceScorer service.

Tests cover:
1. ConfidenceFactors model validation (range, NaN/inf rejection)
2. ConfidenceResult model validation (score range, level enum, threshold)
3. Factor derivation helpers (extraction, validation, consistency)
4. Aggregation formula correctness (weights, clamping)
5. Confidence level classification (all boundaries)
6. Threshold configuration (default and custom)
7. compute() integration (happy path, defaults, None inputs, errors)
8. Edge cases (all zeros, all ones, boundary scores)

Total: 68 tests.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.consistency import ConflictSeverity, ConsistencyReport, FieldConflict
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import (
    SeverityLevel,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)
from app.services.confidence_scorer import (
    CONFIDENCE_THRESHOLD_DEFAULT,
    WEIGHT_COMPLETENESS,
    WEIGHT_CONSISTENCY,
    WEIGHT_EXTRACTION,
    WEIGHT_SOURCE_QUALITY,
    WEIGHT_VALIDATION,
    ConfidenceFactors,
    ConfidenceResult,
    ConfidenceScorer,
)

# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def doc_id():
    return uuid4()


@pytest.fixture
def case_id():
    return uuid4()


@pytest.fixture
def minimal_entities(doc_id):
    """Minimal valid ExtractionResult with high confidence."""
    return ExtractionResult(
        document_id=doc_id,
        supplier=SupplierInfo(name="Acme Corp", country_of_origin="US", certification_status="certified"),
        product=ProductInfo(name="Steel Coils", hs_code="72081100", origin_country="US"),
        location=LocationInfo(country="US", geolocation_verified=True),
        shipment=ShipmentInfo(tracking_number="BL123456"),
        extraction_confidence=0.90,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


@pytest.fixture
def low_confidence_entities(doc_id):
    """ExtractionResult with low confidence."""
    return ExtractionResult(
        document_id=doc_id,
        supplier=SupplierInfo(name="Unknown Supplier", country_of_origin="XX"),
        product=ProductInfo(name="Unknown Product"),
        location=LocationInfo(country="XX"),
        shipment=ShipmentInfo(),
        extraction_confidence=0.30,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


@pytest.fixture
def passing_validation():
    """ValidationResult with perfect score and no failures."""
    return ValidationResult(
        is_valid=True,
        failures=[],
        validation_score=100.0,
        checked_at=datetime.now(UTC),
    )


@pytest.fixture
def failing_validation():
    """ValidationResult with multiple failures and low score."""
    return ValidationResult(
        is_valid=False,
        failures=[
            ValidationFailure(
                rule=ValidationRuleType.COMPLETENESS,
                field="supplier.name",
                message="Required field missing",
                severity=SeverityLevel.ERROR,
            ),
            ValidationFailure(
                rule=ValidationRuleType.DATE_LOGIC,
                field="shipment.arrival_date",
                message="Arrival before shipment",
                severity=SeverityLevel.CRITICAL,
            ),
        ],
        validation_score=30.0,
        checked_at=datetime.now(UTC),
    )


@pytest.fixture
def clean_consistency(case_id):
    """ConsistencyReport with no conflicts and no confidence adjustment."""
    return ConsistencyReport(
        case_id=case_id,
        field_conflicts=[],
        temporal_conflicts=[],
        logical_conflicts=[],
        total_conflict_count=0,
        confidence_adjustment=0.0,
        summary="No conflicts detected.",
    )


@pytest.fixture
def conflicted_consistency(case_id):
    """ConsistencyReport with conflicts and maximum confidence_adjustment."""
    return ConsistencyReport(
        case_id=case_id,
        field_conflicts=[
            FieldConflict(
                field="supplier.country_of_origin",
                values={"doc1": "US", "doc2": "CN"},
                severity=ConflictSeverity.HIGH,
            )
        ],
        temporal_conflicts=[],
        logical_conflicts=[],
        total_conflict_count=1,
        confidence_adjustment=0.3,
        summary="1 field conflict detected.",
    )


@pytest.fixture
def scorer():
    return ConfidenceScorer()


# ============================================================================
# 1. ConfidenceFactors Model Validation
# ============================================================================


class TestConfidenceFactorsModel:
    def test_valid_creation_all_mid(self):
        factors = ConfidenceFactors(
            extraction_confidence=0.8,
            validation_success_rate=0.9,
            consistency_score=0.7,
            evidence_completeness=0.6,
            source_quality=0.5,
        )
        assert factors.extraction_confidence == 0.8
        assert factors.source_quality == 0.5

    def test_valid_boundary_zeros(self):
        factors = ConfidenceFactors(
            extraction_confidence=0.0,
            validation_success_rate=0.0,
            consistency_score=0.0,
            evidence_completeness=0.0,
            source_quality=0.0,
        )
        assert factors.extraction_confidence == 0.0

    def test_valid_boundary_ones(self):
        factors = ConfidenceFactors(
            extraction_confidence=1.0,
            validation_success_rate=1.0,
            consistency_score=1.0,
            evidence_completeness=1.0,
            source_quality=1.0,
        )
        assert factors.evidence_completeness == 1.0

    def test_rejects_extraction_below_zero(self):
        with pytest.raises(Exception):
            ConfidenceFactors(
                extraction_confidence=-0.1,
                validation_success_rate=0.5,
                consistency_score=0.5,
                evidence_completeness=0.5,
                source_quality=0.5,
            )

    def test_rejects_source_quality_above_one(self):
        with pytest.raises(Exception):
            ConfidenceFactors(
                extraction_confidence=0.5,
                validation_success_rate=0.5,
                consistency_score=0.5,
                evidence_completeness=0.5,
                source_quality=1.1,
            )

    def test_rejects_nan_extraction(self):
        with pytest.raises(Exception):
            ConfidenceFactors(
                extraction_confidence=float("nan"),
                validation_success_rate=0.5,
                consistency_score=0.5,
                evidence_completeness=0.5,
                source_quality=0.5,
            )

    def test_rejects_inf_validation(self):
        with pytest.raises(Exception):
            ConfidenceFactors(
                extraction_confidence=0.5,
                validation_success_rate=float("inf"),
                consistency_score=0.5,
                evidence_completeness=0.5,
                source_quality=0.5,
            )


# ============================================================================
# 2. ConfidenceResult Model Validation
# ============================================================================


class TestConfidenceResultModel:
    def _make_factors(self, v: float = 0.8) -> ConfidenceFactors:
        return ConfidenceFactors(
            extraction_confidence=v,
            validation_success_rate=v,
            consistency_score=v,
            evidence_completeness=v,
            source_quality=v,
        )

    def test_valid_creation(self):
        result = ConfidenceResult(
            confidence_score=0.82,
            factors=self._make_factors(0.82),
            confidence_level="high",
            threshold_met=True,
        )
        assert result.confidence_score == 0.82
        assert result.threshold_met is True

    def test_confidence_score_must_be_in_range(self):
        with pytest.raises(Exception):
            ConfidenceResult(
                confidence_score=1.5,
                factors=self._make_factors(),
                confidence_level="very_high",
                threshold_met=True,
            )

    def test_confidence_level_must_be_valid(self):
        with pytest.raises(Exception):
            ConfidenceResult(
                confidence_score=0.5,
                factors=self._make_factors(),
                confidence_level="unknown_level",
                threshold_met=False,
            )

    def test_all_valid_levels_accepted(self):
        for level in ("very_low", "low", "medium", "high", "very_high"):
            result = ConfidenceResult(
                confidence_score=0.5,
                factors=self._make_factors(),
                confidence_level=level,
                threshold_met=False,
            )
            assert result.confidence_level == level

    def test_computed_at_defaults_to_utc(self):
        result = ConfidenceResult(
            confidence_score=0.5,
            factors=self._make_factors(),
            confidence_level="low",
            threshold_met=False,
        )
        assert result.computed_at.tzinfo is not None

    def test_rejects_nan_confidence_score(self):
        with pytest.raises(Exception):
            ConfidenceResult(
                confidence_score=float("nan"),
                factors=self._make_factors(),
                confidence_level="low",
                threshold_met=False,
            )


# ============================================================================
# 3. Factor Derivation Helpers
# ============================================================================


class TestFactorDerivation:
    def test_derive_extraction_reads_from_entity(self, scorer, minimal_entities):
        factor = scorer._derive_extraction_factor(minimal_entities)
        assert factor == pytest.approx(0.90)

    def test_derive_extraction_clamps_to_one(self, scorer, minimal_entities):
        minimal_entities.extraction_confidence = 1.0
        factor = scorer._derive_extraction_factor(minimal_entities)
        assert factor == 1.0

    def test_derive_validation_none_returns_one(self, scorer):
        assert scorer._derive_validation_factor(None) == 1.0

    def test_derive_validation_perfect_score(self, scorer, passing_validation):
        rate = scorer._derive_validation_factor(passing_validation)
        assert rate == pytest.approx(1.0)

    def test_derive_validation_low_score(self, scorer, failing_validation):
        rate = scorer._derive_validation_factor(failing_validation)
        assert rate == pytest.approx(0.30)

    def test_derive_validation_zero_score(self, scorer):
        zero_result = ValidationResult(
            is_valid=False,
            failures=[],
            validation_score=0.0,
            checked_at=datetime.now(UTC),
        )
        assert scorer._derive_validation_factor(zero_result) == pytest.approx(0.0)

    def test_derive_consistency_none_returns_one(self, scorer):
        assert scorer._derive_consistency_factor(None) == 1.0

    def test_derive_consistency_no_conflicts_returns_one(self, scorer, clean_consistency):
        score = scorer._derive_consistency_factor(clean_consistency)
        assert score == pytest.approx(1.0)

    def test_derive_consistency_max_adjustment(self, scorer, conflicted_consistency):
        score = scorer._derive_consistency_factor(conflicted_consistency)
        assert score == pytest.approx(0.70)

    def test_derive_consistency_partial_adjustment(self, scorer, case_id):
        report = ConsistencyReport(
            case_id=case_id,
            field_conflicts=[],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=0,
            confidence_adjustment=0.15,
            summary="Partial conflicts.",
        )
        assert scorer._derive_consistency_factor(report) == pytest.approx(0.85)


# ============================================================================
# 4. Aggregation Formula
# ============================================================================


class TestAggregation:
    def test_all_ones_gives_score_one(self, scorer):
        factors = ConfidenceFactors(
            extraction_confidence=1.0,
            validation_success_rate=1.0,
            consistency_score=1.0,
            evidence_completeness=1.0,
            source_quality=1.0,
        )
        assert scorer._aggregate(factors) == pytest.approx(1.0)

    def test_all_zeros_gives_score_zero(self, scorer):
        factors = ConfidenceFactors(
            extraction_confidence=0.0,
            validation_success_rate=0.0,
            consistency_score=0.0,
            evidence_completeness=0.0,
            source_quality=0.0,
        )
        assert scorer._aggregate(factors) == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        total = WEIGHT_EXTRACTION + WEIGHT_VALIDATION + WEIGHT_CONSISTENCY + WEIGHT_COMPLETENESS + WEIGHT_SOURCE_QUALITY
        assert total == pytest.approx(1.0)

    def test_formula_with_known_inputs(self, scorer):
        # 0.80*0.25 + 0.90*0.20 + 0.70*0.25 + 1.0*0.15 + 0.5*0.15
        # = 0.20 + 0.18 + 0.175 + 0.15 + 0.075 = 0.78
        factors = ConfidenceFactors(
            extraction_confidence=0.80,
            validation_success_rate=0.90,
            consistency_score=0.70,
            evidence_completeness=1.0,
            source_quality=0.50,
        )
        expected = (0.80 * 0.25) + (0.90 * 0.20) + (0.70 * 0.25) + (1.0 * 0.15) + (0.50 * 0.15)
        assert scorer._aggregate(factors) == pytest.approx(expected)

    def test_extraction_weight_is_25_percent(self, scorer):
        factors = ConfidenceFactors(
            extraction_confidence=1.0,
            validation_success_rate=0.0,
            consistency_score=0.0,
            evidence_completeness=0.0,
            source_quality=0.0,
        )
        assert scorer._aggregate(factors) == pytest.approx(WEIGHT_EXTRACTION)

    def test_consistency_weight_is_25_percent(self, scorer):
        factors = ConfidenceFactors(
            extraction_confidence=0.0,
            validation_success_rate=0.0,
            consistency_score=1.0,
            evidence_completeness=0.0,
            source_quality=0.0,
        )
        assert scorer._aggregate(factors) == pytest.approx(WEIGHT_CONSISTENCY)


# ============================================================================
# 5. Confidence Level Classification
# ============================================================================


class TestLevelClassification:
    def test_very_low_at_zero(self, scorer):
        assert scorer._classify_level(0.00) == "very_low"

    def test_very_low_at_boundary(self, scorer):
        assert scorer._classify_level(0.39) == "very_low"

    def test_low_at_boundary(self, scorer):
        assert scorer._classify_level(0.40) == "low"

    def test_low_mid(self, scorer):
        assert scorer._classify_level(0.50) == "low"

    def test_medium_at_boundary(self, scorer):
        assert scorer._classify_level(0.60) == "medium"

    def test_medium_mid(self, scorer):
        assert scorer._classify_level(0.67) == "medium"

    def test_high_at_boundary(self, scorer):
        assert scorer._classify_level(0.75) == "high"

    def test_high_mid(self, scorer):
        assert scorer._classify_level(0.82) == "high"

    def test_very_high_at_boundary(self, scorer):
        assert scorer._classify_level(0.90) == "very_high"

    def test_very_high_at_one(self, scorer):
        assert scorer._classify_level(1.00) == "very_high"


# ============================================================================
# 6. Threshold Configuration
# ============================================================================


class TestThreshold:
    def test_default_threshold_is_0_70(self):
        assert CONFIDENCE_THRESHOLD_DEFAULT == 0.70
        scorer = ConfidenceScorer()
        assert scorer.threshold == 0.70

    def test_below_threshold_not_met(self, scorer):
        assert scorer._check_threshold(0.69) is False

    def test_at_threshold_met(self, scorer):
        assert scorer._check_threshold(0.70) is True

    def test_above_threshold_met(self, scorer):
        assert scorer._check_threshold(0.95) is True

    def test_custom_threshold_lower(self):
        low_scorer = ConfidenceScorer(threshold=0.50)
        assert low_scorer._check_threshold(0.55) is True
        assert low_scorer._check_threshold(0.49) is False

    def test_custom_threshold_higher(self):
        strict_scorer = ConfidenceScorer(threshold=0.95)
        assert strict_scorer._check_threshold(0.90) is False
        assert strict_scorer._check_threshold(0.95) is True

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            ConfidenceScorer(threshold=1.5)

    def test_nan_threshold_raises(self):
        with pytest.raises(ValueError):
            ConfidenceScorer(threshold=float("nan"))


# ============================================================================
# 7. compute() Integration Tests
# ============================================================================


class TestComputeIntegration:
    def test_returns_confidence_result_type(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities)
        assert isinstance(result, ConfidenceResult)

    def test_minimal_inputs_only_entities(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities)
        assert 0.0 <= result.confidence_score <= 1.0
        assert result.factors.validation_success_rate == 1.0
        assert result.factors.consistency_score == 1.0

    def test_none_entities_raises_value_error(self, scorer):
        with pytest.raises(ValueError, match="ExtractionResult is required"):
            scorer.compute(None)  # type: ignore[arg-type]

    def test_full_inputs_high_quality_scores_high(self, scorer, minimal_entities, passing_validation, clean_consistency):
        result = scorer.compute(
            minimal_entities,
            validation_result=passing_validation,
            consistency_result=clean_consistency,
            evidence_completeness=1.0,
            source_quality=0.95,
        )
        assert result.confidence_score >= 0.80
        assert result.confidence_level in ("high", "very_high")
        assert result.threshold_met is True

    def test_low_quality_inputs_scores_low(self, scorer, low_confidence_entities, failing_validation, conflicted_consistency):
        result = scorer.compute(
            low_confidence_entities,
            validation_result=failing_validation,
            consistency_result=conflicted_consistency,
            evidence_completeness=0.2,
            source_quality=0.1,
        )
        assert result.confidence_score < 0.60

    def test_factors_match_derived_values(self, scorer, minimal_entities, failing_validation):
        result = scorer.compute(minimal_entities, validation_result=failing_validation)
        assert result.factors.extraction_confidence == pytest.approx(0.90)
        assert result.factors.validation_success_rate == pytest.approx(0.30)

    def test_none_validation_uses_default_1(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities, validation_result=None)
        assert result.factors.validation_success_rate == 1.0

    def test_none_consistency_uses_default_1(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities, consistency_result=None)
        assert result.factors.consistency_score == 1.0

    def test_evidence_completeness_reflected_in_factors(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities, evidence_completeness=0.60)
        assert result.factors.evidence_completeness == pytest.approx(0.60)

    def test_source_quality_reflected_in_factors(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities, source_quality=0.80)
        assert result.factors.source_quality == pytest.approx(0.80)

    def test_invalid_evidence_completeness_raises(self, scorer, minimal_entities):
        with pytest.raises(ValueError):
            scorer.compute(minimal_entities, evidence_completeness=1.5)

    def test_invalid_source_quality_raises(self, scorer, minimal_entities):
        with pytest.raises(ValueError):
            scorer.compute(minimal_entities, source_quality=-0.1)

    def test_nan_evidence_completeness_raises(self, scorer, minimal_entities):
        with pytest.raises(ValueError):
            scorer.compute(minimal_entities, evidence_completeness=float("nan"))

    def test_threshold_met_true_when_score_high(self, scorer, minimal_entities, passing_validation):
        result = scorer.compute(minimal_entities, validation_result=passing_validation, source_quality=0.95)
        assert result.threshold_met is True

    def test_computed_at_is_utc_datetime(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities)
        assert isinstance(result.computed_at, datetime)
        assert result.computed_at.tzinfo is not None


# ============================================================================
# 8. Edge Cases
# ============================================================================


class TestEdgeCases:
    def test_extraction_confidence_zero(self, scorer, minimal_entities):
        # extraction=0.0, validation=1.0 (default), consistency=1.0 (default),
        # completeness=1.0 (default), source=0.5 (default)
        # => 0*0.25 + 1.0*0.20 + 1.0*0.25 + 1.0*0.15 + 0.5*0.15 = 0.675
        minimal_entities.extraction_confidence = 0.0
        result = scorer.compute(minimal_entities)
        # extraction contributes 0 instead of 0.25, so score drops by 0.225
        assert result.confidence_score < 0.70

    def test_extraction_confidence_one(self, scorer, minimal_entities):
        minimal_entities.extraction_confidence = 1.0
        result = scorer.compute(minimal_entities, source_quality=1.0, evidence_completeness=1.0)
        assert result.confidence_score >= 0.75

    def test_score_never_exceeds_one(self, scorer, minimal_entities, passing_validation, clean_consistency):
        result = scorer.compute(
            minimal_entities,
            validation_result=passing_validation,
            consistency_result=clean_consistency,
            evidence_completeness=1.0,
            source_quality=1.0,
        )
        assert result.confidence_score <= 1.0

    def test_score_never_below_zero(self, scorer, low_confidence_entities, failing_validation, conflicted_consistency):
        result = scorer.compute(
            low_confidence_entities,
            validation_result=failing_validation,
            consistency_result=conflicted_consistency,
            evidence_completeness=0.0,
            source_quality=0.0,
        )
        assert result.confidence_score >= 0.0

    def test_default_source_quality_is_0_5(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities)
        assert result.factors.source_quality == pytest.approx(0.5)

    def test_default_evidence_completeness_is_1(self, scorer, minimal_entities):
        result = scorer.compute(minimal_entities)
        assert result.factors.evidence_completeness == pytest.approx(1.0)
