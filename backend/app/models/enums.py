"""Shared enum definitions across domain models."""

from enum import StrEnum


class CaseStatus(StrEnum):
    """Valid statuses for a compliance case."""

    DRAFT = "draft"
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class RiskLevel(StrEnum):
    """Risk classification levels (used by both ComplianceCase and RiskAssessment)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocumentType(StrEnum):
    """Valid document types for uploaded evidence."""

    SUPPLIER_DECLARATION = "supplier_declaration"
    INVOICE = "invoice"
    SHIPMENT_NOTE = "shipment_note"
    GEOJSON = "geojson"
    CERTIFICATE = "certificate"
    OTHER = "other"


class ProcessingStatus(StrEnum):
    """Processing status for document extraction pipeline.

    State transitions:
    - UPLOADED → VALIDATING → UPLOADED (success) OR FAILED (failure)
    - UPLOADED → EXTRACTING → EXTRACTED (success) OR FAILED (failure)
    - EXTRACTED → EMBEDDING → READY (success) OR FAILED (failure)

    Validation is a prerequisite phase; success returns to UPLOADED ready for extraction.
    """

    UPLOADED = "uploaded"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class ReviewDecisionType(StrEnum):
    """Valid decision types for compliance case reviews."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    OVERRIDE = "override"


class JobType(StrEnum):
    """Valid job types for async background processing."""

    VALIDATE_DOCUMENT = "validate_document"
    EXTRACT_TEXT = "extract_text"
    GENERATE_EMBEDDINGS = "generate_embeddings"
    EXTRACT_ENTITIES = "extract_entities"
    RISK_ASSESSMENT = "risk_assessment"
    GENERATE_REPORT = "generate_report"


class JobStatus(StrEnum):
    """Valid statuses for async job tracking."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepStatus(StrEnum):
    """Status of a single compliance-workflow step checkpoint (Task 52).

    Recorded per checkpoint row so the audit trail distinguishes a step that completed cleanly
    (``COMPLETED``), a step still mid-flight (``IN_PROGRESS``), and the step a run failed at
    (``FAILED``) -- the last of which carries the ``error``/``error_type`` for recovery.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
