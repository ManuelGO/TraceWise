"""Extraction validation service for quality checks on extracted entities.

This module validates extracted entities against business logic rules and computes
validation scores. It provides detailed failure information for debugging and retry.

Validation Rules:
1. Completeness: All required fields present
2. Date Logic: Shipment date <= arrival date
3. Port Validation: Port names are reasonable
4. Country Code: Valid ISO codes or country names
5. HS Code Format: 8-10 digits if present
6. Tracking Format: 5-50 alphanumeric chars if present
"""

import logging
from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import (
    SeverityLevel,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
    is_valid_country_code,
    is_valid_hs_code,
)

logger = logging.getLogger(__name__)


class ExtractionValidator:
    """Service for validating extracted entities against business rules.

    Attributes:
        settings: Application settings for configuration
    """

    def __init__(self, settings: Settings | None = None):
        """Initialize validator with optional settings.

        Args:
            settings: Application settings (defaults to get_settings())
        """
        self.settings = settings or get_settings()

    async def validate_extraction(self, result: ExtractionResult) -> ValidationResult:
        """Validate extraction against all rules.

        Args:
            result: ExtractionResult to validate

        Returns:
            ValidationResult with failures list and computed score
        """
        failures: list[ValidationFailure] = []

        # Run all validation rule checks
        failures.extend(self._check_completeness(result))
        failures.extend(self._check_date_logic(result))
        failures.extend(self._check_port_validation(result))
        failures.extend(self._check_country_codes(result))
        failures.extend(self._check_hs_code_format(result))
        failures.extend(self._check_tracking_format(result))

        # Compute validation score
        validation_score = self._compute_validation_score(failures)

        # Determine if valid (no critical failures)
        critical_failures = [f for f in failures if f.severity == SeverityLevel.CRITICAL]
        is_valid = len(critical_failures) == 0

        result_obj = ValidationResult(
            is_valid=is_valid,
            failures=failures,
            validation_score=validation_score,
            checked_at=datetime.now(UTC),
        )

        # Log validation result
        if is_valid:
            logger.info(
                f"Extraction {result.document_id} passed validation (score: {validation_score:.1f})"
            )
        else:
            logger.warning(
                f"Extraction {result.document_id} failed validation (score: {validation_score:.1f}): "
                f"{len(critical_failures)} critical, {len([f for f in failures if f.severity == SeverityLevel.ERROR])} errors"
            )

        return result_obj

    def _check_completeness(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check that all required fields are present.

        Required fields:
        - supplier.name
        - supplier.country_of_origin
        - product.name
        - location.country

        Returns:
            List of ValidationFailure objects (empty if all fields present)
        """
        failures: list[ValidationFailure] = []

        # Check supplier.name
        if not result.supplier.name or not result.supplier.name.strip():
            failures.append(
                ValidationFailure(
                    rule=ValidationRuleType.COMPLETENESS,
                    field="supplier.name",
                    message="Required field missing: supplier name",
                    severity=SeverityLevel.CRITICAL,
                )
            )

        # Check supplier.country_of_origin
        if (
            not result.supplier.country_of_origin
            or not result.supplier.country_of_origin.strip()
        ):
            failures.append(
                ValidationFailure(
                    rule=ValidationRuleType.COMPLETENESS,
                    field="supplier.country_of_origin",
                    message="Required field missing: supplier country of origin",
                    severity=SeverityLevel.CRITICAL,
                )
            )

        # Check product.name
        if not result.product.name or not result.product.name.strip():
            failures.append(
                ValidationFailure(
                    rule=ValidationRuleType.COMPLETENESS,
                    field="product.name",
                    message="Required field missing: product name",
                    severity=SeverityLevel.CRITICAL,
                )
            )

        # Check location.country
        if not result.location.country or not result.location.country.strip():
            failures.append(
                ValidationFailure(
                    rule=ValidationRuleType.COMPLETENESS,
                    field="location.country",
                    message="Required field missing: location country",
                    severity=SeverityLevel.CRITICAL,
                )
            )

        return failures

    def _check_date_logic(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check that shipment_date <= arrival_date if both present.

        Returns:
            List of ValidationFailure objects (empty if dates are valid)
        """
        failures: list[ValidationFailure] = []

        shipment_date = result.shipment.shipment_date
        arrival_date = result.shipment.arrival_date

        # Only check if both dates are present
        if shipment_date and arrival_date:
            if shipment_date > arrival_date:
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.DATE_LOGIC,
                        field="shipment/arrival_dates",
                        message=f"Arrival date ({arrival_date}) is before shipment date ({shipment_date})",
                        severity=SeverityLevel.ERROR,
                    )
                )

        return failures

    def _check_port_validation(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check that port names are reasonable.

        Port validation checks:
        - Port names contain recognized keywords (port, terminal, dock, harbor, wharf, piers)
        - Or port names are recognizable city names
        - Empty values are allowed

        Returns:
            List of ValidationFailure objects
        """
        failures: list[ValidationFailure] = []

        port_keywords = {
            "port",
            "terminal",
            "dock",
            "harbor",
            "wharf",
            "piers",
            "anchorage",
        }
        common_ports = {
            "singapore",
            "rotterdam",
            "shanghai",
            "hong kong",
            "dubai",
            "hamburg",
            "los angeles",
            "singapore port",
            "port of rotterdam",
        }

        # Check origin port
        if result.shipment.origin_port:
            port_lower = result.shipment.origin_port.lower()
            has_keyword = any(kw in port_lower for kw in port_keywords)
            has_common = any(cp in port_lower for cp in common_ports)

            if not has_keyword and not has_common and len(port_lower.strip()) > 0:
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.PORT_VALIDATION,
                        field="shipment.origin_port",
                        message=f"Origin port name is suspicious: {result.shipment.origin_port[:100]!r}",
                        severity=SeverityLevel.WARNING,
                    )
                )

        # Check destination port
        if result.shipment.destination_port:
            port_lower = result.shipment.destination_port.lower()
            has_keyword = any(kw in port_lower for kw in port_keywords)
            has_common = any(cp in port_lower for cp in common_ports)

            if not has_keyword and not has_common and len(port_lower.strip()) > 0:
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.PORT_VALIDATION,
                        field="shipment.destination_port",
                        message=f"Destination port name is suspicious: {result.shipment.destination_port[:100]!r}",
                        severity=SeverityLevel.WARNING,
                    )
                )

        return failures

    def _check_country_codes(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check that country codes are valid ISO or country names.

        Returns:
            List of ValidationFailure objects
        """
        failures: list[ValidationFailure] = []

        # Check supplier country
        if result.supplier.country_of_origin:
            if not is_valid_country_code(result.supplier.country_of_origin):
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.COUNTRY_CODE,
                        field="supplier.country_of_origin",
                        message=f"Invalid country code: {result.supplier.country_of_origin[:50]!r}",
                        severity=SeverityLevel.ERROR,
                    )
                )

        # Check location country
        if result.location.country:
            if not is_valid_country_code(result.location.country):
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.COUNTRY_CODE,
                        field="location.country",
                        message=f"Invalid country code: {result.location.country[:50]!r}",
                        severity=SeverityLevel.ERROR,
                    )
                )

        return failures

    def _check_hs_code_format(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check HS code format (8-10 digits if present).

        Returns:
            List of ValidationFailure objects
        """
        failures: list[ValidationFailure] = []

        if result.product.hs_code:
            if not is_valid_hs_code(result.product.hs_code):
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.HS_CODE_FORMAT,
                        field="product.hs_code",
                        message=f"Invalid HS code format: {result.product.hs_code[:20]!r} (must be 6-10 digits)",
                        severity=SeverityLevel.WARNING,
                    )
                )

        return failures

    def _check_tracking_format(self, result: ExtractionResult) -> list[ValidationFailure]:
        """Check tracking number format (5-50 alphanumeric if present).

        Returns:
            List of ValidationFailure objects
        """
        failures: list[ValidationFailure] = []

        if result.shipment.tracking_number:
            tracking = result.shipment.tracking_number.strip()

            # Check length
            if len(tracking) < 5 or len(tracking) > 50:
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.TRACKING_FORMAT,
                        field="shipment.tracking_number",
                        message=f"Tracking number length invalid: {len(tracking)} chars (must be 5-50)",
                        severity=SeverityLevel.INFO,
                    )
                )
                return failures

            # Check alphanumeric + common delimiters
            allowed_chars = set(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/."
            )
            if not all(c in allowed_chars for c in tracking):
                failures.append(
                    ValidationFailure(
                        rule=ValidationRuleType.TRACKING_FORMAT,
                        field="shipment.tracking_number",
                        message=f"Tracking number has invalid characters: {result.shipment.tracking_number[:50]!r}",
                        severity=SeverityLevel.INFO,
                    )
                )

        return failures

    def _compute_validation_score(self, failures: list[ValidationFailure]) -> float:
        """Compute validation score based on failures.

        Score formula:
        - Start with 100 points
        - Deduct for failures based on severity:
          - CRITICAL: -25 points each
          - ERROR: -15 points each
          - WARNING: -10 points each
          - INFO: -5 points each
        - Minimum score is 0, maximum is 100

        Args:
            failures: List of validation failures

        Returns:
            Validation score from 0-100
        """
        score = 100.0
        severity_costs = {
            SeverityLevel.CRITICAL: 25,
            SeverityLevel.ERROR: 15,
            SeverityLevel.WARNING: 10,
            SeverityLevel.INFO: 5,
        }

        for failure in failures:
            score -= severity_costs.get(failure.severity, 5)

        # Clamp to 0-100
        return max(0.0, min(100.0, score))
