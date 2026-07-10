"""Compliance Workflow (Task 51, Phase 6).

The top-level LangGraph ``StateGraph`` that composes the six Phase 6 agents (Tasks 45-50) into one
coherent, end-to-end compliance workflow. It is *orchestration of orchestrators*: each node wraps
one agent's compiled graph, bridges that agent's output keys to the next agent's input keys, and
threads a single shared ``WorkflowState``. It does NOT re-run or re-implement any agent's domain
logic (see ``PHASE_6_ARCHITECTURE.md`` Section 1) -- extraction, retrieval, scoring, grounding, and
rendering all stay in the agents and their wrapped Phase 1-5 services.

Pipeline::

    START
      -> ingest?       (optional, gated by file_bytes)
      -> extract
      -> retrieve
      -> assess_risk
      -> validate
      -> generate
      -> persist       (opens/commits/closes the per-run session; no-op when persist=False)
      -> route_review  (terminal: sets overall_status + needs_human_review) -> END

Any node routes straight to END when an upstream error was recorded; a wrapped agent that finishes
with its OWN ``error`` set is re-surfaced as a workflow-level ``workflow_fail(<step>, ...)`` so the
whole pipeline shares ONE error channel (``app.agents._agent_helpers``). Downstream nodes never run
after an error.

Design decisions (coordinator-confirmed, 2026-06-30 -- see ``phase-6/2026-06-30-task-51-*/plan.md``):
- Scope: steps 2-6 (extraction -> report) wired fully; document ingestion is an OPTIONAL leading node
  gated on ``file_bytes`` (the workflow accepts a pre-ingested state by default); human review is a
  routing SIGNAL only (``needs_human_review`` + ``overall_status``) -- the queue/API is Task 53.
- Evidence ``answer``: validate ``risk_assessment.reasoning`` (the LLM narrative that most needs
  grounding), falling back to the retrieval ``context`` when reasoning is empty.
- ``source_quality``: thread the mean retrieval ``similarity_score`` into Risk (default 0.5 when there
  are no sources) -- closing the loop Task 48 left for Task 51.
- Persistence: persist the ``GeneratedReport`` via ``GeneratedReportRepository`` (real ``case_id`` +
  session), closing the Task 50 deferral; ``RiskAssessment``/``ConsistencyCheck`` rows remain
  carried-forward. ``persist_node`` opens and closes its OWN session locally (from the injected
  ``session_factory``); it is NOT threaded through state, so the state stays serializable.
- Business outcomes are NOT errors (Architecture Section 2.8): a ``non_compliant``/``needs_review``
  verdict, an ungrounded ``evidence_validation``, a rule-only risk fallback, and zero retrieval
  results all reach ``route_review``/END normally with ``error=None``.

This task does NOT configure a checkpointer; ``build_compliance_workflow`` accepts an optional
``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
import math
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._agent_helpers import route_after
from app.models import WorkflowStepStatus
from app.models.vector_embedding import SearchResult
from app.monitoring.retry_metrics import _sanitize_log
from app.workflows.langgraph_setup import AgentGraph, WorkflowState, workflow_fail
from app.workflows.state_persistence import WorkflowCheckpointer

if TYPE_CHECKING:
    # Only forwarded to ``compile(checkpointer=...)`` -- never constructed here -- so a TYPE_CHECKING
    # import is enough to type the LangGraph-native saver seam without a runtime import.
    from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)

_GENERATED_BY = "compliance-workflow"
_DEFAULT_DOCUMENT_TYPE = "general"
# Default retrieval-similarity proxy when no sources were retrieved (matches ConfidenceScorer /
# the Risk agent's own ``source_quality`` default so a standalone run behaves identically).
_DEFAULT_SOURCE_QUALITY = 0.5

# Only ``compliant`` clears without a human; every other verdict routes to review (Task 53).
_STATUS_COMPLIANT = "compliant"


# ===== Nodes =====


async def ingest_node(state: WorkflowState, ingestion_graph: AgentGraph) -> dict[str, Any]:
    """Optionally ingest the raw document (first node, gated on ``file_bytes``).

    When the caller supplies ``file_bytes`` the workflow runs the Document Ingestion Agent (Task 45)
    to extract text + persist embeddings; its ``extracted_text`` becomes the extraction input. When
    ``file_bytes`` is absent the document was already ingested by the existing Phase 1-4 path -- this
    node is a no-op pass-through (the caller supplies ``document_text`` directly). A wrapped ingestion
    ``error`` is re-surfaced as a workflow ``"ingestion"`` error.
    """
    if not state.get("file_bytes"):
        logger.info("Ingestion skipped: no file_bytes (pre-ingested document)")
        return {}

    result = await ingestion_graph.ainvoke(
        {
            "document_id": state.get("document_id", ""),
            "filename": state.get("filename", ""),
            "file_bytes": state.get("file_bytes"),
            "document_extraction_id": state.get("document_extraction_id", ""),
        }
    )
    if result.get("error"):
        return workflow_fail("ingestion", str(result["error"]))

    logger.info(
        "Ingestion complete: %d char(s) extracted, %d embedding(s) stored",
        len(result.get("extracted_text") or ""),
        result.get("stored_count", 0),
    )
    return {
        "extracted_text": result.get("extracted_text", ""),
        "stored_count": result.get("stored_count", 0),
        "document_type": result.get("document_type") or _DEFAULT_DOCUMENT_TYPE,
    }


async def extract_node(state: WorkflowState, extraction_graph: AgentGraph) -> dict[str, Any]:
    """Extract + validate structured entities (Entity Extraction Agent, Task 46).

    Feeds the document text (from ingestion's ``extracted_text`` when present, else the caller's
    ``document_text``) to the extraction agent and surfaces its ``extraction_result``. The embedded
    ``ValidationResult`` (``validated_result.validation``) is bridged out as ``validation_result`` for
    the Risk agent's optional input. Missing document text, or a wrapped extraction ``error``, is a
    permanent ``"extraction"`` error.
    """
    document_text = state.get("extracted_text") or state.get("document_text") or ""
    if not document_text.strip():
        return workflow_fail("extraction", "No document text available for entity extraction")

    result = await extraction_graph.ainvoke(
        {
            "document_id": state.get("document_id", ""),
            "document_extraction_id": state.get("document_extraction_id", ""),
            "document_text": document_text,
            "context": state.get("context", ""),
        }
    )
    if result.get("error"):
        return workflow_fail("extraction", str(result["error"]))

    extraction_result = result.get("extraction_result")
    if extraction_result is None:
        return workflow_fail("extraction", "Extraction agent returned no extraction_result")

    update: dict[str, Any] = {
        "extraction_result": extraction_result,
        "validation_status": result.get("validation_status", ""),
    }
    # Bridge the embedded ValidationResult out for the Risk agent's optional ``validation_result``.
    validated_result = result.get("validated_result")
    if validated_result is not None:
        update["validation_result"] = validated_result.validation

    # ``validation_status`` is agent-derived; sanitize before logging (log-injection guard, matching
    # the sibling report agent's INFO-log convention).
    logger.info(
        "Extraction complete: status=%s",
        _sanitize_log(update["validation_status"] or "unknown"),
    )
    return update


async def retrieve_node(state: WorkflowState, retrieval_graph: AgentGraph) -> dict[str, Any]:
    """Retrieve grounded context for the compliance query (Retrieval Agent, Task 47).

    Scopes retrieval to this document's extraction (``extraction_ids=[document_extraction_id]``,
    Architecture Section 3-E) and surfaces the assembled ``context`` (renamed ``retrieval_context`` to
    avoid colliding with the extraction ``context`` input) and ordered ``sources``. Zero results is a
    VALID outcome (empty context, ``source_quality`` falls back to the default) -- not an error. A
    wrapped retrieval ``error`` (empty query / bad ids / RetrievalError) is a ``"retrieval"`` error.
    """
    query = state.get("query", "")
    if not query.strip():
        return workflow_fail("retrieval", "No query provided for retrieval")

    extraction_id = state.get("document_extraction_id")
    extraction_ids = [extraction_id] if extraction_id else None

    result = await retrieval_graph.ainvoke({"query": query, "extraction_ids": extraction_ids})
    if result.get("error"):
        return workflow_fail("retrieval", str(result["error"]))

    sources: list[SearchResult] = result.get("sources") or []
    source_quality = _mean_source_quality(sources)

    logger.info(
        "Retrieval complete: %d source(s), source_quality=%.3f",
        len(sources),
        source_quality,
    )
    return {
        "retrieval_context": result.get("context", ""),
        "sources": sources,
        "result_count": result.get("result_count", len(sources)),
        "source_quality": source_quality,
    }


async def assess_risk_node(state: WorkflowState, risk_graph: AgentGraph) -> dict[str, Any]:
    """Assess compliance risk (Risk Assessment Agent, Task 48).

    Maps the extraction ``extraction_result`` to the agent's required ``entities`` and threads the
    optional ``validation_result`` (from extraction) + ``source_quality`` (from retrieval). The linear
    single-document path carries no ``consistency_result`` (no multi-doc evidence set -- the agent
    treats that as a valid skipped check). Surfaces the assembled ``risk_assessment`` dict. Missing
    entities, or a wrapped risk ``error``, is a permanent ``"risk"`` error.
    """
    entities = state.get("extraction_result")
    if entities is None:
        return workflow_fail("risk", "No extraction_result available for risk assessment")

    agent_input: dict[str, Any] = {
        "entities": entities,
        "document_type": state.get("document_type") or _DEFAULT_DOCUMENT_TYPE,
        "source_quality": state.get("source_quality", _DEFAULT_SOURCE_QUALITY),
    }
    validation_result = state.get("validation_result")
    if validation_result is not None:
        agent_input["validation_result"] = validation_result

    result = await risk_graph.ainvoke(agent_input)
    if result.get("error"):
        return workflow_fail("risk", str(result["error"]))

    risk_assessment = result.get("risk_assessment")
    if not risk_assessment:
        return workflow_fail("risk", "Risk agent returned no risk_assessment")

    # ``risk_level`` is LLM/document-derived; sanitize the string (the numeric ``risk_score`` cannot
    # carry a log-injection payload, so it is logged as-is).
    logger.info(
        "Risk assessment complete: level=%s, score=%s",
        _sanitize_log(str(risk_assessment.get("risk_level") or "")),
        risk_assessment.get("risk_score"),
    )
    return {"risk_assessment": risk_assessment}


async def validate_node(state: WorkflowState, evidence_graph: AgentGraph) -> dict[str, Any]:
    """Validate evidence grounding + consistency (Evidence Validation Agent, Task 49).

    Bridges the ``answer`` the agent grounds: the ``risk_assessment.reasoning`` narrative (the
    LLM-written text that most needs grounding), falling back to the retrieval ``context`` when
    reasoning is empty. Passes the retrieval ``sources`` as ``search_results``. When there is no
    answer text at all (no reasoning AND no context) evidence validation is SKIPPED -- a valid
    outcome that reaches END normally (the report notes validation was not run). A wrapped evidence
    ``error`` (consistency ValueError / unexpected) is a permanent ``"evidence"`` error.
    """
    risk_assessment = state.get("risk_assessment") or {}
    # ``or ""`` before ``.strip()`` guards against a ``None`` reasoning / retrieval_context (either
    # key may be absent or explicitly ``None``); ``.strip()`` on ``None`` would raise.
    reasoning = str(risk_assessment.get("reasoning") or "").strip()
    answer = reasoning or str(state.get("retrieval_context") or "").strip()

    if not answer:
        logger.info("Evidence validation skipped: no answer text to validate")
        return {"answer": ""}

    result = await evidence_graph.ainvoke(
        {
            "answer": answer,
            "search_results": state.get("sources") or [],
            "case_id": state.get("case_id"),
        }
    )
    if result.get("error"):
        return workflow_fail("evidence", str(result["error"]))

    evidence_validation = result.get("evidence_validation")
    if not evidence_validation:
        return workflow_fail("evidence", "Evidence agent returned no evidence_validation")

    # Coerce ``is_valid`` to a real bool so a stray non-bool agent value renders as True/False rather
    # than reaching the log verbatim; ``grounding_score`` is numeric (``%.2f``), so it cannot inject.
    logger.info(
        "Evidence validation complete: is_valid=%s, grounding=%.2f",
        bool(evidence_validation.get("is_valid")),
        evidence_validation.get("grounding_score", 0.0),
    )
    return {"answer": answer, "evidence_validation": evidence_validation}


async def generate_node(state: WorkflowState, report_graph: AgentGraph) -> dict[str, Any]:
    """Render the final compliance report (Report Generation Agent, Task 50).

    Passes the assembled ``risk_assessment`` (required), ``evidence_validation`` (optional -- absent
    when validation was skipped), ``sources``, and header metadata (``case_id`` / ``query``). Surfaces
    the markdown ``report_content`` (the ``GeneratedReportCreate.report_content`` contract) and the
    structured ``report`` dict. Missing ``risk_assessment``, or a wrapped report ``error``, is a
    permanent ``"report"`` error.
    """
    risk_assessment = state.get("risk_assessment")
    if not risk_assessment:
        return workflow_fail("report", "No risk_assessment available for report generation")

    result = await report_graph.ainvoke(
        {
            "risk_assessment": risk_assessment,
            "evidence_validation": state.get("evidence_validation"),
            "sources": state.get("sources") or [],
            "case_id": state.get("case_id"),
            "query": state.get("query"),
        }
    )
    if result.get("error"):
        return workflow_fail("report", str(result["error"]))

    report_content = result.get("report_content")
    report = result.get("report")
    if not report_content:
        return workflow_fail("report", "Report agent returned no report_content")
    if not report:
        return workflow_fail("report", "Report agent returned no report dict")

    logger.info("Report generated: %d char(s)", len(report_content))
    return {"report_content": report_content, "report": report}


async def persist_node(
    state: WorkflowState,
    session_factory: Callable[[], AsyncSession] | None,
    persist: bool,
) -> dict[str, Any]:
    """Persist the generated report (closes the Task 50 persistence deferral).

    When ``persist`` is True this opens a single per-run ``AsyncSession`` from ``session_factory``,
    writes the ``GeneratedReport`` row (via ``GeneratedReportRepository``), commits, and closes the
    session on EVERY terminal path (success, commit failure, unexpected exception) -- the Task 46
    session-lifecycle pattern. When ``persist`` is False (unit tests / dry runs) the node is a no-op
    that opens no session, keeping offline runs DB-free. A commit failure routes to END with a generic
    ``"persist"`` message; the raw DB exception (which can embed DSN/credentials) is logged only.
    """
    if not persist:
        logger.info("Persistence skipped (persist=False)")
        return {}

    # Prerequisite guards, cheapest-first: the session factory is the precondition for the whole
    # write, so check it before parsing anything.
    if session_factory is None:
        return workflow_fail("persist", "No session_factory configured for persistence")

    report_content = state.get("report_content")
    if not report_content:
        return workflow_fail("persist", "No report_content available to persist")

    raw_case_id = state.get("case_id", "")
    try:
        case_id = UUID(raw_case_id)
    except (ValueError, AttributeError, TypeError):
        # The raw id is caller-supplied; sanitize + bound it before it reaches the error/log
        # (``_sanitize_log`` strips only newline/CR/NUL, so also cap the length).
        safe_id = _sanitize_log(str(raw_case_id))[:128]
        return workflow_fail("persist", f"Invalid case_id for persistence: {safe_id}")

    # Local imports keep the module import-light and offline tests (persist=False) untouched.
    from app.db.repositories.generated_report import GeneratedReportRepository
    from app.models import GeneratedReport

    # Assign a real ``UUID`` id up front (the column is ``Uuid(as_uuid=True)`` with a flush-time
    # ``default=uuid4``): passing a ``UUID`` object matches the column type and the flushed default,
    # and makes the returned id deterministic without a DB round-trip.
    report_id = uuid4()
    session: AsyncSession | None = None
    try:
        session = session_factory()
        repository = GeneratedReportRepository()
        report_row = GeneratedReport(
            id=report_id,
            case_id=case_id,
            report_content=report_content,
            generated_by=_GENERATED_BY,
        )
        await repository.create(session, report_row)
        await session.commit()
    except Exception:
        logger.error("Failed to persist generated report for case %s", case_id, exc_info=True)
        return workflow_fail("persist", "Failed to persist generated report")
    finally:
        # ``session`` stays None if the factory itself raised -- guard so ``close`` never raises a
        # NameError that would mask the original failure.
        if session is not None:
            await session.close()

    logger.info("Persisted generated report %s for case %s", report_id, case_id)
    return {"generated_report_id": str(report_id)}


def route_review_node(state: WorkflowState) -> dict[str, Any]:
    """Set the human-review routing signal (terminal node -- the Task 53 hand-off seam).

    Reads the report's ``overall_status`` (compliant / non_compliant / needs_review) and derives the
    ``needs_human_review`` flag: every non-``compliant`` verdict routes to human review. This node
    only produces the SIGNAL; the review queue, assignment, and API are Task 53. Pure -- cannot fail.
    """
    report = state.get("report") or {}
    overall_status = str(report.get("overall_status") or _STATUS_COMPLIANT)
    needs_human_review = overall_status != _STATUS_COMPLIANT

    logger.info(
        "Review routing: status=%s, needs_human_review=%s",
        _sanitize_log(overall_status),
        needs_human_review,
    )
    return {"overall_status": overall_status, "needs_human_review": needs_human_review}


# ===== Helpers =====


def _mean_source_quality(sources: list[SearchResult]) -> float:
    """Mean ``similarity_score`` across retrieved sources -> the Risk agent's ``source_quality``.

    Falls back to ``_DEFAULT_SOURCE_QUALITY`` when there are no sources (zero-result retrieval is a
    valid outcome) or when every score is non-finite, and clamps to ``[0.0, 1.0]`` so a malformed
    score never escapes the expected range.

    NaN/inf scores are dropped BEFORE the mean: a ``max(0.0, min(1.0, nan))`` clamp does NOT catch
    NaN (NaN loses every comparison, so ``min(1.0, nan)`` returns ``1.0``), which would silently turn
    one bad score into a perfect ``source_quality`` and bias the downstream confidence upward.
    """
    if not sources:
        return _DEFAULT_SOURCE_QUALITY
    finite_scores = [
        score for s in sources if math.isfinite(score := float(s["similarity_score"]))
    ]
    if not finite_scores:
        return _DEFAULT_SOURCE_QUALITY
    mean = sum(finite_scores) / len(finite_scores)
    return max(0.0, min(1.0, mean))


def _with_checkpoint(
    step: str,
    node: Callable[[WorkflowState], Awaitable[dict[str, Any]]],
    checkpointer: WorkflowCheckpointer,
) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
    """Wrap a node so its merged post-node state is checkpointed after it runs (Task 52).

    Runs ``node``, then persists ONE checkpoint for ``step`` from the state as the graph will see it
    after this node (incoming ``state`` merged with the node's partial ``update``). The status is
    ``failed`` when the node recorded an ``error`` (the run short-circuits from here), else
    ``completed``. Checkpointing is best-effort inside ``save_checkpoint`` -- a persistence failure
    never changes the node's returned update. ``run_id``/``case_id`` come from the state; a run with no
    ``run_id`` yet (should not happen -- ``run_compliance_workflow`` seeds one) is skipped by the
    checkpointer's own id guard.
    """

    async def _wrapped(state: WorkflowState) -> dict[str, Any]:
        update = await node(state)
        merged: WorkflowState = cast(WorkflowState, {**state, **update})
        error = update.get("error")
        status = WorkflowStepStatus.FAILED if error else WorkflowStepStatus.COMPLETED
        await checkpointer.save_checkpoint(
            run_id=str(merged.get("run_id", "")),
            case_id=str(merged.get("case_id", "")),
            step=step,
            status=status,
            state=merged,
            error=str(error) if error else None,
            error_type=update.get("error_type"),
        )
        return update

    return _wrapped


# ===== Graph assembly =====


def build_compliance_workflow(
    *,
    ingestion_graph: AgentGraph | None = None,
    extraction_graph: AgentGraph | None = None,
    retrieval_graph: AgentGraph | None = None,
    risk_graph: AgentGraph | None = None,
    evidence_graph: AgentGraph | None = None,
    report_graph: AgentGraph | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    persist: bool = True,
    state_checkpointer: WorkflowCheckpointer | None = None,
    checkpointing_enabled: bool | None = None,
    checkpointer: "BaseCheckpointSaver | None" = None,
) -> CompiledStateGraph:
    """Build and compile the top-level compliance workflow ``StateGraph``.

    Composes the six Phase 6 agents in sequence plus a persistence + review-routing tail. Every agent
    graph and the ``session_factory`` are injectable so ``tests/unit`` run fully offline; defaults
    build the real agent graphs lazily (and the real cached session factory) only on the non-injected
    path. Because the per-run session lives in ``WorkflowState`` rather than a builder holder,
    concurrent ``ainvoke`` calls on one compiled workflow stay isolated.

    Args:
        ingestion_graph: Document ingestion agent graph (Task 45). Optional -- only invoked when the
            caller supplies ``file_bytes``. Defaults to ``build_document_ingestion_graph()``.
        extraction_graph: Entity extraction agent graph (Task 46). Defaults to the real graph.
        retrieval_graph: Retrieval agent graph (Task 47). Defaults to the real graph.
        risk_graph: Risk assessment agent graph (Task 48). Defaults to the real graph.
        evidence_graph: Evidence validation agent graph (Task 49). Defaults to the real graph.
        report_graph: Report generation agent graph (Task 50). Defaults to the real graph.
        session_factory: Zero-arg callable returning an ``AsyncSession`` for the persist node
            (injected for testing). Defaults to the cached engine/session factory used by the Celery
            tasks. Ignored when ``persist=False``.
        persist: When True (default) ``persist_node`` writes the ``GeneratedReport`` row; when False
            it is a no-op (no session opened) -- the offline default for unit tests.
        state_checkpointer: Optional ``WorkflowCheckpointer`` (Task 52). When provided AND checkpointing
            is enabled, each node is wrapped so its post-node state is persisted as a
            ``WorkflowStateCheckpoint`` (fault tolerance + auditability). Injected for testing; defaults
            to a real one built lazily from ``session_factory`` when checkpointing is enabled. Writes
            are best-effort and never break a run.
        checkpointing_enabled: Override for the ``WORKFLOW_CHECKPOINTING_ENABLED`` config gate. When
            None (default) the config value is used; pass True/False to force it (e.g. in tests). No
            node is wrapped when checkpointing is disabled -- the offline/default behavior is unchanged.
        checkpointer: Optional LangGraph ``BaseCheckpointSaver`` forwarded to ``compile(checkpointer=)``.
            Distinct from ``state_checkpointer`` (the Task 52 domain checkpointer): this is the LangGraph
            graph-level saver seam, left inert (``None``) by default -- see the note at the ``compile``
            call below.

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    # Resolve each injectable graph to a concrete ``AgentGraph``. The real ``build_*_graph`` helpers
    # return a ``CompiledStateGraph`` (structurally an ``AgentGraph`` -- it exposes ``ainvoke``); the
    # ``cast`` states that intent so the closures below capture a non-optional, uniform type.
    if ingestion_graph is None:
        from app.agents.document_ingestion_agent import build_document_ingestion_graph

        ingestion_graph = cast(AgentGraph, build_document_ingestion_graph())
    if extraction_graph is None:
        from app.agents.entity_extraction_agent import build_entity_extraction_graph

        extraction_graph = cast(AgentGraph, build_entity_extraction_graph())
    if retrieval_graph is None:
        from app.agents.retrieval_agent import build_retrieval_graph

        retrieval_graph = cast(AgentGraph, build_retrieval_graph())
    if risk_graph is None:
        from app.agents.risk_assessment_agent import build_risk_assessment_graph

        risk_graph = cast(AgentGraph, build_risk_assessment_graph())
    if evidence_graph is None:
        from app.agents.evidence_validation_agent import build_evidence_validation_graph

        evidence_graph = cast(AgentGraph, build_evidence_validation_graph())
    if report_graph is None:
        from app.agents.report_generation_agent import build_report_generation_graph

        report_graph = cast(AgentGraph, build_report_generation_graph())
    # Resolve the checkpointing gate: explicit override wins, else the config flag.
    if checkpointing_enabled is None:
        from app.config import get_settings

        checkpointing_enabled = get_settings().WORKFLOW_CHECKPOINTING_ENABLED

    # A session factory is needed for persistence OR for the default state checkpointer.
    if session_factory is None and (persist or (checkpointing_enabled and state_checkpointer is None)):
        from app.tasks.document_tasks import _get_engine_and_factory

        _, session_factory = _get_engine_and_factory()

    # Build a default state checkpointer only when checkpointing is enabled and none was injected.
    if checkpointing_enabled and state_checkpointer is None and session_factory is not None:
        state_checkpointer = WorkflowCheckpointer(session_factory)

    # After resolution every graph is non-None; bind to locals so mypy narrows away the ``| None``.
    ingest_graph: AgentGraph = ingestion_graph
    extract_graph: AgentGraph = extraction_graph
    retrieval: AgentGraph = retrieval_graph
    risk: AgentGraph = risk_graph
    evidence: AgentGraph = evidence_graph
    report: AgentGraph = report_graph

    async def _ingest(state: WorkflowState) -> dict[str, Any]:
        return await ingest_node(state, ingest_graph)

    async def _extract(state: WorkflowState) -> dict[str, Any]:
        return await extract_node(state, extract_graph)

    async def _retrieve(state: WorkflowState) -> dict[str, Any]:
        return await retrieve_node(state, retrieval)

    async def _assess_risk(state: WorkflowState) -> dict[str, Any]:
        return await assess_risk_node(state, risk)

    async def _validate(state: WorkflowState) -> dict[str, Any]:
        return await validate_node(state, evidence)

    async def _generate(state: WorkflowState) -> dict[str, Any]:
        return await generate_node(state, report)

    async def _persist(state: WorkflowState) -> dict[str, Any]:
        return await persist_node(state, session_factory, persist)

    async def _route_review(state: WorkflowState) -> dict[str, Any]:
        # ``route_review_node`` is pure/sync; the async wrapper keeps a uniform node type so the
        # checkpoint wrapper (which awaits every node) treats it like the rest.
        return route_review_node(state)

    # When checkpointing is active, wrap each node so its post-node state is persisted (Task 52).
    # ``checkpointing_enabled`` alone is not enough -- a checkpointer must have been resolved (it is
    # None if no session factory was available). When inactive, ``_cp`` is an identity wrapper so the
    # default/offline path is byte-for-byte the Task 51 behavior.
    _active_checkpointer = state_checkpointer if checkpointing_enabled else None

    def _cp(
        step: str, node: Callable[[WorkflowState], Awaitable[dict[str, Any]]]
    ) -> Any:
        # Returns ``Any`` so ``add_node`` accepts it exactly as it accepts the bare async closures
        # (LangGraph's ``_Node`` union is not expressible here); the wrapper preserves node semantics.
        if _active_checkpointer is None:
            return node
        return _with_checkpoint(step, node, _active_checkpointer)

    builder: StateGraph = StateGraph(WorkflowState)
    builder.add_node("ingest", _cp("ingest", _ingest))
    builder.add_node("extract", _cp("extract", _extract))
    builder.add_node("retrieve", _cp("retrieve", _retrieve))
    builder.add_node("assess_risk", _cp("assess_risk", _assess_risk))
    builder.add_node("validate", _cp("validate", _validate))
    builder.add_node("generate", _cp("generate", _generate))
    builder.add_node("persist", _cp("persist", _persist))
    builder.add_node("route_review", _cp("route_review", _route_review))

    builder.add_edge(START, "ingest")
    # Every node can record a permanent error (bad input / wrapped-agent error / persist failure) ->
    # short-circuit to END. route_review cannot fail, but routing into it stays conditional so a
    # persist error still short-circuits cleanly.
    builder.add_conditional_edges("ingest", route_after("extract"))
    builder.add_conditional_edges("extract", route_after("retrieve"))
    builder.add_conditional_edges("retrieve", route_after("assess_risk"))
    builder.add_conditional_edges("assess_risk", route_after("validate"))
    builder.add_conditional_edges("validate", route_after("generate"))
    builder.add_conditional_edges("generate", route_after("persist"))
    builder.add_conditional_edges("persist", route_after("route_review"))
    builder.add_edge("route_review", END)

    # Task 52 persists workflow state via the DOMAIN ``state_checkpointer`` above (a
    # ``WorkflowStateCheckpoint`` row per node), NOT via this LangGraph graph-level saver. The
    # ``checkpointer`` seam is left for optional LangGraph-native checkpointing: in LangGraph 1.0,
    # ``checkpointer=None`` INHERITS a parent graph's checkpointer when this graph is embedded as a
    # subgraph (it does NOT force "off"; ``checkpointer=False`` does). It is inert (``None``) by default
    # for the standalone run; pass a saver here only when LangGraph-native thread persistence is wanted.
    return builder.compile(checkpointer=checkpointer)  # None => LangGraph saver inert (domain CP is used)


async def run_compliance_workflow(
    initial_state: WorkflowState,
    *,
    graph: CompiledStateGraph | None = None,
    resume_from: str | None = None,
    state_checkpointer: WorkflowCheckpointer | None = None,
) -> WorkflowState:
    """Run the compliance workflow over ``initial_state``.

    Always ensures the state carries a ``run_id`` (generated when absent) so every run is
    identifiable and its checkpoints (Task 52) are groupable. When ``resume_from`` is given, the run's
    ``initial_state`` is first SEEDED from the newest checkpoint of that run (recovery): the loaded
    state is merged UNDER the caller's ``initial_state`` (caller keys win), and the run reuses that
    ``run_id`` so the resumed run appends to the same audit trail.

    Args:
        initial_state: Caller-supplied state with at least ``case_id``, ``query``, ``document_id``,
            and ``document_extraction_id``, plus either ``document_text`` (pre-ingested fast path) or
            ``file_bytes`` + ``filename`` (to run the optional ingestion node). May include ``run_id``.
        graph: Optional pre-built compiled graph (injected for testing). When omitted a default graph
            is built with the real agent graphs and persistence enabled.
        resume_from: Optional ``run_id`` (UUID string) of a prior run to recover: its latest checkpoint
            seeds this run. Requires a ``state_checkpointer`` (injected here or built from defaults).
        state_checkpointer: Optional ``WorkflowCheckpointer`` used ONLY to load the ``resume_from``
            state (recovery). Injected for testing; defaults to a real one built from the cached session
            factory when ``resume_from`` is set. Not used for writing -- the graph's own wrapped nodes
            persist checkpoints. (Named to match ``build_compliance_workflow``'s ``state_checkpointer``;
            distinct from that builder's ``checkpointer``, which is the LangGraph-native saver seam.)

    Returns:
        The final ``WorkflowState`` after execution.
    """
    state: WorkflowState = dict(initial_state)  # type: ignore[assignment]

    if resume_from:
        if state_checkpointer is None:
            from app.tasks.document_tasks import _get_engine_and_factory

            _, session_factory = _get_engine_and_factory()
            state_checkpointer = WorkflowCheckpointer(session_factory)
        loaded = await state_checkpointer.load_latest(resume_from)
        if loaded is not None:
            # The newest checkpoint of a FAILED run carries that run's terminal ``error`` /
            # ``error_type`` (the run short-circuited from there). Seeding them verbatim would make the
            # resumed run route straight to END on the first node (``has_error`` is True) instead of
            # retrying -- defeating recovery. Strip them so the resumed run starts clean; the caller
            # can still pass a fresh ``error`` explicitly if it wants to short-circuit.
            recovered = {k: v for k, v in loaded.items() if k not in ("error", "error_type")}
            # Caller-supplied keys win over the recovered snapshot.
            state = cast(WorkflowState, {**recovered, **state})
        # Resume under the SAME run_id so the trail continues (caller may already carry it).
        state.setdefault("run_id", resume_from)

    # Guarantee a run_id for grouping + checkpointing.
    if not state.get("run_id"):
        state["run_id"] = str(uuid4())

    if graph is None:
        graph = build_compliance_workflow()
    result = await graph.ainvoke(state)
    return cast(WorkflowState, result)


__all__ = [
    "assess_risk_node",
    "build_compliance_workflow",
    "extract_node",
    "generate_node",
    "ingest_node",
    "persist_node",
    "retrieve_node",
    "route_review_node",
    "run_compliance_workflow",
    "validate_node",
]
