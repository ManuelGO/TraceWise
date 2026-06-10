"""Unit tests for extraction validation service (Task 39, Increment 2).

Tests ExtractionValidator service:
- Validation rule checks (all 6 rules)
- Validation score computation
- Failure detection and severity levels
- Error handling
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import (
    SeverityLevel,
    ValidationRuleType,
)
from app.services.extraction_validator import ExtractionValidator


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock(spec=Settings)
    return mock


@pytest.fixture
def validator(mock_settings):
    """Create ExtractionValidator instance for testing."""
    return ExtractionValidator(mock_settings)


@pytest.fixture
def valid_extraction_result():
    """Create a valid extraction result for testing."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(
            name="Acme Corp",
            country_of_origin="CN",
            registration_number="123456",
            business_type="manufacturer",
        ),
        product=ProductInfo(
            name="Industrial Widget",
            hs_code="12345678",
            category="machinery",
            origin_country="CN",
            quantity=100.0,
            unit="units",
        ),
        location=LocationInfo(
            country="US",
            region="California",
            risk_profile="low",
            geolocation_verified=True,
        ),
        shipment=ShipmentInfo(
            shipment_date=date(2024, 1, 1),
            arrival_date=date(2024, 2, 1),
            origin_port="Shanghai Port",
            destination_port="Los Angeles Port",
            transport_mode="sea",
            tracking_number="BL123456789",
        ),
        extraction_confidence=0.95,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


class TestExtractionValidatorInitialization:
    """Tests for ExtractionValidator initialization."""

    def test_init_with_settings(self, mock_settings):
        """Test creating validator with settings."""
        validator = ExtractionValidator(mock_settings)
        assert validator.settings == mock_settings

    def test_init_without_settings_uses_default(self):
        """Test that validator can initialize without explicit settings."""
        validator = ExtractionValidator()
        assert validator.settings is not None


class TestValidationCompleteness:
    """Tests for completeness validation rule."""

    @pytest.mark.asyncio
    async def test_all_required_fields_present(self, validator, valid_extraction_result):
        """Test validation passes when all required fields present."""
        result = await validator.validate_extraction(valid_extraction_result)
        completeness_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COMPLETENESS
        ]
        assert len(completeness_failures) == 0

    @pytest.mark.asyncio
    async def test_missing_supplier_name(self, validator, valid_extraction_result):
        """Test validation fails when supplier name missing."""
        valid_extraction_result.supplier.name = ""
        result = await validator.validate_extraction(valid_extraction_result)
        completeness_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COMPLETENESS
            and f.field == "supplier.name"
        ]
        assert len(completeness_failures) == 1
        assert completeness_failures[0].severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_missing_supplier_country(self, validator, valid_extraction_result):
        """Test validation fails when supplier country missing."""
        valid_extraction_result.supplier.country_of_origin = ""
        result = await validator.validate_extraction(valid_extraction_result)
        completeness_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COMPLETENESS
            and f.field == "supplier.country_of_origin"
        ]
        assert len(completeness_failures) == 1
        assert completeness_failures[0].severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_missing_product_name(self, validator, valid_extraction_result):
        """Test validation fails when product name missing."""
        valid_extraction_result.product.name = ""
        result = await validator.validate_extraction(valid_extraction_result)
        completeness_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COMPLETENESS
            and f.field == "product.name"
        ]
        assert len(completeness_failures) == 1
        assert completeness_failures[0].severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_missing_location_country(self, validator, valid_extraction_result):
        """Test validation fails when location country missing."""
        valid_extraction_result.location.country = ""
        result = await validator.validate_extraction(valid_extraction_result)
        completeness_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COMPLETENESS
            and f.field == "location.country"
        ]
        assert len(completeness_failures) == 1
        assert completeness_failures[0].severity == SeverityLevel.CRITICAL


