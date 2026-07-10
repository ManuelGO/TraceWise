"""LangGraph workflow scaffolding (Task 51, Phase 6).

Shared building blocks for the top-level compliance workflow that composes the six Phase 6 agents
(Tasks 45-50) into one coherent ``StateGraph``. This module owns:

- ``WorkflowState`` -- the single ``TypedDict`` threaded through every workflow node.
- ``AgentGraph`` -- the minimal structural protocol a wrapped agent's compiled graph satisfies
  (``ainvoke``), so unit tests can inject fakes without importing LangGraph internals.
- ``workflow_fail`` -- the workflow-level failure helper (thin wrapper over the shared
  ``agent_fail`` so the whole pipeline shares ONE error channel + routing convention).

The workflow is orchestration-of-orchestrators: it re-uses ``agent_fail`` / ``route_after`` /
``has_error`` from ``app.agents._agent_helpers`` rather than redefining the error/routing idiom, so
Task 51 stays consistent with every agent it wraps (see ``PHASE_6_ARCHITECTURE.md`` Section 1).
"""

from typing import Any, Protocol, TypedDict, runtime_checkable

from app.agents._agent_helpers import agent_fail
from app.models.vector_embedding import SearchResult
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult

_WORKFLOW_LABEL = "Compliance workflow"


@runtime_checkable
class AgentGraph(Protocol):
    """Structural type for a compiled agent graph the workflow invokes.

    Every Phase 6 agent's ``build_*_graph`` returns a LangGraph ``CompiledStateGraph`` exposing
    ``ainvoke(state) -> state``. The workflow only needs that one method, so it depends on this
    Protocol -- letting ``tests/unit`` inject a trivial fake (an object with an async ``ainvoke``)
    instead of a real compiled graph, keeping the suite fully offline.
    """

    # Positional-only + ``**kwargs`` so BOTH a trivial test fake and the real ``CompiledStateGraph``
    # (whose ``ainvoke`` names its first arg ``input`` and takes many optional kwargs) satisfy the
    # protocol structurally.
    async def ainvoke(  # pragma: no cover - structural typing only
        self, state: Any, /, **kwargs: Any
    ) -> Any: ...


class WorkflowState(TypedDict, total=False):
    """Shared state threaded through the compliance workflow graph.

    ``total=False`` so each node returns a partial update without re-declaring every key. Inputs are
    caller-supplied; later keys are filled by successive nodes. Every dict the workflow carries
    (``risk_assessment`` / ``evidence_validation`` / ``report``) already round-trips ``json.dumps``
    (Tasks 48-50), so the whole state is Task 52 checkpoint-ready. The DB session is NOT threaded
    through state -- ``persist_node`` opens and closes its own session locally -- so nothing here is
    unserializable.
    """

    # ---- Inputs (caller-supplied) ----
    run_id: str  # per-run identifier (UUID string); the workflow generates one when absent (Task 52)
    case_id: str  # required -- parent compliance case (UUID string)
    query: str  # required -- originating compliance question
    document_id: str  # required -- source document (UUID string)
    document_extraction_id: str  # required -- extraction row (UUID string); retrieval scope
    context: str  # optional -- extraction context hint
    # Ingestion inputs (only when the optional ingest node runs):
    filename: str
    file_bytes: bytes
    # Pre-ingested fast path (skip ingestion): the caller supplies the text directly instead.
    document_text: str

    # ---- ingest_node (optional) ----
    extracted_text: str
    stored_count: int
    document_type: str  # optional, default "general" (from ingestion classify or caller)

    # ---- extract_node ----
    extraction_result: ExtractionResult  # Task 46 output -> Risk's ``entities``
    validation_result: ValidationResult  # = validated_result.validation (bridge)
    validation_status: str

    # ---- retrieve_node ----
    retrieval_context: str  # = RetrievalState.context (renamed to avoid the extraction ``context``)
    sources: list[SearchResult]  # -> Evidence's search_results, Report's sources
    result_count: int
    source_quality: float  # mean source similarity -> Risk input

    # ---- assess_risk_node ----
    risk_assessment: dict[str, Any]  # Task 48 output

    # ---- validate_node ----
    answer: str  # bridged input for Evidence Validation (risk reasoning, else retrieval context)
    evidence_validation: dict[str, Any]  # Task 49 output

    # ---- generate_node (primary report output) ----
    report_content: str  # markdown == GeneratedReportCreate.report_content
    report: dict[str, Any]  # JSON-serializable structured view

    # ---- persist_node ----
    # No DB session is threaded through state: ``persist_node`` opens and closes its own session
    # locally (from the injected ``session_factory``), keeping the state fully serializable.
    generated_report_id: str | None  # set when the GeneratedReport row is written

    # ---- route_review_node (terminal) ----
    overall_status: str  # compliant | non_compliant | needs_review
    needs_human_review: bool  # Task 53 hand-off signal

    # ---- Error channel: when ``error`` is set the graph short-circuits to END. ----
    error: str | None
    # "ingestion"|"extraction"|"retrieval"|"risk"|"evidence"|"report"|"persist"
    error_type: str | None


def workflow_fail(error_type: str, message: str) -> dict[str, Any]:
    """Build a partial state update representing a permanent workflow failure.

    Thin wrapper over the shared ``agent_fail`` so the workflow uses the SAME sanitized-message +
    ``error``/``error_type`` convention as every agent it wraps. ``error_type`` names the failing
    step (``"extraction"``, ``"retrieval"``, ...) so monitoring can locate where a run stopped.
    """
    return agent_fail(_WORKFLOW_LABEL, error_type, message)


__all__ = [
    "AgentGraph",
    "WorkflowState",
    "workflow_fail",
]
