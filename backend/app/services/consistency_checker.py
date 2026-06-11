"""Consistency checker service for cross-document entity validation."""

import logging
from typing import Any
from uuid import UUID

from rapidfuzz import fuzz

from app.schemas.consistency import ConsistencyReport
from app.schemas.validation import ValidatedExtractionResult
from app.services.validators import FieldValidator, LogicalValidator, TemporalValidator

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """Main consistency checking service for case-level validation."""

    def __init__(self, fuzzy_threshold: int = 95, future_days_allowed: int = 0):
        """Initialize consistency checker.

        Args:
            fuzzy_threshold: Supplier name matching threshold (0-100, default 95)
            future_days_allowed: Days into future that are acceptable (default 0)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.field_validator = FieldValidator(fuzzy_threshold=fuzzy_threshold)
        self.temporal_validator = TemporalValidator(future_days_allowed=future_days_allowed)
        self.logical_validator = LogicalValidator()

    async def check_consistency(
        self,
        case_id: UUID,
        validated_entities: list[ValidatedExtractionResult],
    ) -> ConsistencyReport:
        """Run all consistency checks across documents in a case.

        Args:
            case_id: Case ID for context
            validated_entities: Validated extraction results per document

        Returns:
            ConsistencyReport with conflicts and adjustments

        Raises:
            ValueError: If fewer than 1 document provided or data malformed
        """
        if not validated_entities:
            raise ValueError("At least one validated entity is required")

        # Group documents by supplier (fuzzy matching)
        supplier_groups = self._group_by_supplier(validated_entities)

        # Run validators for each supplier group
        field_conflicts = []
        temporal_conflicts = []
        logical_conflicts = []

        for supplier_name, entities_by_doc in supplier_groups.items():
            # Only check consistency if multiple documents
            if len(entities_by_doc) > 1:
                field_conflicts.extend(await self.field_validator.validate_fields(entities_by_doc))
                temporal_conflicts.extend(
                    await self.temporal_validator.validate_temporal(entities_by_doc)
                )
                logical_conflicts.extend(
                    await self.logical_validator.validate_logical(entities_by_doc)
                )

            # Also check logical conflicts even for single documents
            else:
                logical_conflicts.extend(
                    await self.logical_validator.validate_logical(entities_by_doc)
                )

        # Aggregate results
        total_conflict_count = (
            len(field_conflicts) + len(temporal_conflicts) + len(logical_conflicts)
        )
        confidence_adjustment = self._calculate_confidence_adjustment(total_conflict_count)
        summary = self._generate_summary(
            field_conflicts, temporal_conflicts, logical_conflicts, total_conflict_count
        )

        report = ConsistencyReport(
            case_id=case_id,
            field_conflicts=field_conflicts,
            temporal_conflicts=temporal_conflicts,
            logical_conflicts=logical_conflicts,
            total_conflict_count=total_conflict_count,
            confidence_adjustment=confidence_adjustment,
            summary=summary,
        )

        logger.info(
            f"Consistency check completed for case {case_id}: "
            f"{total_conflict_count} conflicts found, "
            f"confidence adjustment: {confidence_adjustment:.2%}"
        )

        return report

    def _group_by_supplier(
        self, validated_entities: list[ValidatedExtractionResult]
    ) -> dict[str, dict[str, ValidatedExtractionResult]]:
        """Group entities by supplier using fuzzy matching.

        Args:
            validated_entities: List of extraction results

        Returns:
            Dict mapping supplier names to entities_by_doc dicts
        """
        groups: dict[str, dict[str, ValidatedExtractionResult]] = {}
        MAX_SUPPLIER_NAME = 200

        for i, entity in enumerate(validated_entities):
            supplier_name = self._get_supplier_name(entity)
            if not supplier_name:
                # Use UUID-based key for unknown suppliers to prevent fuzzy-match collisions
                supplier_name = f"unknown_{entity.extraction_id.hex[:8]}"
            else:
                # Cap supplier name length to prevent DoS via fuzzy matching
                supplier_name = supplier_name[:MAX_SUPPLIER_NAME]

            # Try to find matching group
            matched_group = None
            for existing_supplier in groups.keys():
                similarity = fuzz.token_set_ratio(
                    supplier_name.lower(), existing_supplier.lower()
                )
                if similarity >= self.fuzzy_threshold:
                    matched_group = existing_supplier
                    break

            # Use matched group or create new one
            if matched_group:
                group_key = matched_group
            else:
                group_key = supplier_name

            if group_key not in groups:
                groups[group_key] = {}

            # Store entity with document ID as key
            doc_id = str(getattr(entity, "extraction_id", i))
            groups[group_key][doc_id] = entity

        return groups

    def _get_supplier_name(self, entity: ValidatedExtractionResult) -> str | None:
        """Extract supplier name from entity."""
        try:
            # Get supplier name from extraction_data
            if entity.extraction_data and isinstance(entity.extraction_data, dict):
                supplier = entity.extraction_data.get("supplier", {})
                if isinstance(supplier, dict):
                    return supplier.get("name")
            return None
        except (AttributeError, TypeError, KeyError):
            return None

    def _calculate_confidence_adjustment(self, conflict_count: int) -> float:
        """Calculate confidence adjustment based on conflict count.

        Args:
            conflict_count: Number of conflicts detected

        Returns:
            Confidence adjustment factor (0.0-0.3)
        """
        if conflict_count == 0:
            return 0.0
        elif conflict_count <= 2:
            return 0.10
        elif conflict_count <= 5:
            return 0.20
        else:
            return 0.30

    def _generate_summary(
        self,
        field_conflicts: list[Any],
        temporal_conflicts: list[Any],
        logical_conflicts: list[Any],
        total_count: int,
    ) -> str:
        """Generate human-readable summary.

        Args:
            field_conflicts: List of field conflicts
            temporal_conflicts: List of temporal conflicts
            logical_conflicts: List of logical conflicts
            total_count: Total conflict count

        Returns:
            Summary string
        """
        if total_count == 0:
            return "All consistency checks passed."

        parts = [f"Found {total_count} consistency issue(s):"]
        if field_conflicts:
            parts.append(f"- {len(field_conflicts)} field mismatch(es)")
        if temporal_conflicts:
            parts.append(f"- {len(temporal_conflicts)} temporal issue(s)")
        if logical_conflicts:
            parts.append(f"- {len(logical_conflicts)} logical inconsistency(ies)")

        return " ".join(parts)