class TestValidationDateLogic:
    """Tests for date logic validation rule."""

    @pytest.mark.asyncio
    async def test_valid_dates_shipment_before_arrival(
        self, validator, valid_extraction_result
    ):
        """Test validation passes when shipment before arrival."""
        valid_extraction_result.shipment.shipment_date = date(2024, 1, 1)
        valid_extraction_result.shipment.arrival_date = date(2024, 2, 1)
        result = await validator.validate_extraction(valid_extraction_result)
        date_failures = [
            f for f in result.failures if f.rule == ValidationRuleType.DATE_LOGIC
        ]
        assert len(date_failures) == 0

    @pytest.mark.asyncio
    async def test_valid_dates_same_day(self, validator, valid_extraction_result):
        """Test validation passes when dates are same day (air freight)."""
        valid_extraction_result.shipment.shipment_date = date(2024, 1, 1)
        valid_extraction_result.shipment.arrival_date = date(2024, 1, 1)
        result = await validator.validate_extraction(valid_extraction_result)
        date_failures = [
            f for f in result.failures if f.rule == ValidationRuleType.DATE_LOGIC
        ]
        assert len(date_failures) == 0

    @pytest.mark.asyncio
    async def test_invalid_dates_arrival_before_shipment(
        self, validator, valid_extraction_result
    ):
        """Test validation fails when arrival before shipment."""
        valid_extraction_result.shipment.shipment_date = date(2024, 2, 1)
        valid_extraction_result.shipment.arrival_date = date(2024, 1, 1)
        result = await validator.validate_extraction(valid_extraction_result)
        date_failures = [
            f for f in result.failures if f.rule == ValidationRuleType.DATE_LOGIC
        ]
        assert len(date_failures) == 1
        assert date_failures[0].severity == SeverityLevel.ERROR

    @pytest.mark.asyncio
    async def test_only_shipment_date_present(self, validator, valid_extraction_result):
        """Test validation passes when only shipment date present."""
        valid_extraction_result.shipment.shipment_date = date(2024, 1, 1)
        valid_extraction_result.shipment.arrival_date = None
        result = await validator.validate_extraction(valid_extraction_result)
        date_failures = [
            f for f in result.failures if f.rule == ValidationRuleType.DATE_LOGIC
        ]
        assert len(date_failures) == 0

    @pytest.mark.asyncio
    async def test_no_dates_present(self, validator, valid_extraction_result):
        """Test validation passes when no dates present."""
        valid_extraction_result.shipment.shipment_date = None
        valid_extraction_result.shipment.arrival_date = None
        result = await validator.validate_extraction(valid_extraction_result)
        date_failures = [
            f for f in result.failures if f.rule == ValidationRuleType.DATE_LOGIC
        ]
        assert len(date_failures) == 0


class TestValidationPortValidation:
    """Tests for port validation rule."""

    @pytest.mark.asyncio
    async def test_valid_port_with_keyword(self, validator, valid_extraction_result):
        """Test validation passes for port with keyword."""
        valid_extraction_result.shipment.origin_port = "Shanghai Port"
        valid_extraction_result.shipment.destination_port = "Los Angeles Port"
        result = await validator.validate_extraction(valid_extraction_result)
        port_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.PORT_VALIDATION
        ]
        assert len(port_failures) == 0

    @pytest.mark.asyncio
    async def test_valid_port_with_city_name(self, validator, valid_extraction_result):
        """Test validation passes for known city/port."""
        valid_extraction_result.shipment.origin_port = "Rotterdam"
        valid_extraction_result.shipment.destination_port = "Singapore"
        result = await validator.validate_extraction(valid_extraction_result)
        port_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.PORT_VALIDATION
        ]
        assert len(port_failures) == 0

    @pytest.mark.asyncio
    async def test_empty_ports_valid(self, validator, valid_extraction_result):
        """Test validation passes when ports empty (optional)."""
        valid_extraction_result.shipment.origin_port = None
        valid_extraction_result.shipment.destination_port = None
        result = await validator.validate_extraction(valid_extraction_result)
        port_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.PORT_VALIDATION
        ]
        assert len(port_failures) == 0

    @pytest.mark.asyncio
    async def test_suspicious_port_name(self, validator, valid_extraction_result):
        """Test validation warns for suspicious port name."""
        valid_extraction_result.shipment.origin_port = "XYZ Location"
        result = await validator.validate_extraction(valid_extraction_result)
        port_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.PORT_VALIDATION
        ]
        assert len(port_failures) == 1
        assert port_failures[0].severity == SeverityLevel.WARNING


