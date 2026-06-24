"""Retrieval Agent (Task 47, Phase 6).

A LangGraph ``StateGraph`` that orchestrates RAG retrieval by wrapping the existing Phase 4
``RetrievalService``. The agent does NOT reimplement query embedding, vector search, metadata
filtering, or similarity ranking -- it is a thin orchestration layer that produces *grounded
context* (an assembled context string plus the ordered source chunks).

Pipeline::

    START -> retrieve -> rerank -> assemble -> END
                |
                | (empty query / invalid extraction_ids / RetrievalError)
                +--------------------------------------------------------> END (error set)

Each node returns a partial update to ``RetrievalState``. Only ``retrieve_node`` can record a
permanent error (empty/whitespace query, non-UUID ``extraction_ids``, or a ``RetrievalError``);
it sets ``state["error"]`` and routes straight to ``END`` via ``route_after`` -- it does not raise
out of the graph. ``rerank_node`` and ``assemble_node`` are pure, deterministic, and cannot fail,
so they are wired with plain edges. This mirrors the "fail immediately, no retry" + error-channel
semantics established by Tasks 45/46 (``app.agents._agent_helpers``).

Design notes (coordinator-confirmed, 2026-06-21 -- see ``phase-6/PHASE_6_ARCHITECTURE.md``):
- A: three nodes (``retrieve`` / ``rerank`` / ``assemble``), and -- unlike Task 46 -- NO DB
  session threaded through state. Retrieval is read-only; ``RetrievalService`` owns its read
  session internally (via the injected ``PostgresVectorStore``).
- B: ``rerank_node`` is a *deterministic* stable sort by ``similarity_score`` DESC plus de-dup of
  duplicate ``(document_extraction_id, chunk_index)`` chunks (highest score kept). Gated by
  ``RERANKING_ENABLED``; when the flag is on the ordering is unchanged and a no-op is logged. A
  real cross-encoder/LLM reranker is deferred (Phase 8) -- no new dependency here.
- C: zero retrieved results is a VALID outcome -- ``assemble_node`` yields ``context=""`` /
  ``result_count=0`` and the graph reaches END normally; ``error`` stays ``None``. Only an empty
  query, invalid ``extraction_ids``, or a ``RetrievalError`` set ``error``.
- D: the assembled context is bounded by ``RETRIEVAL_CONTEXT_MAX_CHUNKS`` /
  ``RETRIEVAL_CONTEXT_MAX_CHARS`` (config).
- E: pure ``initial_state`` input contract; scope is ``extraction_ids`` only (forwarded verbatim
  to ``RetrievalService.query``) -- no separate required ``document_extraction_id``.

This task does NOT configure a checkpointer; ``build_retrieval_graph`` accepts an optional
``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
from typing import Any, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents._agent_helpers import agent_fail, route_after
from app.config import get_settings
from app.models.vector_embedding import SearchResult
from app.services.retrieval_service import RetrievalError, RetrievalService

logger = logging.getLogger(__name__)

_AGENT_LABEL = "Retrieval"
_CONTEXT_SEPARATOR = "\n\n---\n\n"


def _fail(error_type: str, message: str) -> dict[str, Any]:
    """Partial state update for a permanent failure (see ``agent_fail``)."""
    return agent_fail(_AGENT_LABEL, error_type, message)


# ===== State contract =====


class RetrievalState(TypedDict, total=False):
    """Shared state threaded through the retrieval graph.

    ``total=False`` so each node may return a partial update without re-declaring every key.
    Only ``query`` is a required caller input; the rest are optional overrides (defaults pulled
    from settings by ``RetrievalService``) or outputs filled by successive nodes.
    """

    # Inputs (caller-supplied)
    query: str
    k: int | None
    similarity_threshold: float | None
    # Optional scope filter (UUID strings). If omitted, ``None``, or an empty list, no
    # filtering is applied and results come from all extractions (matches
    # ``RetrievalService.query``'s ``if extraction_ids:`` semantics).
    extraction_ids: list[str] | None

    # retrieve_node
    results: list[SearchResult]
    # rerank_node
    ranked_results: list[SearchResult]
    # assemble_node (primary output)
    context: str
    sources: list[SearchResult]
    result_count: int

    # Error channel: when ``error`` is set the graph short-circuits to END.
    error: str | None
    error_type: str | None


# ===== Nodes =====


async def retrieve_node(
    state: RetrievalState,
    retrieval_service: RetrievalService,
) -> dict[str, Any]:
    """Retrieve relevant chunks for the query via ``RetrievalService.query``.

    Wraps the full embed -> vector-search -> metadata-filter -> similarity-rank pipeline. An
    empty/whitespace query and any non-UUID value in ``extraction_ids`` are guarded up front as
    permanent ``retrieval`` errors; a ``RetrievalError`` from the service is mapped the same way.
    An empty result list is NOT an error (decision C) -- it flows on to rerank/assemble.
    """
    query = state.get("query", "")
    stripped_query = query.strip()
    if not stripped_query:
        return _fail("retrieval", "No query provided for retrieval")

    raw_extraction_ids = state.get("extraction_ids")
    extraction_ids: list[UUID] | None = None
    if raw_extraction_ids:
        try:
            extraction_ids = [UUID(raw_id) for raw_id in raw_extraction_ids]
        except (ValueError, AttributeError, TypeError):
            # Don't reflect raw caller-supplied values into the error/log (they survive
            # _sanitize_log, which strips only newline/CR/NUL) -- report the count instead.
            return _fail(
                "retrieval",
                f"Invalid extraction_ids: {len(raw_extraction_ids)} value(s) not valid UUIDs",
            )

    try:
        results = await retrieval_service.query(
            stripped_query,
            k=state.get("k"),
            similarity_threshold=state.get("similarity_threshold"),
            extraction_ids=extraction_ids,
        )
    except RetrievalError as exc:
        return _fail("retrieval", str(exc))

    logger.info("Retrieved %d chunks for query (len=%d)", len(results), len(stripped_query))
    return {"results": results}


def rerank_node(state: RetrievalState) -> dict[str, Any]:
    """Deterministically rerank + de-duplicate the retrieved chunks (decision B).

    Stable-sorts by ``similarity_score`` descending and drops duplicate
    ``(document_extraction_id, chunk_index)`` chunks (keeping the first / highest-scoring after
    the sort). Results already arrive ranked from the vector store, so in practice this is an
    identity transform -- but the node guarantees the invariant regardless of input ordering.

    ``RERANKING_ENABLED`` toggles a real reranker hook; no model is wired yet (deferred to
    Phase 8), so when the flag is on the ordering is unchanged and a no-op is logged.
    """
    results = state.get("results", [])

    # Stable sort by similarity descending (Python's sort is stable, so equal scores keep order).
    ordered = sorted(results, key=lambda r: r["similarity_score"], reverse=True)

    seen: set[tuple[str, int]] = set()
    ranked: list[SearchResult] = []
    for result in ordered:
        key = (result["document_extraction_id"], result["chunk_index"])
        if key in seen:
            continue
        seen.add(key)
        ranked.append(result)

    if get_settings().RERANKING_ENABLED:
        # debug (not info): this fires every invocation while the flag is on, so keep it out
        # of normal prod logs until a real reranker model is wired (Phase 8).
        logger.debug(
            "RERANKING_ENABLED is set but no reranker model is wired; "
            "keeping deterministic similarity ordering (%d chunks)",
            len(ranked),
        )

    logger.info("Reranked %d chunks (%d after de-dup)", len(results), len(ranked))
    return {"ranked_results": ranked}


def assemble_node(state: RetrievalState) -> dict[str, Any]:
    """Assemble grounded context from the ranked chunks (decisions C, D).

    Concatenates ``chunk_text`` from ``ranked_results`` (in order) into a single context string,
    bounded by ``RETRIEVAL_CONTEXT_MAX_CHUNKS`` and ``RETRIEVAL_CONTEXT_MAX_CHARS``. ``sources``
    and ``result_count`` reflect the chunks actually included in ``context`` (so downstream
    citation in Task 50 lines up with the text it sees). Zero ranked results yields an empty
    context and ``result_count=0`` -- a valid outcome, not an error.
    """
    settings = get_settings()
    max_chunks = settings.RETRIEVAL_CONTEXT_MAX_CHUNKS
    max_chars = settings.RETRIEVAL_CONTEXT_MAX_CHARS

    ranked_results = state.get("ranked_results", [])

    included: list[SearchResult] = []
    parts: list[str] = []
    total_chars = 0
    for result in ranked_results[:max_chunks]:
        chunk_text = result["chunk_text"]
        # Account for the separator joining this chunk to the previous one.
        added = len(chunk_text) + (len(_CONTEXT_SEPARATOR) if parts else 0)
        if total_chars + added > max_chars:
            break
        parts.append(chunk_text)
        included.append(result)
        total_chars += added

    context = _CONTEXT_SEPARATOR.join(parts)
    logger.info("Assembled context from %d sources (%d chars)", len(included), len(context))
    return {
        "context": context,
        "sources": included,
        "result_count": len(included),
    }


# ===== Graph assembly =====


def _default_retrieval_service() -> RetrievalService:
    """Construct a real ``RetrievalService`` (embedding service + Postgres vector store).

    Mirrors the wiring in ``document_ingestion_agent.build_document_ingestion_graph``: the
    session factory comes from the cached engine used by the Celery tasks. Used only on the
    non-injected path.
    """
    from app.services.embedding_service import EmbeddingService
    from app.services.vector_store import PostgresVectorStore
    from app.tasks.document_tasks import _get_engine_and_factory

    _, session_factory = _get_engine_and_factory()
    return RetrievalService(EmbeddingService(), PostgresVectorStore(session_factory))


def build_retrieval_graph(
    *,
    retrieval_service: RetrievalService | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the retrieval ``StateGraph``.

    The graph is read-only: no DB session is threaded through state. ``retrieve_node`` delegates
    to the injected ``RetrievalService`` (which owns its own read session); ``rerank_node`` and
    ``assemble_node`` are pure and deterministic.

    Args:
        retrieval_service: Retrieval service (injected for testing). Defaults to a real
            ``RetrievalService`` built from ``EmbeddingService`` + ``PostgresVectorStore``.
        checkpointer: Optional LangGraph checkpointer (forward-compat for Task 52).

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    if retrieval_service is None:
        retrieval_service = _default_retrieval_service()

    async def _retrieve(state: RetrievalState) -> dict[str, Any]:
        return await retrieve_node(state, retrieval_service)

    builder: StateGraph = StateGraph(RetrievalState)
    builder.add_node("retrieve", _retrieve)
    builder.add_node("rerank", rerank_node)
    builder.add_node("assemble", assemble_node)

    builder.add_edge(START, "retrieve")
    # Only retrieve can record a permanent error -> conditional short-circuit to END.
    builder.add_conditional_edges("retrieve", route_after("rerank"))
    # rerank/assemble are pure and cannot fail -> plain edges.
    builder.add_edge("rerank", "assemble")
    builder.add_edge("assemble", END)

    return builder.compile(checkpointer=checkpointer)


async def run_retrieval(
    initial_state: RetrievalState,
    *,
    graph: CompiledStateGraph | None = None,
) -> RetrievalState:
    """Run the retrieval graph over ``initial_state``.

    Args:
        initial_state: Caller-supplied state with at least ``query`` (plus optional ``k``,
            ``similarity_threshold``, ``extraction_ids``).
        graph: Optional pre-built compiled graph (injected for testing). When omitted a default
            graph is built with real services.

    Returns:
        The final ``RetrievalState`` after execution.
    """
    if graph is None:
        graph = build_retrieval_graph()
    result = await graph.ainvoke(initial_state)
    return cast(RetrievalState, result)
