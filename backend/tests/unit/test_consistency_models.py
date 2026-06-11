"""Unit tests for consistency schema models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.consistency import (
    ConflictSeverity,
    ConsistencyReport,
    FieldConflict,
    LogicalConflict,
    LogicalConflictType,
    TemporalConflict,
    TemporalConflictType,
)


class TestFieldConflict:
    """Test FieldConflict model."""

    def test_field_conflict_creation(self):
        """Create a valid FieldConflict."""
        conflict = FieldConflict(
            field="supplier.name",
            values={"doc1": "Supplier A", "doc2": "Supplier B"},
            severity=ConflictSeverity.HIGH,
            resolved_value="Supplier A",
        )
        assert conflict.field == "supplier.name"
        assert len(conflict.values) == 2
        assert conflict.severity == ConflictSeverity.HIGH

    def test_field_conflict_with_none_resolved_value(self):
        """Create FieldConflict with no resolved value."""
        conflict = FieldConflict(
            field="supplier.certification_status",
            values={"doc1": "certified", "doc2": None},
            severity=ConflictSeverity.LOW,
        )
        assert conflict.resolved_value is None


class TestTemporalConflict:
    """Test TemporalConflict model."""

    def test_temporal_conflict_creation(self):
        """Create a valid TemporalConflict."""
        conflict = TemporalConflict(
            conflict_type=TemporalConflictType.DATE_ORDER_VIOLATION,
            dates_involved={"doc1": {"shipment_date": "2026-01-10", "arrival_date": "2026-01-05"}},
            severity=ConflictSeverity.HIGH,
            description="Shipment date is after arrival date",
        )
        assert conflict.conflict_type == TemporalConflictType.DATE_ORDER_VIOLATION
        assert "doc1" in conflict.dates_involved
        assert conflict.severity == ConflictSeverity.HIGH


class TestLogicalConflict:
    """Test LogicalConflict model."""

    def test_logical_conflict_creation(self):
        """Create a valid LogicalConflict."""
        conflict = LogicalConflict(
            conflict_type=LogicalConflictType.LOCATION_SUPPLIER_MISMATCH,
            involved_fields={
                "doc1": {"supplier_country": "US", "location_country": "CN"}
            },
            severity=ConflictSeverity.MEDIUM,
            description="Supplier origin does not match location",
        )
        assert conflict.conflict_type == LogicalConflictType.LOCATION_SUPPLIER_MISMATCH
        assert conflict.severity == ConflictSeverity.MEDIUM


class TestConsistencyReport:
    """Test ConsistencyReport model."""

    def test_consistency_report_no_conflicts(self):
        """Create a report with no conflicts."""
        case_id = uuid4()
        report = ConsistencyReport(
            case_id=case_id,
            field_conflicts=[],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=0,
            confidence_adjustment=0.0,
            summary="All checks passed",
        )
        assert report.case_id == case_id
        assert report.total_conflict_count == 0
        assert report.confidence_adjustment == 0.0
        assert report.timestamp is not None

    def test_consistency_report_with_conflicts(self):
        """Create a report with multiple conflicts."""
        case_id = uuid4()
        field_conflict = FieldConflict(
            field="supplier.name",
            values={"doc1": "Supplier A", "doc2": "Supplier B"},
            severity=ConflictSeverity.HIGH,
        )
        report = ConsistencyReport(
            case_id=case_id,
            field_conflicts=[field_conflict],
            temporal_conflicts=[],
            logical_conflicts=[],
            total_conflict_count=1,
            confidence_adjustment=0.1,
            summary="Found 1 conflict",
        )
        assert len(report.field_conflicts) == 1
        assert report.total_conflict_count == 1
        assert report.confidence_adjustment == 0.1

    def test_consistency_report_confidence_bounds(self):
        """Verify confidence adjustment is bounded."""
        case_id = uuid4()

        # Valid: 0.3 (max)
        report = ConsistencyReport(
            case_id=case_id,
            total_conflict_count=10,
            confidence_adjustment=0.3,
            summary="Max reduction",
        )
        assert report.confidence_adjustment == 0.3

        # Invalid: > 0.3 should fail validation
        with pytest.raises(Exception):
            ConsistencyReport(
                case_id=case_id,
                total_conflict_count=10,
                confidence_adjustment=0.4,
                summary="Too high",
            )


class TestEnumValues:
    """Test enumeration values."""

    def test_conflict_severity_values(self):
        """Verify ConflictSeverity enum values."""
        assert ConflictSeverity.HIGH.value == "high"
        assert ConflictSeverity.MEDIUM.value == "medium"
        assert ConflictSeverity.LOW.value == "low"

    def test_temporal_conflict_type_values(self):
        """Verify TemporalConflictType enum values."""
        assert TemporalConflictType.DATE_ORDER_VIOLATION.value == "date_order_violation"
        assert TemporalConflictType.OVERLAPPING_SHIPMENTS.value == "overlapping_shipments"
        assert TemporalConflictType.FUTURE_DATE.value == "future_date"

    def test_logical_conflict_type_values(self):
        """Verify LogicalConflictType enum values."""
        assert LogicalConflictType.LOCATION_SUPPLIER_MISMATCH.value == "location_supplier_mismatch"
        assert LogicalConflictType.PRODUCT_ORIGIN_MISMATCH.value == "product_origin_mismatch"
