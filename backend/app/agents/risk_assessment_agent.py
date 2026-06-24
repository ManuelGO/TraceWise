"""Risk Assessment Agent (Task 48, Phase 6).

A LangGraph ``StateGraph`` that orchestrates compliance risk assessment by wrapping the four
existing Phase 5 risk services. The agent does NOT reimplement scoring rules, LLM assessment,
confidence weighting, or gap detection -- it is a thin orchestration layer that produces a single
assembled *risk assessment* (a JSON-serializable summary plus the individual typed results).

Pipeline::

    START -> analyze_evidence -> score_rules -> assess_llm -> score_confidence -> END
                  |                  |              |               |
                  | (missing entities / ValueError from a service / unexpected error)
                  +------------------+--------------+---------------+----> END (error set)

Each node returns a partial update to ``RiskAssessmentState``. Nodes are ordered by data
dependency: ``analyze_evidence`` produces the ``completeness_score`` that feeds
``score_confidence``; ``score_rules`` produces the ``RiskScoreResult`` that feeds ``assess_llm``.
The chain is linear -- no branching.

Design notes (coordinator-confirmed, 2026-06-24 -- see ``phase-6/PHASE_6_ARCHITECTURE.md``):
- Q1 (persistence): READ-ONLY. Like Task 47 there is NO DB session threaded through state and NO
  ``RiskAssessment`` row written. The four services are pure computation; persistence (which needs
  a ``case_id``) is deferred to Task 51 orchestration.
- Q2 (LLM failure): ``AIRiskAssessor.assess`` already catches ``LLMError`` internally and returns a
  rule-only fallback assessment (``model_used="fallback"``, ``llm_confidence=0.0``). That fallback
  is a VALID business outcome -- it reaches END normally with ``error=None`` (mirrors Task 47-C).
  Only missing ``entities``, a ``ValueError`` from a service (invalid inputs), or an unexpected
  exception set ``error``.
- Q3 (source_quality): ``source_quality`` is an OPTIONAL input (default 0.5, matching
  ``ConfidenceScorer``). The agent runs standalone; Task 51 threads the real retrieval-agent
  similarity through later. ``evidence_completeness`` is derived from ``analyze_evidence``.
- Q4 (output): the primary output is the assembled ``risk_assessment`` dict (JSON-serializable for
  Task 52 checkpointing) plus the four typed results kept in state for in-process consumers.

This task does NOT configure a checkpointer; ``build_risk_assessment_graph`` accepts an optional
``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
from functools import partial
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents._agent_helpers import agent_fail, route_after
from app.schemas.consistency import ConsistencyReport
from app.schemas.evidence_gap import GENERAL_DOC_TYPE, EvidenceGapResult
from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult
from app.services.ai_risk_assessor import AIRiskAssessment, AIRiskAssessor
from app.services.confidence_scorer import ConfidenceResult, ConfidenceScorer
from app.services.evidence_gap_analyzer import EvidenceGapAnalyzer
from app.services.risk_scorer import RiskScorer, RiskScoreResult

logger = logging.getLogger(__name__)

_AGENT_LABEL = "Risk assessment"
_FALLBACK_MODEL = "fallback"

# Default for the source-quality confidence factor when the caller does not supply one (Q3).
# Matches ``ConfidenceScorer.compute``'s own default so standalone runs behave identically.
_DEFAULT_SOURCE_QUALITY = 0.5


def _fail(error_type: str, message: str) -> dict[str, Any]:
    """Partial state update for a permanent failure (see ``agent_fail``).

    Each node passes a per-stage ``error_type`` (``"evidence_gap"`` / ``"risk_scoring"`` /
    ``"llm_assessment"`` / ``"confidence_scoring"``) so monitoring can distinguish *where* a run
    failed -- matching the per-stage error-category convention of the sibling Phase 6 agents.
    """
    return agent_fail(_AGENT_LABEL, error_type, message)


# ===== State contract =====


class RiskAssessmentState(TypedDict, total=False):
    """Shared state threaded through the risk assessment graph.

    ``total=False`` so each node may return a partial update without re-declaring every key.
    Only ``entities`` is a required caller input; the rest are optional inputs (with service
    defaults) or outputs filled by successive nodes.
    """

    # Inputs (caller-supplied)
    entities: ExtractionResult  # required (Task 38)
    validation_result: ValidationResult | None  # optional (Task 39)
    consistency_result: ConsistencyReport | None  # optional (Task 40)
    document_type: str  # optional, default "general" (gap catalogue)
    source_quality: float  # optional, default 0.5 (retrieval similarity)

    # analyze_evidence_node
    evidence_gap_result: EvidenceGapResult
    completeness_score: float
    # score_rules_node
    risk_score_result: RiskScoreResult
    # assess_llm_node
    ai_risk_assessment: AIRiskAssessment
    # score_confidence_node (final)
    confidence_result: ConfidenceResult
    risk_assessment: dict[str, Any]  # PRIMARY OUTPUT -- assembled, JSON-serializable

    # Error channel: when ``error`` is set the graph short-circuits to END.
    error: str | None
    error_type: str | None


# ===== Nodes =====


def analyze_evidence_node(
    state: RiskAssessmentState,
    evidence_analyzer: EvidenceGapAnalyzer,
) -> dict[str, Any]:
    """Analyze evidence quality via ``EvidenceGapAnalyzer.analyze`` (first node).

    Wraps the required-field gap detection and produces the ``completeness_score`` that
    ``score_confidence_node`` consumes as ``evidence_completeness``. A missing ``entities`` input
    is the only permanent error here (guarded up front) -- it routes straight to END.
    """
    entities = state.get("entities")
    if entities is None:
        return _fail("evidence_gap", "No entities provided for risk assessment")

    document_type = state.get("document_type") or GENERAL_DOC_TYPE
    result = evidence_analyzer.analyze(entities, document_type=document_type)

    logger.info(
        "Evidence analysis complete: %d gap(s), completeness=%.3f",
        len(result.gaps),
        result.completeness_score,
    )
    return {
        "evidence_gap_result": result,
        "completeness_score": result.completeness_score,
    }


def score_rules_node(
    state: RiskAssessmentState,
    risk_scorer: RiskScorer,
) -> dict[str, Any]:
    """Identify and score risks deterministically via ``RiskScorer.score``.

    Wraps the five-category rule-based scoring. ``entities`` is guaranteed present here (the prior
    node would have short-circuited otherwise), but ``RiskScorer.score`` raises ``ValueError`` on
    falsy entities -- mapped to a permanent error to stay defensive.
    """
    entities = state.get("entities")
    if entities is None:
        return _fail("risk_scoring", "No entities provided for risk scoring")

    try:
        result = risk_scorer.score(
            entities,
            consistency_result=state.get("consistency_result"),
            validation_result=state.get("validation_result"),
        )
    except ValueError as exc:
        return _fail("risk_scoring", str(exc))

    logger.info(
        "Rule-based scoring complete: score=%d, level=%s, violations=%d",
        result.risk_score,
        result.risk_level,
        result.violation_count,
    )
    return {"risk_score_result": result}


async def assess_llm_node(
    state: RiskAssessmentState,
    ai_assessor: AIRiskAssessor,
) -> dict[str, Any]:
    """Produce the nuanced LLM-assisted assessment via ``AIRiskAssessor.assess``.

    The only node that calls the LLM. ``AIRiskAssessor.assess`` catches ``LLMError`` internally and
    returns a rule-only fallback (``model_used="fallback"``); that is a VALID outcome (Q2), not a
    graph error -- the graph proceeds normally. Only a ``ValueError`` from invalid inputs is a
    permanent error.
    """
    entities = state.get("entities")
    risk_score_result = state.get("risk_score_result")
    if entities is None or risk_score_result is None:
        return _fail("llm_assessment", "Missing entities or rule score for LLM assessment")

    try:
        assessment = await ai_assessor.assess(
            entities,
            risk_score_result,
            consistency_result=state.get("consistency_result"),
        )
    except ValueError as exc:
        return _fail("llm_assessment", str(exc))

    logger.info(
        "LLM assessment complete: combined=%d, level=%s, llm_available=%s",
        assessment.combined_score,
        assessment.risk_level,
        assessment.model_used != _FALLBACK_MODEL,
    )
    return {"ai_risk_assessment": assessment}


def score_confidence_node(
    state: RiskAssessmentState,
    confidence_scorer: ConfidenceScorer,
) -> dict[str, Any]:
    """Compute the aggregate confidence and assemble the primary output (final node).

    Wraps ``ConfidenceScorer.compute`` -- threading the ``completeness_score`` from
    ``analyze_evidence_node`` as ``evidence_completeness`` and the optional ``source_quality`` input
    (default 0.5). Then assembles the JSON-serializable ``risk_assessment`` summary from all four
    typed results (Q4). Pure: cannot fail on valid inputs.
    """
    entities = state.get("entities")
    evidence_gap_result = state.get("evidence_gap_result")
    risk_score_result = state.get("risk_score_result")
    ai_risk_assessment = state.get("ai_risk_assessment")
    if (
        entities is None
        or evidence_gap_result is None
        or risk_score_result is None
        or ai_risk_assessment is None
    ):
        return _fail("confidence_scoring", "Missing prerequisite results for confidence scoring")

    completeness = state.get("completeness_score", evidence_gap_result.completeness_score)
    # ``state.get(key, default)`` returns ``None`` (not the default) when the key is present with a
    # ``None`` value; coerce that to the default so ``ConfidenceScorer`` never receives ``None``
    # (which would raise an uncaught ``TypeError`` from ``math.isnan``, bypassing the error channel).
    source_quality = state.get("source_quality")
    if source_quality is None:
        source_quality = _DEFAULT_SOURCE_QUALITY

    try:
        confidence_result = confidence_scorer.compute(
            entities,
            validation_result=state.get("validation_result"),
            consistency_result=state.get("consistency_result"),
            evidence_completeness=completeness,
            source_quality=source_quality,
        )
    except ValueError as exc:
        return _fail("confidence_scoring", str(exc))

    risk_assessment = _assemble_risk_assessment(
        risk_score_result=risk_score_result,
        ai_risk_assessment=ai_risk_assessment,
        confidence_result=confidence_result,
        evidence_gap_result=evidence_gap_result,
    )

    logger.info(
        "Risk assessment assembled: risk_score=%d, level=%s, confidence=%.3f",
        risk_assessment["risk_score"],
        risk_assessment["risk_level"],
        risk_assessment["confidence_score"],
    )
    return {
        "confidence_result": confidence_result,
        "risk_assessment": risk_assessment,
    }


def _assemble_risk_assessment(
    *,
    risk_score_result: RiskScoreResult,
    ai_risk_assessment: AIRiskAssessment,
    confidence_result: ConfidenceResult,
    evidence_gap_result: EvidenceGapResult,
) -> dict[str, Any]:
    """Build the JSON-serializable primary output from the four typed results (Q4).

    The combined (rule+LLM) ``combined_score``/``risk_level`` are the headline figures; the
    rule-based and LLM scores are kept alongside for transparency. ``violations`` and
    ``evidence_gaps`` are ``model_dump``-ed so the whole dict round-trips through ``json.dumps``
    (Task 52 checkpoint forward-compat). ``llm_available`` distinguishes a real assessment from the
    rule-only fallback.
    """
    return {
        "risk_score": ai_risk_assessment.combined_score,
        "risk_level": ai_risk_assessment.risk_level,
        "rule_based_score": risk_score_result.risk_score,
        "llm_score": ai_risk_assessment.llm_score,
        "confidence_score": confidence_result.confidence_score,
        "confidence_level": confidence_result.confidence_level,
        "reasoning": ai_risk_assessment.llm_reasoning,
        "recommended_actions": list(ai_risk_assessment.recommended_actions),
        "violations": [v.model_dump(mode="json") for v in risk_score_result.violations],
        "evidence_gaps": [g.model_dump(mode="json") for g in evidence_gap_result.gaps],
        "completeness_score": evidence_gap_result.completeness_score,
        "llm_available": ai_risk_assessment.model_used != _FALLBACK_MODEL,
    }


# ===== Graph assembly =====


def _default_ai_assessor() -> AIRiskAssessor:
    """Construct a real ``AIRiskAssessor`` from the shared LLM provider.

    ``AIRiskAssessor`` calls the low-level ``LLMProvider`` interface
    (``generate``/``get_model_name``), so it takes the *provider* that ``LLMService`` composes --
    not the ``LLMService`` orchestrator itself. Used only on the non-injected path; unit tests
    always inject a fake provider so the suite runs offline.
    """
    from app.services.llm_service import get_llm_service

    return AIRiskAssessor(get_llm_service().provider)


def build_risk_assessment_graph(
    *,
    evidence_analyzer: EvidenceGapAnalyzer | None = None,
    risk_scorer: RiskScorer | None = None,
    ai_assessor: AIRiskAssessor | None = None,
    confidence_scorer: ConfidenceScorer | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the risk assessment ``StateGraph``.

    The graph is read-only (Q1): no DB session is threaded through state and no ``RiskAssessment``
    row is written. Each node wraps one pure Phase 5 service; only ``assess_llm`` touches the LLM
    (and that service self-falls-back, so an LLM outage is a valid outcome, not a graph error).

    Args:
        evidence_analyzer: Evidence gap analyzer (injected for testing). Defaults to a real
            ``EvidenceGapAnalyzer`` (no args).
        risk_scorer: Rule-based risk scorer (injected for testing). Defaults to ``RiskScorer``.
        ai_assessor: LLM-assisted assessor (injected for testing). Defaults to an ``AIRiskAssessor``
            built from ``get_llm_service()``.
        confidence_scorer: Confidence scorer (injected for testing). Defaults to ``ConfidenceScorer``.
        checkpointer: Optional LangGraph checkpointer (forward-compat for Task 52).

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    if evidence_analyzer is None:
        evidence_analyzer = EvidenceGapAnalyzer()
    if risk_scorer is None:
        risk_scorer = RiskScorer()
    if ai_assessor is None:
        ai_assessor = _default_ai_assessor()
    if confidence_scorer is None:
        confidence_scorer = ConfidenceScorer()

    analyze = partial(analyze_evidence_node, evidence_analyzer=evidence_analyzer)
    score_rules = partial(score_rules_node, risk_scorer=risk_scorer)
    assess = partial(assess_llm_node, ai_assessor=ai_assessor)
    score_confidence = partial(score_confidence_node, confidence_scorer=confidence_scorer)

    builder: StateGraph = StateGraph(RiskAssessmentState)
    builder.add_node("analyze_evidence", analyze)
    builder.add_node("score_rules", score_rules)
    builder.add_node("assess_llm", assess)
    builder.add_node("score_confidence", score_confidence)

    builder.add_edge(START, "analyze_evidence")
    # Each node can record a permanent error (bad input / service ValueError) -> short-circuit END.
    builder.add_conditional_edges("analyze_evidence", route_after("score_rules"))
    builder.add_conditional_edges("score_rules", route_after("assess_llm"))
    builder.add_conditional_edges("assess_llm", route_after("score_confidence"))
    builder.add_edge("score_confidence", END)

    return builder.compile(checkpointer=checkpointer)


async def run_risk_assessment(
    initial_state: RiskAssessmentState,
    *,
    graph: CompiledStateGraph | None = None,
) -> RiskAssessmentState:
    """Run the risk assessment graph over ``initial_state``.

    Args:
        initial_state: Caller-supplied state with at least ``entities`` (plus optional
            ``validation_result``, ``consistency_result``, ``document_type``, ``source_quality``).
        graph: Optional pre-built compiled graph (injected for testing). When omitted a default
            graph is built with real services.

    Returns:
        The final ``RiskAssessmentState`` after execution.
    """
    if graph is None:
        graph = build_risk_assessment_graph()
    result = await graph.ainvoke(initial_state)
    return cast(RiskAssessmentState, result)
