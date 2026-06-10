"""Unit tests for validation orchestrator (Task 39, Increment 4).

Tests ValidationOrchestrator:
- Full validation→retry→storage pipeline
- Status determination logic
- Database persistence
- Error handling
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.models import ExtractedEntity
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import (
    SeverityLevel,
    ValidatedExtractionResult,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)
from app.services.extraction_retry import ExtractionRetryService
from app.services.extraction_validator import ExtractionValidator
from app.services.validation_orchestrator import (
    ValidationOrchestrationError,
    ValidationOrchestrator,
)


@pytest.fixture
def mock_validator():
    """Create mock ExtractionValidator."""
    validator = MagicMock(spec=ExtractionValidator)
    validator.validate_extraction = AsyncMock()
    return validator


@pytest.fixture
def mock_retry_service():
    """Create mock ExtractionRetryService."""
    retry_service = MagicMock(spec=ExtractionRetryService)
    retry_service.retry_extraction = AsyncMock()
    return retry_service


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock(spec=Settings)
    mock.VALIDATION_MAX_RETRIES = 3
    mock.VALIDATION_TIMEOUT = 60
    mock.VALIDATION_SCORE_THRESHOLD = 0.7
    mock.VALIDATION_STRICT_MODE = False
    mock.EXTRACTION_TEMPERATURE = 0.3
    mock.EXTRACTION_MAX_TOKENS = 2000
    return mock


@pytest.fixture
def orchestrator(mock_validator, mock_retry_service, mock_db, mock_settings):
    """Create ValidationOrchestrator instance for testing."""
    return ValidationOrchestrator(
        mock_validator, mock_retry_service, mock_db, mock_settings
    )


@pytest.fixture
def valid_extraction_result():
    """Create a valid extraction result."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(
            name="Acme Corp",
            country_of_origin="CN",
        ),
        product=ProductInfo(
            name="Industrial Widget",
        ),
        location=LocationInfo(
            country="US",
        ),
        shipment=ShipmentInfo(),
        extraction_confidence=0.95,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


@pytest.fixture
def valid_validation_result():
    """Create a valid validation result."""
    return ValidationResult(
        is_valid=True,
        failures=[],
        validation_score=100.0,
        checked_at=datetime.now(UTC),
    )


@pytest.fixture
def invalid_validation_result():
    """Create an invalid validation result."""
    return ValidationResult(
        is_valid=False,
        failures=[
            ValidationFailure(
                rule=ValidationRuleType.COMPLETENESS,
                field="supplier.country_of_origin",
                message="Required field missing",
                severity=SeverityLevel.CRITICAL,
            ),
        ],
        validation_score=75.0,
        checked_at=datetime.now(UTC),
    )


class TestValidationOrchestratorInitialization:
    """Tests for ValidationOrchestrator initialization."""

    def test_init_with_valid_dependencies(
        self, mock_validator, mock_retry_service, mock_db, mock_settings
    ):
        """Test creating orchestrator with valid dependencies."""
        orchestrator = ValidationOrchestrator(
            mock_validator, mock_retry_service, mock_db, mock_settings
        )
        assert orchestrator.validator == mock_validator
        assert orchestrator.retry_service == mock_retry_service
        assert orchestrator.db == mock_db
        assert orchestrator.settings == mock_settings

    def test_init_without_validator_raises_error(
        self, mock_retry_service, mock_db, mock_settings
    ):
        """Test that missing validator raises ValueError."""
        with pytest.raises(ValueError, match="ExtractionValidator is required"):
            ValidationOrchestrator(None, mock_retry_service, mock_db, mock_settings)

    def test_init_without_retry_service_raises_error(
        self, mock_validator, mock_db, mock_settings
    ):
        """Test that missing retry service raises ValueError."""
        with pytest.raises(ValueError, match="ExtractionRetryService is required"):
            ValidationOrchestrator(mock_validator, None, mock_db, mock_settings)

    def test_init_without_db_raises_error(
        self, mock_validator, mock_retry_service, mock_settings
    ):
        """Test that missing database raises ValueError."""
        with pytest.raises(ValueError, match="Database session is required"):
            ValidationOrchestrator(mock_validator, mock_retry_service, None, mock_settings)

    def test_init_without_settings_uses_default(
        self, mock_validator, mock_retry_service, mock_db
    ):
        """Test that missing settings uses get_settings()."""
        orchestrator = ValidationOrchestrator(
            mock_validator, mock_retry_service, mock_db
        )
        assert orchestrator.settings is not None


