"""Extraction retry service with intelligent prompt improvement.

This module provides retry logic for failed extractions, with improved prompts
that include context about what failed and how to fix it.

Retry Strategy:
- Max 3 retries per extraction
- Exponential backoff: 1s, 2s, 4s
- Include original failure information in retry prompt
- Feed specific field failures back to LLM
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.prompts.retry_prompts import build_retry_prompt
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult
from app.services.entity_extractor import EntityExtractionError, EntityExtractor
from app.services.llm_service import LLMError

logger = logging.getLogger(__name__)


class ExtractionRetryError(Exception):
    """Raised when extraction retry fails or max retries exceeded."""

    pass


class ExtractionRetryService:
    """Service for retrying failed extractions with improved prompts.

    Attributes:
        extractor: EntityExtractor for re-extraction
        settings: Application settings for configuration
    """

    def __init__(self, extractor: EntityExtractor, settings: Settings | None = None):
        """Initialize retry service with dependencies.

        Args:
            extractor: EntityExtractor instance for re-extraction
            settings: Application settings (defaults to get_settings())

        Raises:
            ValueError: If extractor is None
        """
        if extractor is None:
            raise ValueError("EntityExtractor is required")
        self.extractor = extractor
        self.settings = settings or get_settings()

    async def retry_extraction(
        self,
        original_result: ExtractionResult,
        validation_result: ValidationResult,
        document_text: str,
        context: str = "",
        retry_count: int = 0,
    ) -> ExtractionResult:
        """Retry extraction with improved prompt based on validation failures.

        Args:
            original_result: The failed extraction result
            validation_result: Validation result explaining what failed
            document_text: Original document text for re-extraction
            context: Retrieval context for extraction
            retry_count: Current retry attempt (0, 1, 2)

        Returns:
            New ExtractionResult from retry

        Raises:
            ExtractionRetryError: If max retries exceeded or extraction fails
        """
        max_retries = self.settings.VALIDATION_MAX_RETRIES
        if retry_count >= max_retries:
            raise ExtractionRetryError(
                f"Max retries ({max_retries}) exceeded for extraction {original_result.document_id}"
            )

        # Apply exponential backoff with hard cap to prevent DoS
        MAX_BACKOFF_CAP_SECONDS = 30.0
        backoff_base = self.settings.RETRY_BACKOFF_BASE
        backoff_multiplier = self.settings.RETRY_BACKOFF_MULTIPLIER
        backoff_delay = min(
            backoff_base * (backoff_multiplier ** retry_count),
            MAX_BACKOFF_CAP_SECONDS,
        )

        logger.info(
            f"Retrying extraction {original_result.document_id} "
            f"(attempt {retry_count + 1}/{max_retries}, wait {backoff_delay}s)"
        )

        # Wait before retry
        await asyncio.sleep(backoff_delay)

        # Build improved prompt with failure information
        retry_prompt = build_retry_prompt(
            original_result, validation_result, document_text, context
        )

        # Re-extract with improved prompt by calling LLM directly
        try:
            llm_response = await self.extractor.llm_service.provider.generate(
                prompt=retry_prompt,
                temperature=self.settings.EXTRACTION_TEMPERATURE,
                max_tokens=self.settings.EXTRACTION_MAX_TOKENS,
            )

            response_text = llm_response.get("text", "")
            if not response_text:
                raise EntityExtractionError("LLM returned empty response on retry")

            # Parse JSON response
            try:
                extracted_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse JSON from retry response: {e!s}"
                )
                raise EntityExtractionError(f"Invalid JSON in retry response: {e!s}") from e

            # Verify parsed JSON is a dict (not array, null, string, etc)
            if not isinstance(extracted_data, dict):
                raise EntityExtractionError(
                    f"LLM response must be a JSON object, got {type(extracted_data).__name__}"
                )

            # Inject required fields that the LLM doesn't provide
            extracted_data["document_id"] = original_result.document_id
            extracted_data["extracted_at"] = datetime.now(UTC)
            extracted_data["model_used"] = original_result.model_used

            # Validate against ExtractionResult schema
            new_result = ExtractionResult(**extracted_data)

            logger.info(
                f"Extraction retry succeeded for {original_result.document_id} "
                f"(confidence: {new_result.extraction_confidence:.2f})"
            )

            return new_result
        except EntityExtractionError as e:
            logger.error(
                f"Extraction retry failed for {original_result.document_id}: {e!s}"
            )
            raise ExtractionRetryError(
                f"Retry extraction failed for document {original_result.document_id}: {e!s}"
            ) from e
        except (ValidationError, LLMError) as e:
            logger.error(
                f"Extraction retry failed with error: {e!s}"
            )
            raise ExtractionRetryError(
                f"Retry extraction failed: {e!s}"
            ) from e
