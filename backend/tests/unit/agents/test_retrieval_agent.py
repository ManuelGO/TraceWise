"""Unit tests for the Retrieval Agent (Task 47).

Nodes are tested in isolation with a fake ``RetrievalService`` so the suite runs fully offline
(no embedding API, no DB). Graph-level tests inject the fake to exercise routing without real
I/O. ``rerank_node`` / ``assemble_node`` are pure and read settings via ``get_settings``, which
is monkeypatched where the budget/flag matters.
"""

from typing import Any
from uuid import uuid4

import pytest

from app.agents import retrieval_agent as agent
from app.agents.retrieval_agent import (
    RetrievalState,
    assemble_node,
    rerank_node,
    retrieve_node,
)
from app.models.vector_embedding import SearchResult
from app.services.retrieval_service import RetrievalError

EXT_ID_1 = "11111111-1111-1111-1111-111111111111"
EXT_ID_2 = "22222222-2222-2222-2222-222222222222"


# ===== Fixtures / builders =====


def _result(
    *,
    extraction_id: str = EXT_ID_1,
    chunk_index: int = 0,
    score: float = 0.9,
    text: str = "chunk text",
) -> SearchResult:
    return SearchResult(
        embedding_id=str(uuid4()),
        document_extraction_id=extraction_id,
        chunk_index=chunk_index,
        chunk_text=text,
        similarity_score=score,
        embedding_model="fake-model",
    )


