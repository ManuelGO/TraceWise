"""Unit tests for RiskScorer service.

Tests cover all five risk categories with deterministic scoring logic:
- Geolocation Risk (0-25 points)
- Supplier Risk (0-25 points)
- Temporal Risk (0-15 points)
- Compliance Risk (0-25 points)
- Evidence Quality Risk (0-10 points)

Total: 35+ tests covering unit, integration, and edge cases
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.schemas.consistency import (
    ConflictSeverity,
    ConsistencyReport,
    FieldConflict,
    TemporalConflict,
    TemporalConflictType,
)
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
from app.services.risk_scorer import RiskScorer, RiskScoreResult, RuleViolation

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def risk_scorer():
    """Create a RiskScorer instance for testing."""
    return RiskScorer()


@pytest.fixture
def minimal_extraction_result():
    """Create minimal valid ExtractionResult for testing."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(
            name="Test Supplier",
            country_of_origin="US",
        ),
        product=ProductInfo(name="Test Product"),
        location=LocationInfo(country="US"),
        shipment=ShipmentInfo(),
        extraction_confidence=0.9,
        extracted_at=datetime.now(UTC),
        model_used="gpt-4o-mini",
    )


@pytest.fixture
def high_risk_extraction_result():
    """Create ExtractionResult with high-risk values for testing."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(
            name="High Risk Corp",
            country_of_origin="IR",  # Iran (high-risk country)
            certification_status="none",
        ),
        product=ProductInfo(
            name="Restricted Product",
            hs_code=None,  # Missing HS code
            origin_country=None,  # Missing origin
        ),
        location=LocationInfo(
            country="IR",  # High-risk country
            geolocation_verified=False,
        ),
        shipment=ShipmentInfo(
            tracking_number=None,  # Missing tracking number
            shipment_date=date.today(),
        ),
        extraction_confidence=0.5,  # Low confidence
        extracted_at=datetime.now(UTC),
        model_used="gpt-4o-mini",
    )


# ============================================================================
# CATEGORY 1: Geolocation Risk Tests (0-25 points)
# ============================================================================


class TestGeolocationRisk:
    """Tests for geolocation risk evaluation."""

    def test_no_location_data(self, risk_scorer, minimal_extraction_result):
        """No location data → +25 points."""
        minimal_extraction_result.location = None
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "geolocation"]
        assert len(violations) == 1
        assert violations[0].rule_name == "no_location_data"
        assert violations[0].points == 25
        assert violations[0].severity == "critical"

    def test_high_risk_country(self, risk_scorer, minimal_extraction_result):
        """High-risk country → +20 points."""
        minimal_extraction_result.location.country = "IR"  # Iran
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "high_risk_country"]
        assert len(violations) == 1
        assert violations[0].points == 20
        assert violations[0].severity == "critical"

    def test_unverified_location(self, risk_scorer, minimal_extraction_result):
        """Unverified location → +10 points."""
        minimal_extraction_result.location.geolocation_verified = False
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "unverified_location"]
        assert len(violations) == 1
        assert violations[0].points == 10
        assert violations[0].severity == "medium"

    def test_verified_low_risk_location(self, risk_scorer, minimal_extraction_result):
        """Verified low-risk location → 0 points."""
        minimal_extraction_result.location.geolocation_verified = True
        minimal_extraction_result.location.country = "US"  # Not high-risk
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "geolocation"]
        assert len(violations) == 0

    def test_multiple_geolocation_violations(self, risk_scorer, minimal_extraction_result):
        """High-risk country + unverified → both violations detected, capped at 25."""
        minimal_extraction_result.location.country = "KP"  # North Korea
        minimal_extraction_result.location.geolocation_verified = False
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "geolocation"]
        assert len(violations) == 2
        # Both violations exist, but total is capped at MAX_GEOLOCATION_POINTS (25)
        assert sum(v.points for v in violations) == 25

    def test_all_high_risk_countries(self, risk_scorer, minimal_extraction_result):
        """All high-risk countries trigger risk scoring."""
        high_risk_countries = ["IR", "KP", "MM", "LY", "SY", "VE"]
        for country in high_risk_countries:
            minimal_extraction_result.location.country = country
            result = risk_scorer.score(minimal_extraction_result)

            violations = [v for v in result.violations if v.rule_name == "high_risk_country"]
            assert len(violations) == 1, f"Failed for country {country}"
            assert violations[0].points == 20


# ============================================================================
# CATEGORY 2: Supplier Risk Tests (0-25 points)
# ============================================================================


class TestSupplierRisk:
    """Tests for supplier risk evaluation."""

    def test_no_supplier_info(self, risk_scorer, minimal_extraction_result):
        """No supplier info → +25 points."""
        minimal_extraction_result.supplier = None
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "no_supplier_info"]
        assert len(violations) == 1
        assert violations[0].points == 25
        assert violations[0].severity == "critical"

    def test_no_certification(self, risk_scorer, minimal_extraction_result):
        """Missing or invalid certification → +15 points."""
        minimal_extraction_result.supplier.certification_status = None
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "no_certification"]
        assert len(violations) == 1
        assert violations[0].points == 15

    def test_certification_status_none_string(self, risk_scorer, minimal_extraction_result):
        """certification_status = 'none' → +15 points."""
        minimal_extraction_result.supplier.certification_status = "none"
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "no_certification"]
        assert len(violations) == 1

    def test_certified_supplier(self, risk_scorer, minimal_extraction_result):
        """Certified supplier → 0 points."""
        minimal_extraction_result.supplier.certification_status = "certified"
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "supplier"]
        assert len(violations) == 0

    def test_supplier_conflict_from_consistency(self, risk_scorer, minimal_extraction_result):
        """Supplier field conflict from Task 40 → +10 points."""
        consistency = ConsistencyReport(
            case_id=uuid4(),
            field_conflicts=[
                FieldConflict(
                    field="supplier.certification_status",
                    values={"doc1": "certified", "doc2": "pending"},
                    severity=ConflictSeverity.HIGH,
                )
            ],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=1,
            confidence_adjustment=0.1,
            summary="Supplier conflicts detected",
        )

        result = risk_scorer.score(minimal_extraction_result, consistency)

        violations = [v for v in result.violations if v.rule_name == "supplier_conflict"]
        assert len(violations) == 1
        assert violations[0].points == 10


# ============================================================================
# CATEGORY 3: Temporal Risk Tests (0-15 points)
# ============================================================================


class TestTemporalRisk:
    """Tests for temporal risk evaluation."""

    def test_temporal_conflict_from_consistency(self, risk_scorer, minimal_extraction_result):
        """Task 40 temporal conflict → +15 points."""
        consistency = ConsistencyReport(
            case_id=uuid4(),
            field_conflicts=[],
            temporal_conflicts=[
                TemporalConflict(
                    conflict_type=TemporalConflictType.DATE_ORDER_VIOLATION,
                    dates_involved={"doc1": {"shipment_date": "2026-06-11"}},
                    severity=ConflictSeverity.HIGH,
                    description="Shipment date after arrival date",
                )
            ],
            logical_conflicts=[],
            total_conflict_count=1,
            confidence_adjustment=0.15,
            summary="Temporal conflicts found",
        )

        result = risk_scorer.score(minimal_extraction_result, consistency)

        violations = [v for v in result.violations if v.rule_name == "temporal_conflict"]
        assert len(violations) == 1
        assert violations[0].points == 15

    def test_recent_shipment_within_7_days(self, risk_scorer, minimal_extraction_result):
        """Shipment within last 7 days → +5 points."""
        minimal_extraction_result.shipment.shipment_date = date.today()  # Today
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "recent_shipment"]
        assert len(violations) == 1
        assert violations[0].points == 5

    def test_old_shipment_no_risk(self, risk_scorer, minimal_extraction_result):
        """Shipment > 7 days ago → 0 points."""
        minimal_extraction_result.shipment.shipment_date = date(2026, 6, 1)  # 10+ days ago
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "recent_shipment"]
        assert len(violations) == 0

    def test_recent_supplier_update(self, risk_scorer, minimal_extraction_result):
        """Supplier updated within last 30 days → +5 points."""
        minimal_extraction_result.supplier.last_updated = datetime.now(UTC)  # Today
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "recent_supplier_update"]
        assert len(violations) == 1
        assert violations[0].points == 5

    def test_old_supplier_update_no_risk(self, risk_scorer, minimal_extraction_result):
        """Supplier updated > 30 days ago → 0 points."""
        minimal_extraction_result.supplier.last_updated = datetime(2026, 5, 1, tzinfo=UTC)
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "recent_supplier_update"]
        assert len(violations) == 0


# ============================================================================
# CATEGORY 4: Compliance Risk Tests (0-25 points)
# ============================================================================


class TestComplianceRisk:
    """Tests for compliance risk evaluation."""

    def test_missing_all_required_documents(self, risk_scorer, minimal_extraction_result):
        """Missing tracking_number, hs_code, origin_country → +25 points."""
        minimal_extraction_result.product.hs_code = None
        minimal_extraction_result.product.origin_country = None
        minimal_extraction_result.shipment.tracking_number = None
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "missing_required_documentation"]
        assert len(violations) == 1
        assert violations[0].points == 25

    def test_missing_tracking_number_only(self, risk_scorer, minimal_extraction_result):
        """Missing tracking_number (one field) → +25 points."""
        minimal_extraction_result.shipment.tracking_number = None
        minimal_extraction_result.product.hs_code = "12345678"
        minimal_extraction_result.product.origin_country = "US"
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "missing_required_documentation"]
        assert len(violations) == 1
        assert violations[0].points == 25

    def test_missing_hs_code_only(self, risk_scorer, minimal_extraction_result):
        """Missing hs_code (one field) → +25 points."""
        minimal_extraction_result.product.hs_code = None
        minimal_extraction_result.shipment.tracking_number = "AWB123"
        minimal_extraction_result.product.origin_country = "CN"
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "missing_required_documentation"]
        assert len(violations) == 1

    def test_all_required_documents_present(self, risk_scorer, minimal_extraction_result):
        """All required docs present → 0 points."""
        minimal_extraction_result.product.hs_code = "12345678"
        minimal_extraction_result.product.origin_country = "US"
        minimal_extraction_result.shipment.tracking_number = "BL123456"
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "missing_required_documentation"]
        assert len(violations) == 0


# ============================================================================
# CATEGORY 5: Evidence Quality Risk Tests (0-10 points)
# ============================================================================


class TestEvidenceQualityRisk:
    """Tests for evidence quality risk evaluation."""

    def test_low_extraction_confidence(self, risk_scorer, minimal_extraction_result):
        """extraction_confidence < 0.7 → +10 points."""
        minimal_extraction_result.extraction_confidence = 0.65
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "low_extraction_confidence"]
        assert len(violations) == 1
        assert violations[0].points == 10

    def test_medium_extraction_confidence(self, risk_scorer, minimal_extraction_result):
        """0.7 <= extraction_confidence < 0.8 → +5 points."""
        minimal_extraction_result.extraction_confidence = 0.75
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "medium_extraction_confidence"]
        assert len(violations) == 1
        assert violations[0].points == 5

    def test_high_extraction_confidence(self, risk_scorer, minimal_extraction_result):
        """extraction_confidence >= 0.8 → 0 points."""
        minimal_extraction_result.extraction_confidence = 0.95
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "evidence"]
        assert len(violations) == 0

    def test_extraction_confidence_boundary_0_7(self, risk_scorer, minimal_extraction_result):
        """extraction_confidence = 0.7 (boundary) → +5 points (medium, not low)."""
        minimal_extraction_result.extraction_confidence = 0.7
        result = risk_scorer.score(minimal_extraction_result)

        # Assert low confidence is NOT triggered
        low_violations = [v for v in result.violations if v.rule_name == "low_extraction_confidence"]
        assert len(low_violations) == 0

        # Assert medium confidence IS triggered
        medium_violations = [v for v in result.violations if v.rule_name == "medium_extraction_confidence"]
        assert len(medium_violations) == 1
        assert medium_violations[0].points == 5

    def test_extraction_confidence_boundary_0_8(self, risk_scorer, minimal_extraction_result):
        """extraction_confidence = 0.8 (boundary) → 0 points."""
        minimal_extraction_result.extraction_confidence = 0.8
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.category == "evidence"]
        assert len(violations) == 0

    def test_validation_failures(self, risk_scorer, minimal_extraction_result):
        """Validation failures present → +5 points."""
        validation = ValidationResult(
            is_valid=False,
            failures=[
                ValidationFailure(
                    rule=ValidationRuleType.COMPLETENESS,
                    field="supplier.name",
                    message="Missing required field",
                    severity=SeverityLevel.ERROR,
                )
            ],
            validation_score=75,
            checked_at=datetime.now(UTC),
        )

        result = risk_scorer.score(minimal_extraction_result, validation_result=validation)

        violations = [v for v in result.violations if v.rule_name == "validation_failures"]
        assert len(violations) == 1
        assert violations[0].points == 5


# ============================================================================
# Integration Tests: Full Scoring Pipeline
# ============================================================================


class TestFullScoringPipeline:
    """Integration tests for complete risk scoring flow."""

    def test_no_violations_low_risk(self, risk_scorer):
        """No violations → score 0, level 'low'."""
        extraction = ExtractionResult(
            document_id=uuid4(),
            supplier=SupplierInfo(
                name="Safe Corp",
                country_of_origin="US",
                certification_status="certified",
            ),
            product=ProductInfo(
                name="Safe Product",
                hs_code="12345678",
                origin_country="US",
            ),
            location=LocationInfo(country="US", geolocation_verified=True),
            shipment=ShipmentInfo(
                tracking_number="BL123",
                shipment_date=date(2026, 5, 1),  # Old date
            ),
            extraction_confidence=0.95,
            extracted_at=datetime.now(UTC),
            model_used="gpt-4o-mini",
        )

        result = risk_scorer.score(extraction)

        assert result.risk_score == 0
        assert result.risk_level == "low"
        assert len(result.violations) == 0

    def test_multiple_violations_high_risk(self, risk_scorer, high_risk_extraction_result):
        """Multiple violations across categories → high/critical risk."""
        result = risk_scorer.score(high_risk_extraction_result)

        assert result.risk_score > 40
        assert result.risk_level in ("high", "critical")
        assert len(result.violations) > 3

    def test_score_capping_at_100(self, risk_scorer, high_risk_extraction_result):
        """Score capped at 100 even if violations exceed."""
        consistency = ConsistencyReport(
            case_id=uuid4(),
            field_conflicts=[
                FieldConflict(
                    field="supplier.certification_status",
                    values={"doc1": "a", "doc2": "b"},
                    severity=ConflictSeverity.HIGH,
                ),
                FieldConflict(
                    field="supplier.country_of_origin",
                    values={"doc1": "IR", "doc2": "SY"},
                    severity=ConflictSeverity.HIGH,
                ),
            ],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=2,
            confidence_adjustment=0.2,
            summary="Multiple conflicts",
        )

        result = risk_scorer.score(high_risk_extraction_result, consistency)

        assert result.risk_score <= 100
        assert result.risk_level == "critical"

    def test_risk_level_boundaries(self, risk_scorer, minimal_extraction_result):
        """Test risk level assignment at boundaries."""
        test_cases = [
            (0, "low"),
            (20, "low"),
            (21, "medium"),
            (40, "medium"),
            (41, "high"),
            (70, "high"),
            (71, "critical"),
            (100, "critical"),
        ]

        for score, expected_level in test_cases:
            # Manually create a result with specific score
            level = risk_scorer._get_risk_level(score)
            assert level == expected_level, f"Score {score} should map to '{expected_level}', got '{level}'"


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_minimal_required_fields(self, risk_scorer):
        """Minimal entity fields (no optional data) still produces valid result."""
        extraction = ExtractionResult(
            document_id=uuid4(),
            supplier=SupplierInfo(name="Test", country_of_origin="US"),
            product=ProductInfo(name="Test"),
            location=LocationInfo(country="US"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.5,
            extracted_at=datetime.now(UTC),
            model_used="gpt-4o-mini",
        )

        result = risk_scorer.score(extraction)

        assert isinstance(result, RiskScoreResult)
        assert result.risk_score >= 0
        # Low confidence should trigger evidence quality violation
        assert any(v.rule_name == "low_extraction_confidence" for v in result.violations)

    def test_empty_consistency_result(self, risk_scorer, minimal_extraction_result):
        """Empty ConsistencyReport → no conflicts, no points."""
        consistency = ConsistencyReport(
            case_id=uuid4(),
            field_conflicts=[],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=0,
            confidence_adjustment=0.0,
            summary="No conflicts",
        )

        result_with = risk_scorer.score(minimal_extraction_result, consistency)
        result_without = risk_scorer.score(minimal_extraction_result)

        assert result_with.risk_score == result_without.risk_score

    def test_zero_extraction_confidence(self, risk_scorer, minimal_extraction_result):
        """extraction_confidence = 0.0 → maximum evidence quality risk."""
        minimal_extraction_result.extraction_confidence = 0.0
        result = risk_scorer.score(minimal_extraction_result)

        violations = [v for v in result.violations if v.rule_name == "low_extraction_confidence"]
        assert len(violations) == 1
        assert violations[0].points == 10

    def test_categories_affected_tracking(self, risk_scorer, high_risk_extraction_result):
        """categories_affected list includes all violated categories."""
        result = risk_scorer.score(high_risk_extraction_result)

        # Should have violations in multiple categories
        assert len(result.categories_affected) > 1
        assert isinstance(result.categories_affected, list)
        assert all(isinstance(cat, str) for cat in result.categories_affected)

    def test_deterministic_scoring(self, risk_scorer, high_risk_extraction_result):
        """Same input always produces same output (deterministic)."""
        result1 = risk_scorer.score(high_risk_extraction_result)
        result2 = risk_scorer.score(high_risk_extraction_result)

        assert result1.risk_score == result2.risk_score
        assert result1.risk_level == result2.risk_level
        assert len(result1.violations) == len(result2.violations)


# ============================================================================
# Invalid Input Tests
# ============================================================================


class TestInvalidInputs:
    """Tests for invalid or missing inputs."""

    def test_none_entities_raises_error(self, risk_scorer):
        """None ExtractionResult raises ValueError."""
        with pytest.raises(ValueError, match="ExtractionResult is required"):
            risk_scorer.score(None)  # type: ignore

    def test_rule_violation_creation(self):
        """RuleViolation model validates correctly."""
        violation = RuleViolation(
            rule_name="test_rule",
            category="geolocation",
            points=15,
            reason="Test violation",
            severity="high",
            remediation="Fix it",
            evidence={"key": "value"},
        )

        assert violation.rule_name == "test_rule"
        assert violation.points == 15
        assert violation.severity == "high"

    def test_risk_score_result_serializable(self, risk_scorer, minimal_extraction_result):
        """RiskScoreResult can be serialized to JSON."""
        result = risk_scorer.score(minimal_extraction_result)

        # Should be able to call model_dump without errors
        data = result.model_dump()
        assert "risk_score" in data
        assert "risk_level" in data
        assert "violations" in data

    def test_result_has_calculated_at_timestamp(self, risk_scorer, minimal_extraction_result):
        """RiskScoreResult.calculated_at is set."""
        before = datetime.now(UTC)
        result = risk_scorer.score(minimal_extraction_result)
        after = datetime.now(UTC)

        assert before <= result.calculated_at <= after
