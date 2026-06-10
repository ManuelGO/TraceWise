"""Validation orchestrator for the full validation→retry→storage pipeline.

This module orchestrates the complete validation workflow:
1. Validate extraction against business logic rules
2. Retry if validation fails (up to 3 times)
3. Store validated result in database
4. Return ValidatedExtractionResult

Coordinates EntityExtractor, ExtractionValidator, and ExtractionRetryService.
"""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import ExtractedEntity
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import (
    SeverityLevel,
    ValidatedExtractionResult,
    ValidationResult,
)
from app.services.extraction_retry import ExtractionRetryError, ExtractionRetryService
from app.services.extraction_validator import ExtractionValidator

logger = logging.getLogger(__name__)


class ValidationOrchestrationError(Exception):
    """Raised when orchestration fails."""

    pass


class ValidationOrchestrator:
    """Orchestrates the validation→retry→storage pipeline.

    Attributes:
        validator: ExtractionValidator for validation
        retry_service: ExtractionRetryService for retries
        db: Database session for persistence
        settings: Application settings
    """

    def __init__(
        self,
        validator: ExtractionValidator,
        retry_service: ExtractionRetryService,
        db: AsyncSession,
        settings: Settings | None = None,
    ):
        """Initialize orchestrator with dependencies.

        Args:
            validator: ExtractionValidator instance
            retry_service: ExtractionRetryService instance
            db: AsyncSession for database operations
            settings: Application settings (defaults to get_settings())

        Raises:
            ValueError: If any required dependency is None
        """
        if validator is None:
            raise ValueError("ExtractionValidator is required")
        if retry_service is None:
            raise ValueError("ExtractionRetryService is required")
        if db is None:
            raise ValueError("Database session is required")

        self.validator = validator
        self.retry_service = retry_service
        self.db = db
        self.settings = settings or get_settings()

    async def validate_and_retry(
        self,
        extraction_result: ExtractionResult,
        document_extraction_id: UUID,
        document_text: str,
        context: str = "",
    ) -> ValidatedExtractionResult:
        """Orchestrate validation→retry→storage pipeline.

        This is the main entry point for the validation workflow:
        1. Validate the extraction
        2. If invalid and retries remaining: retry with improved prompt
        3. Store result in database
        4. Return ValidatedExtractionResult

        Args:
            extraction_result: ExtractionResult from Task 38
            document_text: Original document text for potential retries
            context: Retrieved context for potential retries

        Returns:
            ValidatedExtractionResult with final validation status

        Raises:
            ValidationOrchestrationError: If orchestration fails
        """
        logger.info(
            f"Starting validation orchestration for extraction {extraction_result.document_id}"
        )

        try:
            return await asyncio.wait_for(
                self._validate_and_retry_internal(
                    extraction_result, document_extraction_id, document_text, context
                ),
                timeout=self.settings.VALIDATION_TIMEOUT,
            )
        except TimeoutError:
            logger.error(
                f"Validation pipeline exceeded timeout ({self.settings.VALIDATION_TIMEOUT}s) "
                f"for extraction {extraction_result.document_id}"
            )
            raise ValidationOrchestrationError(
                f"Validation pipeline timed out after {self.settings.VALIDATION_TIMEOUT} seconds"
            )

    async def _validate_and_retry_internal(
        self,
        extraction_result: ExtractionResult,
        document_extraction_id: UUID,
        document_text: str,
        context: str,
    ) -> ValidatedExtractionResult:
        """Internal validation and retry logic with timeout protection."""
        retry_count = 0
        current_result = extraction_result
        validation_result = None

        # Validation→Retry loop (initial validation + up to VALIDATION_MAX_RETRIES retries)
        while retry_count < self.settings.VALIDATION_MAX_RETRIES:
            # Validate current extraction
            logger.debug(
                f"Validating extraction (attempt {retry_count + 1}/"
                f"{self.settings.VALIDATION_MAX_RETRIES + 1})"
            )
            validation_result = await self.validator.validate_extraction(current_result)

            # Check if valid
            if validation_result.is_valid:
                logger.info(
                    f"Extraction passed validation on attempt {retry_count + 1}"
                )
                break

            # Retry with improved prompt
            logger.info(
                f"Retrying extraction (attempt {retry_count + 1} → {retry_count + 2})"
            )
            try:
                current_result = await self.retry_service.retry_extraction(
                    original_result=current_result,
                    validation_result=validation_result,
                    document_text=document_text,
                    context=context,
                    retry_count=retry_count,
                )
                retry_count += 1
            except ExtractionRetryError as e:
                logger.error(f"Retry failed: {e!s}")
                # Don't retry anymore, exit loop
                break

        # Determine final validation status
        validation_status = self._determine_validation_status(
            validation_result, retry_count
        )

        # Build ValidatedExtractionResult
        validated_result = ValidatedExtractionResult(
            extraction_id=current_result.document_id,
            entity_type="result",
            validation=validation_result,
            retry_count=retry_count,
            validated_at=datetime.now(UTC),
        )

        # Store in database
        try:
            await self._store_validated_result(
                current_result, validation_result, validation_status, retry_count,
                document_extraction_id,
            )
            logger.info(
                f"Stored validated extraction for {extraction_result.document_id} "
                f"(status: {validation_status}, score: {validation_result.validation_score:.1f})"
            )
        except Exception as e:
            logger.error(f"Failed to store validated result: {e!s}")
            raise ValidationOrchestrationError(
                f"Failed to store validated result: {e!s}"
            ) from e

        return validated_result

    async def _store_validated_result(
        self,
        extraction_result: ExtractionResult,
        validation_result: ValidationResult,
        validation_status: str,
        retry_count: int,
        document_extraction_id: UUID,
    ) -> None:
        """Store validated extraction in database.

        Args:
            extraction_result: The extraction result to store
            validation_result: The validation result with failures
            validation_status: Final validation status
            retry_count: Number of retries performed

        Raises:
            Exception: If database operation fails
        """
        # Convert validation failures to JSON-serializable format
        failures_json = None
        if validation_result.failures:
            failures_json = [
                {
                    "rule": str(f.rule),
                    "field": f.field,
                    "message": f.message,
                    "severity": str(f.severity),
                }
                for f in validation_result.failures
            ]

        # Create ExtractedEntity record
        entity = ExtractedEntity(
            document_extraction_id=document_extraction_id,
            entity_type="result",
            entity_data=extraction_result.model_dump(mode="json"),
            extraction_confidence=extraction_result.extraction_confidence,
            model_used=extraction_result.model_used,
            validation_status=validation_status,
            validation_score=validation_result.validation_score,
            validation_failures=failures_json,
            retry_count=retry_count,
            last_retry_at=datetime.now(UTC) if retry_count > 0 else None,
        )

        self.db.add(entity)
        await self.db.flush()  # Flush to get the ID, but don't commit yet

    def _determine_validation_status(
        self, validation_result: ValidationResult, retry_count: int
    ) -> str:
        """Determine final validation status based on validation result and retries.

        Status logic:
        - If is_valid and no critical failures: "valid"
        - If not is_valid and retries exhausted: "failed"
        - If is_valid but has high failures: "needs_improvement"
        - Otherwise: "invalid"

        Args:
            validation_result: The validation result
            retry_count: Number of retries performed

        Returns:
            Validation status string
        """
        if validation_result.is_valid:
            # Check if there are any high-severity failures despite being valid
            high_failures = [
                f
                for f in validation_result.failures
                if f.severity in [SeverityLevel.ERROR, SeverityLevel.CRITICAL]
            ]
            if high_failures and not self.settings.VALIDATION_STRICT_MODE:
                return "needs_improvement"
            return "valid"

        # Not valid
        if retry_count >= self.settings.VALIDATION_MAX_RETRIES:
            return "failed"

        return "invalid"
