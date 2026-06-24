"""Unit tests for the Risk Assessment Agent (Task 48).

Nodes are tested in isolation and via the full graph with a fake ``LLMProvider`` so the suite runs
fully offline (no LLM API, no network, no DB). The three pure Phase 5 services
(``EvidenceGapAnalyzer`` / ``RiskScorer`` / ``ConfidenceScorer``) are real and injected directly;
``AIRiskAssessor`` is real but built on the fake provider, which lets us exercise both the LLM
success path and the service's internal ``LLMError`` fallback.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.agents import risk_assessment_agent as agent
from app.agents.risk_assessment_agent import (
    RiskAssessmentState,
    analyze_evidence_node,
    assess_llm_node,
    build_risk_assessment_graph,
    run_risk_assessment,
    score_confidence_node,
    score_rules_node,
)
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.services.ai_risk_assessor import AIRiskAssessor
from app.services.confidence_scorer import ConfidenceScorer
from app.services.evidence_gap_analyzer import EvidenceGapAnalyzer
from app.services.llm_service import LLMError
from app.services.risk_scorer import RiskScorer

# ===== Fakes / builders =====


class FakeLLMProvider:
    """Stand-in for ``LLMProvider`` (no network). Drives ``AIRiskAssessor`` both ways."""

    def __init__(
        self,
        *,
        text: str | None = None,
        raises: Exception | None = None,
        model: str = "fake/model-1",
    ) -> None:
        self._text = text if text is not None else _llm_json()
        self._raises = raises
        self._model = model
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        self.calls.append(
            {"prompt_len": len(prompt), "temperature": temperature, "max_tokens": max_tokens}
        )
        if self._raises is not None:
            raise self._raises
        return {"text": self._text, "tokens": {}, "cost": 0.0, "model": self._model}

    def get_model_name(self) -> str:
        return self._model

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _llm_json(
    *,
    score: int = 55,
    confidence: float = 0.8,
    reasoning: str = "Supplier lacks certification and location is unverified.",
    actions: list[str] | None = None,
) -> str:
    payload = {
        "llm_score": score,
        "reasoning": reasoning,
        "confidence": confidence,
        "recommended_actions": actions if actions is not None else ["Request certification"],
    }
    return json.dumps(payload)


def _low_risk_entities() -> ExtractionResult:
    """A fully-populated, low-risk extraction (high confidence, all required fields)."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(
            name="Acme Timber Co",
            country_of_origin="DE",
            certification_status="certified",
        ),
        product=ProductInfo(
            name="Oak planks",
            hs_code="44071000",
            origin_country="DE",
            quantity=100.0,
            unit="kg",
        ),
        location=LocationInfo(country="DE", geolocation_verified=True),
        shipment=ShipmentInfo(
            origin_port="Hamburg",
            destination_port="Rotterdam",
            tracking_number="BL123456",
        ),
        extraction_confidence=0.95,
        extracted_at=datetime.now(UTC),
        model_used="fake/model-1",
    )


def _high_risk_entities() -> ExtractionResult:
    """A sparse, high-risk extraction (high-risk country, no certification, low confidence)."""
    return ExtractionResult(
        document_id=uuid4(),
        supplier=SupplierInfo(name="Unknown Supplier", country_of_origin="IR"),
        product=ProductInfo(name="Generic goods"),
        location=LocationInfo(country="IR", geolocation_verified=False),
        shipment=ShipmentInfo(),
        extraction_confidence=0.4,
        extracted_at=datetime.now(UTC),
        model_used="fake/model-1",
    )


def _state(entities: ExtractionResult | None = None, **extra: Any) -> RiskAssessmentState:
    state: dict[str, Any] = {}
    if entities is not None:
        state["entities"] = entities
    state.update(extra)
    return state  # type: ignore[return-value]


def _assessor(**kwargs: Any) -> AIRiskAssessor:
    return AIRiskAssessor(FakeLLMProvider(**kwargs))


