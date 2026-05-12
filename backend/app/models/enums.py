"""Shared enum definitions across domain models."""

from enum import Enum


class CaseStatus(str, Enum):
    """Valid statuses for a compliance case."""

    DRAFT = "draft"
    PROCESSING = "processing"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    """Risk classification levels (used by both ComplianceCase and RiskAssessment)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocumentType(str, Enum):
    """Valid document types for uploaded evidence."""

    SUPPLIER_DECLARATION = "supplier_declaration"
    INVOICE = "invoice"
    SHIPMENT_NOTE = "shipment_note"
    GEOJSON = "geojson"
    CERTIFICATE = "certificate"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    """Processing status for document extraction pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