class TestValidationCountryCode:
    """Tests for country code validation rule."""

    @pytest.mark.asyncio
    async def test_valid_iso_code_uppercase(self, validator, valid_extraction_result):
        """Test validation passes for valid ISO code."""
        valid_extraction_result.supplier.country_of_origin = "CN"
        valid_extraction_result.location.country = "US"
        result = await validator.validate_extraction(valid_extraction_result)
        country_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COUNTRY_CODE
        ]
        assert len(country_failures) == 0

    @pytest.mark.asyncio
    async def test_invalid_country_code(self, validator, valid_extraction_result):
        """Test validation fails for invalid ISO code."""
        valid_extraction_result.supplier.country_of_origin = "XX"
        result = await validator.validate_extraction(valid_extraction_result)
        country_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.COUNTRY_CODE
            and f.field == "supplier.country_of_origin"
        ]
        assert len(country_failures) == 1
        assert country_failures[0].severity == SeverityLevel.ERROR


class TestValidationHSCodeFormat:
    """Tests for HS code format validation rule."""

    @pytest.mark.asyncio
    async def test_valid_hs_code_8_digits(self, validator, valid_extraction_result):
        """Test validation passes for valid 8-digit HS code."""
        valid_extraction_result.product.hs_code = "12345678"
        result = await validator.validate_extraction(valid_extraction_result)
        hs_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.HS_CODE_FORMAT
        ]
        assert len(hs_failures) == 0

    @pytest.mark.asyncio
    async def test_valid_hs_code_10_digits(self, validator, valid_extraction_result):
        """Test validation passes for valid 10-digit HS code."""
        valid_extraction_result.product.hs_code = "1234567890"
        result = await validator.validate_extraction(valid_extraction_result)
        hs_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.HS_CODE_FORMAT
        ]
        assert len(hs_failures) == 0

    @pytest.mark.asyncio
    async def test_empty_hs_code_valid(self, validator, valid_extraction_result):
        """Test validation passes when HS code empty (optional)."""
        valid_extraction_result.product.hs_code = None
        result = await validator.validate_extraction(valid_extraction_result)
        hs_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.HS_CODE_FORMAT
        ]
        assert len(hs_failures) == 0

    @pytest.mark.asyncio
    async def test_invalid_hs_code_with_dashes(self, validator, valid_extraction_result):
        """Test validation warns for HS code with dashes."""
        valid_extraction_result.product.hs_code = "1234-5678"
        result = await validator.validate_extraction(valid_extraction_result)
        hs_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.HS_CODE_FORMAT
        ]
        assert len(hs_failures) == 0  # Should be normalized to "12345678"