def _graph(
    *,
    provider_kwargs: dict[str, Any] | None = None,
    checkpointer: Any | None = None,
):
    return build_risk_assessment_graph(
        evidence_analyzer=EvidenceGapAnalyzer(),
        risk_scorer=RiskScorer(),
        ai_assessor=_assessor(**(provider_kwargs or {})),
        confidence_scorer=ConfidenceScorer(),
        checkpointer=checkpointer,
    )


# ===== analyze_evidence_node =====


def test_analyze_evidence_populates_completeness_and_gaps() -> None:
    out = analyze_evidence_node(_state(_low_risk_entities()), EvidenceGapAnalyzer())
    assert "evidence_gap_result" in out
    assert 0.0 <= out["completeness_score"] <= 1.0
    assert out["completeness_score"] == out["evidence_gap_result"].completeness_score
    assert "error" not in out


def test_analyze_evidence_high_risk_has_gaps() -> None:
    out = analyze_evidence_node(
        _state(_high_risk_entities(), document_type="supplier_declaration"),
        EvidenceGapAnalyzer(),
    )
    assert out["evidence_gap_result"].gaps  # missing certification etc.


def test_analyze_evidence_missing_entities_sets_error() -> None:
    out = analyze_evidence_node(_state(None), EvidenceGapAnalyzer())
    assert out["error"]
    assert out["error_type"] == "evidence_gap"
    assert "evidence_gap_result" not in out


def test_analyze_evidence_default_document_type() -> None:
    # No document_type provided -> general catalogue, no exception.
    out = analyze_evidence_node(_state(_low_risk_entities()), EvidenceGapAnalyzer())
    assert out["evidence_gap_result"].document_type == "general"


# ===== score_rules_node =====


def test_score_rules_low_risk() -> None:
    out = score_rules_node(_state(_low_risk_entities()), RiskScorer())
    assert out["risk_score_result"].risk_level == "low"
    assert "error" not in out


def test_score_rules_high_risk_has_violations() -> None:
    out = score_rules_node(_state(_high_risk_entities()), RiskScorer())
    result = out["risk_score_result"]
    assert result.violation_count > 0
    assert result.risk_score > 20  # above the "low" band


def test_score_rules_passes_through_optional_inputs() -> None:
    # consistency_result / validation_result are forwarded without error when None.
    out = score_rules_node(
        _state(_low_risk_entities(), consistency_result=None, validation_result=None),
        RiskScorer(),
    )
    assert "risk_score_result" in out


def test_score_rules_missing_entities_sets_error() -> None:
    out = score_rules_node(_state(None), RiskScorer())
    assert out["error"]
    assert out["error_type"] == "risk_scoring"


# ===== assess_llm_node =====


@pytest.mark.asyncio
async def test_assess_llm_success_path() -> None:
    entities = _high_risk_entities()
    rule_result = RiskScorer().score(entities)
    out = await assess_llm_node(
        _state(entities, risk_score_result=rule_result),
        _assessor(text=_llm_json(score=60)),
    )
    assessment = out["ai_risk_assessment"]
    assert assessment.model_used != "fallback"
    assert assessment.llm_reasoning
    assert 0 <= assessment.combined_score <= 100
    assert "error" not in out


@pytest.mark.asyncio
async def test_assess_llm_fallback_is_not_an_error() -> None:
    entities = _high_risk_entities()
    rule_result = RiskScorer().score(entities)
    out = await assess_llm_node(
        _state(entities, risk_score_result=rule_result),
        _assessor(raises=LLMError("provider down")),
    )
    assessment = out["ai_risk_assessment"]
    assert assessment.model_used == "fallback"
    assert assessment.llm_confidence == 0.0
    assert "error" not in out  # business outcome, not a graph error


@pytest.mark.asyncio
async def test_assess_llm_missing_rule_score_sets_error() -> None:
    out = await assess_llm_node(_state(_high_risk_entities()), _assessor())
    assert out["error"]
    assert out["error_type"] == "llm_assessment"


