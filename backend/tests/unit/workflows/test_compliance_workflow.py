"""Unit tests for the Compliance Workflow (Task 51).

The workflow is *orchestration of orchestrators*: it composes the six Phase 6 agents (Tasks 45-50)
into one ``StateGraph``, bridging each agent's state contract to the next. These tests inject FAKE
agent graphs (trivial objects exposing an async ``ainvoke``) so the whole suite runs fully offline --
no LLM API, no network, no DB, no Celery broker. Persistence is exercised with a fake session; the
default ``persist=False`` keeps the graph-level tests DB-free.
"""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.models.vector_embedding import SearchResult
from app.workflows.compliance_workflow import (
    assess_risk_node,
    build_compliance_workflow,
    extract_node,
    generate_node,
    ingest_node,
    persist_node,
    retrieve_node,
    route_review_node,
    run_compliance_workflow,
    validate_node,
)
from app.workflows.langgraph_setup import WorkflowState

# ===== Fakes =====


class _FakeGraph:
    """Fake agent graph: returns a canned result and records every state it was invoked with."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self._result = result if result is not None else {}
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, state: Any, /, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(state))
        return self._result


class _NeverCalledGraph:
    """Fake agent graph that fails the test if it is ever invoked (asserts short-circuit)."""

    async def ainvoke(self, state: Any, /, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError("downstream agent graph should not have been invoked")


class _FakeSession:
    """Minimal async session recording commit/close and optionally failing the commit."""

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.committed = False
        self.closed = False
        self.added: list[Any] = []
        self._fail_commit = fail_commit

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("simulated commit failure")
        self.committed = True

    async def close(self) -> None:
        self.closed = True


# ===== Fixtures / builders =====


def _risk_assessment(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "risk_score": 42,
        "risk_level": "medium",
        "confidence_score": 0.8,
        "confidence_level": "high",
        "completeness_score": 0.9,
        "reasoning": "The supplier lacks a valid certificate.",
        "recommended_actions": ["Request the certificate"],
        "violations": [],
        "evidence_gaps": [],
        "llm_available": True,
    }
    base.update(overrides)
    return base


def _evidence_validation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "is_valid": True,
        "is_grounded": True,
        "grounding_score": 0.8,
        "hallucination_risk": 0.2,
        "hallucination_band": "low",
        "citation_count": 1,
        "citations": [],
        "consistency": {"high_severity_count": 0},
        "findings": ["80% of claims grounded"],
        "reasoning": "Grounded.",
    }
    base.update(overrides)
    return base


def _report(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"overall_status": "compliant", "risk_level": "medium"}
    base.update(overrides)
    return base


def _source(*, doc_id: str = "doc-1", chunk: int = 0, score: float = 0.6) -> SearchResult:
    return SearchResult(
        embedding_id=f"emb-{doc_id}-{chunk}",
        document_extraction_id=doc_id,
        chunk_index=chunk,
        chunk_text="chunk text",
        similarity_score=score,
        embedding_model="fake-model",
    )


def _core_state(**overrides: Any) -> WorkflowState:
    """A minimal pre-ingested WorkflowState carrying required inputs for the core path."""
    state: WorkflowState = WorkflowState(
        case_id=str(uuid4()),
        query="Is the supplier compliant?",
        document_id=str(uuid4()),
        document_extraction_id=str(uuid4()),
        document_text="Supplier ACME ships widgets.",
    )
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ===== ingest_node =====


async def test_ingest_skipped_without_file_bytes() -> None:
    graph = _FakeGraph({"extracted_text": "should not be used"})
    result = await ingest_node(_core_state(), graph)
    assert result == {}
    assert graph.calls == []  # no ainvoke when there are no file_bytes


async def test_ingest_runs_when_file_bytes_present() -> None:
    graph = _FakeGraph(
        {"extracted_text": "extracted body", "stored_count": 3, "document_type": "invoice"}
    )
    state = _core_state(file_bytes=b"%PDF-1.4 ...", filename="doc.pdf")
    result = await ingest_node(state, graph)
    assert result["extracted_text"] == "extracted body"
    assert result["stored_count"] == 3
    assert result["document_type"] == "invoice"
    assert len(graph.calls) == 1


async def test_ingest_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "unsupported MIME", "error_type": "extraction"})
    state = _core_state(file_bytes=b"junk", filename="doc.bin")
    result = await ingest_node(state, graph)
    assert result["error_type"] == "ingestion"
    assert "unsupported MIME" in result["error"]


# ===== extract_node =====


async def test_extract_errors_without_document_text() -> None:
    graph = _FakeGraph()
    state = _core_state()
    del state["document_text"]  # no ingested text, no supplied text
    result = await extract_node(state, graph)
    assert result["error_type"] == "extraction"
    assert graph.calls == []


async def test_extract_prefers_ingested_text_and_bridges_validation() -> None:
    entities = SimpleNamespace(document_id="d")
    validation = SimpleNamespace(is_valid=True, validation_score=95.0)
    validated = SimpleNamespace(validation=validation)
    graph = _FakeGraph(
        {
            "extraction_result": entities,
            "validated_result": validated,
            "validation_status": "valid",
        }
    )
    state = _core_state(extracted_text="ingested text", document_text="stale caller text")
    result = await extract_node(state, graph)
    # Ingested text wins over the caller-supplied document_text.
    assert graph.calls[0]["document_text"] == "ingested text"
    assert result["extraction_result"] is entities
    # The embedded ValidationResult is bridged out for the Risk agent.
    assert result["validation_result"] is validation
    assert result["validation_status"] == "valid"


async def test_extract_without_validated_result_omits_validation_bridge() -> None:
    graph = _FakeGraph({"extraction_result": SimpleNamespace(), "validation_status": "valid"})
    result = await extract_node(_core_state(), graph)
    assert "validation_result" not in result


async def test_extract_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "LLM outage", "error_type": "extraction"})
    result = await extract_node(_core_state(), graph)
    assert result["error_type"] == "extraction"
    assert "LLM outage" in result["error"]


async def test_extract_errors_when_no_extraction_result() -> None:
    graph = _FakeGraph({"validation_status": "valid"})  # no extraction_result key
    result = await extract_node(_core_state(), graph)
    assert result["error_type"] == "extraction"


# ===== retrieve_node =====


async def test_retrieve_scopes_to_extraction_and_computes_source_quality() -> None:
    sources = [_source(score=0.4), _source(chunk=1, score=0.8)]
    graph = _FakeGraph({"context": "grounded ctx", "sources": sources, "result_count": 2})
    ext_id = str(uuid4())
    state = _core_state(document_extraction_id=ext_id)
    result = await retrieve_node(state, graph)
    assert graph.calls[0]["extraction_ids"] == [ext_id]
    assert result["retrieval_context"] == "grounded ctx"
    assert result["sources"] == sources
    assert result["source_quality"] == pytest.approx(0.6)  # mean(0.4, 0.8)


async def test_retrieve_empty_sources_uses_default_source_quality() -> None:
    graph = _FakeGraph({"context": "", "sources": [], "result_count": 0})
    result = await retrieve_node(_core_state(), graph)
    assert result["sources"] == []
    assert result["source_quality"] == 0.5  # default when no sources


async def test_retrieve_drops_nan_similarity_from_source_quality() -> None:
    # A NaN score must be dropped, NOT clamped to 1.0 (a max/min clamp does not catch NaN and would
    # silently produce a perfect source_quality, biasing downstream confidence upward).
    sources = [_source(score=float("nan")), _source(chunk=1, score=0.4)]
    graph = _FakeGraph({"context": "c", "sources": sources, "result_count": 2})
    result = await retrieve_node(_core_state(), graph)
    assert result["source_quality"] == pytest.approx(0.4)


async def test_retrieve_all_nan_similarity_falls_back_to_default() -> None:
    sources = [_source(score=float("nan")), _source(chunk=1, score=float("inf"))]
    graph = _FakeGraph({"context": "c", "sources": sources, "result_count": 2})
    result = await retrieve_node(_core_state(), graph)
    assert result["source_quality"] == 0.5  # no finite scores -> default


async def test_retrieve_errors_on_empty_query() -> None:
    graph = _FakeGraph()
    result = await retrieve_node(_core_state(query="   "), graph)
    assert result["error_type"] == "retrieval"
    assert graph.calls == []


async def test_retrieve_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "RetrievalError", "error_type": "retrieval"})
    result = await retrieve_node(_core_state(), graph)
    assert result["error_type"] == "retrieval"


# ===== assess_risk_node =====


async def test_assess_risk_maps_entities_and_threads_optional_inputs() -> None:
    entities = SimpleNamespace(document_id="d")
    validation = SimpleNamespace(is_valid=True)
    graph = _FakeGraph({"risk_assessment": _risk_assessment()})
    state = _core_state(
        extraction_result=entities,
        validation_result=validation,
        source_quality=0.72,
        document_type="invoice",
    )
    result = await assess_risk_node(state, graph)
    call = graph.calls[0]
    assert call["entities"] is entities
    assert call["validation_result"] is validation
    assert call["source_quality"] == 0.72
    assert call["document_type"] == "invoice"
    assert result["risk_assessment"]["risk_level"] == "medium"


async def test_assess_risk_defaults_when_optionals_absent() -> None:
    graph = _FakeGraph({"risk_assessment": _risk_assessment()})
    state = _core_state(extraction_result=SimpleNamespace())
    await assess_risk_node(state, graph)
    call = graph.calls[0]
    assert call["source_quality"] == 0.5
    assert call["document_type"] == "general"
    assert "validation_result" not in call  # omitted, not passed as None


async def test_assess_risk_errors_without_entities() -> None:
    graph = _FakeGraph()
    result = await assess_risk_node(_core_state(), graph)
    assert result["error_type"] == "risk"
    assert graph.calls == []


async def test_assess_risk_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "bad input", "error_type": "risk_scoring"})
    state = _core_state(extraction_result=SimpleNamespace())
    result = await assess_risk_node(state, graph)
    assert result["error_type"] == "risk"


async def test_assess_risk_errors_when_agent_returns_no_assessment() -> None:
    graph = _FakeGraph({})  # no error, but also no risk_assessment
    state = _core_state(extraction_result=SimpleNamespace())
    result = await assess_risk_node(state, graph)
    assert result["error_type"] == "risk"
    assert "risk_assessment" in result["error"]


# ===== validate_node =====


async def test_validate_uses_risk_reasoning_as_answer() -> None:
    graph = _FakeGraph({"evidence_validation": _evidence_validation()})
    state = _core_state(
        risk_assessment=_risk_assessment(reasoning="Supplier lacks certificate."),
        sources=[_source()],
        retrieval_context="fallback context",
    )
    result = await validate_node(state, graph)
    assert graph.calls[0]["answer"] == "Supplier lacks certificate."
    assert graph.calls[0]["search_results"] == state["sources"]
    assert result["evidence_validation"]["is_valid"] is True


async def test_validate_falls_back_to_retrieval_context() -> None:
    graph = _FakeGraph({"evidence_validation": _evidence_validation()})
    state = _core_state(
        risk_assessment=_risk_assessment(reasoning=""),
        retrieval_context="the grounded retrieval context",
    )
    result = await validate_node(state, graph)
    assert graph.calls[0]["answer"] == "the grounded retrieval context"
    assert "evidence_validation" in result


async def test_validate_skipped_when_no_answer_text() -> None:
    graph = _FakeGraph({"evidence_validation": _evidence_validation()})
    state = _core_state(risk_assessment=_risk_assessment(reasoning=""), retrieval_context="")
    result = await validate_node(state, graph)
    assert result == {"answer": ""}
    assert graph.calls == []  # agent not invoked when there is nothing to validate


async def test_validate_handles_none_reasoning_and_context() -> None:
    # Neither ``.strip()`` should crash on a None reasoning / retrieval_context.
    graph = _FakeGraph({"evidence_validation": _evidence_validation()})
    state = _core_state(risk_assessment=_risk_assessment(reasoning=None), retrieval_context=None)
    result = await validate_node(state, graph)
    assert result == {"answer": ""}
    assert graph.calls == []


async def test_validate_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "consistency ValueError", "error_type": "consistency"})
    state = _core_state(risk_assessment=_risk_assessment())
    result = await validate_node(state, graph)
    assert result["error_type"] == "evidence"


async def test_validate_errors_when_agent_returns_no_validation() -> None:
    graph = _FakeGraph({})  # no error, but also no evidence_validation
    state = _core_state(risk_assessment=_risk_assessment())
    result = await validate_node(state, graph)
    assert result["error_type"] == "evidence"
    assert "evidence_validation" in result["error"]


# ===== generate_node =====


async def test_generate_passes_all_inputs_and_surfaces_report() -> None:
    graph = _FakeGraph({"report_content": "# Report", "report": _report()})
    state = _core_state(
        risk_assessment=_risk_assessment(),
        evidence_validation=_evidence_validation(),
        sources=[_source()],
    )
    result = await generate_node(state, graph)
    call = graph.calls[0]
    assert call["risk_assessment"]["risk_level"] == "medium"
    assert call["evidence_validation"]["is_valid"] is True
    assert call["query"] == state["query"]
    assert result["report_content"] == "# Report"
    assert result["report"]["overall_status"] == "compliant"


async def test_generate_errors_without_risk_assessment() -> None:
    graph = _FakeGraph()
    result = await generate_node(_core_state(), graph)
    assert result["error_type"] == "report"
    assert graph.calls == []


async def test_generate_errors_on_empty_report_content() -> None:
    graph = _FakeGraph({"report_content": "", "report": {}})
    state = _core_state(risk_assessment=_risk_assessment())
    result = await generate_node(state, graph)
    assert result["error_type"] == "report"
    assert "report_content" in result["error"]


async def test_generate_missing_report_dict_names_the_right_field() -> None:
    # report_content present but the structured report dict missing -> the message must name the
    # report dict, not report_content.
    graph = _FakeGraph({"report_content": "# body", "report": None})
    state = _core_state(risk_assessment=_risk_assessment())
    result = await generate_node(state, graph)
    assert result["error_type"] == "report"
    assert "report dict" in result["error"]


async def test_generate_propagates_agent_error() -> None:
    graph = _FakeGraph({"error": "render failure", "error_type": "render"})
    state = _core_state(risk_assessment=_risk_assessment())
    result = await generate_node(state, graph)
    assert result["error_type"] == "report"


# ===== persist_node =====


async def test_persist_disabled_is_noop() -> None:
    result = await persist_node(_core_state(report_content="# R"), session_factory=None, persist=False)
    assert result == {}


async def test_persist_writes_report_and_closes_session() -> None:
    session = _FakeSession()
    state = _core_state(report_content="# Compliance Report")
    result = await persist_node(state, session_factory=lambda: session, persist=True)
    assert session.committed is True
    assert session.closed is True
    assert len(session.added) == 1
    # A real UUID string, not "None" from an unflushed column default.
    from uuid import UUID as _UUID

    assert _UUID(result["generated_report_id"])


async def test_persist_commit_failure_closes_session_and_errors() -> None:
    session = _FakeSession(fail_commit=True)
    state = _core_state(report_content="# R")
    result = await persist_node(state, session_factory=lambda: session, persist=True)
    assert result["error_type"] == "persist"
    # Raw exception text is NOT surfaced (it can embed DSN/credentials).
    assert "simulated commit failure" not in result["error"]
    assert session.closed is True  # closed on the failure path too


async def test_persist_errors_on_missing_report_content() -> None:
    result = await persist_node(_core_state(), session_factory=lambda: _FakeSession(), persist=True)
    assert result["error_type"] == "persist"


async def test_persist_errors_on_invalid_case_id() -> None:
    state = _core_state(case_id="not-a-uuid", report_content="# R")
    result = await persist_node(state, session_factory=lambda: _FakeSession(), persist=True)
    assert result["error_type"] == "persist"


async def test_persist_errors_without_session_factory() -> None:
    state = _core_state(report_content="# R")
    result = await persist_node(state, session_factory=None, persist=True)
    assert result["error_type"] == "persist"


async def test_persist_session_factory_raising_returns_error_not_crash() -> None:
    # If the factory itself raises (e.g. pool exhausted), persist_node must return a clean
    # workflow_fail via the error channel -- not let the exception escape uncaught, and not raise a
    # NameError from ``session.close()`` on a session that was never bound.
    def _boom() -> _FakeSession:
        raise RuntimeError("pool exhausted")

    state = _core_state(report_content="# R")
    result = await persist_node(state, session_factory=_boom, persist=True)
    assert result["error_type"] == "persist"
    assert "pool exhausted" not in result["error"]  # raw exception text not surfaced


# ===== route_review_node =====


def test_route_review_compliant_needs_no_review() -> None:
    result = route_review_node(_core_state(report=_report(overall_status="compliant")))
    assert result["overall_status"] == "compliant"
    assert result["needs_human_review"] is False


@pytest.mark.parametrize("status", ["non_compliant", "needs_review"])
def test_route_review_non_compliant_needs_review(status: str) -> None:
    result = route_review_node(_core_state(report=_report(overall_status=status)))
    assert result["overall_status"] == status
    assert result["needs_human_review"] is True


def test_route_review_defaults_to_compliant_without_report() -> None:
    result = route_review_node(_core_state())
    assert result["overall_status"] == "compliant"
    assert result["needs_human_review"] is False


# ===== Full-graph integration (build_compliance_workflow / run_compliance_workflow) =====


def _happy_graphs() -> dict[str, _FakeGraph]:
    return {
        "extraction_graph": _FakeGraph(
            {"extraction_result": SimpleNamespace(), "validation_status": "valid"}
        ),
        "retrieval_graph": _FakeGraph(
            {"context": "ctx", "sources": [_source(score=0.7)], "result_count": 1}
        ),
        "risk_graph": _FakeGraph({"risk_assessment": _risk_assessment()}),
        "evidence_graph": _FakeGraph({"evidence_validation": _evidence_validation()}),
        "report_graph": _FakeGraph({"report_content": "# Compliance Report", "report": _report()}),
    }


async def test_full_workflow_happy_path() -> None:
    graphs = _happy_graphs()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        **graphs,
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final.get("error") is None
    assert final["report_content"] == "# Compliance Report"
    assert final["overall_status"] == "compliant"
    assert final["needs_human_review"] is False
    assert final["source_quality"] == pytest.approx(0.7)


async def test_full_workflow_persists_report() -> None:
    session = _FakeSession()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        session_factory=lambda: session,
        persist=True,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final.get("error") is None
    assert final["generated_report_id"]
    assert session.committed is True


async def test_full_workflow_non_compliant_routes_to_review() -> None:
    graphs = _happy_graphs()
    graphs["report_graph"] = _FakeGraph(
        {"report_content": "# R", "report": _report(overall_status="non_compliant")}
    )
    graph = build_compliance_workflow(ingestion_graph=_FakeGraph(), persist=False, **graphs)
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final["overall_status"] == "non_compliant"
    assert final["needs_human_review"] is True


async def test_full_workflow_short_circuits_on_retrieval_error() -> None:
    graphs = _happy_graphs()
    graphs["retrieval_graph"] = _FakeGraph({"error": "RetrievalError", "error_type": "retrieval"})
    # Downstream agents must never run once retrieval fails.
    graphs["risk_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    graphs["evidence_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    graphs["report_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    graph = build_compliance_workflow(ingestion_graph=_FakeGraph(), persist=False, **graphs)
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final["error_type"] == "retrieval"
    assert "report_content" not in final


async def test_full_workflow_runs_ingestion_when_file_bytes_present() -> None:
    graphs = _happy_graphs()
    ingestion = _FakeGraph({"extracted_text": "ingested body", "stored_count": 2})
    graph = build_compliance_workflow(ingestion_graph=ingestion, persist=False, **graphs)
    state = _core_state(file_bytes=b"%PDF-1.4", filename="doc.pdf")
    del state["document_text"]  # force reliance on the ingested text
    final = await run_compliance_workflow(state, graph=graph)
    assert final.get("error") is None
    assert len(ingestion.calls) == 1
    # The extraction agent received the ingested text.
    assert graphs["extraction_graph"].calls[0]["document_text"] == "ingested body"


async def test_full_workflow_evidence_skipped_still_reports() -> None:
    graphs = _happy_graphs()
    # No reasoning and no retrieval context -> evidence validation skipped, report still generated.
    graphs["risk_graph"] = _FakeGraph({"risk_assessment": _risk_assessment(reasoning="")})
    graphs["retrieval_graph"] = _FakeGraph({"context": "", "sources": [], "result_count": 0})
    evidence = graphs["evidence_graph"]
    graph = build_compliance_workflow(ingestion_graph=_FakeGraph(), persist=False, **graphs)
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final.get("error") is None
    assert final["report_content"] == "# Compliance Report"
    assert evidence.calls == []  # evidence agent skipped
    assert "evidence_validation" not in final


def test_build_with_injected_graphs_touches_no_real_services() -> None:
    # Building with all agent graphs injected and persist=False must NOT construct any real service
    # or session factory -- the offline guarantee the unit suite relies on. (The non-injected default
    # path deliberately builds real agent graphs, which need credentials, so it is not exercised
    # here -- mirroring how the per-agent suites never build their real defaults offline.)
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        **_happy_graphs(),
    )
    assert hasattr(graph, "ainvoke")


# ===== Task 52: state-persistence wiring + recovery =====


class _RecordingCheckpointer:
    """Fake WorkflowCheckpointer: records every save_checkpoint call; serves a canned load_latest."""

    def __init__(self, loaded: WorkflowState | None = None) -> None:
        self.saves: list[dict[str, Any]] = []
        self._loaded = loaded
        self.load_calls: list[str] = []

    async def save_checkpoint(
        self,
        *,
        run_id: str,
        case_id: str,
        step: str,
        status: Any,
        state: Any,
        error: str | None = None,
        error_type: str | None = None,
    ) -> None:
        self.saves.append(
            {
                "run_id": run_id,
                "case_id": case_id,
                "step": step,
                "status": status,
                "state": dict(state),
                "error": error,
                "error_type": error_type,
            }
        )

    async def load_latest(self, run_id: str) -> WorkflowState | None:
        self.load_calls.append(run_id)
        return self._loaded


def _steps(saves: list[dict[str, Any]]) -> list[str]:
    return [s["step"] for s in saves]


async def test_checkpoint_recorded_per_step_on_happy_path() -> None:
    cp = _RecordingCheckpointer()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)

    assert final.get("error") is None
    # One checkpoint per node, in pipeline order.
    assert _steps(cp.saves) == [
        "ingest",
        "extract",
        "retrieve",
        "assess_risk",
        "validate",
        "generate",
        "persist",
        "route_review",
    ]
    # Every step completed (no error on the happy path).
    from app.models import WorkflowStepStatus

    assert all(s["status"] == WorkflowStepStatus.COMPLETED for s in cp.saves)
    # A run_id was generated and threaded into every checkpoint.
    run_ids = {s["run_id"] for s in cp.saves}
    assert len(run_ids) == 1 and next(iter(run_ids))


async def test_final_checkpoint_carries_review_signal() -> None:
    cp = _RecordingCheckpointer()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    await run_compliance_workflow(_core_state(), graph=graph)

    route_cp = cp.saves[-1]
    assert route_cp["step"] == "route_review"
    assert route_cp["state"]["overall_status"] == "compliant"
    assert route_cp["state"]["needs_human_review"] is False


async def test_failed_step_records_failed_checkpoint_and_stops_trail() -> None:
    from app.models import WorkflowStepStatus

    graphs = _happy_graphs()
    graphs["retrieval_graph"] = _FakeGraph({"error": "RetrievalError", "error_type": "retrieval"})
    graphs["risk_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    graphs["evidence_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    graphs["report_graph"] = _NeverCalledGraph()  # type: ignore[assignment]
    cp = _RecordingCheckpointer()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **graphs,
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)

    assert final["error_type"] == "retrieval"
    # The trail ends at the failing step; downstream nodes never checkpoint.
    assert _steps(cp.saves) == ["ingest", "extract", "retrieve"]
    retrieve_cp = cp.saves[-1]
    assert retrieve_cp["status"] == WorkflowStepStatus.FAILED
    assert retrieve_cp["error_type"] == "retrieval"
    assert "RetrievalError" in (retrieve_cp["error"] or "")


async def test_no_checkpoints_when_disabled() -> None:
    cp = _RecordingCheckpointer()
    # Checkpointer injected but the gate is OFF -> nothing is wrapped, nothing is written.
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=False,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final.get("error") is None
    assert cp.saves == []


async def test_no_checkpoints_when_no_checkpointer_injected() -> None:
    # Enabled but no checkpointer and no session factory (persist=False) -> no writer resolved.
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)
    # Runs cleanly with no checkpointer available (best-effort: absence is not an error).
    assert final.get("error") is None


async def test_default_checkpointer_built_from_session_factory_when_enabled() -> None:
    # When enabled with a session_factory but no explicit checkpointer, a default one is built and
    # writes checkpoints through that factory's session/repository. We assert writes happened by
    # observing the session was used (the real WorkflowStateRepository.create + commit path).
    session = _FakeSession()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        session_factory=lambda: session,
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(_core_state(), graph=graph)
    assert final.get("error") is None
    # The default checkpointer used the injected session factory to persist at least one checkpoint.
    assert session.committed is True
    assert session.added  # at least one WorkflowStateCheckpoint row was added


async def test_run_id_preserved_when_supplied() -> None:
    cp = _RecordingCheckpointer()
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    state = _core_state(run_id="99999999-9999-9999-9999-999999999999")
    await run_compliance_workflow(state, graph=graph)
    assert {s["run_id"] for s in cp.saves} == {"99999999-9999-9999-9999-999999999999"}


async def test_run_generates_run_id_when_absent() -> None:
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        **_happy_graphs(),
    )
    state = _core_state()
    assert "run_id" not in state
    final = await run_compliance_workflow(state, graph=graph)
    assert final.get("run_id")  # a run_id was generated and threaded through


async def test_resume_from_seeds_state_from_checkpoint() -> None:
    seeded: WorkflowState = _core_state(
        run_id="88888888-8888-8888-8888-888888888888",
        risk_assessment=_risk_assessment(reasoning="recovered reasoning"),
    )
    cp = _RecordingCheckpointer(loaded=seeded)
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    # Caller supplies only the resume id; the state is seeded from the loaded checkpoint.
    final = await run_compliance_workflow(
        _core_state(),
        graph=graph,
        resume_from="88888888-8888-8888-8888-888888888888",
        state_checkpointer=cp,  # type: ignore[arg-type]
    )
    assert cp.load_calls == ["88888888-8888-8888-8888-888888888888"]
    # The resumed run reuses the same run_id (continues the trail).
    assert final["run_id"] == "88888888-8888-8888-8888-888888888888"


async def test_resume_from_missing_checkpoint_still_runs() -> None:
    cp = _RecordingCheckpointer(loaded=None)  # nothing to recover
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **_happy_graphs(),
    )
    final = await run_compliance_workflow(
        _core_state(),
        graph=graph,
        resume_from="77777777-7777-7777-7777-777777777777",
        state_checkpointer=cp,  # type: ignore[arg-type]
    )
    assert cp.load_calls == ["77777777-7777-7777-7777-777777777777"]
    # Falls back to the resume id as the run_id and runs to completion.
    assert final.get("error") is None
    assert final["run_id"] == "77777777-7777-7777-7777-777777777777"


async def test_resume_from_failed_run_retries_instead_of_reraising_stale_error() -> None:
    # FIX 1 regression: the newest checkpoint of a FAILED run carries that run's terminal
    # error/error_type. Resuming must STRIP them and actually retry the pipeline -- not seed the
    # stale error and short-circuit straight to END (which would defeat recovery).
    failed_snapshot: WorkflowState = _core_state(
        run_id="88888888-8888-8888-8888-888888888888",
        error="RetrievalError: boom",  # type: ignore[typeddict-unknown-key]
        error_type="retrieval",  # type: ignore[typeddict-unknown-key]
    )
    cp = _RecordingCheckpointer(loaded=failed_snapshot)
    graphs = _happy_graphs()
    extraction = graphs["extraction_graph"]
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **graphs,
    )
    # A realistic recovery caller passes a fresh initial_state with no error key.
    final = await run_compliance_workflow(
        _core_state(),
        graph=graph,
        resume_from="88888888-8888-8888-8888-888888888888",
        state_checkpointer=cp,  # type: ignore[arg-type]
    )
    # The stale error must NOT survive: the run actually retries end-to-end.
    assert final.get("error") is None
    assert final.get("error_type") is None
    assert len(extraction.calls) == 1  # extraction (and the rest of the pipeline) really ran
    assert final["report_content"] == "# Compliance Report"


async def test_resume_from_corrupt_extraction_snapshot_fails_cleanly() -> None:
    # FIX 2 regression: a checkpoint whose extraction_result can't re-hydrate must not crash the
    # resumed run; deserialize drops the field, so the Risk node's "no extraction_result" guard
    # fails the run cleanly through the workflow error channel.
    corrupt_snapshot: WorkflowState = {  # type: ignore[typeddict-item]
        "run_id": "66666666-6666-6666-6666-666666666666",
        "case_id": str(uuid4()),
        "query": "q",
        "document_id": str(uuid4()),
        "document_extraction_id": str(uuid4()),
        # Corrupt: a dict that is NOT a valid ExtractionResult.
        "extraction_result": {"bogus": 1},  # type: ignore[typeddict-item]
    }
    cp = _RecordingCheckpointer(loaded=corrupt_snapshot)
    graphs = _happy_graphs()
    # If the corrupt dict leaked through, risk would receive it and crash; instead the field is
    # dropped and the workflow's own guard produces a clean error. Extraction has no document text
    # in the corrupt snapshot, so the extraction node guards first.
    graph = build_compliance_workflow(
        ingestion_graph=_FakeGraph(),
        persist=False,
        state_checkpointer=cp,  # type: ignore[arg-type]
        checkpointing_enabled=True,
        **graphs,
    )
    final = await run_compliance_workflow(
        {  # type: ignore[arg-type]
            "case_id": corrupt_snapshot["case_id"],
            "query": "q",
            "document_id": corrupt_snapshot["document_id"],
            "document_extraction_id": corrupt_snapshot["document_extraction_id"],
        },
        graph=graph,
        resume_from="66666666-6666-6666-6666-666666666666",
        state_checkpointer=cp,  # type: ignore[arg-type]
    )
    # No crash: a clean workflow-level error (not an unhandled AttributeError from a mistyped dict).
    assert final.get("error") is not None
    assert final.get("error_type") == "extraction"
