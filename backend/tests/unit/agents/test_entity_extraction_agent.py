"""Unit tests for the Entity Extraction Agent (Task 46).

Nodes are tested in isolation with fakes for ``EntityExtractor``,
``ValidationOrchestrator``, and ``AsyncSession`` so the suite runs fully offline (no
LLM, no DB). Graph-level tests inject fakes to exercise routing without real I/O.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.agents import entity_extraction_agent as agent
from app.agents.entity_extraction_agent import (
    EntityExtractionState,
    extract_node,
    store_node,
    validate_node,
)
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import (
    SeverityLevel,
    ValidatedExtractionResult,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)
from app.services.entity_extractor import EntityExtractionError
from app.services.llm_service import LLMError
from app.services.validation_orchestrator import ValidationOrchestrationError

DOC_ID = "11111111-1111-1111-1111-111111111111"
EXT_ID = "22222222-2222-2222-2222-222222222222"


# ===== Fixtures / builders =====


def _extraction_result(*, confidence: float = 0.9) -> ExtractionResult:
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(name="Acme Corp", country_of_origin="DE"),
        product=ProductInfo(name="Coffee beans"),
        location=LocationInfo(country="BR"),
        shipment=ShipmentInfo(),
        extraction_confidence=confidence,
        extracted_at=datetime.now(UTC),
        model_used="fake-model",
    )


def _validated_result(
    *, is_valid: bool = True, retry_count: int = 0, score: float = 95.0
) -> ValidatedExtractionResult:
    failures: list[ValidationFailure] = []
    if not is_valid:
        failures.append(
            ValidationFailure(
                rule=ValidationRuleType.COMPLETENESS,
                field="supplier.name",
                message="Required field missing: supplier name",
                severity=SeverityLevel.CRITICAL,
            )
        )
    return ValidatedExtractionResult(
        extraction_id=uuid4(),
        entity_type="result",
        validation=ValidationResult(
            is_valid=is_valid,
            failures=failures,
            validation_score=score,
            checked_at=datetime.now(UTC),
        ),
        retry_count=retry_count,
        validated_at=datetime.now(UTC),
        extraction_data=None,
    )


class FakeExtractor:
    """Stand-in for EntityExtractor.extract_entities (no LLM)."""

    def __init__(
        self, *, result: ExtractionResult | None = None, raise_exc: Exception | None = None
    ) -> None:
        self._result = result if result is not None else _extraction_result()
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def extract_entities(
        self, *, document_id: Any, document_text: str, context: str = ""
    ) -> ExtractionResult:
        self.calls.append(
            {"document_id": document_id, "document_text": document_text, "context": context}
        )
        if self._raise is not None:
            raise self._raise
        return self._result


class FakeOrchestrator:
    """Stand-in for ValidationOrchestrator.validate_and_retry (no DB)."""

    def __init__(
        self, *, result: ValidatedExtractionResult | None = None, raise_exc: Exception | None = None
    ) -> None:
        self._result = result if result is not None else _validated_result()
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def validate_and_retry(
        self,
        *,
        extraction_result: Any,
        document_extraction_id: Any,
        document_text: str,
        context: str = "",
    ) -> ValidatedExtractionResult:
        self.calls.append(
            {
                "extraction_result": extraction_result,
                "document_extraction_id": document_extraction_id,
                "document_text": document_text,
                "context": context,
            }
        )
        if self._raise is not None:
            raise self._raise
        return self._result


class FakeSession:
    """Stand-in for AsyncSession (tracks commit/close).

    ``factory_calls`` counts how many times this instance was vended by a fake
    ``session_factory`` (see ``_run_validate``), so tests can assert that the
    session is only opened past the input guards.
    """

    def __init__(self, *, raise_on_commit: bool = False) -> None:
        self.raise_on_commit = raise_on_commit
        self.commits = 0
        self.closes = 0
        self.factory_calls = 0

    async def commit(self) -> None:
        if self.raise_on_commit:
            raise RuntimeError("db connection lost")
        self.commits += 1

    async def close(self) -> None:
        self.closes += 1


async def _run_validate(
    state: EntityExtractionState,
    orchestrator: "FakeOrchestrator",
    session: FakeSession,
) -> dict[str, Any]:
    """Invoke validate_node with a session_factory that vends ``session`` once."""

    def _session_factory() -> FakeSession:
        session.factory_calls += 1
        return session

    return await validate_node(
        state,
        session_factory=_session_factory,  # type: ignore[arg-type]
        orchestrator_factory=lambda _s: orchestrator,  # type: ignore[arg-type,return-value]
    )


# ===== extract_node =====


async def test_extract_node_success() -> None:
    extractor = FakeExtractor()
    result = await extract_node(
        {"document_id": DOC_ID, "document_text": "Supplier: Acme"}, extractor
    )  # type: ignore[arg-type]

    assert "extraction_result" in result
    assert "error" not in result
    assert extractor.calls[0]["document_text"] == "Supplier: Acme"


async def test_extract_node_passes_context() -> None:
    extractor = FakeExtractor()
    await extract_node(
        {"document_id": DOC_ID, "document_text": "text", "context": "retrieved ctx"},
        extractor,  # type: ignore[arg-type]
    )
    assert extractor.calls[0]["context"] == "retrieved ctx"


async def test_extract_node_empty_text() -> None:
    extractor = FakeExtractor()
    result = await extract_node({"document_id": DOC_ID, "document_text": ""}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"
    assert "document_text" in result["error"]
    assert extractor.calls == []


async def test_extract_node_whitespace_text() -> None:
    extractor = FakeExtractor()
    result = await extract_node({"document_id": DOC_ID, "document_text": "   \n\t"}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"
    assert extractor.calls == []


async def test_extract_node_invalid_document_id() -> None:
    extractor = FakeExtractor()
    result = await extract_node({"document_id": "not-a-uuid", "document_text": "text"}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"
    assert "document_id" in result["error"]
    assert extractor.calls == []


async def test_extract_node_llm_error() -> None:
    extractor = FakeExtractor(raise_exc=LLMError("provider down"))
    result = await extract_node({"document_id": DOC_ID, "document_text": "text"}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"
    assert "provider down" in result["error"]


async def test_extract_node_entity_extraction_error() -> None:
    extractor = FakeExtractor(raise_exc=EntityExtractionError("invalid JSON"))
    result = await extract_node({"document_id": DOC_ID, "document_text": "text"}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"
    assert "invalid JSON" in result["error"]


async def test_extract_node_validation_error() -> None:
    # Trigger a real pydantic ValidationError by constructing an invalid model.
    from pydantic import ValidationError

    try:
        SupplierInfo(name="", country_of_origin="DE")
    except ValidationError as exc:
        extractor = FakeExtractor(raise_exc=exc)
    else:  # pragma: no cover - guard
        pytest.fail("expected ValidationError")

    result = await extract_node({"document_id": DOC_ID, "document_text": "text"}, extractor)  # type: ignore[arg-type]
    assert result["error_type"] == "extraction"


# ===== validate_node =====


async def test_validate_node_valid_first_try() -> None:
    orch = FakeOrchestrator(result=_validated_result(is_valid=True, retry_count=0, score=98.0))
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
    }
    result = await _run_validate(state, orch, FakeSession())

    assert result["validation_status"] == "valid"
    assert result["retry_count"] == 0
    assert result["validation_score"] == 98.0
    assert "error" not in result


async def test_validate_node_retries_then_valid() -> None:
    orch = FakeOrchestrator(result=_validated_result(is_valid=True, retry_count=2))
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
    }
    result = await _run_validate(state, orch, FakeSession())

    assert result["retry_count"] == 2
    assert result["validation_status"] == "valid"


async def test_validate_node_retries_exhausted_is_failed_not_error() -> None:
    orch = FakeOrchestrator(result=_validated_result(is_valid=False, retry_count=3, score=10.0))
    session = FakeSession()
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
    }
    result = await _run_validate(state, orch, session)

    assert result["validation_status"] == "failed"
    assert result["retry_count"] == 3
    assert "error" not in result  # decision D: stored outcome, not a graph error
    assert result["_session"] is session  # success path hands the session to store
    assert session.closes == 0  # store_node closes it, not validate_node


async def test_validate_node_passes_context() -> None:
    orch = FakeOrchestrator()
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
        "context": "ctx",
    }
    await _run_validate(state, orch, FakeSession())
    assert orch.calls[0]["context"] == "ctx"


async def test_validate_node_missing_extraction_result() -> None:
    orch = FakeOrchestrator()
    session = FakeSession()
    result = await _run_validate({"document_extraction_id": EXT_ID}, orch, session)
    assert result["error_type"] == "validation"
    assert orch.calls == []
    assert session.factory_calls == 0  # guard fires before a session is opened


async def test_validate_node_missing_extraction_id() -> None:
    orch = FakeOrchestrator()
    session = FakeSession()
    state: EntityExtractionState = {"extraction_result": _extraction_result()}
    result = await _run_validate(state, orch, session)
    assert result["error_type"] == "validation"
    assert "document_extraction_id" in result["error"]
    assert orch.calls == []
    assert session.factory_calls == 0


async def test_validate_node_blank_extraction_id() -> None:
    orch = FakeOrchestrator()
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": "",
    }
    result = await _run_validate(state, orch, FakeSession())
    assert result["error_type"] == "validation"
    assert orch.calls == []


async def test_validate_node_orchestration_error_closes_session() -> None:
    orch = FakeOrchestrator(raise_exc=ValidationOrchestrationError("pipeline timed out"))
    session = FakeSession()
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
    }
    result = await _run_validate(state, orch, session)
    assert result["error_type"] == "validation"
    assert "timed out" in result["error"]
    assert "_session" not in result  # error path does not hand off the session
    assert session.closes == 1  # validate_node closes it since store won't run


async def test_validate_node_unexpected_exception_closes_session() -> None:
    orch = FakeOrchestrator(raise_exc=RuntimeError("boom"))
    session = FakeSession()
    state: EntityExtractionState = {
        "extraction_result": _extraction_result(),
        "document_extraction_id": EXT_ID,
        "document_text": "text",
    }
    with pytest.raises(RuntimeError):
        await _run_validate(state, orch, session)
    assert session.closes == 1  # session released even on an unexpected error


# ===== store_node =====


async def test_store_node_commits_and_closes() -> None:
    session = FakeSession()
    result = await store_node({"document_id": DOC_ID, "_session": session})  # type: ignore[arg-type]
    assert result["stored"] is True
    assert session.commits == 1
    assert session.closes == 1


async def test_store_node_commit_failure_closes_and_hides_detail() -> None:
    session = FakeSession(raise_on_commit=True)
    result = await store_node({"document_id": DOC_ID, "_session": session})  # type: ignore[arg-type]
    assert result["error_type"] == "storage"
    assert "stored" not in result
    # Generic message only — the raw DB exception must not leak into state.
    assert "db connection lost" not in result["error"]
    assert session.closes == 1


async def test_store_node_missing_session() -> None:
    result = await store_node({"document_id": DOC_ID})  # type: ignore[arg-type]
    assert result["error_type"] == "storage"
    assert "No active session" in result["error"]


# ===== helpers =====


def test_fail_helper_shape() -> None:
    out = agent._fail("extraction", "boom")
    assert out == {"error": "boom", "error_type": "extraction"}


def test_fail_helper_sanitizes_returned_message() -> None:
    out = agent._fail("extraction", "line1\nline2\rline3")
    # Newlines/CRs are stripped in the returned error (not just the log line).
    assert "\n" not in out["error"]
    assert "\r" not in out["error"]


def test_status_of_valid_and_failed() -> None:
    assert agent._status_of(_validated_result(is_valid=True)) == "valid"
    assert agent._status_of(_validated_result(is_valid=False, retry_count=3)) == "failed"


# ===== Graph assembly + routing =====


def _build_graph(
    *,
    extractor: FakeExtractor | None = None,
    orchestrator: FakeOrchestrator | None = None,
    session: FakeSession | None = None,
) -> Any:
    extractor = extractor or FakeExtractor()
    orchestrator = orchestrator or FakeOrchestrator()
    session = session or FakeSession()
    return agent.build_entity_extraction_graph(
        extractor=extractor,  # type: ignore[arg-type]
        orchestrator_factory=lambda _s: orchestrator,  # type: ignore[arg-type,return-value]
        session_factory=lambda: session,  # type: ignore[arg-type,return-value]
    )


def _valid_initial_state() -> EntityExtractionState:
    return {
        "document_id": DOC_ID,
        "document_extraction_id": EXT_ID,
        "document_text": "Supplier: Acme Corp, Germany. Product: coffee.",
    }


async def test_graph_happy_path() -> None:
    session = FakeSession()
    graph = _build_graph(session=session)
    final = await graph.ainvoke(_valid_initial_state())

    assert final.get("error") is None
    assert final["stored"] is True
    assert final["validation_status"] == "valid"
    assert "extraction_result" in final
    assert session.commits == 1


async def test_graph_extraction_failure_short_circuits() -> None:
    extractor = FakeExtractor(raise_exc=LLMError("down"))
    orchestrator = FakeOrchestrator()
    session = FakeSession()
    graph = _build_graph(extractor=extractor, orchestrator=orchestrator, session=session)

    final = await graph.ainvoke(_valid_initial_state())

    assert final["error_type"] == "extraction"
    assert orchestrator.calls == []  # validate not reached
    assert session.commits == 0  # store not reached


async def test_graph_validation_failure_short_circuits() -> None:
    orchestrator = FakeOrchestrator(raise_exc=ValidationOrchestrationError("timeout"))
    session = FakeSession()
    graph = _build_graph(orchestrator=orchestrator, session=session)

    final = await graph.ainvoke(_valid_initial_state())

    assert final["error_type"] == "validation"
    assert session.commits == 0  # store not reached


async def test_graph_failed_status_still_stores() -> None:
    orchestrator = FakeOrchestrator(
        result=_validated_result(is_valid=False, retry_count=3, score=5.0)
    )
    session = FakeSession()
    graph = _build_graph(orchestrator=orchestrator, session=session)

    final = await graph.ainvoke(_valid_initial_state())

    # decision D: 'failed' is a stored outcome that still reaches store/END.
    assert final.get("error") is None
    assert final["validation_status"] == "failed"
    assert final["stored"] is True
    assert session.commits == 1


async def test_graph_shares_single_session() -> None:
    """The same session feeds the orchestrator factory and store commit."""
    seen: dict[str, Any] = {}
    session = FakeSession()

    def _orch_factory(s: Any) -> FakeOrchestrator:
        seen["session"] = s
        return FakeOrchestrator()

    graph = agent.build_entity_extraction_graph(
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        orchestrator_factory=_orch_factory,  # type: ignore[arg-type]
        session_factory=lambda: session,  # type: ignore[arg-type,return-value]
    )
    await graph.ainvoke(_valid_initial_state())

    assert seen["session"] is session
    assert session.commits == 1
    assert session.closes == 1  # closed after store


def test_build_graph_accepts_injected_fakes_without_real_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Injecting fakes must not construct any real LLM/DB service."""

    def _boom(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover - must not be called
        raise AssertionError("real service constructed despite injection")

    monkeypatch.setattr(agent, "_default_orchestrator_factory", _boom)

    graph = _build_graph()
    assert graph is not None


def test_build_graph_checkpointer_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    stub_graph = object()

    def _spy_compile(self: Any, *, checkpointer: Any = None) -> Any:
        captured["checkpointer"] = checkpointer
        return stub_graph

    monkeypatch.setattr(agent.StateGraph, "compile", _spy_compile)
    sentinel = object()

    graph = agent.build_entity_extraction_graph(
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        orchestrator_factory=lambda _s: FakeOrchestrator(),  # type: ignore[arg-type,return-value]
        session_factory=lambda: FakeSession(),  # type: ignore[arg-type,return-value]
        checkpointer=sentinel,
    )

    assert captured["checkpointer"] is sentinel
    assert graph is stub_graph


# ===== run_entity_extraction =====


async def test_run_entity_extraction_with_injected_graph() -> None:
    graph = _build_graph()
    final = await agent.run_entity_extraction(_valid_initial_state(), graph=graph)
    assert final["stored"] is True


def test_default_orchestrator_factory_wires_real_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default factory constructs a real ValidationOrchestrator from a session."""
    from app.services.validation_orchestrator import ValidationOrchestrator

    monkeypatch.setattr(agent, "get_llm_service", lambda: object(), raising=False)
    monkeypatch.setattr("app.services.llm_service.get_llm_service", lambda: object())
    # EntityExtractor only requires a truthy llm_service; ExtractionRetryService a non-None
    # extractor. A FakeSession satisfies the orchestrator's session arg.
    orch = agent._default_orchestrator_factory(FakeSession())  # type: ignore[arg-type]
    assert isinstance(orch, ValidationOrchestrator)


def test_build_graph_default_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing injected, the builder constructs real services lazily."""
    monkeypatch.setattr("app.services.llm_service.get_llm_service", lambda: object())
    monkeypatch.setattr(
        "app.tasks.document_tasks._get_engine_and_factory",
        lambda: (object(), lambda: FakeSession()),
    )
    graph = agent.build_entity_extraction_graph()
    assert graph is not None


async def test_store_closure_handles_missing_session() -> None:
    """The _store closure fails gracefully when no session was bound (defensive guard).

    If ``session_factory`` yields ``None``, the orchestrator factory still validates,
    but ``_store`` finds no active session and routes to a storage error instead of
    raising.
    """
    graph = agent.build_entity_extraction_graph(
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        # Orchestrator tolerates a None session (it is never used by the fake).
        orchestrator_factory=lambda _s: FakeOrchestrator(),  # type: ignore[arg-type,return-value]
        session_factory=lambda: None,  # type: ignore[arg-type,return-value]
    )
    final = await graph.ainvoke(_valid_initial_state())
    assert final["error_type"] == "storage"
    assert "No active session" in final["error"]


async def test_run_entity_extraction_builds_default_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    built: dict[str, bool] = {}
    real_build = agent.build_entity_extraction_graph

    def _fake_build(**kwargs: Any) -> Any:
        built["called"] = True
        return real_build(
            extractor=FakeExtractor(),  # type: ignore[arg-type]
            orchestrator_factory=lambda _s: FakeOrchestrator(),  # type: ignore[arg-type,return-value]
            session_factory=lambda: FakeSession(),  # type: ignore[arg-type,return-value]
        )

    monkeypatch.setattr(agent, "build_entity_extraction_graph", _fake_build)

    final = await agent.run_entity_extraction(_valid_initial_state())

    assert built["called"] is True
    assert final["stored"] is True