@pytest.mark.asyncio
async def test_assess_llm_combined_score_uses_rule_and_llm() -> None:
    entities = _low_risk_entities()
    rule_result = RiskScorer().score(entities)
    out = await assess_llm_node(
        _state(entities, risk_score_result=rule_result),
        _assessor(text=_llm_json(score=80)),
    )
    assessment = out["ai_risk_assessment"]
    # Combined = 0.4*rule + 0.6*llm; with llm=80 it must exceed the rule-only score.
    assert assessment.llm_score == 80
    assert assessment.rule_based_score == rule_result.risk_score


# ===== score_confidence_node =====


def _confidence_state(entities: ExtractionResult, **extra: Any) -> RiskAssessmentState:
    """A state pre-loaded with the outputs the confidence node depends on."""
    evidence = EvidenceGapAnalyzer().analyze(entities)
    rule_result = RiskScorer().score(entities)
    # Build an AIRiskAssessment via the real assessor's fallback (sync, no await needed here):
    from app.services.ai_risk_assessor import AIRiskAssessment

    ai = AIRiskAssessment(
        rule_based_score=rule_result.risk_score,
        llm_score=50,
        combined_score=50,
        risk_level="high",
        llm_reasoning="reasoning",
        llm_confidence=0.7,
        recommended_actions=["act"],
        model_used="fake/model-1",
    )
    return _state(
        entities,
        evidence_gap_result=evidence,
        completeness_score=evidence.completeness_score,
        risk_score_result=rule_result,
        ai_risk_assessment=ai,
        **extra,
    )


def test_score_confidence_assembles_primary_output() -> None:
    entities = _low_risk_entities()
    out = score_confidence_node(_confidence_state(entities), ConfidenceScorer())
    ra = out["risk_assessment"]
    assert 0.0 <= ra["confidence_score"] <= 1.0
    assert ra["risk_level"] in {"low", "medium", "high", "critical"}
    assert ra["risk_score"] == 50  # combined from the injected assessment
    assert "error" not in out


def test_score_confidence_uses_default_source_quality() -> None:
    entities = _low_risk_entities()
    out_default = score_confidence_node(_confidence_state(entities), ConfidenceScorer())
    out_high = score_confidence_node(
        _confidence_state(entities, source_quality=1.0), ConfidenceScorer()
    )
    # Higher source_quality must not lower confidence.
    assert (
        out_high["confidence_result"].confidence_score
        >= out_default["confidence_result"].confidence_score
    )


def test_score_confidence_threads_completeness() -> None:
    entities = _high_risk_entities()
    out = score_confidence_node(_confidence_state(entities), ConfidenceScorer())
    factors = out["confidence_result"].factors
    # The completeness factor must equal the gap analysis completeness for these entities.
    expected = EvidenceGapAnalyzer().analyze(entities).completeness_score
    assert factors.evidence_completeness == expected


def test_score_confidence_missing_prereqs_sets_error() -> None:
    out = score_confidence_node(_state(_low_risk_entities()), ConfidenceScorer())
    assert out["error"]
    assert out["error_type"] == "confidence_scoring"


def test_score_confidence_explicit_none_source_quality_uses_default() -> None:
    # state.get("source_quality", default) returns None (not the default) when the key is present
    # with a None value; the node must coerce that to the default so ConfidenceScorer never gets
    # None (which would raise an uncaught TypeError from math.isnan, bypassing the error channel).
    entities = _low_risk_entities()
    out_none = score_confidence_node(
        _confidence_state(entities, source_quality=None), ConfidenceScorer()
    )
    assert "error" not in out_none
    out_default = score_confidence_node(_confidence_state(entities), ConfidenceScorer())
    # None coerces to the same default the absent-key path uses -> identical confidence.
    assert (
        out_none["confidence_result"].confidence_score
        == out_default["confidence_result"].confidence_score
    )