class TestValidationAndRetryPipeline:
    """Tests for the full validation→retry→storage pipeline."""

    @pytest.mark.asyncio
    async def test_valid_extraction_no_retry(
        self,
        orchestrator,
        mock_validator,
        mock_db,
        valid_extraction_result,
        valid_validation_result,
    ):
        """Test pipeline with valid extraction (no retry needed)."""
        mock_validator.validate_extraction.return_value = valid_validation_result

        result = await orchestrator.validate_and_retry(
            valid_extraction_result, "test doc", "test context"
        )

        assert isinstance(result, ValidatedExtractionResult)
        assert result.validation.is_valid is True
        assert result.retry_count == 0
        mock_validator.validate_extraction.assert_called_once()
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_extraction_successful_retry(
        self,
        orchestrator,
        mock_validator,
        mock_retry_service,
        mock_db,
        valid_extraction_result,
        invalid_validation_result,
        valid_validation_result,
    ):
        """Test pipeline where retry succeeds."""
        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
            supplier=SupplierInfo(name="Acme Corp", country_of_origin="CN"),
            product=ProductInfo(name="Widget"),
            location=LocationInfo(country="US"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.98,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_validator.validate_extraction.side_effect = [
            invalid_validation_result,  # First validation fails
            valid_validation_result,  # After retry, passes
        ]
        mock_retry_service.retry_extraction.return_value = improved_result

        result = await orchestrator.validate_and_retry(
            valid_extraction_result, "test doc", "test context"
        )

        assert isinstance(result, ValidatedExtractionResult)
        assert result.retry_count == 1
        mock_retry_service.retry_extraction.assert_called_once()
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_extraction_max_retries_exceeded(
        self,
        orchestrator,
        mock_validator,
        mock_retry_service,
        mock_db,
        valid_extraction_result,
        invalid_validation_result,
    ):
        """Test pipeline where max retries are exceeded."""
        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
            supplier=SupplierInfo(name="Acme Corp", country_of_origin="CN"),
            product=ProductInfo(name="Widget"),
            location=LocationInfo(country="US"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.90,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_validator.validate_extraction.return_value = invalid_validation_result
        mock_retry_service.retry_extraction.return_value = improved_result

        result = await orchestrator.validate_and_retry(
            valid_extraction_result, "test doc", "test context"
        )

        assert isinstance(result, ValidatedExtractionResult)
        assert result.retry_count == 3  # Max retries
        # Validator called: initial + after each retry
        assert mock_validator.validate_extraction.call_count >= 2


class TestValidationStatusDetermination:
    """Tests for validation status determination logic."""

    def test_status_valid_no_failures(self, orchestrator, valid_validation_result):
        """Test status is 'valid' when no failures."""
        status = orchestrator._determine_validation_status(valid_validation_result, 0)
        assert status == "valid"

    def test_status_valid_with_info_failures(self, orchestrator):
        """Test status is 'valid' when only info failures."""
        result = ValidationResult(
            is_valid=True,
            failures=[
                ValidationFailure(
                    rule=ValidationRuleType.TRACKING_FORMAT,
                    field="shipment.tracking_number",
                    message="Tracking number too long",
                    severity=SeverityLevel.INFO,
                ),
            ],
            validation_score=95.0,
            checked_at=datetime.now(UTC),
        )
        status = orchestrator._determine_validation_status(result, 0)
        assert status == "valid"

    def test_status_needs_improvement_with_error_failures(self, orchestrator):
        """Test status is 'needs_improvement' when error failures present."""
        result = ValidationResult(
            is_valid=True,
            failures=[
                ValidationFailure(
                    rule=ValidationRuleType.DATE_LOGIC,
                    field="shipment/arrival_dates",
                    message="Date logic issue",
                    severity=SeverityLevel.ERROR,
                ),
            ],
            validation_score=85.0,
            checked_at=datetime.now(UTC),
        )
        status = orchestrator._determine_validation_status(result, 0)
        assert status == "needs_improvement"

    def test_status_invalid_not_valid(self, orchestrator, invalid_validation_result):
        """Test status is 'invalid' when not valid and retries available."""
        status = orchestrator._determine_validation_status(invalid_validation_result, 0)
        assert status == "invalid"

    def test_status_failed_max_retries_exceeded(self, orchestrator, invalid_validation_result):
        """Test status is 'failed' when max retries exceeded."""
        status = orchestrator._determine_validation_status(invalid_validation_result, 3)
        assert status == "failed"

    def test_status_strict_mode(self, orchestrator):
        """Test status in strict mode (only 'valid' acceptable)."""
        orchestrator.settings.VALIDATION_STRICT_MODE = True
        result = ValidationResult(
            is_valid=True,
            failures=[
                ValidationFailure(
                    rule=ValidationRuleType.DATE_LOGIC,
                    field="shipment/arrival_dates",
                    message="Date logic issue",
                    severity=SeverityLevel.ERROR,
                ),
            ],
            validation_score=85.0,
            checked_at=datetime.now(UTC),
        )
        status = orchestrator._determine_validation_status(result, 0)
        assert status == "valid"  # Strict mode ignores error failures


class TestDatabasePersistence:
    """Tests for database persistence."""

    @pytest.mark.asyncio
    async def test_store_validated_result_creates_entity(
        self, orchestrator, mock_db, valid_extraction_result, valid_validation_result
    ):
        """Test that validated result is stored in database."""
        doc_extraction_id = uuid4()
        await orchestrator._store_validated_result(
            valid_extraction_result, valid_validation_result, "valid", 0,
            doc_extraction_id,
        )

        mock_db.add.assert_called_once()
        added_entity = mock_db.add.call_args[0][0]
        assert isinstance(added_entity, ExtractedEntity)
        assert added_entity.validation_status == "valid"
        assert added_entity.validation_score == 100.0
        assert added_entity.retry_count == 0

    @pytest.mark.asyncio
    async def test_store_validated_result_with_failures(
        self, orchestrator, mock_db, valid_extraction_result, invalid_validation_result
    ):
        """Test that validation failures are stored."""
        doc_extraction_id = uuid4()
        await orchestrator._store_validated_result(
            valid_extraction_result, invalid_validation_result, "failed", 3,
            doc_extraction_id,
        )

        added_entity = mock_db.add.call_args[0][0]
        assert added_entity.validation_failures is not None
        assert len(added_entity.validation_failures) == 1
        assert added_entity.validation_failures[0]["rule"] == "completeness"


class TestErrorHandling:
    """Tests for error handling."""

    def test_init_without_validator_raises_error(self, mock_retry_service, mock_db):
        """Test that missing validator raises ValueError."""
        with pytest.raises(ValueError, match="ExtractionValidator is required"):
            ValidationOrchestrator(None, mock_retry_service, mock_db)

    @pytest.mark.asyncio
    async def test_database_error_raises_orchestration_error(
        self,
        orchestrator,
        mock_validator,
        mock_db,
        valid_extraction_result,
        valid_validation_result,
    ):
        """Test that database errors are wrapped in ValidationOrchestrationError."""
        mock_validator.validate_extraction.return_value = valid_validation_result
        mock_db.flush = AsyncMock(side_effect=Exception("DB Error"))

        with pytest.raises(ValidationOrchestrationError, match="Failed to store"):
            await orchestrator.validate_and_retry(
                valid_extraction_result, "test doc", "test context"
            )


class TestValidatedExtractionResult:
    """Tests for ValidatedExtractionResult construction."""

    @pytest.mark.asyncio
    async def test_result_has_correct_structure(
        self,
        orchestrator,
        mock_validator,
        mock_db,
        valid_extraction_result,
        valid_validation_result,
    ):
        """Test that returned result has correct structure."""
        mock_validator.validate_extraction.return_value = valid_validation_result

        result = await orchestrator.validate_and_retry(
            valid_extraction_result, "test doc", "test context"
        )

        assert isinstance(result, ValidatedExtractionResult)
        assert result.extraction_id == valid_extraction_result.document_id
        assert result.entity_type == "result"
        assert result.validation == valid_validation_result
        assert result.retry_count == 0
        assert isinstance(result.validated_at, datetime)
