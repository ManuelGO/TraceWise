"""Entity extraction service for structured information extraction.

This module provides LLM-based extraction of structured entities (supplier, product,
location, shipment information) from documents using Pydantic validation.

The service:
1. Calls LLMService with extraction prompts
2. Parses JSON responses from LLM
3. Validates against Pydantic schemas
4. Tracks extraction confidence
5. Provides clear error messages for validation failures
"""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.config import get_settings
from app.prompts.extraction_prompts import build_extraction_prompt
from app.schemas.extraction import ExtractionResult
from app.services.llm_service import LLMError, LLMService

logger = logging.getLogger(__name__)


class EntityExtractionError(Exception):
    """Raised when entity extraction fails."""

    pass


class EntityExtractor:
    """Service for extracting structured entities from documents using LLM.

    Attributes:
        llm_service: LLMService for making LLM calls
        settings: Application settings for configuration
    """

    def __init__(self, llm_service: LLMService, settings=None):
        """Initialize EntityExtractor with dependencies.

        Args:
            llm_service: LLMService instance for LLM calls
            settings: Application settings (defaults to get_settings())

        Raises:
            ValueError: If LLMService is not provided
        """
        if not llm_service:
            raise ValueError("LLMService is required")

        self.llm_service = llm_service
        self.settings = settings or get_settings()

    async def extract_entities(
        self,
        document_id: UUID,
        document_text: str,
        context: str = "",
    ) -> ExtractionResult:
        """Extract structured entities from document using LLM.

        Calls the LLM with extraction prompts, parses JSON response, and validates
        against Pydantic schemas. Returns ExtractionResult with all entities or
        raises detailed error for debugging by Task 39 (retry logic).

        Args:
            document_id: UUID of the source document
            document_text: Full or summarized document content
            context: Retrieved context from retrieval service (optional)

        Returns:
            ExtractionResult with all extracted entities and confidence score

        Raises:
            LLMError: If LLM API call fails
            EntityExtractionError: If JSON parsing fails
            ValidationError: If extracted data fails Pydantic validation

        Example:
            >>> extractor = EntityExtractor(llm_service, settings)
            >>> result = await extractor.extract_entities(
            ...     document_id=uuid4(),
            ...     document_text="Supplier: Acme Corp...",
            ...     context="Additional context..."
            ... )
            >>> print(f"Supplier: {result.supplier.name}")
            >>> print(f"Confidence: {result.extraction_confidence}")
        """
        logger.info(f"Starting entity extraction for document {document_id}")

        if not document_text or not document_text.strip():
            raise EntityExtractionError("Document text cannot be empty")

        # Build extraction prompts
        system_prompt, user_prompt = build_extraction_prompt(document_text, context)

        # Combine system and user prompts for provider call
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # Call LLM provider directly with extraction prompts
        logger.debug(f"Calling LLM with {len(full_prompt)} character prompt")
        try:
            llm_response = await self.llm_service.provider.generate(
                prompt=full_prompt,
                temperature=self.settings.EXTRACTION_TEMPERATURE,
                max_tokens=self.settings.EXTRACTION_MAX_TOKENS,
            )
        except LLMError as e:
            logger.error(
                f"LLM call failed for document {document_id}: {e!s}"
            )
            raise

        # Extract response text from provider response
        response_text = llm_response.get("text", "")
        if not response_text:
            raise EntityExtractionError("LLM returned empty response")

        logger.debug(f"LLM response length: {len(response_text)} characters")

        # Parse JSON response from LLM
        try:
            extracted_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse JSON from LLM for document {document_id}: {e!s}"
            )
            logger.debug(f"Raw LLM response: {response_text[:500]}")
            raise EntityExtractionError(
                f"LLM returned invalid JSON for document {document_id}: {e!s}"
            ) from e

        # Validate JSON is an object, not array or scalar
        if not isinstance(extracted_data, dict):
            raise EntityExtractionError(
                f"LLM response must be JSON object, got {type(extracted_data).__name__}"
            )

        # Extract confidence score from LLM response (or use default)
        extraction_confidence = extracted_data.pop("extraction_confidence", None) or 0.5
        if extraction_confidence == 0.5:
            logger.warning(
                "LLM did not provide extraction_confidence, using default 0.5"
            )

        # Pop reserved keys to prevent collision with constructor kwargs
        reserved_keys = {"document_id", "extracted_at", "model_used", "extraction_confidence"}
        for key in reserved_keys:
            extracted_data.pop(key, None)

        # Validate extracted data against Pydantic schemas
        try:
            result = ExtractionResult(
                document_id=document_id,
                extracted_at=datetime.now(UTC),
                model_used=llm_response.get("model", "unknown"),
                extraction_confidence=extraction_confidence,
                **extracted_data,
            )
        except ValidationError as e:
            logger.warning(
                f"Pydantic validation failed for document {document_id}: {e!s}"
            )
            logger.debug(f"Extracted data: {json.dumps(extracted_data, default=str)}")
            raise

        logger.info(
            f"Successfully extracted entities for document {document_id} "
            f"with confidence {extraction_confidence:.2f}"
        )
        return result