def test_assembled_output_has_all_keys_and_is_json_serializable() -> None:
    out = score_confidence_node(_confidence_state(_high_risk_entities()), ConfidenceScorer())
    ra = out["risk_assessment"]
    expected_keys = {
        "risk_score",
        "risk_level",
        "rule_based_score",
        "llm_score",
        "confidence_score",
        "confidence_level",
        "reasoning",
        "recommended_actions",
        "violations",
        "evidence_gaps",
        "completeness_score",
        "llm_available",
    }
    assert expected_keys == set(ra)
    assert isinstance(ra["violations"], list)
    assert isinstance(ra["evidence_gaps"], list)
    # Round-trips through json.dumps (Task 52 forward-compat).
    json.loads(json.dumps(ra))


# ===== Full graph =====


@pytest.mark.asyncio
async def test_graph_happy_path_produces_all_results() -> None:
    final = await run_risk_assessment(
        _state(_high_risk_entities()), graph=_graph()
    )
    assert final.get("error") is None
    assert "evidence_gap_result" in final
    assert "risk_score_result" in final
    assert "ai_risk_assessment" in final
    assert "confidence_result" in final
    assert "risk_assessment" in final
    assert final["risk_assessment"]["llm_available"] is True


@pytest.mark.asyncio
async def test_graph_short_circuits_on_bad_input() -> None:
    final = await run_risk_assessment(_state(None), graph=_graph())
    assert final["error"]
    assert final["error_type"] == "evidence_gap"
    # Later nodes never ran.
    assert "risk_score_result" not in final
    assert "ai_risk_assessment" not in final
    assert "risk_assessment" not in final


@pytest.mark.asyncio
async def test_graph_llm_down_still_reaches_end() -> None:
    final = await run_risk_assessment(
        _state(_high_risk_entities()),
        graph=_graph(provider_kwargs={"raises": LLMError("down")}),
    )
    assert final.get("error") is None
    assert final["risk_assessment"]["llm_available"] is False
    assert "risk_assessment" in final


@pytest.mark.asyncio
async def test_graph_accepts_checkpointer() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    graph = _graph(checkpointer=MemorySaver())
    final = await graph.ainvoke(
        _state(_low_risk_entities()),
        config={"configurable": {"thread_id": "t1"}},
    )
    assert final["risk_assessment"]["risk_level"] in {"low", "medium", "high", "critical"}


@pytest.mark.asyncio
async def test_graph_threads_source_quality_and_document_type() -> None:
    final = await run_risk_assessment(
        _state(
            _low_risk_entities(),
            source_quality=0.9,
            document_type="invoice",
        ),
        graph=_graph(),
    )
    assert final.get("error") is None
    assert final["evidence_gap_result"].document_type == "invoice"


@pytest.mark.asyncio
async def test_run_risk_assessment_preserves_inputs() -> None:
    entities = _low_risk_entities()
    final = await run_risk_assessment(_state(entities), graph=_graph())
    assert final["entities"] is entities


# ===== Wiring / exports =====


def test_default_builder_lazily_constructs_services(monkeypatch: pytest.MonkeyPatch) -> None:
    # build with no injected services must not require a live LLM service at import time:
    sentinel = _assessor()
    monkeypatch.setattr(agent, "_default_ai_assessor", lambda: sentinel)
    graph = build_risk_assessment_graph()
    assert graph is not None


def test_public_exports() -> None:
    import app.agents as agents_pkg

    for name in (
        "RiskAssessmentState",
        "build_risk_assessment_graph",
        "run_risk_assessment",
    ):
        assert name in agents_pkg.__all__
        assert hasattr(agents_pkg, name)


def test_default_ai_assessor_uses_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # _default_ai_assessor wires the provider that LLMService composes, without a live call.
    fake_provider = FakeLLMProvider()

    class _FakeLLMService:
        provider = fake_provider

    monkeypatch.setattr(
        "app.services.llm_service.get_llm_service", lambda: _FakeLLMService()
    )
    assessor = agent._default_ai_assessor()
    assert isinstance(assessor, AIRiskAssessor)
    assert assessor.provider is fake_provider


