"""Model-specific repository implementations."""

from app.db.repositories.compliance_case import ComplianceCaseRepository
from app.db.repositories.document import DocumentRepository
from app.db.repositories.extracted_evidence import ExtractedEvidenceRepository
from app.db.repositories.generated_report import GeneratedReportRepository
from app.db.repositories.job import JobRepository
from app.db.repositories.review_decision import ReviewDecisionRepository
from app.db.repositories.risk_assessment import RiskAssessmentRepository
from app.db.repositories.vector_embedding import VectorEmbeddingRepository
from app.db.repositories.workflow_state import WorkflowStateRepository

__all__ = [
    "ComplianceCaseRepository",
    "DocumentRepository",
    "ExtractedEvidenceRepository",
    "GeneratedReportRepository",
    "JobRepository",
    "ReviewDecisionRepository",
    "RiskAssessmentRepository",
    "VectorEmbeddingRepository",
    "WorkflowStateRepository",
]
