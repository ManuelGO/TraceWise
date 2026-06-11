"""Temporal consistency validator for date and time logic validation."""

import logging
from datetime import date, datetime, timedelta

from app.schemas.consistency import ConflictSeverity, TemporalConflict, TemporalConflictType
from app.schemas.validation import ValidatedExtractionResult

logger = logging.getLogger(__name__)


class TemporalValidator:
    """Validates temporal consistency and date logic across documents."""

    def __init__(self, future_days_allowed: int = 0):
        """Initialize temporal validator.

        Args:
            future_days_allowed: Number of days into future that are acceptable (default 0 = today)
        """
        self.future_days_allowed = future_days_allowed

    async def validate_temporal(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[TemporalConflict]:
        """Check temporal consistency across documents.

        Args:
            entities_by_doc: Dict mapping document IDs to extraction results

        Returns:
            List of TemporalConflict objects
        """
        conflicts = []

        # Check date order within each document
        conflicts.extend(self._check_date_ordering(entities_by_doc))

        # Check for overlapping shipments
        conflicts.extend(self._check_overlapping_shipments(entities_by_doc))

        # Check for future dates
        conflicts.extend(self._check_future_dates(entities_by_doc))

        return conflicts

    def _check_date_ordering(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[TemporalConflict]:
        """Check that shipment_date <= arrival_date within each document."""
        conflicts: list[TemporalConflict] = []

        for doc_id, result in entities_by_doc.items():
            if not result:
                continue

            try:
                # Get shipment info
                shipment_date = self._get_field_value(result, ["shipment", "shipment_date"])
                arrival_date = self._get_field_value(result, ["shipment", "arrival_date"])

                # Normalize datetime to date for comparison
                if isinstance(shipment_date, datetime):
                    shipment_date = shipment_date.date()
                if isinstance(arrival_date, datetime):
                    arrival_date = arrival_date.date()

                if (
                    isinstance(shipment_date, date)
                    and isinstance(arrival_date, date)
                    and shipment_date > arrival_date
                ):
                    conflict = TemporalConflict(
                        conflict_type=TemporalConflictType.DATE_ORDER_VIOLATION,
                        dates_involved={
                            doc_id: {
                                "shipment_date": str(shipment_date) if shipment_date else None,
                                "arrival_date": str(arrival_date) if arrival_date else None,
                            }
                        },
                        severity=ConflictSeverity.HIGH,
                        description=f"Shipment date ({shipment_date}) is after arrival date ({arrival_date})",
                    )
                    conflicts.append(conflict)
            except (AttributeError, TypeError) as e:
                logger.debug(f"Error checking date ordering for {doc_id}: {e}")

        return conflicts

    def _check_overlapping_shipments(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[TemporalConflict]:
        """Check for overlapping shipment date ranges across documents."""
        conflicts: list[TemporalConflict] = []
        shipments: list[dict[str, str | date]] = []

        # Collect shipment date ranges
        for doc_id, result in entities_by_doc.items():
            if not result:
                continue

            try:
                shipment_date = self._get_field_value(result, ["shipment", "shipment_date"])
                arrival_date = self._get_field_value(result, ["shipment", "arrival_date"])

                # Normalize datetime to date
                if isinstance(shipment_date, datetime):
                    shipment_date = shipment_date.date()
                if isinstance(arrival_date, datetime):
                    arrival_date = arrival_date.date()

                if isinstance(shipment_date, date):
                    arrival: date = arrival_date if isinstance(arrival_date, date) else shipment_date
                    shipments.append(
                        {
                            "doc_id": doc_id,
                            "shipment_date": shipment_date,
                            "arrival_date": arrival,
                        }
                    )
            except (AttributeError, TypeError):
                pass

        # Check for overlaps
        for i, shipment1 in enumerate(shipments):
            for shipment2 in shipments[i + 1 :]:
                s1_start = shipment1.get("shipment_date")
                s1_end = shipment1.get("arrival_date")
                s2_start = shipment2.get("shipment_date")
                s2_end = shipment2.get("arrival_date")
                try:
                    if (
                        isinstance(s1_start, date)
                        and isinstance(s1_end, date)
                        and isinstance(s2_start, date)
                        and isinstance(s2_end, date)
                        and self._date_ranges_overlap(s1_start, s1_end, s2_start, s2_end)
                    ):
                        doc1_id = str(shipment1.get("doc_id", "unknown"))
                        doc2_id = str(shipment2.get("doc_id", "unknown"))
                        conflict = TemporalConflict(
                            conflict_type=TemporalConflictType.OVERLAPPING_SHIPMENTS,
                            dates_involved={
                                doc1_id: {
                                    "shipment_date": str(s1_start),
                                    "arrival_date": str(s1_end),
                                },
                                doc2_id: {
                                    "shipment_date": str(s2_start),
                                    "arrival_date": str(s2_end),
                                },
                            },
                            severity=ConflictSeverity.MEDIUM,
                            description=f"Shipments overlap: {doc1_id} and {doc2_id}",
                        )
                        conflicts.append(conflict)
                except (TypeError, AttributeError):
                    logger.debug(f"Error comparing overlapping shipments for {shipment1} and {shipment2}")

        return conflicts

    def _check_future_dates(
        self,
        entities_by_doc: dict[str, ValidatedExtractionResult],
    ) -> list[TemporalConflict]:
        """Check for dates in the future."""
        conflicts: list[TemporalConflict] = []
        cutoff = date.today() + timedelta(days=self.future_days_allowed)

        for doc_id, result in entities_by_doc.items():
            if not result:
                continue

            try:
                shipment_date = self._get_field_value(result, ["shipment", "shipment_date"])
                arrival_date = self._get_field_value(result, ["shipment", "arrival_date"])

                # Normalize datetime to date for consistent comparison
                if isinstance(shipment_date, datetime):
                    shipment_date = shipment_date.date()
                if isinstance(arrival_date, datetime):
                    arrival_date = arrival_date.date()

                for date_val, field_name in [
                    (shipment_date, "shipment_date"),
                    (arrival_date, "arrival_date"),
                ]:
                    if isinstance(date_val, date) and date_val > cutoff:
                        conflict = TemporalConflict(
                            conflict_type=TemporalConflictType.FUTURE_DATE,
                            dates_involved={doc_id: {field_name: str(date_val)}},
                            severity=ConflictSeverity.MEDIUM,
                            description=f"{field_name} is in the future: {date_val}",
                        )
                        conflicts.append(conflict)
            except (AttributeError, TypeError) as e:
                logger.debug(f"Error checking future dates for {doc_id}: {e}")

        return conflicts

    def _date_ranges_overlap(self, start1: date, end1: date, start2: date, end2: date) -> bool:
        """Check if two date ranges overlap."""
        return start1 <= end2 and start2 <= end1

    def _get_field_value(
        self, result: ValidatedExtractionResult, field_parts: list[str]
    ) -> date | None:
        """Safely get nested field value from result, normalized to date type."""
        try:
            # Try to use extraction_data if available
            if result.extraction_data:
                value: object = result.extraction_data
                for part in field_parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None

                # Convert all date-like values to date type for consistency
                if isinstance(value, str):
                    try:
                        return datetime.fromisoformat(value).date()
                    except (ValueError, AttributeError):
                        return None
                if isinstance(value, datetime):
                    return value.date()
                if isinstance(value, date):
                    return value
            return None
        except (AttributeError, KeyError, TypeError):
            return None
