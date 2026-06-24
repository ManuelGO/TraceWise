"""LangGraph agents for TraceWise multi-agent orchestration (Phase 6).

Each agent wraps existing Phase 1-5 services as a compiled LangGraph ``StateGraph``.
Agents contain orchestration only; domain logic lives in ``app.services``.
"""

from app.agents.document_ingestion_agent import (
    DocumentIngestionState,
    build_document_ingestion_graph,
    run_document_ingestion,
)
from app.agents.entity_extraction_agent import (
    EntityExtractionState,
    build_entity_extraction_graph,
    run_entity_extraction,
)
from app.agents.retrieval_agent import (
    RetrievalState,
    build_retrieval_graph,
    run_retrieval,
)
from app.agents.risk_assessment_agent import (
    RiskAssessmentState,
    build_risk_assessment_graph,
    run_risk_assessment,
)

__all__ = [
    "DocumentIngestionState",
    "EntityExtractionState",
    "RetrievalState",
    "RiskAssessmentState",
    "build_document_ingestion_graph",
    "build_entity_extraction_graph",
    "build_retrieval_graph",
    "build_risk_assessment_graph",
    "run_document_ingestion",
    "run_entity_extraction",
    "run_retrieval",
    "run_risk_assessment",
]
