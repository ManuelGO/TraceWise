"""Unit tests for entity extraction service (Task 38).

Tests EntityExtractor service:
- LLM calls and response parsing
- JSON validation
- Pydantic schema validation
- Error handling
- Confidence scoring
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas.extraction import ExtractionResult
from app.services.entity_extractor import EntityExtractionError, EntityExtractor


@pytest.fixture
def mock_llm_service():
    """Create a mock LLMService."""
    mock_service = MagicMock()
    mock_provider = MagicMock()
    mock_provider.get_model_name.return_value = "openai/gpt-4o-mini"
    mock_service.provider = mock_provider
    return mock_service


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock(spec=Settings)
    mock.EXTRACTION_TEMPERATURE = 0.3
    mock.EXTRACTION_MAX_TOKENS = 2000
    mock.EXTRACTION_TIMEOUT = 30
    mock.EXTRACTION_CONTEXT_LENGTH = 3000
    return mock


@pytest.fixture
def extractor(mock_llm_service, mock_settings):
    """Create EntityExtractor instance for testing."""
    return EntityExtractor(mock_llm_service, mock_settings)


class TestEntityExtractorInitialization:
    """Tests for EntityExtractor initialization."""

    def test_init_with_valid_service(self, mock_llm_service, mock_settings):
        """Test creating EntityExtractor with valid LLMService."""
        extractor = EntityExtractor(mock_llm_service, mock_settings)
        assert extractor.llm_service == mock_llm_service
        assert extractor.settings == mock_settings

    def test_init_without_service_raises_error(self, mock_settings):
        """Test that missing LLMService raises ValueError."""
        with pytest.raises(ValueError, match="LLMService is required"):
            EntityExtractor(None, mock_settings)

    def test_init_without_settings_uses_default(self, mock_llm_service):
        """Test that missing settings uses get_settings()."""
        # Mock get_settings to avoid actual config loading in tests
        extractor = EntityExtractor(mock_llm_service)
        assert extractor.llm_service == mock_llm_service
        assert extractor.settings is not None


class TestEntityExtraction:
    """Tests for entity extraction."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self, extractor, mock_llm_service):
        """Test successful entity extraction."""
        # Prepare mock response
        doc_id = uuid4()
        valid_response = {
            "supplier": {
                "name": "Acme Corp",
                "country_of_origin": "CN",
                "registration_number": "12345",
                "business_type": "manufacturer",
                "certification_status": "certified",
                "last_updated": "2026-06-02T10:00:00",
            },
            "product": {
                "name": "Steel Coils",
                "hs_code": "72081100",
                "category": "metals",
                "origin_country": "CN",
                "quantity": 500.0,
                "unit": "kg",
            },
            "location": {
                "country": "CN",
                "region": "Shanghai",
                "risk_profile": "medium-risk",
                "geolocation_verified": False,
            },
            "shipment": {
                "shipment_date": "2026-06-01",
                "arrival_date": "2026-06-15",
                "origin_port": "Shanghai Port",
                "destination_port": "Rotterdam Port",
                "transport_mode": "sea",
                "tracking_number": "BL123456789",
            },
            "extraction_confidence": 0.95,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(valid_response),
                "tokens": {"input": 500, "output": 200, "total": 700},
                "cost": 0.05,
                "model": "openai/gpt-4o-mini",
            }
        )

        # Execute extraction
        result = await extractor.extract_entities(
            document_id=doc_id,
            document_text="Test document content",
            context="Additional context",
        )

        # Verify result
        assert isinstance(result, ExtractionResult)
        assert result.document_id == doc_id
        assert result.supplier.name == "Acme Corp"
        assert result.supplier.country_of_origin == "CN"
        assert result.product.name == "Steel Coils"
        assert result.location.country == "CN"
        assert result.extraction_confidence == 0.95

    @pytest.mark.asyncio
    async def test_empty_optional_fields(self, extractor, mock_llm_service):
        """Test extraction with minimal data (only required fields)."""
        doc_id = uuid4()
        minimal_response = {
            "supplier": {
                "name": "Supplier Inc",
                "country_of_origin": "US",
            },
            "product": {
                "name": "Product A",
            },
            "location": {
                "country": "US",
            },
            "shipment": {},
            "extraction_confidence": 0.7,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(minimal_response),
                "tokens": {"input": 300, "output": 150, "total": 450},
                "cost": 0.03,
                "model": "openai/gpt-4o-mini",
            }
        )

        result = await extractor.extract_entities(
            document_id=doc_id,
            document_text="Minimal document",
        )

        assert result.supplier.name == "Supplier Inc"
        assert result.supplier.registration_number is None
        assert result.product.hs_code is None
        assert result.shipment.shipment_date is None
        assert result.extraction_confidence == 0.7

    @pytest.mark.asyncio
    async def test_invalid_json_from_llm(self, extractor, mock_llm_service):
        """Test handling of invalid JSON from LLM."""
        doc_id = uuid4()
        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": "Not valid JSON {broken",
                "tokens": {"input": 100, "output": 50, "total": 150},
                "cost": 0.01,
                "model": "openai/gpt-4o-mini",
            }
        )

        with pytest.raises(EntityExtractionError, match="LLM returned invalid JSON"):
            await extractor.extract_entities(
                document_id=doc_id,
                document_text="Test document",
            )

    @pytest.mark.asyncio
    async def test_validation_failure_missing_required_field(self, extractor, mock_llm_service):
        """Test Pydantic validation failure when required field missing."""
        doc_id = uuid4()
        invalid_response = {
            "supplier": {
                # Missing required 'name' field
                "country_of_origin": "CN",
            },
            "product": {
                "name": "Product",
            },
            "location": {
                "country": "CN",
            },
            "shipment": {},
            "extraction_confidence": 0.9,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(invalid_response),
                "tokens": {"input": 300, "output": 150, "total": 450},
                "cost": 0.03,
                "model": "openai/gpt-4o-mini",
            }
        )

        with pytest.raises(ValidationError):
            await extractor.extract_entities(
                document_id=doc_id,
                document_text="Test document",
            )

    @pytest.mark.asyncio
    async def test_confidence_score_edge_cases(self, extractor, mock_llm_service):
        """Test extraction with edge case confidence values."""
        doc_id = uuid4()
        # Test with 0.0 confidence
        response_low = {
            "supplier": {"name": "A", "country_of_origin": "US"},
            "product": {"name": "P"},
            "location": {"country": "US"},
            "shipment": {},
            "extraction_confidence": 0.0,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(response_low),
                "tokens": {"input": 200, "output": 100, "total": 300},
                "cost": 0.02,
                "model": "openai/gpt-4o-mini",
            }
        )

        result = await extractor.extract_entities(
            document_id=doc_id,
            document_text="Test",
        )
        assert result.extraction_confidence == 0.0

        # Test with 1.0 confidence
        response_high = {
            "supplier": {"name": "B", "country_of_origin": "UK"},
            "product": {"name": "P2"},
            "location": {"country": "UK"},
            "shipment": {},
            "extraction_confidence": 1.0,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(response_high),
                "tokens": {"input": 200, "output": 100, "total": 300},
                "cost": 0.02,
                "model": "openai/gpt-4o-mini",
            }
        )

        result = await extractor.extract_entities(
            document_id=uuid4(),
            document_text="Test",
        )
        assert result.extraction_confidence == 1.0

    @pytest.mark.asyncio
    async def test_llm_service_error_propagation(self, extractor, mock_llm_service):
        """Test that LLM service errors are properly propagated."""
        from app.services.llm_service import LLMError

        doc_id = uuid4()
        mock_llm_service.provider.generate = AsyncMock(
            side_effect=LLMError("API timeout")
        )

        with pytest.raises(LLMError, match="API timeout"):
            await extractor.extract_entities(
                document_id=doc_id,
                document_text="Test",
            )

    @pytest.mark.asyncio
    async def test_empty_llm_response(self, extractor, mock_llm_service):
        """Test handling of empty LLM response."""
        doc_id = uuid4()
        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": "",  # Empty response
                "tokens": {"input": 100, "output": 0, "total": 100},
                "cost": 0.01,
                "model": "openai/gpt-4o-mini",
            }
        )

        with pytest.raises(EntityExtractionError, match="empty response"):
            await extractor.extract_entities(
                document_id=doc_id,
                document_text="Test",
            )

    @pytest.mark.asyncio
    async def test_context_passed_to_llm(self, extractor, mock_llm_service):
        """Test that context is passed through to LLM prompts."""
        doc_id = uuid4()
        doc_text = "Document content"
        context_text = "Retrieved context"

        response = {
            "supplier": {"name": "A", "country_of_origin": "US"},
            "product": {"name": "P"},
            "location": {"country": "US"},
            "shipment": {},
            "extraction_confidence": 0.8,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(response),
                "tokens": {"input": 400, "output": 150, "total": 550},
                "cost": 0.04,
                "model": "openai/gpt-4o-mini",
            }
        )

        await extractor.extract_entities(
            document_id=doc_id,
            document_text=doc_text,
            context=context_text,
        )

        # Verify LLM was called
        assert mock_llm_service.provider.generate.called
        call_args = mock_llm_service.provider.generate.call_args
        prompt = call_args.kwargs["prompt"]

        # Context should be in the prompt
        assert context_text in prompt
        assert doc_text in prompt

    @pytest.mark.asyncio
    async def test_extracted_at_timestamp(self, extractor, mock_llm_service):
        """Test that extracted_at timestamp is set correctly."""
        doc_id = uuid4()
        before_extraction = datetime.now()

        response = {
            "supplier": {"name": "A", "country_of_origin": "US"},
            "product": {"name": "P"},
            "location": {"country": "US"},
            "shipment": {},
            "extraction_confidence": 0.9,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(response),
                "tokens": {"input": 300, "output": 150, "total": 450},
                "cost": 0.03,
                "model": "openai/gpt-4o-mini",
            }
        )

        result = await extractor.extract_entities(
            document_id=doc_id,
            document_text="Test",
        )

        after_extraction = datetime.now()

        # Timestamp should be between before and after
        assert before_extraction <= result.extracted_at <= after_extraction

    @pytest.mark.asyncio
    async def test_model_used_set_correctly(self, extractor, mock_llm_service):
        """Test that model_used is set from provider."""
        doc_id = uuid4()
        expected_model = "openai/gpt-4o-mini"
        mock_llm_service.provider.get_model_name.return_value = expected_model

        response = {
            "supplier": {"name": "A", "country_of_origin": "US"},
            "product": {"name": "P"},
            "location": {"country": "US"},
            "shipment": {},
            "extraction_confidence": 0.85,
        }

        mock_llm_service.provider.generate = AsyncMock(
            return_value={
                "text": json.dumps(response),
                "tokens": {"input": 300, "output": 150, "total": 450},
                "cost": 0.03,
                "model": expected_model,
            }
        )

        result = await extractor.extract_entities(
            document_id=doc_id,
            document_text="Test",
        )

        assert result.model_used == expected_model
