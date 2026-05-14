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
    """Processing status for document extraction pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewDecisionType(StrEnum):
    """Valid decision types for compliance case reviews."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    OVERRIDE = "override"


class JobType(StrEnum):
    """Valid job types for async background processing."""

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
