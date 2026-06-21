"""Entity Extraction Agent (Task 46, Phase 6).

A LangGraph ``StateGraph`` that orchestrates structured entity extraction by wrapping
existing Phase 5 services. The agent does NOT reimplement extraction, validation, or
retry logic -- it is a thin orchestration layer.

Pipeline::

    START -> extract -> validate -> store -> END
                |          |
                | (LLM/    | (orchestration
                |  parse   |  error)
                |  error)  |
                +----------+----------------------> END (error set)

Each node is a function ``state -> dict`` returning a partial update to
``EntityExtractionState``. Permanent errors (empty text, LLM failure, JSON/Pydantic
parse failure, orchestration failure) set ``state["error"]`` and route straight to
``END`` -- they do not raise out of the graph. This mirrors the "fail immediately, no
retry" semantics established by Task 45 (``app.agents.document_ingestion_agent``).

Design notes (coordinator-confirmed, 2026-06-21):
- extract_node wraps ``EntityExtractor.extract_entities`` (decision E: pure ``initial_state``
  input; the graph core takes ``document_text``/``document_id``/``document_extraction_id``).
- validate_node delegates the validate<->retry loop AND the ``ExtractedEntity`` flush to
  ``ValidationOrchestrator.validate_and_retry`` -- no second retry loop in the agent
  (decisions A, B).
- A single ``AsyncSession`` is opened per run; the orchestrator flushes the entity and
  store_node commits the same transaction (decision C). The session is threaded through
  the graph *state* (``_session``) rather than a builder-level holder, so concurrent
  ``ainvoke`` calls on the same compiled graph never share a session, and the session is
  closed on every terminal path (validate-error included).
- ``validation_status == "failed"`` (retries exhausted) is a persisted business outcome
  that reaches END normally; only exceptions set ``state["error"]`` (decision D).

This task does NOT configure a checkpointer; ``build_entity_extraction_graph`` accepts an
optional ``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
from collections.abc import Callable
from functools import partial
from typing import Any, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._agent_helpers import agent_fail, route_after
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidatedExtractionResult
from app.services.entity_extractor import EntityExtractionError, EntityExtractor
from app.services.extraction_retry import ExtractionRetryService
from app.services.extraction_validator import ExtractionValidator
from app.services.llm_service import LLMError
from app.services.validation_orchestrator import (
    ValidationOrchestrationError,
    ValidationOrchestrator,
)

logger = logging.getLogger(__name__)

_AGENT_LABEL = "Entity extraction"


def _fail(error_type: str, message: str) -> dict[str, Any]:
    """Partial state update for a permanent failure (see ``agent_fail``)."""
    return agent_fail(_AGENT_LABEL, error_type, message)


# ===== State contract =====


class EntityExtractionState(TypedDict, total=False):
    """Shared state threaded through the entity extraction graph.

    ``total=False`` so each node may return a partial update without re-declaring
    every key. Inputs (``document_id``, ``document_extraction_id``, ``document_text``)
    are supplied by the caller; later keys are filled in by successive nodes.
    """

    # Inputs (caller-supplied)
    document_id: str
    document_extraction_id: str
    document_text: str
    context: str

    # extract_node
    extraction_result: ExtractionResult
    # validate_node
    validated_result: ValidatedExtractionResult
    validation_status: str
    validation_score: float
    retry_count: int
    # store_node
    stored: bool

    # Internal: the per-run AsyncSession, opened by validate_node and closed by store_node.
    # Threaded through state (not a builder holder) so concurrent runs stay isolated.
    _session: AsyncSession | None

    # Error channel: when ``error`` is set the graph short-circuits to END.
    error: str | None
    error_type: str | None


# ===== Nodes =====


async def extract_node(
    state: EntityExtractionState,
    extractor: EntityExtractor,
) -> dict[str, Any]:
    """Extract structured entities from the document text via the LLM.

    Wraps ``EntityExtractor.extract_entities``. Empty/whitespace-only text, an invalid
    ``document_id``, LLM failures, and JSON/Pydantic parse failures are all treated as
    permanent extraction errors that route to END.
    """
    document_text = state.get("document_text", "")
    if not document_text or not document_text.strip():
        return _fail("extraction", "No document_text provided for extraction")

    raw_document_id = state.get("document_id", "")
    try:
        document_id = UUID(raw_document_id)
    except (ValueError, AttributeError, TypeError):
        return _fail("extraction", f"Invalid document_id: {raw_document_id!r}")

    context = state.get("context", "")
    try:
        extraction_result = await extractor.extract_entities(
            document_id=document_id,
            document_text=document_text,
            context=context,
        )
    except (EntityExtractionError, LLMError, ValidationError) as exc:
        return _fail("extraction", str(exc))

    logger.info(
        "Extracted entities for document %s (confidence %.2f)",
        document_id,
        extraction_result.extraction_confidence,
    )
    return {"extraction_result": extraction_result}


async def validate_node(
    state: EntityExtractionState,
    session_factory: Callable[[], AsyncSession],
    orchestrator_factory: Callable[[AsyncSession], ValidationOrchestrator],
) -> dict[str, Any]:
    """Validate the extraction, retrying via the orchestrator, then flush persistence.

    Delegates the full validate<->retry loop and the ``ExtractedEntity`` flush to
    ``ValidationOrchestrator.validate_and_retry`` (decisions A, B). Retries are owned by
    the orchestrator (up to ``VALIDATION_MAX_RETRIES``); this node only surfaces the
    final ``retry_count`` and ``validation_status``.

    Session lifecycle: this node opens the per-run ``AsyncSession`` (from
    ``session_factory``), constructs the orchestrator on it, and -- on the success path --
    hands the still-open session to ``store_node`` via ``_session`` in the returned state.
    On *any* terminal-error path (bad inputs, orchestration failure, unexpected exception)
    ``store_node`` will not run, so this node closes the session itself before returning.
    Threading the session through state (not a builder holder) keeps concurrent ``ainvoke``
    runs isolated.

    A ``validation_status`` of ``"failed"`` (retries exhausted, still invalid) is a
    persisted business outcome -- it does NOT set ``error`` and the graph proceeds to
    store/END (decision D). Only a ``ValidationOrchestrationError`` is a graph error.
    """
    extraction_result = state.get("extraction_result")
    if extraction_result is None:
        return _fail("validation", "No extraction_result available for validation")

    raw_extraction_id = state.get("document_extraction_id", "")
    try:
        document_extraction_id = UUID(raw_extraction_id)
    except (ValueError, AttributeError, TypeError):
        return _fail("validation", f"Invalid document_extraction_id: {raw_extraction_id!r}")

    document_text = state.get("document_text", "")
    context = state.get("context", "")

    # Open the session here; close it ourselves on any error path (store won't run then).
    session = session_factory()
    try:
        orchestrator = orchestrator_factory(session)
        validated_result = await orchestrator.validate_and_retry(
            extraction_result=extraction_result,
            document_extraction_id=document_extraction_id,
            document_text=document_text,
            context=context,
        )
    except ValidationOrchestrationError as exc:
        await session.close()
        return _fail("validation", str(exc))
    except BaseException:
        # Unexpected failure: store_node is bypassed, so release the session here.
        await session.close()
        raise

    logger.info(
        "Validated extraction %s (status=%s, score=%.1f, retries=%d)",
        document_extraction_id,
        _status_of(validated_result),
        validated_result.validation.validation_score,
        validated_result.retry_count,
    )
    return {
        "validated_result": validated_result,
        "validation_status": _status_of(validated_result),
        "validation_score": validated_result.validation.validation_score,
        "retry_count": validated_result.retry_count,
        "_session": session,
    }


def _status_of(validated_result: ValidatedExtractionResult) -> str:
    """Derive a human-readable validation status string from the validated result.

    The orchestrator persists a richer status on the ``ExtractedEntity`` row, but the
    returned ``ValidatedExtractionResult`` only exposes the ``ValidationResult``. We map
    it to the same vocabulary: ``valid`` when the validation passed, otherwise
    ``failed`` (the orchestrator only returns after retries are exhausted).
    """
    return "valid" if validated_result.validation.is_valid else "failed"


async def store_node(state: EntityExtractionState) -> dict[str, Any]:
    """Commit the ``ExtractedEntity`` flushed by the orchestrator (decision C).

    ``validate_node`` opened the session, the orchestrator flushed the row on it, and this
    node owns the commit so the write is durable. The session (threaded via ``_session``)
    is always closed here, including on commit failure. Commit failures route to END with
    ``error_type="storage"`` and a generic message -- the raw DB exception (which can embed
    credentials/DSN/schema) is logged server-side only.
    """
    session = state.get("_session")
    if session is None:
        return _fail("storage", "No active session for storage")

    try:
        await session.commit()
    except Exception as exc:
        logger.error(
            "Failed to commit extracted entity for document %s: %s",
            state.get("document_id"),
            exc,
            exc_info=True,
        )
        return _fail("storage", "Failed to commit extracted entity")
    finally:
        await session.close()

    logger.info("Committed extracted entity for document %s", state.get("document_id"))
    return {"stored": True}


# ===== Graph assembly =====


def _default_orchestrator_factory(session: AsyncSession) -> ValidationOrchestrator:
    """Construct a real ``ValidationOrchestrator`` bound to ``session``.

    Wires the real ``ExtractionValidator`` + ``ExtractionRetryService`` (which itself
    needs an ``EntityExtractor`` for re-extraction). Used only on the non-injected path.
    """
    from app.services.llm_service import get_llm_service

    llm_service = get_llm_service()
    extractor = EntityExtractor(llm_service)
    validator = ExtractionValidator()
    retry_service = ExtractionRetryService(extractor)
    return ValidationOrchestrator(validator, retry_service, session)


def build_entity_extraction_graph(
    *,
    extractor: EntityExtractor | None = None,
    orchestrator_factory: Callable[[AsyncSession], ValidationOrchestrator] | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the entity extraction ``StateGraph``.

    A single ``AsyncSession`` is opened per graph run inside ``validate_node`` (from
    ``session_factory``) and threaded through the graph *state* to ``store_node``: the
    orchestrator flushes the ``ExtractedEntity`` and ``store_node`` commits, both on the
    same transaction. Because the session lives in per-invocation state rather than a
    builder-level holder, concurrent ``ainvoke`` calls on the same compiled graph stay
    isolated.

    Args:
        extractor: Entity extractor (injected for testing). Defaults to a real
            ``EntityExtractor`` built from ``get_llm_service()``.
        orchestrator_factory: Factory mapping a session to a ``ValidationOrchestrator``
            (injected for testing). Defaults to the real wiring.
        session_factory: Zero-arg callable returning an ``AsyncSession`` (injected for
            testing). Defaults to the cached engine/session factory used by the Celery
            tasks.
        checkpointer: Optional LangGraph checkpointer (forward-compat for Task 52).

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    if extractor is None:
        from app.services.llm_service import get_llm_service

        extractor = EntityExtractor(get_llm_service())
    if orchestrator_factory is None:
        orchestrator_factory = _default_orchestrator_factory
    if session_factory is None:
        from app.tasks.document_tasks import _get_engine_and_factory

        _, session_factory = _get_engine_and_factory()

    # Nodes take their dependencies via partials; the session lives in graph state.
    extract = partial(extract_node, extractor=extractor)
    validate = partial(
        validate_node,
        session_factory=session_factory,
        orchestrator_factory=orchestrator_factory,
    )

    builder: StateGraph = StateGraph(EntityExtractionState)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("store", store_node)

    builder.add_edge(START, "extract")
    # Each step routes to END if a permanent error was recorded, else to the next node.
    builder.add_conditional_edges("extract", route_after("validate"))
    builder.add_conditional_edges("validate", route_after("store"))
    builder.add_edge("store", END)

    return builder.compile(checkpointer=checkpointer)


async def run_entity_extraction(
    initial_state: EntityExtractionState,
    *,
    graph: CompiledStateGraph | None = None,
) -> EntityExtractionState:
    """Run the entity extraction graph over ``initial_state``.

    Args:
        initial_state: Caller-supplied state with at least ``document_id``,
            ``document_extraction_id``, and ``document_text`` (plus optional ``context``).
        graph: Optional pre-built compiled graph (injected for testing). When omitted a
            default graph is built with real services.

    Returns:
        The final ``EntityExtractionState`` after execution.
    """
    if graph is None:
        graph = build_entity_extraction_graph()
    result = await graph.ainvoke(initial_state)
    return cast(EntityExtractionState, result)
