"""Logical consistency validator for entity relationship validation."""

import logging

from app.schemas.consistency import ConflictSeverity, LogicalConflict, LogicalConflictType
from app.schemas.validation import ValidatedExtractionResult

logger = logging.getLogger(__name__)


class LogicalValidator:
    """Validates logical consistency of entity relationships."""

    async def validate_logical(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[LogicalConflict]:
        """Check logical consistency of entity relationships.

        Args:
            entities_by_doc: Dict mapping document IDs to extraction results

        Returns:
            List of LogicalConflict objects
        """
        conflicts = []

        # Check location matches supplier origin
        conflicts.extend(self._check_location_supplier_match(entities_by_doc))

        # Check product origin aligns with supplier
        conflicts.extend(self._check_product_origin_match(entities_by_doc))

        return conflicts

    def _check_location_supplier_match(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[LogicalConflict]:
        """Check that location country matches supplier country."""
        conflicts: list[LogicalConflict] = []
        MAX_FIELD = 100

        for doc_id, result in entities_by_doc.items():
            if not result:
                continue

            try:
                supplier_country = self._get_field_value(result, ["supplier", "country_of_origin"])
                location_country = self._get_field_value(result, ["location", "country"])

                # Only flag if both are present and different
                if supplier_country and location_country:
                    if not self._countries_match(supplier_country, location_country):
                        # Truncate field values before interpolation to prevent ValidationError
                        sc = (supplier_country or "")[:MAX_FIELD]
                        lc = (location_country or "")[:MAX_FIELD]
                        conflict = LogicalConflict(
                            conflict_type=LogicalConflictType.LOCATION_SUPPLIER_MISMATCH,
                            involved_fields={
                                doc_id: {
                                    "supplier_country": supplier_country,
                                    "location_country": location_country,
                                }
                            },
                            severity=ConflictSeverity.MEDIUM,
                            description=f"Supplier origin ({sc}) differs from location ({lc})",
                        )
                        conflicts.append(conflict)
            except (AttributeError, TypeError) as e:
                logger.debug(f"Error checking location-supplier match for {doc_id}: {e}")

        return conflicts

    def _check_product_origin_match(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[LogicalConflict]:
        """Check that product origin aligns with supplier country."""
        conflicts: list[LogicalConflict] = []
        MAX_FIELD = 100

        for doc_id, result in entities_by_doc.items():
            if not result:
                continue

            try:
                supplier_country = self._get_field_value(result, ["supplier", "country_of_origin"])
                product_origin = self._get_field_value(result, ["product", "origin_country"])

                # Only flag if both are present and different
                if supplier_country and product_origin:
                    if not self._countries_match(supplier_country, product_origin):
                        # Truncate field values before interpolation to prevent ValidationError
                        sc = (supplier_country or "")[:MAX_FIELD]
                        po = (product_origin or "")[:MAX_FIELD]
                        conflict = LogicalConflict(
                            conflict_type=LogicalConflictType.PRODUCT_ORIGIN_MISMATCH,
                            involved_fields={
                                doc_id: {
                                    "supplier_country": supplier_country,
                                    "product_origin": product_origin,
                                }
                            },
                            severity=ConflictSeverity.LOW,
                            description=f"Product origin ({po}) differs from supplier country ({sc})",
                        )
                        conflicts.append(conflict)
            except (AttributeError, TypeError) as e:
                logger.debug(f"Error checking product origin match for {doc_id}: {e}")

        return conflicts

    def _countries_match(self, country1: str, country2: str) -> bool:
        """Check if two country values match (case-insensitive, normalize codes)."""
        if not country1 or not country2:
            return False

        # Normalize to uppercase for comparison
        c1 = country1.upper().strip()
        c2 = country2.upper().strip()

        # Exact match
        if c1 == c2:
            return True

        # Handle ISO 2-letter code vs full name (simplified)
        # In production, would use pycountry for proper normalization
        return False

    def _get_field_value(
        self, result: ValidatedExtractionResult, field_parts: list[str]
    ) -> str | None:
        """Safely get nested field value from result."""
        try:
            # Try to use extraction_data if available
            if result.extraction_data:
                value: object = result.extraction_data
                for part in field_parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None
                if isinstance(value, str):
                    return value
            return None
        except (AttributeError, KeyError, TypeError):
            return None
