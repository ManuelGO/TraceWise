"""Evidence gap analysis API (Task 44).

Exposes a stateless endpoint that computes missing-evidence gaps on demand from a
Task 38 ExtractionResult. No persistence (TASK_44_COORDINATOR_DECISION.md, Option 1):
the report is computed and returned without any database writes.
"""

import logging

from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.schemas.evidence_gap import EvidenceGapRequest, EvidenceGapResult
from app.services.evidence_gap_analyzer import EvidenceGapAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evidence-gaps", tags=["evidence-gaps"])

_analyzer = EvidenceGapAnalyzer()


@router.post(
    "/analyze",
    response_model=EvidenceGapResult,
    dependencies=[Depends(require_auth)],
    summary="Analyze a document extraction for missing required evidence",
)
def analyze_evidence_gaps(payload: EvidenceGapRequest) -> EvidenceGapResult:
    """Compute missing-evidence gaps for an extracted document.

    Compares the supplied extraction result against the required-field catalogue for
    the given document type and returns the detected gaps plus a completeness score.

    Args:
        payload: Request body with the extraction result and document type.

    Returns:
        EvidenceGapResult with gaps, counts, and completeness_score.
    """
    return _analyzer.analyze(payload.extraction, payload.document_type)
