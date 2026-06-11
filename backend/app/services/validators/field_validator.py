"""Field consistency validator for detecting value mismatches across documents."""

import logging
from collections import Counter
from typing import Any

from rapidfuzz import fuzz

from app.schemas.consistency import ConflictSeverity, FieldConflict
from app.schemas.validation import ValidatedExtractionResult

logger = logging.getLogger(__name__)


class FieldValidator:
    """Validates field consistency within a supplier group."""

    def __init__(self, fuzzy_threshold: int = 95):
        """Initialize field validator.

        Args:
            fuzzy_threshold: Similarity threshold for fuzzy matching (0-100)
        """
        self.fuzzy_threshold = fuzzy_threshold

        # Fields to check with their severity levels
        self.field_checks = {
            "supplier.name": ("HIGH", self._check_supplier_name),
            "supplier.country_of_origin": ("HIGH", self._check_country),
            "supplier.business_type": ("MEDIUM", self._check_string_field),
            "supplier.certification_status": ("MEDIUM", self._check_string_field),
            "product.origin_country": ("MEDIUM", self._check_country),
            "product.category": ("LOW", self._check_string_field),
            "location.country": ("HIGH", self._check_country),
        }

    async def validate_fields(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[FieldConflict]:
        """Check field consistency within entities.

        Args:
            entities_by_doc: Dict mapping document IDs to extraction results

        Returns:
            List of FieldConflict objects
        """
        conflicts: list[FieldConflict] = []

        for field_path, (severity, check_fn) in self.field_checks.items():
            conflicts.extend(check_fn(entities_by_doc, severity, field_path=field_path))

        return conflicts

    def _check_supplier_name(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
        severity: str,
        field_path: str | None = None,
    ) -> list[FieldConflict]:
        """Check supplier name consistency using fuzzy matching."""
        conflicts: list[FieldConflict] = []
        names = {}

        # Extract supplier names
        for doc_id, result in entities_by_doc.items():
            if result and hasattr(result, "extraction_id"):
                # Access supplier info from entity_data if available
                name = self._get_field_value(result, ["supplier", "name"])
                if name:
                    names[doc_id] = name

        if len(names) <= 1:
            return conflicts

        # Check if all names match within threshold
        name_list = list(names.values())
        for i, name1 in enumerate(name_list):
            for name2 in name_list[i + 1 :]:
                similarity = fuzz.token_set_ratio(name1.lower(), name2.lower())
                if similarity < self.fuzzy_threshold:
                    conflict = FieldConflict(
                        field="supplier.name",
                        values=names,
                        severity=ConflictSeverity(severity.lower()),
                        resolved_value=self._majority_vote(name_list),
                    )
                    conflicts.append(conflict)
                    return conflicts

        return conflicts

    def _check_country(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
        severity: str,
        field_path: str | None = None,
    ) -> list[FieldConflict]:
        """Check country field consistency."""
        conflicts: list[FieldConflict] = []
        values = {}

        # Parse field_path into nested keys
        field_parts = (field_path or "supplier.country_of_origin").split(".")

        for doc_id, result in entities_by_doc.items():
            if result:
                value = self._get_field_value(result, field_parts)
                if isinstance(value, str) and value:
                    values[doc_id] = value

        # Check if all values are the same (comparing strings only)
        if not values:
            return conflicts

        unique_values = set(values.values())
        if len(unique_values) <= 1:
            return conflicts

        # Cast values dict to match FieldConflict type signature
        values_with_none: dict[str, str | None] = {k: v for k, v in values.items()}
        conflict = FieldConflict(
            field=field_path or "supplier.country_of_origin",
            values=values_with_none,
            severity=ConflictSeverity(severity.lower()),
            resolved_value=self._majority_vote(list(values.values())),
        )
        conflicts.append(conflict)
        return conflicts

    def _check_string_field(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
        severity: str,
        field_path: str | None = None,
    ) -> list[FieldConflict]:
        """Check generic string field consistency."""
        # TODO: Post-MVP — Implement fuzzy matching for non-critical string fields
        # (business_type, certification_status, product.category)
        return []

    def _get_field_value(
        self, result: ValidatedExtractionResult, field_parts: list[str]
    ) -> Any:
        """Safely get nested field value from result."""
        try:
            # Try to use extraction_data if available
            if result.extraction_data:
                value: Any = result.extraction_data
                for part in field_parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None
                return value
            return None
        except (AttributeError, KeyError, TypeError):
            return None

    def _majority_vote(self, values: list[str | None]) -> str | None:
        """Get majority vote value, or first non-None value."""
        non_none = [v for v in values if v is not None]
        if not non_none:
            return None

        counts = Counter(non_none)
        most_common, _ = counts.most_common(1)[0]
        return most_common
