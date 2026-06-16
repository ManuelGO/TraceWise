"""Pydantic request/response schemas."""

from app.schemas.compliance_case import (
    ComplianceCaseCreate,
    ComplianceCaseRead,
    ComplianceCaseUpdate,
)
from app.schemas.consistency import (
    ConflictSeverity,
    ConsistencyReport,
    FieldConflict,
    LogicalConflict,
    LogicalConflictType,
    TemporalConflict,
    TemporalConflictType,
)
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.schemas.evidence_gap import (
    EvidenceGap,
    EvidenceGapRequest,
    EvidenceGapResult,
    GapSeverity,
)
from app.schemas.extracted_evidence import ExtractedEvidenceCreate, ExtractedEvidenceRead
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.generated_report import GeneratedReportCreate, GeneratedReportRead
from app.schemas.job import JobCreate, JobRead
from app.schemas.review_decision import ReviewDecisionCreate, ReviewDecisionRead
from app.schemas.risk_assessment import RiskAssessmentCreate, RiskAssessmentRead
from app.schemas.validation import (
    SeverityLevel,
    ValidatedExtractionResult,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)

__all__ = [
    "ComplianceCaseCreate",
    "ComplianceCaseRead",
    "ComplianceCaseUpdate",
    "ConflictSeverity",
    "ConsistencyReport",
    "DocumentCreate",
    "DocumentRead",
    "DocumentUpdate",
    "EvidenceGap",
    "EvidenceGapRequest",
    "EvidenceGapResult",
    "ExtractedEvidenceCreate",
    "ExtractedEvidenceRead",
    "ExtractionResult",
    "FieldConflict",
    "GapSeverity",
    "GeneratedReportCreate",
    "GeneratedReportRead",
    "JobCreate",
    "JobRead",
    "LocationInfo",
    "LogicalConflict",
    "LogicalConflictType",
    "ProductInfo",
    "ReviewDecisionCreate",
    "ReviewDecisionRead",
    "RiskAssessmentCreate",
    "RiskAssessmentRead",
    "SeverityLevel",
    "ShipmentInfo",
    "SupplierInfo",
    "TemporalConflict",
    "TemporalConflictType",
    "ValidatedExtractionResult",
    "ValidationFailure",
    "ValidationResult",
    "ValidationRuleType",
]
