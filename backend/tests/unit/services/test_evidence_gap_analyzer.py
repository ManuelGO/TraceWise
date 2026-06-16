"""Unit tests for the EvidenceGapAnalyzer service (Task 44).

Tests cover:
1. Schema validation (EvidenceGap, EvidenceGapResult, GapSeverity)
2. Required-fields catalogue integrity (coverage + path resolution)
3. _is_missing semantics (None/empty/whitespace vs present, incl. False/0.0)
4. _resolve_value dotted-path resolution
5. _completeness math (full/none/partial/empty)
6. analyze() per document type (happy + gap paths)
7. _catalogue_for fallback (general + unknown)
8. Integration with ConfidenceScorer (completeness_score consumption)

Total: 40+ tests.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import DocumentType
from app.schemas.evidence_gap import EvidenceGap, EvidenceGapResult, GapSeverity
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.services.confidence_scorer import ConfidenceScorer
from app.services.evidence_gap_analyzer import (
    GENERAL_DOC_TYPE,
    REQUIRED_FIELDS_BY_DOC_TYPE,
    EvidenceGapAnalyzer,
    RequiredField,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def doc_id():
    return uuid4()


@pytest.fixture
def analyzer():
    return EvidenceGapAnalyzer()


@pytest.fixture
def complete_entities(doc_id):
    """ExtractionResult with every catalogued optional field populated."""
    return ExtractionResult(
        document_id=doc_id,
        supplier=SupplierInfo(
            name="Acme Corp",
            country_of_origin="US",
            certification_status="certified",
        ),
        product=ProductInfo(name="Steel Coils", quantity=100.0),
        location=LocationInfo(country="US", geolocation_verified=True),
        shipment=ShipmentInfo(
            shipment_date=date(2026, 1, 1),
            origin_port="Shanghai",
            destination_port="Rotterdam",
        ),
        extraction_confidence=0.90,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


@pytest.fixture
def sparse_entities(doc_id):
    """ExtractionResult with all optional catalogued fields absent."""
    return ExtractionResult(
        document_id=doc_id,
        supplier=SupplierInfo(name="Acme Corp", country_of_origin="US"),
        product=ProductInfo(name="Steel Coils"),
        location=LocationInfo(country="US"),
        shipment=ShipmentInfo(),
        extraction_confidence=0.50,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


# ============================================================================
# Schema validation
# ============================================================================


def test_gap_severity_values():
    assert GapSeverity.CRITICAL == "critical"
    assert GapSeverity.HIGH == "high"
    assert GapSeverity.MEDIUM == "medium"
    assert GapSeverity.LOW == "low"


def test_evidence_gap_valid_construction():
    gap = EvidenceGap(
        document_type="invoice",
        required_field="Product name",
        entity_path="product.name",
        severity=GapSeverity.HIGH,
        suggested_action="Add the product name.",
    )
    assert gap.entity_path == "product.name"
    assert gap.severity == GapSeverity.HIGH


def test_evidence_gap_rejects_extra_keys():
    with pytest.raises(ValidationError):
        EvidenceGap(
            document_type="invoice",
            required_field="Product name",
            entity_path="product.name",
            severity=GapSeverity.HIGH,
            suggested_action="Add it.",
            unexpected="x",
        )


def test_evidence_gap_rejects_empty_suggestion():
    with pytest.raises(ValidationError):
        EvidenceGap(
            document_type="invoice",
            required_field="Product name",
            entity_path="product.name",
            severity=GapSeverity.HIGH,
            suggested_action="",
        )


def test_evidence_gap_result_valid_construction(doc_id):
    result = EvidenceGapResult(
        document_id=doc_id,
        document_type="invoice",
        gaps=[],
        total_required=3,
        required_found=3,
        completeness_score=1.0,
        is_complete=True,
    )
    assert result.is_complete is True
    assert result.completeness_score == 1.0


def test_evidence_gap_result_rejects_extra_keys(doc_id):
    with pytest.raises(ValidationError):
        EvidenceGapResult(
            document_id=doc_id,
            document_type="invoice",
            gaps=[],
            total_required=0,
            required_found=0,
            completeness_score=1.0,
            is_complete=True,
            extra="nope",
        )


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_evidence_gap_result_rejects_out_of_range(doc_id, bad):
    with pytest.raises(ValidationError):
        EvidenceGapResult(
            document_id=doc_id,
            document_type="invoice",
            gaps=[],
            total_required=1,
            required_found=1,
            completeness_score=bad,
            is_complete=True,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_evidence_gap_result_rejects_nan_inf(doc_id, bad):
    with pytest.raises(ValidationError):
        EvidenceGapResult(
            document_id=doc_id,
            document_type="invoice",
            gaps=[],
            total_required=1,
            required_found=1,
            completeness_score=bad,
            is_complete=True,
        )


def test_evidence_gap_result_generated_at_defaults(doc_id):
    result = EvidenceGapResult(
        document_id=doc_id,
        document_type="invoice",
        gaps=[],
        total_required=0,
        required_found=0,
        completeness_score=1.0,
        is_complete=True,
    )
    assert result.generated_at.tzinfo is not None


# ============================================================================
# Catalogue integrity
# ============================================================================


def test_catalogue_covers_every_document_type():
    for doc_type in DocumentType:
        assert doc_type.value in REQUIRED_FIELDS_BY_DOC_TYPE


def test_catalogue_has_general_baseline():
    assert GENERAL_DOC_TYPE in REQUIRED_FIELDS_BY_DOC_TYPE
    assert REQUIRED_FIELDS_BY_DOC_TYPE[GENERAL_DOC_TYPE]


def test_catalogue_entries_are_required_fields():
    for fields in REQUIRED_FIELDS_BY_DOC_TYPE.values():
        assert fields, "catalogue entry must be non-empty"
        for field in fields:
            assert isinstance(field, RequiredField)
            assert field.label
            assert field.entity_path
            assert field.suggestion
            assert isinstance(field.severity, GapSeverity)


def test_catalogue_paths_resolve_on_complete_entities(analyzer, complete_entities):
    for fields in REQUIRED_FIELDS_BY_DOC_TYPE.values():
        for field in fields:
            value = analyzer._resolve_value(complete_entities, field.entity_path)
            assert not analyzer._is_missing(value), field.entity_path


# ============================================================================
# _is_missing
# ============================================================================


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_is_missing_true(analyzer, value):
    assert analyzer._is_missing(value) is True


@pytest.mark.parametrize("value", ["x", "US", False, True, 0.0, 0, 100.0])
def test_is_missing_false_for_present_values(analyzer, value):
    assert analyzer._is_missing(value) is False


def test_is_missing_false_for_date(analyzer):
    assert analyzer._is_missing(date(2026, 1, 1)) is False


@pytest.mark.parametrize("value", [False, 0, 0.0, ""])
def test_is_missing_true_when_falsy_is_missing(analyzer, value):
    assert analyzer._is_missing(value, falsy_is_missing=True) is True


@pytest.mark.parametrize("value", [True, 1, "x"])
def test_is_missing_false_for_truthy_when_falsy_is_missing(analyzer, value):
    assert analyzer._is_missing(value, falsy_is_missing=True) is False


# ============================================================================
# _resolve_value
# ============================================================================


def test_resolve_value_nested(analyzer, complete_entities):
    assert analyzer._resolve_value(complete_entities, "supplier.name") == "Acme Corp"


def test_resolve_value_optional_present(analyzer, complete_entities):
    assert analyzer._resolve_value(complete_entities, "product.quantity") == 100.0


def test_resolve_value_optional_absent(analyzer, sparse_entities):
    assert analyzer._resolve_value(sparse_entities, "product.quantity") is None


def test_resolve_value_unknown_path_returns_none(analyzer, complete_entities):
    assert analyzer._resolve_value(complete_entities, "supplier.does_not_exist") is None


def test_resolve_value_deep_unknown_segment(analyzer, complete_entities):
    assert analyzer._resolve_value(complete_entities, "supplier.name.nope") is None


def test_resolve_value_false_bool(analyzer, sparse_entities):
    # geolocation_verified defaults to False — present, not missing
    assert analyzer._resolve_value(sparse_entities, "location.geolocation_verified") is False


# ============================================================================
# _completeness
# ============================================================================


def test_completeness_full(analyzer):
    assert analyzer._completeness(3, 3) == 1.0


def test_completeness_none(analyzer):
    assert analyzer._completeness(0, 3) == 0.0


def test_completeness_partial(analyzer):
    assert analyzer._completeness(2, 3) == pytest.approx(2 / 3)


def test_completeness_empty_catalogue(analyzer):
    assert analyzer._completeness(0, 0) == 1.0


def test_catalogue_for_known(analyzer):
    fields = analyzer._catalogue_for(DocumentType.INVOICE.value)
    assert fields is REQUIRED_FIELDS_BY_DOC_TYPE[DocumentType.INVOICE.value]


def test_catalogue_for_unknown_falls_back_to_general(analyzer):
    fields = analyzer._catalogue_for("totally-unknown")
    assert fields is REQUIRED_FIELDS_BY_DOC_TYPE[GENERAL_DOC_TYPE]


# ============================================================================
# analyze() — happy paths
# ============================================================================


def test_analyze_complete_supplier_declaration(analyzer, complete_entities):
    result = analyzer.analyze(
        complete_entities, DocumentType.SUPPLIER_DECLARATION.value
    )
    assert result.is_complete is True
    assert result.gaps == []
    assert result.completeness_score == 1.0
    assert result.total_required == result.required_found


def test_analyze_complete_invoice(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, DocumentType.INVOICE.value)
    assert result.is_complete is True
    assert result.required_found == 3


def test_analyze_complete_shipment_note(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, DocumentType.SHIPMENT_NOTE.value)
    assert result.is_complete is True


def test_analyze_complete_geojson(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, DocumentType.GEOJSON.value)
    assert result.is_complete is True


def test_analyze_complete_certificate(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, DocumentType.CERTIFICATE.value)
    assert result.is_complete is True


# ============================================================================
# analyze() — gap paths
# ============================================================================


def test_analyze_supplier_declaration_missing_certification(
    analyzer, sparse_entities
):
    result = analyzer.analyze(
        sparse_entities, DocumentType.SUPPLIER_DECLARATION.value
    )
    assert result.is_complete is False
    paths = {g.entity_path for g in result.gaps}
    assert "supplier.certification_status" in paths
    cert_gap = next(g for g in result.gaps if g.entity_path == "supplier.certification_status")
    assert cert_gap.severity == GapSeverity.HIGH
    assert cert_gap.suggested_action


def test_analyze_invoice_missing_quantity(analyzer, sparse_entities):
    result = analyzer.analyze(sparse_entities, DocumentType.INVOICE.value)
    paths = {g.entity_path for g in result.gaps}
    assert "product.quantity" in paths
    assert result.required_found == result.total_required - len(result.gaps)


def test_analyze_shipment_note_all_missing(analyzer, sparse_entities):
    result = analyzer.analyze(sparse_entities, DocumentType.SHIPMENT_NOTE.value)
    assert len(result.gaps) == 3
    assert result.completeness_score == 0.0
    assert result.required_found == 0


def test_analyze_geojson_unverified_geolocation_is_gap(analyzer, sparse_entities):
    # geolocation_verified defaults to False; the GEOJSON catalogue marks that
    # field falsy_is_missing=True, so an unverified location IS a gap.
    result = analyzer.analyze(sparse_entities, DocumentType.GEOJSON.value)
    assert result.is_complete is False
    paths = {g.entity_path for g in result.gaps}
    assert "location.geolocation_verified" in paths
    geo_gap = next(g for g in result.gaps if g.entity_path == "location.geolocation_verified")
    assert geo_gap.severity == GapSeverity.HIGH
    # country is present, so completeness is 1 of 2 required fields
    assert result.completeness_score == 0.5


def test_analyze_geojson_verified_geolocation_complete(analyzer, complete_entities):
    # complete_entities has geolocation_verified=True → no gap.
    result = analyzer.analyze(complete_entities, DocumentType.GEOJSON.value)
    assert result.is_complete is True


def test_analyze_certificate_missing_status(analyzer, sparse_entities):
    result = analyzer.analyze(sparse_entities, DocumentType.CERTIFICATE.value)
    paths = {g.entity_path for g in result.gaps}
    assert "supplier.certification_status" in paths


def test_analyze_gap_document_type_echoed(analyzer, sparse_entities):
    result = analyzer.analyze(sparse_entities, DocumentType.INVOICE.value)
    for gap in result.gaps:
        assert gap.document_type == DocumentType.INVOICE.value


def test_analyze_result_document_id_matches(analyzer, complete_entities, doc_id):
    result = analyzer.analyze(complete_entities, DocumentType.OTHER.value)
    assert result.document_id == doc_id


# ============================================================================
# analyze() — doc type fallback
# ============================================================================


def test_analyze_default_general(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities)
    assert result.document_type == GENERAL_DOC_TYPE
    assert result.is_complete is True


def test_analyze_unknown_doc_type_uses_general(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, "mystery-type")
    # general baseline has 3 required fields, all present in complete_entities
    assert result.total_required == len(REQUIRED_FIELDS_BY_DOC_TYPE[GENERAL_DOC_TYPE])
    assert result.is_complete is True


def test_analyze_other_doc_type(analyzer, complete_entities):
    result = analyzer.analyze(complete_entities, DocumentType.OTHER.value)
    assert result.document_type == DocumentType.OTHER.value


# ============================================================================
# analyze() — errors
# ============================================================================


def test_analyze_none_extraction_raises(analyzer):
    with pytest.raises(ValueError, match="extraction_result is required"):
        analyzer.analyze(None)  # type: ignore[arg-type]


# ============================================================================
# Integration with ConfidenceScorer
# ============================================================================


def test_completeness_feeds_confidence_scorer(analyzer, sparse_entities):
    gap_result = analyzer.analyze(
        sparse_entities, DocumentType.SHIPMENT_NOTE.value
    )
    scorer = ConfidenceScorer()
    confidence = scorer.compute(
        entities=sparse_entities,
        evidence_completeness=gap_result.completeness_score,
    )
    assert 0.0 <= confidence.confidence_score <= 1.0
    assert confidence.factors.evidence_completeness == gap_result.completeness_score
