"""Unit tests for the Evidence Validation Agent (Task 49).

Nodes are tested in isolation and via the full graph. The agent makes NO LLM call -- both wrapped
services (``CitationService`` grounding + ``ConsistencyChecker`` conflict detection) are deterministic
and offline, so they are constructed for real and injected directly. The suite runs fully offline
(no LLM API, no network, no DB).
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.agents import evidence_validation_agent as agent
from app.agents.evidence_validation_agent import (
    EvidenceValidationState,
    assess_validation_node,
    build_evidence_validation_graph,
    check_consistency_node,
    check_grounding_node,
    run_evidence_validation,
)
from app.models.vector_embedding import SearchResult
from app.schemas.validation import (
    SeverityLevel,
    ValidatedExtractionResult,
    ValidationFailure,
    ValidationResult,
    ValidationRuleType,
)
from app.services.citation_service import CitationService
from app.services.consistency_checker import ConsistencyChecker

# ===== Builders =====


def _search_result(*, doc_id: str, text: str, score: float = 0.9) -> SearchResult:
    """Build a SearchResult whose chunk_text controls term overlap with a crafted answer."""
    return SearchResult(
        embedding_id=f"emb-{doc_id}",
        document_extraction_id=doc_id,
        chunk_index=0,
        chunk_text=text,
        similarity_score=score,
        embedding_model="fake-model",
    )


def _validation_result(*, is_valid: bool = True) -> ValidationResult:
    failures: list[ValidationFailure] = (
        []
        if is_valid
        else [
            ValidationFailure(
                rule=ValidationRuleType.COMPLETENESS,
                field="supplier.name",
                message="missing",
                severity=SeverityLevel.WARNING,
            )
        ]
    )
    return ValidationResult(
        is_valid=is_valid,
        failures=failures,
        validation_score=100.0 if is_valid else 50.0,
        checked_at=datetime.now(UTC),
    )


def _validated_entity(
    *,
    supplier_name: str = "Acme Corp",
    country: str = "CN",
) -> ValidatedExtractionResult:
    """Build a ValidatedExtractionResult whose extraction_data drives the consistency validators.

    Two entities with the same ``supplier_name`` group together; differing ``country`` produces a
    HIGH-severity ``supplier.country_of_origin`` field conflict.
    """
    return ValidatedExtractionResult(
        extraction_id=uuid4(),
        entity_type="supplier",
        validation=_validation_result(),
        retry_count=0,
        validated_at=datetime.now(UTC),
        extraction_data={
            "supplier": {"name": supplier_name, "country_of_origin": country},
        },
    )


# A grounded answer shares many >3-char terms with the source chunk below.
_GROUNDED_ANSWER = (
    "The supplier Acme Corporation ships electronics from Shanghai port with certification documents."
)
_GROUNDED_SOURCE = (
    "Acme Corporation supplier ships electronics from Shanghai port; certification documents attached."
)
# An ungrounded answer shares no meaningful terms with the source.
_UNGROUNDED_ANSWER = "Quarterly revenue projections exceeded forecasts substantially."
_UNRELATED_SOURCE = "Shipping manifest lists tomatoes oranges bananas mangoes pineapples."


def _grounded_state(**overrides: Any) -> EvidenceValidationState:
    state: EvidenceValidationState = {
        "answer": _GROUNDED_ANSWER,
        "search_results": [_search_result(doc_id="doc-1", text=_GROUNDED_SOURCE)],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


# ===== check_grounding_node =====


def test_grounding_grounded_answer_produces_citations() -> None:
    out = check_grounding_node(_grounded_state(), CitationService())
    assert out["citations"], "expected at least one citation for a grounded answer"
    assert out["is_grounded"] is True
    assert 0.0 < out["grounding_score"] <= 1.0
    assert "error" not in out


def test_grounding_score_and_risk_are_complementary() -> None:
    out = check_grounding_node(_grounded_state(), CitationService())
    assert out["hallucination_risk"] == pytest.approx(1.0 - out["grounding_score"])


def test_grounding_ungrounded_answer_no_citations_no_error() -> None:
    state: EvidenceValidationState = {
        "answer": _UNGROUNDED_ANSWER,
        "search_results": [_search_result(doc_id="doc-1", text=_UNRELATED_SOURCE)],
    }
    out = check_grounding_node(state, CitationService())
    assert out["citations"] == []
    assert out["is_grounded"] is False
    assert out["grounding_score"] == 0.0
    assert out["hallucination_risk"] == 1.0
    assert "error" not in out


def test_grounding_empty_search_results_is_ungrounded_not_error() -> None:
    state: EvidenceValidationState = {"answer": _GROUNDED_ANSWER, "search_results": []}
    out = check_grounding_node(state, CitationService())
    assert out["citations"] == []
    assert out["is_grounded"] is False
    assert "error" not in out


def test_grounding_missing_search_results_key_is_ungrounded() -> None:
    out = check_grounding_node({"answer": _GROUNDED_ANSWER}, CitationService())
    assert out["citations"] == []
    assert "error" not in out


def test_grounding_empty_answer_is_error() -> None:
    out = check_grounding_node({"answer": ""}, CitationService())
    assert out["error"]
    assert out["error_type"] == "grounding"


def test_grounding_whitespace_answer_is_error() -> None:
    out = check_grounding_node({"answer": "   \n  "}, CitationService())
    assert out["error_type"] == "grounding"


def test_grounding_missing_answer_key_is_error() -> None:
    out = check_grounding_node({}, CitationService())
    assert out["error_type"] == "grounding"


def test_grounding_score_in_range() -> None:
    out = check_grounding_node(_grounded_state(), CitationService())
    assert 0.0 <= out["grounding_score"] <= 1.0
    assert 0.0 <= out["hallucination_risk"] <= 1.0


# ===== check_consistency_node =====


@pytest.mark.asyncio
async def test_consistency_detects_field_conflict() -> None:
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="VN"),
    ]
    out = await check_consistency_node(
        {"validated_entities": entities, "case_id": str(uuid4())}, ConsistencyChecker()
    )
    assert out["consistency_checked"] is True
    report = out["consistency_report"]
    assert report.total_conflict_count > 0
    assert "error" not in out


@pytest.mark.asyncio
async def test_consistency_no_conflict_for_agreeing_docs() -> None:
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="CN"),
    ]
    out = await check_consistency_node({"validated_entities": entities}, ConsistencyChecker())
    assert out["consistency_checked"] is True
    assert out["consistency_report"].total_conflict_count == 0


@pytest.mark.asyncio
async def test_consistency_skipped_when_no_entities() -> None:
    out = await check_consistency_node({"validated_entities": None}, ConsistencyChecker())
    assert out["consistency_checked"] is False
    assert out["consistency_report"].total_conflict_count == 0
    assert "skipped" in out["consistency_report"].summary.lower()
    assert "error" not in out


@pytest.mark.asyncio
async def test_consistency_skipped_when_empty_list() -> None:
    out = await check_consistency_node({"validated_entities": []}, ConsistencyChecker())
    assert out["consistency_checked"] is False
    assert "error" not in out


@pytest.mark.asyncio
async def test_consistency_skipped_when_key_missing() -> None:
    out = await check_consistency_node({}, ConsistencyChecker())
    assert out["consistency_checked"] is False


@pytest.mark.asyncio
async def test_consistency_service_valueerror_is_error() -> None:
    class _RaisingChecker:
        async def check_consistency(self, case_id: UUID, validated_entities: list[Any]) -> Any:
            raise ValueError("malformed entities")

    out = await check_consistency_node(
        {"validated_entities": [_validated_entity()]}, _RaisingChecker()  # type: ignore[arg-type]
    )
    assert out["error_type"] == "consistency"
    assert "malformed" in out["error"]


@pytest.mark.asyncio
async def test_consistency_default_case_id_when_absent() -> None:
    captured: dict[str, Any] = {}

    class _CapturingChecker:
        async def check_consistency(self, case_id: UUID, validated_entities: list[Any]) -> Any:
            captured["case_id"] = case_id
            return await ConsistencyChecker().check_consistency(case_id, validated_entities)

    await check_consistency_node(
        {"validated_entities": [_validated_entity()]}, _CapturingChecker()  # type: ignore[arg-type]
    )
    assert captured["case_id"] == UUID("00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_consistency_invalid_case_id_falls_back_to_sentinel() -> None:
    captured: dict[str, Any] = {}

    class _CapturingChecker:
        async def check_consistency(self, case_id: UUID, validated_entities: list[Any]) -> Any:
            captured["case_id"] = case_id
            return await ConsistencyChecker().check_consistency(case_id, validated_entities)

    await check_consistency_node(
        {"validated_entities": [_validated_entity()], "case_id": "not-a-uuid"},
        _CapturingChecker(),  # type: ignore[arg-type]
    )
    assert captured["case_id"] == UUID("00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_consistency_parses_supplied_case_id() -> None:
    captured: dict[str, Any] = {}
    cid = uuid4()

    class _CapturingChecker:
        async def check_consistency(self, case_id: UUID, validated_entities: list[Any]) -> Any:
            captured["case_id"] = case_id
            return await ConsistencyChecker().check_consistency(case_id, validated_entities)

    await check_consistency_node(
        {"validated_entities": [_validated_entity()], "case_id": str(cid)},
        _CapturingChecker(),  # type: ignore[arg-type]
    )
    assert captured["case_id"] == cid


# ===== assess_validation_node =====


def _grounding_part(*, grounded: bool) -> dict[str, Any]:
    if grounded:
        return {
            "citations": [{"source_doc_id": "d1", "confidence": 0.8, "relevance_score": 0.9}],
            "grounding_score": 0.8,
            "is_grounded": True,
            "hallucination_risk": 0.2,
        }
    return {
        "citations": [],
        "grounding_score": 0.0,
        "is_grounded": False,
        "hallucination_risk": 1.0,
    }


async def _consistency_part(entities: list[Any] | None) -> dict[str, Any]:
    return await check_consistency_node({"validated_entities": entities}, ConsistencyChecker())


@pytest.mark.asyncio
async def test_assess_grounded_and_consistent_is_valid() -> None:
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    out = assess_validation_node(state)
    ev = out["evidence_validation"]
    assert ev["is_valid"] is True
    assert ev["is_grounded"] is True
    assert ev["citation_count"] == 1


@pytest.mark.asyncio
async def test_assess_ungrounded_is_not_valid() -> None:
    state: EvidenceValidationState = {**_grounding_part(grounded=False)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    ev = assess_validation_node(state)["evidence_validation"]
    assert ev["is_valid"] is False
    assert ev["is_grounded"] is False
    assert any("ungrounded" in f.lower() for f in ev["findings"])


@pytest.mark.asyncio
async def test_assess_grounded_but_high_risk_band_is_not_valid() -> None:
    # A citation just over the grounding floor (is_grounded=True) but with a low grounding_score
    # falls in the "high" hallucination band -> is_valid must be False (no contradictory verdict).
    state: EvidenceValidationState = {
        "citations": [{"source_doc_id": "d1", "confidence": 0.35, "relevance_score": 0.9}],
        "grounding_score": 0.35,  # >= min_confidence (0.3) but < medium (0.5) -> high band
        "is_grounded": True,
        "hallucination_risk": 0.65,
    }
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    ev = assess_validation_node(state)["evidence_validation"]
    assert ev["is_grounded"] is True
    assert ev["hallucination_band"] == "high"
    assert ev["is_valid"] is False


@pytest.mark.asyncio
async def test_assess_high_severity_conflict_fails_validation() -> None:
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="VN"),
    ]
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(entities))  # type: ignore[typeddict-item]
    ev = assess_validation_node(state)["evidence_validation"]
    assert ev["consistency"]["high_severity_count"] > 0
    assert ev["is_valid"] is False
    assert "high-severity" in ev["reasoning"].lower()


@pytest.mark.asyncio
async def test_assess_findings_include_percentages() -> None:
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    findings = assess_validation_node(state)["evidence_validation"]["findings"]
    assert any("%" in f and "grounded" in f.lower() for f in findings)
    assert any("hallucination risk" in f.lower() and "%" in f for f in findings)


@pytest.mark.asyncio
async def test_assess_output_is_json_serializable() -> None:
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="VN"),
    ]
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(entities))  # type: ignore[typeddict-item]
    ev = assess_validation_node(state)["evidence_validation"]
    encoded = json.dumps(ev)
    assert json.loads(encoded)["is_valid"] in (True, False)


@pytest.mark.asyncio
async def test_assess_consistency_block_has_all_keys() -> None:
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    block = assess_validation_node(state)["evidence_validation"]["consistency"]
    for key in (
        "checked",
        "total_conflict_count",
        "field_conflicts",
        "temporal_conflicts",
        "logical_conflicts",
        "high_severity_count",
        "confidence_adjustment",
        "summary",
        "conflicts",
    ):
        assert key in block


def test_assess_missing_prerequisites_is_error() -> None:
    out = assess_validation_node({"grounding_score": 0.5})
    assert out["error_type"] == "validation"


@pytest.mark.asyncio
async def test_assess_skipped_consistency_finding() -> None:
    state: EvidenceValidationState = {**_grounding_part(grounded=True)}  # type: ignore[typeddict-item]
    state.update(await _consistency_part(None))  # type: ignore[typeddict-item]
    findings = assess_validation_node(state)["evidence_validation"]["findings"]
    assert any("skipped" in f.lower() for f in findings)


def test_hallucination_band_all_three_reachable_at_defaults() -> None:
    # Banded on grounding_score with the DEFAULT thresholds (medium=0.5, high=0.7); all three
    # bands must be reachable -- a prior single-threshold form left "medium" dead at the default.
    md, hi = 0.5, 0.7
    assert agent._hallucination_band(0.9, medium_threshold=md, high_threshold=hi) == "low"
    assert agent._hallucination_band(0.7, medium_threshold=md, high_threshold=hi) == "low"
    assert agent._hallucination_band(0.6, medium_threshold=md, high_threshold=hi) == "medium"
    assert agent._hallucination_band(0.5, medium_threshold=md, high_threshold=hi) == "medium"
    assert agent._hallucination_band(0.49, medium_threshold=md, high_threshold=hi) == "high"
    assert agent._hallucination_band(0.0, medium_threshold=md, high_threshold=hi) == "high"


# ===== Graph assembly + run =====


@pytest.mark.asyncio
async def test_run_full_graph_grounded_consistent_is_valid() -> None:
    graph = build_evidence_validation_graph(
        citation_service=CitationService(), consistency_checker=ConsistencyChecker()
    )
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="CN"),
    ]
    final = await run_evidence_validation(
        _grounded_state(validated_entities=entities), graph=graph
    )
    assert final.get("error") is None
    ev = final["evidence_validation"]
    assert ev["is_valid"] is True
    assert final["consistency_checked"] is True


@pytest.mark.asyncio
async def test_run_full_graph_ungrounded_with_conflict_not_valid() -> None:
    graph = build_evidence_validation_graph(
        citation_service=CitationService(), consistency_checker=ConsistencyChecker()
    )
    entities = [
        _validated_entity(supplier_name="Acme Corp", country="CN"),
        _validated_entity(supplier_name="Acme Corp", country="VN"),
    ]
    state: EvidenceValidationState = {
        "answer": _UNGROUNDED_ANSWER,
        "search_results": [_search_result(doc_id="d1", text=_UNRELATED_SOURCE)],
        "validated_entities": entities,
    }
    final = await run_evidence_validation(state, graph=graph)
    ev = final["evidence_validation"]
    assert ev["is_valid"] is False
    assert ev["is_grounded"] is False
    assert ev["consistency"]["total_conflict_count"] > 0


@pytest.mark.asyncio
async def test_run_empty_answer_short_circuits_before_consistency() -> None:
    graph = build_evidence_validation_graph(
        citation_service=CitationService(), consistency_checker=ConsistencyChecker()
    )
    final = await run_evidence_validation(
        {"answer": "", "validated_entities": [_validated_entity()]}, graph=graph
    )
    assert final["error"]
    assert final["error_type"] == "grounding"
    # Later nodes did not run.
    assert "consistency_report" not in final
    assert "evidence_validation" not in final


@pytest.mark.asyncio
async def test_run_standalone_no_entities_reaches_end() -> None:
    graph = build_evidence_validation_graph(
        citation_service=CitationService(), consistency_checker=ConsistencyChecker()
    )
    final = await run_evidence_validation(_grounded_state(), graph=graph)
    assert final.get("error") is None
    assert final["consistency_checked"] is False
    assert final["evidence_validation"]["is_valid"] is True


@pytest.mark.asyncio
async def test_run_consistency_error_short_circuits() -> None:
    class _RaisingChecker:
        async def check_consistency(self, case_id: UUID, validated_entities: list[Any]) -> Any:
            raise ValueError("boom")

    graph = build_evidence_validation_graph(
        citation_service=CitationService(),
        consistency_checker=_RaisingChecker(),  # type: ignore[arg-type]
    )
    final = await run_evidence_validation(
        _grounded_state(validated_entities=[_validated_entity()]), graph=graph
    )
    assert final["error_type"] == "consistency"
    assert "evidence_validation" not in final


@pytest.mark.asyncio
async def test_build_graph_accepts_checkpointer() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    graph = build_evidence_validation_graph(checkpointer=MemorySaver())
    assert graph is not None


@pytest.mark.asyncio
async def test_run_builds_default_graph_when_none() -> None:
    # graph=None path builds real (offline) services; grounded standalone answer.
    final = await run_evidence_validation(_grounded_state())
    assert final.get("error") is None
    assert "evidence_validation" in final


@pytest.mark.asyncio
async def test_full_output_round_trips_json() -> None:
    final = await run_evidence_validation(_grounded_state())
    encoded = json.dumps(final["evidence_validation"])
    assert "is_valid" in json.loads(encoded)


# ===== exports =====


def test_exports_present() -> None:
    from app import agents as agents_pkg

    for name in (
        "EvidenceValidationState",
        "build_evidence_validation_graph",
        "run_evidence_validation",
    ):
        assert name in agents_pkg.__all__
        assert hasattr(agents_pkg, name)


def test_node_exports_present() -> None:
    assert "check_grounding_node" in agent.__all__
    assert "check_consistency_node" in agent.__all__
    assert "assess_validation_node" in agent.__all__