class FakeRetrievalService:
    """Stand-in for RetrievalService.query (no embedding API, no DB)."""

    def __init__(
        self,
        results: list[SearchResult] | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._results = results if results is not None else []
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    async def query(
        self,
        query: str,
        k: int | None = None,
        similarity_threshold: float | None = None,
        extraction_ids: Any = None,
    ) -> list[SearchResult]:
        self.calls.append(
            {
                "query": query,
                "k": k,
                "similarity_threshold": similarity_threshold,
                "extraction_ids": extraction_ids,
            }
        )
        if self._raises is not None:
            raise self._raises
        return self._results


class _Settings:
    def __init__(
        self,
        *,
        reranking_enabled: bool = False,
        max_chunks: int = 10,
        max_chars: int = 8000,
    ) -> None:
        self.RERANKING_ENABLED = reranking_enabled
        self.RETRIEVAL_CONTEXT_MAX_CHUNKS = max_chunks
        self.RETRIEVAL_CONTEXT_MAX_CHARS = max_chars


@pytest.fixture
def patch_settings(monkeypatch: pytest.MonkeyPatch):
    def _apply(**kwargs: Any) -> None:
        monkeypatch.setattr(agent, "get_settings", lambda: _Settings(**kwargs))

    return _apply


# ===== retrieve_node =====


@pytest.mark.asyncio
async def test_retrieve_success():
    service = FakeRetrievalService([_result()])
    state: RetrievalState = {"query": "deforestation risk"}
    out = await retrieve_node(state, service)  # type: ignore[arg-type]
    assert out["results"] == service._results
    assert "error" not in out


@pytest.mark.asyncio
async def test_retrieve_empty_query():
    service = FakeRetrievalService([_result()])
    out = await retrieve_node({"query": ""}, service)  # type: ignore[arg-type]
    assert out["error_type"] == "retrieval"
    assert service.calls == []


@pytest.mark.asyncio
async def test_retrieve_whitespace_query():
    service = FakeRetrievalService([_result()])
    out = await retrieve_node({"query": "   \n\t "}, service)  # type: ignore[arg-type]
    assert out["error_type"] == "retrieval"
    assert service.calls == []


@pytest.mark.asyncio
async def test_retrieve_retrieval_error():
    service = FakeRetrievalService(raises=RetrievalError("boom"))
    out = await retrieve_node({"query": "q"}, service)  # type: ignore[arg-type]
    assert out["error_type"] == "retrieval"
    assert out["error"]


@pytest.mark.asyncio
async def test_retrieve_invalid_extraction_ids():
    service = FakeRetrievalService([_result()])
    state: RetrievalState = {"query": "q", "extraction_ids": ["not-a-uuid"]}
    out = await retrieve_node(state, service)  # type: ignore[arg-type]
    assert out["error_type"] == "retrieval"
    assert service.calls == []


@pytest.mark.asyncio
async def test_retrieve_valid_extraction_ids_parsed_to_uuid():
    from uuid import UUID

    service = FakeRetrievalService([_result()])
    state: RetrievalState = {"query": "q", "extraction_ids": [EXT_ID_1, EXT_ID_2]}
    await retrieve_node(state, service)  # type: ignore[arg-type]
    forwarded = service.calls[0]["extraction_ids"]
    assert forwarded == [UUID(EXT_ID_1), UUID(EXT_ID_2)]
    assert all(isinstance(x, UUID) for x in forwarded)


@pytest.mark.asyncio
async def test_retrieve_forwards_k():
    service = FakeRetrievalService([_result()])
    await retrieve_node({"query": "q", "k": 7}, service)  # type: ignore[arg-type]
    assert service.calls[0]["k"] == 7


@pytest.mark.asyncio
async def test_retrieve_forwards_threshold():
    service = FakeRetrievalService([_result()])
    await retrieve_node({"query": "q", "similarity_threshold": 0.5}, service)  # type: ignore[arg-type]
    assert service.calls[0]["similarity_threshold"] == 0.5


@pytest.mark.asyncio
async def test_retrieve_defaults_forwarded_as_none():
    service = FakeRetrievalService([_result()])
    await retrieve_node({"query": "q"}, service)  # type: ignore[arg-type]
    assert service.calls[0]["k"] is None
    assert service.calls[0]["similarity_threshold"] is None
    assert service.calls[0]["extraction_ids"] is None


@pytest.mark.asyncio
async def test_retrieve_zero_results_is_not_error():
    service = FakeRetrievalService([])
    out = await retrieve_node({"query": "q"}, service)  # type: ignore[arg-type]
    assert out["results"] == []
    assert "error" not in out


@pytest.mark.asyncio
async def test_retrieve_strips_query_before_calling_service():
    service = FakeRetrievalService([_result()])
    await retrieve_node({"query": "  hello  "}, service)  # type: ignore[arg-type]
    assert service.calls[0]["query"] == "hello"


# ===== rerank_node =====


def test_rerank_preserves_descending_input(patch_settings):
    patch_settings()
    results = [
        _result(chunk_index=0, score=0.9),
        _result(chunk_index=1, score=0.5),
    ]
    out = rerank_node({"results": results})
    scores = [r["similarity_score"] for r in out["ranked_results"]]
    assert scores == [0.9, 0.5]


def test_rerank_resorts_out_of_order(patch_settings):
    patch_settings()
    results = [
        _result(chunk_index=0, score=0.3),
        _result(chunk_index=1, score=0.95),
        _result(chunk_index=2, score=0.6),
    ]
    out = rerank_node({"results": results})
    scores = [r["similarity_score"] for r in out["ranked_results"]]
    assert scores == [0.95, 0.6, 0.3]


def test_rerank_dedupes_extraction_chunk_pairs(patch_settings):
    patch_settings()
    results = [
        _result(extraction_id=EXT_ID_1, chunk_index=0, score=0.9),
        _result(extraction_id=EXT_ID_1, chunk_index=0, score=0.4),  # dup, lower score
        _result(extraction_id=EXT_ID_2, chunk_index=0, score=0.7),
    ]
    out = rerank_node({"results": results})
    ranked = out["ranked_results"]
    assert len(ranked) == 2
    keys = {(r["document_extraction_id"], r["chunk_index"]) for r in ranked}
    assert keys == {(EXT_ID_1, 0), (EXT_ID_2, 0)}
    # highest-scoring duplicate kept
    kept = next(r for r in ranked if r["document_extraction_id"] == EXT_ID_1)
    assert kept["similarity_score"] == 0.9


def test_rerank_empty_input(patch_settings):
    patch_settings()
    out = rerank_node({"results": []})
    assert out["ranked_results"] == []


def test_rerank_missing_results_key(patch_settings):
    patch_settings()
    out = rerank_node({})
    assert out["ranked_results"] == []


def test_rerank_flag_enabled_same_ordering(patch_settings):
    patch_settings(reranking_enabled=True)
    results = [
        _result(chunk_index=0, score=0.3),
        _result(chunk_index=1, score=0.9),
    ]
    out = rerank_node({"results": results})
    scores = [r["similarity_score"] for r in out["ranked_results"]]
    assert scores == [0.9, 0.3]


def test_rerank_stable_for_equal_scores(patch_settings):
    patch_settings()
    a = _result(extraction_id=EXT_ID_1, chunk_index=0, score=0.8, text="A")
    b = _result(extraction_id=EXT_ID_2, chunk_index=0, score=0.8, text="B")
    out = rerank_node({"results": [a, b]})
    texts = [r["chunk_text"] for r in out["ranked_results"]]
    assert texts == ["A", "B"]


# ===== assemble_node =====


def test_assemble_context_order_matches_ranking(patch_settings):
    patch_settings()
    ranked = [
        _result(chunk_index=0, text="first"),
        _result(extraction_id=EXT_ID_2, chunk_index=0, text="second"),
    ]
    out = assemble_node({"ranked_results": ranked})
    assert out["context"].index("first") < out["context"].index("second")
    assert out["result_count"] == 2
    assert out["sources"] == ranked


def test_assemble_sources_carried_verbatim(patch_settings):
    patch_settings()
    ranked = [_result(text="hello")]
    out = assemble_node({"ranked_results": ranked})
    assert out["sources"][0] == ranked[0]


def test_assemble_chunk_count_truncation(patch_settings):
    patch_settings(max_chunks=2)
    ranked = [_result(extraction_id=EXT_ID_1, chunk_index=i, text=f"c{i}") for i in range(5)]
    out = assemble_node({"ranked_results": ranked})
    assert out["result_count"] == 2
    assert len(out["sources"]) == 2


def test_assemble_char_budget_truncation(patch_settings):
    patch_settings(max_chars=10)
    ranked = [
        _result(extraction_id=EXT_ID_1, chunk_index=0, text="x" * 8),
        _result(extraction_id=EXT_ID_1, chunk_index=1, text="y" * 8),
    ]
    out = assemble_node({"ranked_results": ranked})
    # first chunk (8 chars) fits; second would push past 10 incl. separator -> excluded
    assert out["result_count"] == 1
    assert out["context"] == "x" * 8


def test_assemble_empty_results(patch_settings):
    patch_settings()
    out = assemble_node({"ranked_results": []})
    assert out["context"] == ""
    assert out["result_count"] == 0
    assert out["sources"] == []
    assert "error" not in out


def test_assemble_missing_ranked_key(patch_settings):
    patch_settings()
    out = assemble_node({})
    assert out["context"] == ""
    assert out["result_count"] == 0


# ===== Graph assembly + routing =====


@pytest.mark.asyncio
async def test_graph_happy_path(patch_settings):
    patch_settings()
    service = FakeRetrievalService([_result(text="grounded")])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    final = await graph.ainvoke({"query": "q"})
    assert final.get("error") is None
    assert "grounded" in final["context"]
    assert final["result_count"] == 1
    assert final["sources"]


@pytest.mark.asyncio
async def test_graph_retrieval_failure_short_circuits(patch_settings):
    patch_settings()
    service = FakeRetrievalService(raises=RetrievalError("down"))
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    final = await graph.ainvoke({"query": "q"})
    assert final["error_type"] == "retrieval"
    # rerank/assemble skipped -> no context/sources produced
    assert "context" not in final
    assert "ranked_results" not in final


@pytest.mark.asyncio
async def test_graph_empty_query_routes_to_end(patch_settings):
    patch_settings()
    service = FakeRetrievalService([_result()])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    final = await graph.ainvoke({"query": "  "})
    assert final["error_type"] == "retrieval"
    assert service.calls == []


@pytest.mark.asyncio
async def test_graph_zero_results_reaches_end(patch_settings):
    patch_settings()
    service = FakeRetrievalService([])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    final = await graph.ainvoke({"query": "q"})
    assert final.get("error") is None
    assert final["context"] == ""
    assert final["result_count"] == 0


@pytest.mark.asyncio
async def test_build_graph_accepts_injected_service(patch_settings):
    patch_settings()
    service = FakeRetrievalService([_result()])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    assert graph is not None


def test_default_retrieval_service_wiring(monkeypatch):
    """_default_retrieval_service wires EmbeddingService + PostgresVectorStore (no real I/O)."""
    created: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.embedding_service.EmbeddingService",
        lambda: created.setdefault("embedding", object()),
    )
    monkeypatch.setattr(
        "app.services.vector_store.PostgresVectorStore",
        lambda factory: created.setdefault("store", object()),
    )
    monkeypatch.setattr(
        "app.tasks.document_tasks._get_engine_and_factory",
        lambda: (object(), lambda: None),
    )

    service = agent._default_retrieval_service()
    assert service is not None
    assert "embedding" in created
    assert "store" in created