@pytest.mark.asyncio
async def test_run_risk_assessment_builds_default_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # When no graph is passed, run_risk_assessment builds the default graph itself.
    monkeypatch.setattr(agent, "build_risk_assessment_graph", lambda: _graph())
    final = await run_risk_assessment(_state(_low_risk_entities()))
    assert final.get("error") is None
    assert "risk_assessment" in final


# ===== Defensive guards (service ValueError -> error channel) =====


class _RaisingRiskScorer:
    """Stand-in whose ``score`` raises a ValueError (invalid inputs guard)."""

    def score(self, *args: Any, **kwargs: Any):
        raise ValueError("bad rule inputs")


class _RaisingConfidenceScorer:
    """Stand-in whose ``compute`` raises a ValueError (out-of-range factor guard)."""

    def compute(self, *args: Any, **kwargs: Any):
        raise ValueError("bad confidence inputs")


def test_score_rules_maps_value_error_to_error_channel() -> None:
    out = score_rules_node(_state(_low_risk_entities()), _RaisingRiskScorer())  # type: ignore[arg-type]
    assert out["error"]
    assert out["error_type"] == "risk_scoring"
    assert "risk_score_result" not in out


def test_score_confidence_maps_value_error_to_error_channel() -> None:
    out = score_confidence_node(
        _confidence_state(_low_risk_entities()),
        _RaisingConfidenceScorer(),  # type: ignore[arg-type]
    )
    assert out["error"]
    assert out["error_type"] == "confidence_scoring"
    assert "risk_assessment" not in out


class _RaisingAssessor:
    """Stand-in whose async ``assess`` raises a ValueError (invalid inputs guard)."""

    async def assess(self, *args: Any, **kwargs: Any):
        raise ValueError("bad assess inputs")


@pytest.mark.asyncio
async def test_assess_llm_maps_value_error_to_error_channel() -> None:
    entities = _low_risk_entities()
    rule_result = RiskScorer().score(entities)
    out = await assess_llm_node(
        _state(entities, risk_score_result=rule_result),
        _RaisingAssessor(),  # type: ignore[arg-type]
    )
    assert out["error"]
    assert out["error_type"] == "llm_assessment"
    assert "ai_risk_assessment" not in out


@pytest.mark.asyncio
async def test_assess_llm_missing_entities_sets_error() -> None:
    rule_result = RiskScorer().score(_low_risk_entities())
    out = await assess_llm_node(
        _state(None, risk_score_result=rule_result), _assessor()
    )
    assert out["error"]
    assert out["error_type"] == "llm_assessment"


def test_score_confidence_missing_ai_assessment_sets_error() -> None:
    # Pre-load everything except ai_risk_assessment.
    entities = _low_risk_entities()
    evidence = EvidenceGapAnalyzer().analyze(entities)
    state = _state(
        entities,
        evidence_gap_result=evidence,
        completeness_score=evidence.completeness_score,
        risk_score_result=RiskScorer().score(entities),
    )
    out = score_confidence_node(state, ConfidenceScorer())
    assert out["error"]
    assert out["error_type"] == "confidence_scoring"


def test_assembled_llm_available_false_on_fallback() -> None:
    # Build a confidence state whose assessment is the fallback model.
    from app.services.ai_risk_assessor import AIRiskAssessment

    entities = _high_risk_entities()
    evidence = EvidenceGapAnalyzer().analyze(entities)
    rule_result = RiskScorer().score(entities)
    fallback = AIRiskAssessment(
        rule_based_score=rule_result.risk_score,
        llm_score=rule_result.risk_score,
        combined_score=rule_result.risk_score,
        risk_level=rule_result.risk_level,
        llm_reasoning="fallback reasoning",
        llm_confidence=0.0,
        recommended_actions=[],
        model_used="fallback",
    )
    state = _state(
        entities,
        evidence_gap_result=evidence,
        completeness_score=evidence.completeness_score,
        risk_score_result=rule_result,
        ai_risk_assessment=fallback,
    )
    out = score_confidence_node(state, ConfidenceScorer())
    assert out["risk_assessment"]["llm_available"] is False