class TestValidationTrackingFormat:
    """Tests for tracking number format validation rule."""

    @pytest.mark.asyncio
    async def test_valid_tracking_number(self, validator, valid_extraction_result):
        """Test validation passes for valid tracking number."""
        valid_extraction_result.shipment.tracking_number = "BL123456789"
        result = await validator.validate_extraction(valid_extraction_result)
        tracking_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.TRACKING_FORMAT
        ]
        assert len(tracking_failures) == 0

    @pytest.mark.asyncio
    async def test_empty_tracking_valid(self, validator, valid_extraction_result):
        """Test validation passes when tracking empty (optional)."""
        valid_extraction_result.shipment.tracking_number = None
        result = await validator.validate_extraction(valid_extraction_result)
        tracking_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.TRACKING_FORMAT
        ]
        assert len(tracking_failures) == 0

    @pytest.mark.asyncio
    async def test_tracking_number_too_short(self, validator, valid_extraction_result):
        """Test validation warns for tracking number too short."""
        valid_extraction_result.shipment.tracking_number = "BL12"
        result = await validator.validate_extraction(valid_extraction_result)
        tracking_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.TRACKING_FORMAT
        ]
        assert len(tracking_failures) == 1
        assert tracking_failures[0].severity == SeverityLevel.INFO

    @pytest.mark.asyncio
    async def test_tracking_number_invalid_chars(self, validator, valid_extraction_result):
        """Test validation warns for tracking with invalid characters."""
        valid_extraction_result.shipment.tracking_number = "BL@#$%^&*()"
        result = await validator.validate_extraction(valid_extraction_result)
        tracking_failures = [
            f
            for f in result.failures
            if f.rule == ValidationRuleType.TRACKING_FORMAT
        ]
        assert len(tracking_failures) == 1


class TestValidationScore:
    """Tests for validation score computation."""

    @pytest.mark.asyncio
    async def test_score_perfect(self, validator, valid_extraction_result):
        """Test score is 100 for no failures."""
        result = await validator.validate_extraction(valid_extraction_result)
        assert result.validation_score == 100.0

    @pytest.mark.asyncio
    async def test_score_with_critical_failure(self, validator, valid_extraction_result):
        """Test score reduced for critical failure."""
        valid_extraction_result.supplier.name = ""
        result = await validator.validate_extraction(valid_extraction_result)
        # Critical = -25
        assert result.validation_score == 75.0

    @pytest.mark.asyncio
    async def test_score_with_error_failure(self, validator, valid_extraction_result):
        """Test score reduced for error failure."""
        valid_extraction_result.shipment.shipment_date = date(2024, 2, 1)
        valid_extraction_result.shipment.arrival_date = date(2024, 1, 1)
        result = await validator.validate_extraction(valid_extraction_result)
        # Error = -15
        assert result.validation_score == 85.0

    @pytest.mark.asyncio
    async def test_score_clamped_at_zero(self, validator, valid_extraction_result):
        """Test score doesn't go below 0."""
        valid_extraction_result.supplier.name = ""
        valid_extraction_result.supplier.country_of_origin = ""
        valid_extraction_result.product.name = ""
        valid_extraction_result.location.country = ""
        result = await validator.validate_extraction(valid_extraction_result)
        # 4 critical failures = -100 points
        assert result.validation_score == 0.0


class TestValidationIsValid:
    """Tests for is_valid determination."""

    @pytest.mark.asyncio
    async def test_is_valid_true_with_non_critical_failures(
        self, validator, valid_extraction_result
    ):
        """Test is_valid true when only non-critical failures present."""
        valid_extraction_result.shipment.shipment_date = date(2024, 2, 1)
        valid_extraction_result.shipment.arrival_date = date(2024, 1, 1)
        result = await validator.validate_extraction(valid_extraction_result)
        assert result.is_valid is True  # No critical failures, only error
        assert len([f for f in result.failures if f.severity == SeverityLevel.CRITICAL]) == 0

    @pytest.mark.asyncio
    async def test_is_valid_false_with_critical_failure(
        self, validator, valid_extraction_result
    ):
        """Test is_valid false when critical failure present."""
        valid_extraction_result.supplier.name = ""
        result = await validator.validate_extraction(valid_extraction_result)
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_is_valid_true_perfect_extraction(
        self, validator, valid_extraction_result
    ):
        """Test is_valid true for perfect extraction."""
        result = await validator.validate_extraction(valid_extraction_result)
        assert result.is_valid is True


class TestValidationMetadata:
    """Tests for validation result metadata."""

    @pytest.mark.asyncio
    async def test_checked_at_timestamp(self, validator, valid_extraction_result):
        """Test that checked_at timestamp is set."""
        result = await validator.validate_extraction(valid_extraction_result)
        assert result.checked_at is not None
        assert isinstance(result.checked_at, datetime)