@pytest.mark.asyncio
async def test_build_graph_defaults_construct_real_services(monkeypatch):
    sentinel = object()
    called = {}

    def _fake_default() -> Any:
        called["built"] = True
        return sentinel

    monkeypatch.setattr(agent, "_default_retrieval_service", _fake_default)
    graph = agent.build_retrieval_graph()
    assert called.get("built") is True
    assert graph is not None


@pytest.mark.asyncio
async def test_run_retrieval_returns_final_state(patch_settings):
    patch_settings()
    service = FakeRetrievalService([_result(text="ctx")])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    final = await agent.run_retrieval({"query": "q"}, graph=graph)
    assert final["result_count"] == 1
    assert "ctx" in final["context"]


@pytest.mark.asyncio
async def test_run_retrieval_builds_default_graph(monkeypatch, patch_settings):
    patch_settings()
    service = FakeRetrievalService([_result()])
    real_build = agent.build_retrieval_graph

    def _fake_build(**kwargs: Any) -> Any:
        return real_build(retrieval_service=service)  # type: ignore[arg-type]

    monkeypatch.setattr(agent, "build_retrieval_graph", _fake_build)
    final = await agent.run_retrieval({"query": "q"})
    assert final["result_count"] == 1


def test_build_graph_checkpointer_passthrough(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}
    stub_graph = object()

    def _spy_compile(self: Any, *, checkpointer: Any = None) -> Any:
        captured["checkpointer"] = checkpointer
        return stub_graph

    monkeypatch.setattr(agent.StateGraph, "compile", _spy_compile)
    sentinel = object()

    graph = agent.build_retrieval_graph(
        retrieval_service=FakeRetrievalService([_result()]),  # type: ignore[arg-type]
        checkpointer=sentinel,
    )

    assert captured["checkpointer"] is sentinel
    assert graph is stub_graph


@pytest.mark.asyncio
async def test_graph_extraction_ids_scope_end_to_end(patch_settings):
    from uuid import UUID

    patch_settings()
    service = FakeRetrievalService([_result()])
    graph = agent.build_retrieval_graph(retrieval_service=service)  # type: ignore[arg-type]
    await graph.ainvoke({"query": "q", "extraction_ids": [EXT_ID_1]})
    assert service.calls[0]["extraction_ids"] == [UUID(EXT_ID_1)]
