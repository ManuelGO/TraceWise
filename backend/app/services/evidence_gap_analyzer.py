"""Evidence gap analysis service for compliance documents (Task 44).

Compares the entities extracted from a document (Task 38 ExtractionResult) against
a catalogue of required fields per document type, detects missing required evidence,
classifies each gap by severity, and emits actionable remediation suggestions.

Pipeline position:
    Task 38 (Extraction) → Task 44 (THIS) → completeness_score → Task 43 (Confidence)

This service is stateless and pure-computation (TASK_44_COORDINATOR_DECISION.md,
Option 1): no database writes, no ORM model, no external API calls. Deterministic for
identical inputs (modulo the result timestamp).
"""

import logging

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentType
from app.schemas.evidence_gap import (
    GENERAL_DOC_TYPE,
    EvidenceGap,
    EvidenceGapResult,
    GapSeverity,
)
from app.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)


class RequiredField(BaseModel):
    """A field that must be present for a given document type.

    Attributes:
        label: Human-readable field name (e.g. "Supplier name")
        entity_path: Dotted path into the ExtractionResult (e.g. "supplier.name")
        severity: Severity assigned when this field is missing
        suggestion: Actionable remediation guidance when this field is missing
        falsy_is_missing: When True, falsy-but-present values (e.g. a `False`
            boolean) count as missing. Defaults to False so that legitimate
            falsy data such as `quantity=0.0` stays "present".
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=200)
    entity_path: str = Field(..., min_length=1, max_length=200)
    severity: GapSeverity
    suggestion: str = Field(..., min_length=1, max_length=500)
    # Plain default (no Field()) so mypy's pydantic plugin treats it as optional
    # in the synthesized __init__; the catalogue constructs most entries without it.
    falsy_is_missing: bool = False


# ---------------------------------------------------------------------------
# Required-fields catalogue (coordinator-reviewable, single source of truth)
# ---------------------------------------------------------------------------

# Baseline required fields shared by the "other" document type and the "general"
# fallback. Defined once to avoid silent drift between the two.
_GENERAL_FIELDS: list[RequiredField] = [
    RequiredField(
        label="Supplier name",
        entity_path="supplier.name",
        severity=GapSeverity.MEDIUM,
        suggestion="Identify the supplier associated with this document.",
    ),
    RequiredField(
        label="Product name",
        entity_path="product.name",
        severity=GapSeverity.MEDIUM,
        suggestion="Identify the product associated with this document.",
    ),
    RequiredField(
        label="Location country",
        entity_path="location.country",
        severity=GapSeverity.MEDIUM,
        suggestion="Identify the country associated with this document.",
    ),
]

# Keyed by DocumentType value strings plus a "general" baseline fallback.
REQUIRED_FIELDS_BY_DOC_TYPE: dict[str, list[RequiredField]] = {
    DocumentType.SUPPLIER_DECLARATION.value: [
        RequiredField(
            label="Supplier name",
            entity_path="supplier.name",
            severity=GapSeverity.CRITICAL,
            suggestion="Provide the supplier's legal company name on the declaration.",
        ),
        RequiredField(
            label="Supplier country of origin",
            entity_path="supplier.country_of_origin",
            severity=GapSeverity.CRITICAL,
            suggestion="State the supplier's country of origin (ISO code or full name).",
        ),
        RequiredField(
            label="Certification status",
            entity_path="supplier.certification_status",
            severity=GapSeverity.HIGH,
            suggestion="Request the supplier's certification status (certified/pending/none).",
        ),
    ],
    DocumentType.INVOICE.value: [
        RequiredField(
            label="Supplier name",
            entity_path="supplier.name",
            severity=GapSeverity.HIGH,
            suggestion="Ensure the invoice identifies the issuing supplier by name.",
        ),
        RequiredField(
            label="Product name",
            entity_path="product.name",
            severity=GapSeverity.HIGH,
            suggestion="Add the product description/name to the invoice line items.",
        ),
        RequiredField(
            label="Product quantity",
            entity_path="product.quantity",
            severity=GapSeverity.MEDIUM,
            suggestion="Include the quantity of goods invoiced.",
        ),
    ],
    DocumentType.SHIPMENT_NOTE.value: [
        RequiredField(
            label="Shipment date",
            entity_path="shipment.shipment_date",
            severity=GapSeverity.HIGH,
            suggestion="Record the date the goods were shipped.",
        ),
        RequiredField(
            label="Origin port",
            entity_path="shipment.origin_port",
            severity=GapSeverity.MEDIUM,
            suggestion="Specify the port of loading on the shipment note.",
        ),
        RequiredField(
            label="Destination port",
            entity_path="shipment.destination_port",
            severity=GapSeverity.MEDIUM,
            suggestion="Specify the port of discharge on the shipment note.",
        ),
    ],
    DocumentType.GEOJSON.value: [
        RequiredField(
            label="Location country",
            entity_path="location.country",
            severity=GapSeverity.CRITICAL,
            suggestion="Provide the country for the geolocation data.",
        ),
        RequiredField(
            label="Geolocation verified",
            entity_path="location.geolocation_verified",
            severity=GapSeverity.HIGH,
            suggestion="Verify the location coordinates and mark geolocation as verified.",
            falsy_is_missing=True,
        ),
    ],
    DocumentType.CERTIFICATE.value: [
        RequiredField(
            label="Supplier name",
            entity_path="supplier.name",
            severity=GapSeverity.HIGH,
            suggestion="Ensure the certificate names the certified supplier.",
        ),
        RequiredField(
            label="Certification status",
            entity_path="supplier.certification_status",
            severity=GapSeverity.CRITICAL,
            suggestion="Confirm the certification status stated on the certificate.",
        ),
    ],
    DocumentType.OTHER.value: _GENERAL_FIELDS,
    GENERAL_DOC_TYPE: _GENERAL_FIELDS,
}


class EvidenceGapAnalyzer:
    """Pure-computation analyzer for missing required evidence.

    Stateless: holds no per-request state, performs no I/O. Safe to share a single
    instance across requests.
    """

    def analyze(
        self,
        extraction_result: ExtractionResult,
        document_type: str = GENERAL_DOC_TYPE,
    ) -> EvidenceGapResult:
        """Compute evidence gaps for an extracted document on demand.

        Args:
            extraction_result: ExtractionResult from Task 38 (required)
            document_type: Document type string. Recognized DocumentType values use
                their specific required-field catalogue; "general" or any unrecognized
                value falls back to the general baseline catalogue.

        Returns:
            EvidenceGapResult with detected gaps, counts, and completeness_score.

        Raises:
            ValueError: If extraction_result is None.
        """
        if extraction_result is None:
            raise ValueError("extraction_result is required for evidence gap analysis")

        required_fields = self._catalogue_for(document_type)

        gaps: list[EvidenceGap] = []
        for field in required_fields:
            value = self._resolve_value(extraction_result, field.entity_path)
            if self._is_missing(value, falsy_is_missing=field.falsy_is_missing):
                gaps.append(self._build_gap(field, document_type))

        total_required = len(required_fields)
        required_found = total_required - len(gaps)
        completeness = self._completeness(required_found, total_required)

        logger.info(
            "Evidence gap analysis complete: document_type=%s, gaps=%d/%d, "
            "completeness=%.3f",
            document_type,
            len(gaps),
            total_required,
            completeness,
        )

        return EvidenceGapResult(
            document_id=extraction_result.document_id,
            document_type=document_type,
            gaps=gaps,
            total_required=total_required,
            required_found=required_found,
            completeness_score=completeness,
            is_complete=not gaps,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _catalogue_for(self, document_type: str) -> list[RequiredField]:
        """Return the required-fields catalogue for a document type.

        Falls back to the general baseline for "general" or any unrecognized value.

        Args:
            document_type: Document type string.

        Returns:
            List of RequiredField definitions.
        """
        return REQUIRED_FIELDS_BY_DOC_TYPE.get(
            document_type, REQUIRED_FIELDS_BY_DOC_TYPE[GENERAL_DOC_TYPE]
        )

    def _resolve_value(self, extraction_result: ExtractionResult, entity_path: str) -> object:
        """Resolve a dotted entity path to its value on the extraction result.

        Args:
            extraction_result: The extraction result to read from.
            entity_path: Dotted attribute path (e.g. "supplier.name").

        Returns:
            The resolved value, or None if any segment of the path is absent.
        """
        current: object = extraction_result
        for segment in entity_path.split("."):
            current = getattr(current, segment, None)
            if current is None:
                return None
        return current

    def _is_missing(self, value: object, falsy_is_missing: bool = False) -> bool:
        """Determine whether a resolved value counts as missing evidence.

        None and empty/whitespace-only strings are always missing. Other falsy
        values (e.g. a `False` boolean or `0.0`) count as present unless the field
        opts in via ``falsy_is_missing`` — used for flags like
        ``location.geolocation_verified`` where `False` means "not verified".

        Args:
            value: The resolved value.
            falsy_is_missing: When True, any falsy value is treated as missing.

        Returns:
            True if the value should be treated as missing.
        """
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if falsy_is_missing:
            return not value
        return False

    def _build_gap(self, field: RequiredField, document_type: str) -> EvidenceGap:
        """Build an EvidenceGap for a missing required field.

        Args:
            field: The required field definition that was missing.
            document_type: Document type string the gap was evaluated under.

        Returns:
            A populated EvidenceGap.
        """
        return EvidenceGap(
            document_type=document_type,
            required_field=field.label,
            entity_path=field.entity_path,
            severity=field.severity,
            suggested_action=field.suggestion,
        )

    def _completeness(self, found: int, total: int) -> float:
        """Compute completeness as found / total, clamped to [0.0, 1.0].

        A document type with no required fields is trivially complete (1.0).

        Args:
            found: Number of required fields found present.
            total: Total number of required fields.

        Returns:
            Completeness fraction in [0.0, 1.0].
        """
        if total <= 0:
            return 1.0
        return max(0.0, min(1.0, found / total))
