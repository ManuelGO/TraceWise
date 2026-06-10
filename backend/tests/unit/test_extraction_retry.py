"""Unit tests for extraction retry service (Task 39, Increment 3).

Tests ExtractionRetryService:
- Retry mechanism with improved prompts
- Exponential backoff
- Max retries enforcement
- Error handling
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
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
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)
from app.services.entity_extractor import EntityExtractor
from app.services.extraction_retry import ExtractionRetryError, ExtractionRetryService


@pytest.fixture
def mock_llm_service():
    """Create a mock LLMService."""
    mock_service = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock()
    mock_service.provider = mock_provider
    return mock_service


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock(spec=Settings)
    mock.EXTRACTION_TEMPERATURE = 0.3
    mock.EXTRACTION_MAX_TOKENS = 2000
    mock.VALIDATION_MAX_RETRIES = 3
    mock.RETRY_BACKOFF_BASE = 0.1  # Use short delay for testing
    mock.RETRY_BACKOFF_MULTIPLIER = 2.0
    return mock


@pytest.fixture
def mock_extractor(mock_llm_service, mock_settings):
    """Create mock EntityExtractor."""
    extractor = MagicMock(spec=EntityExtractor)
    extractor.llm_service = mock_llm_service
    extractor.settings = mock_settings
    return extractor


@pytest.fixture
def retry_service(mock_extractor, mock_settings):
    """Create ExtractionRetryService instance for testing."""
    return ExtractionRetryService(mock_extractor, mock_settings)


@pytest.fixture
def valid_extraction_result():
    """Create a valid extraction result for testing."""
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
def validation_result_with_failures():
    """Create a validation result with failures."""
    return ValidationResult(
        is_valid=False,
        failures=[
            ValidationFailure(
                rule=ValidationRuleType.COMPLETENESS,
                field="supplier.country_of_origin",
                message="Required field missing",
                severity=SeverityLevel.CRITICAL,
            ),
            ValidationFailure(
                rule=ValidationRuleType.DATE_LOGIC,
                field="shipment/arrival_dates",
                message="Arrival date before shipment date",
                severity=SeverityLevel.ERROR,
            ),
        ],
        validation_score=50.0,
        checked_at=datetime.now(UTC),
    )


class TestExtractionRetryServiceInitialization:
    """Tests for ExtractionRetryService initialization."""

    def test_init_with_valid_extractor(self, mock_extractor, mock_settings):
        """Test creating service with valid extractor."""
        service = ExtractionRetryService(mock_extractor, mock_settings)
        assert service.extractor == mock_extractor
        assert service.settings == mock_settings

    def test_init_without_extractor_raises_error(self, mock_settings):
        """Test that missing extractor raises ValueError."""
        with pytest.raises(ValueError, match="EntityExtractor is required"):
            ExtractionRetryService(None, mock_settings)

    def test_init_without_settings_uses_default(self, mock_extractor):
        """Test that missing settings uses get_settings()."""
        service = ExtractionRetryService(mock_extractor)
        assert service.extractor == mock_extractor
        assert service.settings is not None


class TestRetryExecution:
    """Tests for retry execution."""

    @pytest.mark.asyncio
    async def test_retry_extraction_first_attempt(
        self,
        retry_service,
        mock_extractor,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test retry on first attempt (retry_count=0)."""
        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
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
            extraction_confidence=0.98,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_llm_service.provider.generate.return_value = {
            "text": improved_result.model_dump_json()
        }

        result = await retry_service.retry_extraction(
            original_result=valid_extraction_result,
            validation_result=validation_result_with_failures,
            document_text="Test document",
            context="Test context",
            retry_count=0,
        )

        assert result.extraction_confidence == 0.98
        assert result.document_id == valid_extraction_result.document_id
        mock_llm_service.provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded(
        self,
        retry_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that max retries raises error."""
        with pytest.raises(ExtractionRetryError, match=r"Max retries .* exceeded"):
            await retry_service.retry_extraction(
                original_result=valid_extraction_result,
                validation_result=validation_result_with_failures,
                document_text="Test document",
                retry_count=3,  # Already at max
            )

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test exponential backoff delays."""
        import time

        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
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
            extraction_confidence=0.98,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_llm_service.provider.generate.return_value = {
            "text": improved_result.model_dump_json()
        }

        # Test retry_count=1: backoff = 0.1 * 2^1 = 0.2s
        start = time.time()
        await retry_service.retry_extraction(
            original_result=valid_extraction_result,
            validation_result=validation_result_with_failures,
            document_text="Test document",
            retry_count=1,
        )
        elapsed = time.time() - start
        assert elapsed >= 0.15  # Allow some variance

    @pytest.mark.asyncio
    async def test_retry_llm_error_raises_extraction_error(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that LLM errors are wrapped in ExtractionRetryError."""
        from app.services.llm_service import LLMError

        mock_llm_service.provider.generate.side_effect = LLMError("LLM call failed")

        with pytest.raises(ExtractionRetryError, match="Retry extraction failed"):
            await retry_service.retry_extraction(
                original_result=valid_extraction_result,
                validation_result=validation_result_with_failures,
                document_text="Test document",
                retry_count=0,
            )

    @pytest.mark.asyncio
    async def test_retry_invalid_json_raises_error(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that invalid JSON response raises ExtractionRetryError."""
        mock_llm_service.provider.generate.return_value = {
            "text": "not valid json"
        }

        with pytest.raises(ExtractionRetryError, match="Retry extraction failed"):
            await retry_service.retry_extraction(
                original_result=valid_extraction_result,
                validation_result=validation_result_with_failures,
                document_text="Test document",
                retry_count=0,
            )

    @pytest.mark.asyncio
    async def test_retry_empty_response_raises_error(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that empty LLM response raises error."""
        mock_llm_service.provider.generate.return_value = {"text": ""}

        with pytest.raises(ExtractionRetryError, match="Retry extraction failed"):
            await retry_service.retry_extraction(
                original_result=valid_extraction_result,
                validation_result=validation_result_with_failures,
                document_text="Test document",
                retry_count=0,
            )


class TestRetryPromptGeneration:
    """Tests for retry prompt generation."""

    @pytest.mark.asyncio
    async def test_retry_prompt_includes_failures(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that retry prompt includes failure information."""
        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
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
            extraction_confidence=0.98,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_llm_service.provider.generate.return_value = {
            "text": improved_result.model_dump_json()
        }

        await retry_service.retry_extraction(
            original_result=valid_extraction_result,
            validation_result=validation_result_with_failures,
            document_text="Test document",
            retry_count=0,
        )

        # Get the call arguments
        call_args = mock_llm_service.provider.generate.call_args
        prompt = call_args[1]["prompt"]

        # Check that failure information is in the prompt
        assert "validation_result_with_failures" in str(validation_result_with_failures) or "failures" in prompt or "CRITICAL" in prompt


class TestRetryReturnValues:
    """Tests for retry return values."""

    @pytest.mark.asyncio
    async def test_retry_returns_new_extraction_result(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that retry returns ExtractionResult."""
        improved_result = ExtractionResult(
            document_id=valid_extraction_result.document_id,
            supplier=SupplierInfo(
                name="Better Acme Corp",
                country_of_origin="US",
            ),
            product=ProductInfo(
                name="Better Widget",
            ),
            location=LocationInfo(
                country="CN",
            ),
            shipment=ShipmentInfo(),
            extraction_confidence=0.99,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_llm_service.provider.generate.return_value = {
            "text": improved_result.model_dump_json()
        }

        result = await retry_service.retry_extraction(
            original_result=valid_extraction_result,
            validation_result=validation_result_with_failures,
            document_text="Test document",
            retry_count=0,
        )

        assert isinstance(result, ExtractionResult)
        assert result.supplier.name == "Better Acme Corp"
        assert result.extraction_confidence == 0.99

    @pytest.mark.asyncio
    async def test_retry_preserves_document_id(
        self,
        retry_service,
        mock_llm_service,
        valid_extraction_result,
        validation_result_with_failures,
    ):
        """Test that retry preserves original document_id."""
        original_doc_id = valid_extraction_result.document_id

        improved_result = ExtractionResult(
            document_id=original_doc_id,
            supplier=SupplierInfo(
                name="Acme Corp",
                country_of_origin="CN",
            ),
            product=ProductInfo(
                name="Widget",
            ),
            location=LocationInfo(
                country="US",
            ),
            shipment=ShipmentInfo(),
            extraction_confidence=0.98,
            extracted_at=datetime.now(UTC),
            model_used="openai/gpt-4o-mini",
        )

        mock_llm_service.provider.generate.return_value = {
            "text": improved_result.model_dump_json()
        }

        result = await retry_service.retry_extraction(
            original_result=valid_extraction_result,
            validation_result=validation_result_with_failures,
            document_text="Test document",
            retry_count=0,
        )

        assert result.document_id == original_doc_id
