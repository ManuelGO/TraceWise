"""Evidence Validation Agent (Task 49, Phase 6).

A LangGraph ``StateGraph`` that validates generated claims against their evidence: it verifies that
claims are *grounded* in retrieved source documents and that the underlying evidence set is
*internally consistent*, surfacing inconsistencies and flagging likely hallucinations. Like every
Phase 6 agent it is a thin orchestration layer (see ``phase-6/PHASE_6_ARCHITECTURE.md`` Section 1):
it does NOT reimplement citation mapping, term-overlap grounding, fuzzy supplier grouping, or
conflict detection. All of that domain logic lives in ``app.services``.

Pipeline::

    START -> check_grounding -> check_consistency -> assess_validation -> END
                  |                    |                     |
                  | (empty answer / consistency ValueError / unexpected error)
                  +--------------------+---------------------+----> END (error set)

Two services are wrapped:

- ``CitationService.map_citations(answer, search_results)`` (Phase 4) -- the project's *grounding*
  mechanism. It traces meaningful answer terms back to retrieved source chunks (Jaccard confidence).
  An answer with no citations (or only low-confidence ones) is, by construction, ungrounded -- the
  signal this agent uses to flag hallucination risk. We do NOT invent a new grounding algorithm.
- ``ConsistencyChecker.check_consistency(case_id, validated_entities)`` (Phase 3) -- cross-document
  field/temporal/logical conflict detection over an in-memory validated-entity set.

Design notes (coordinator-confirmed, 2026-06-25 -- see ``PHASE_6_ARCHITECTURE.md`` Section 6):
- Q1 (persistence): READ-ONLY. No DB session threaded through state, no ``ConsistencyCheck`` row.
  We wrap ``ConsistencyChecker`` (pure, in-memory) NOT ``ConsistencyService`` (DB persistence).
  Persistence (which needs a real ``case_id``) is deferred to Task 51 orchestration.
- Q2 (hallucination signal): DERIVED from citation grounding -- zero / low-confidence citations imply
  a high hallucination risk. No LLM faithfulness judge (deferred to Phase 8). This agent makes NO
  LLM call; both wrapped services are deterministic and offline.
- Q3 (thresholds): three env-tunable ``config.py`` keys (policy -> config, per the Task 47-D
  precedent) -- ``EVIDENCE_GROUNDING_MIN_CONFIDENCE`` (a citation counts as grounding evidence),
  ``EVIDENCE_GROUNDING_MEDIUM_THRESHOLD`` and ``EVIDENCE_GROUNDING_HIGH_THRESHOLD`` (the
  ``grounding_score`` cutoffs for the high/medium/low hallucination-risk band).
- Q4 (empty/missing inputs, mirrors Task 47-C): an empty ``answer`` is a permanent error (nothing to
  validate); zero citations is a VALID ungrounded outcome (reaches END, ``error=None``); missing /
  empty ``validated_entities`` is a VALID outcome (the consistency check is skipped, single-answer
  standalone run); empty ``search_results`` with a non-empty answer is a VALID outcome (ungrounded,
  high hallucination risk). Only an empty answer, a ``ConsistencyChecker`` ``ValueError``, or an
  unexpected exception set ``error``.
- Q5 (verdict): ``is_valid = is_grounded AND no HIGH-severity consistency conflict``. ``is_valid`` is
  a GATE, not a final decision -- a downstream consumer (Task 50 report generation) may still render
  evidence with ``is_valid=False``, flagged as "ungrounded", rather than dropping it. Medium / low
  conflicts and medium hallucination risk lower confidence but do not by themselves fail validation.

This task does NOT configure a checkpointer; ``build_evidence_validation_graph`` accepts an optional
``checkpointer`` so Task 52 (workflow state persistence) is a drop-in.
"""

import logging
from functools import partial
from typing import Any, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents._agent_helpers import agent_fail, route_after
from app.config import get_settings
from app.models.vector_embedding import SearchResult
from app.schemas.consistency import ConflictSeverity, ConsistencyReport
from app.schemas.validation import ValidatedExtractionResult
from app.services.citation_service import Citation, CitationService
from app.services.consistency_checker import ConsistencyChecker

logger = logging.getLogger(__name__)

_AGENT_LABEL = "Evidence validation"

# Hallucination-risk bands (numeric 0.0-1.0 in the primary output; a human-readable band is derived
# for ``findings``). ``hallucination_risk`` is ``1.0 - grounding_score`` so it composes cleanly with
# the confidence math downstream and renders directly as a percentage.
_RISK_BAND_LOW = "low"
_RISK_BAND_MEDIUM = "medium"
_RISK_BAND_HIGH = "high"

# Sentinel case id for standalone runs where the caller supplies no ``case_id`` (read-only; the value
# never reaches the DB -- ``ConsistencyChecker.check_consistency`` only uses it for log context).
_SENTINEL_CASE_ID = UUID("00000000-0000-0000-0000-000000000000")


def _fail(error_type: str, message: str) -> dict[str, Any]:
    """Partial state update for a permanent failure (see ``agent_fail``).

    Each node passes a per-stage ``error_type`` (``"grounding"`` / ``"consistency"`` /
    ``"validation"``) so monitoring can distinguish *where* a run failed -- matching the per-stage
    error-category convention of the sibling Phase 6 agents.
    """
    return agent_fail(_AGENT_LABEL, error_type, message)


# ===== State contract =====


class EvidenceValidationState(TypedDict, total=False):
    """Shared state threaded through the evidence validation graph.

    ``total=False`` so each node may return a partial update without re-declaring every key.
    Only ``answer`` is a required caller input; the rest are optional inputs (with defaults) or
    outputs filled by successive nodes.
    """

    # Inputs (caller-supplied)
    answer: str  # required -- the claim/answer text under validation
    search_results: list[SearchResult]  # optional, default [] -- retrieved source chunks (Task 47)
    validated_entities: list[ValidatedExtractionResult] | None  # optional -- multi-doc evidence set
    case_id: str | None  # optional -- UUID string; defaults to a sentinel for standalone runs

    # check_grounding_node
    citations: list[Citation]
    grounding_score: float  # citation coverage 0.0-1.0 (mean citation confidence)
    hallucination_risk: float  # 0.0-1.0 == 1.0 - grounding_score
    is_grounded: bool

    # check_consistency_node
    consistency_report: ConsistencyReport
    consistency_checked: bool  # False when skipped (no validated_entities)

    # assess_validation_node (final, primary output)
    evidence_validation: dict[str, Any]  # JSON-serializable summary

    # Error channel: when ``error`` is set the graph short-circuits to END.
    error: str | None
    error_type: str | None


# ===== Nodes =====


def check_grounding_node(
    state: EvidenceValidationState,
    citation_service: CitationService,
) -> dict[str, Any]:
    """Verify that the answer's claims are grounded in retrieved sources (first node).

    Wraps ``CitationService.map_citations`` -- the existing grounding mechanism -- and derives the
    grounding/hallucination signals from the citations it returns (Q2):

    - ``grounding_score`` = mean citation confidence (0.0 when there are no citations).
    - ``is_grounded`` = at least one citation meets ``EVIDENCE_GROUNDING_MIN_CONFIDENCE``.
    - ``hallucination_risk`` = ``1.0 - grounding_score`` (numeric; a band is derived later).

    An empty / whitespace ``answer`` is the only permanent error here (nothing to validate). Zero
    citations is a VALID ungrounded outcome (high hallucination risk), not a graph error (Q4).
    """
    answer = state.get("answer")
    if not answer or not answer.strip():
        return _fail("grounding", "No answer provided for evidence validation")

    settings = get_settings()
    search_results = state.get("search_results") or []
    citations = citation_service.map_citations(answer, search_results)

    if citations:
        grounding_score = sum(c["confidence"] for c in citations) / len(citations)
    else:
        grounding_score = 0.0
    grounding_score = max(0.0, min(1.0, grounding_score))

    is_grounded = any(
        c["confidence"] >= settings.EVIDENCE_GROUNDING_MIN_CONFIDENCE for c in citations
    )
    hallucination_risk = 1.0 - grounding_score

    logger.info(
        "Grounding check complete: %d citation(s), grounding=%.3f, grounded=%s",
        len(citations),
        grounding_score,
        is_grounded,
    )
    return {
        "citations": citations,
        "grounding_score": grounding_score,
        "is_grounded": is_grounded,
        "hallucination_risk": hallucination_risk,
    }


async def check_consistency_node(
    state: EvidenceValidationState,
    consistency_checker: ConsistencyChecker,
) -> dict[str, Any]:
    """Detect inconsistencies across the evidence set via ``ConsistencyChecker.check_consistency``.

    Async because the underlying field/temporal/logical validators are async. ``validated_entities``
    is OPTIONAL: when absent / empty the consistency check is *skipped* and an empty report is
    returned (``consistency_checked=False``, ``error=None``) so the agent runs standalone on a
    single answer with no multi-document evidence set (Q4). A ``ValueError`` from the service
    (malformed entities) is a permanent error.
    """
    validated_entities = state.get("validated_entities")
    if not validated_entities:
        empty_report = ConsistencyReport(
            case_id=_parse_case_id(state.get("case_id")),
            total_conflict_count=0,
            confidence_adjustment=0.0,
            summary="No multi-document evidence set; consistency check skipped.",
        )
        logger.info("Consistency check skipped: no validated entities supplied")
        return {"consistency_report": empty_report, "consistency_checked": False}

    case_id = _parse_case_id(state.get("case_id"))
    try:
        report = await consistency_checker.check_consistency(case_id, validated_entities)
    except ValueError as exc:
        return _fail("consistency", str(exc))

    logger.info(
        "Consistency check complete: %d conflict(s), confidence_adjustment=%.3f",
        report.total_conflict_count,
        report.confidence_adjustment,
    )
    return {"consistency_report": report, "consistency_checked": True}


def assess_validation_node(state: EvidenceValidationState) -> dict[str, Any]:
    """Assemble the primary ``evidence_validation`` output and the overall verdict (final node).

    Pure assembly: combines the grounding signals and the consistency report into a single
    JSON-serializable summary plus human-readable ``findings``. Cannot fail on valid inputs; the
    prerequisite guard is defensive (a prior node would have short-circuited otherwise).
    """
    citations = state.get("citations")
    grounding_score = state.get("grounding_score")
    hallucination_risk = state.get("hallucination_risk")
    consistency_report = state.get("consistency_report")
    if (
        citations is None
        or grounding_score is None
        or hallucination_risk is None
        or consistency_report is None
    ):
        return _fail("validation", "Missing prerequisite results for evidence validation")

    is_grounded = bool(state.get("is_grounded", False))
    consistency_checked = bool(state.get("consistency_checked", False))

    settings = get_settings()
    evidence_validation = _assemble_evidence_validation(
        citations=citations,
        grounding_score=grounding_score,
        is_grounded=is_grounded,
        hallucination_risk=hallucination_risk,
        consistency_report=consistency_report,
        consistency_checked=consistency_checked,
        medium_threshold=settings.EVIDENCE_GROUNDING_MEDIUM_THRESHOLD,
        high_threshold=settings.EVIDENCE_GROUNDING_HIGH_THRESHOLD,
    )

    logger.info(
        "Evidence validation complete: is_valid=%s, grounding=%.2f, hallucination_risk=%.2f",
        evidence_validation["is_valid"],
        grounding_score,
        hallucination_risk,
    )
    return {"evidence_validation": evidence_validation}


# ===== Assembly helpers =====


def _parse_case_id(raw: str | None) -> UUID:
    """Parse the optional ``case_id`` input into a UUID, falling back to the standalone sentinel.

    The value is read-only -- ``ConsistencyChecker`` uses it only for log context (no DB write), so a
    malformed / absent id degrades gracefully to the sentinel rather than failing the run.
    """
    if not raw:
        return _SENTINEL_CASE_ID
    try:
        return UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return _SENTINEL_CASE_ID


def _hallucination_band(
    grounding_score: float, *, medium_threshold: float, high_threshold: float
) -> str:
    """Map the grounding score onto a human-readable hallucination-risk band for ``findings``.

    Banded on ``grounding_score`` (not the derived risk) so the cutoffs read directly off the config
    keys, matching their descriptions:

    - ``low`` when grounding is strong (``grounding_score >= high_threshold``);
    - ``medium`` when grounding is moderate (``>= medium_threshold`` but below ``high_threshold``);
    - ``high`` when grounding is weak/absent (below ``medium_threshold``).

    All three bands are reachable with the defaults (``medium_threshold=0.5``, ``high_threshold=0.7``).
    The numeric ``hallucination_risk`` (``1.0 - grounding_score``) remains the canonical figure in the
    output; this band only feeds the readable finding line.
    """
    if grounding_score >= high_threshold:
        return _RISK_BAND_LOW
    if grounding_score >= medium_threshold:
        return _RISK_BAND_MEDIUM
    return _RISK_BAND_HIGH


def _build_findings(
    *,
    grounding_score: float,
    hallucination_risk: float,
    hallucination_band: str,
    is_grounded: bool,
    consistency_report: ConsistencyReport,
    consistency_checked: bool,
) -> list[str]:
    """Build human-readable finding lines explaining the verdict.

    Example output::

        ["80% of claims grounded in retrieved sources",
         "Hallucination risk: 20% (low)",
         "3 temporal conflicts detected (medium severity)"]
    """
    findings: list[str] = []

    grounded_pct = round(grounding_score * 100)
    if is_grounded:
        findings.append(f"{grounded_pct}% of claims grounded in retrieved sources")
    else:
        findings.append(
            f"Answer is ungrounded: only {grounded_pct}% of claims traced to retrieved sources"
        )

    findings.append(
        f"Hallucination risk: {round(hallucination_risk * 100)}% ({hallucination_band})"
    )

    if not consistency_checked:
        findings.append("Consistency check skipped: no multi-document evidence set")
        return findings

    # Each conflict list has a distinct element type; describe them separately to keep the
    # ``.severity`` access type-checked (a mixed-type tuple would widen the element to ``object``).
    _append_conflict_finding(
        findings, "field", [c.severity.value for c in consistency_report.field_conflicts]
    )
    _append_conflict_finding(
        findings, "temporal", [c.severity.value for c in consistency_report.temporal_conflicts]
    )
    _append_conflict_finding(
        findings, "logical", [c.severity.value for c in consistency_report.logical_conflicts]
    )

    if consistency_report.total_conflict_count == 0:
        findings.append("No cross-document inconsistencies detected")

    return findings


def _append_conflict_finding(findings: list[str], label: str, severities: list[str]) -> None:
    """Append a "<n> <label> conflict(s) detected (<severities> severity)" line, if any."""
    if not severities:
        return
    distinct = sorted(set(severities))
    findings.append(
        f"{len(severities)} {label} conflict(s) detected ({', '.join(distinct)} severity)"
    )


def _assemble_evidence_validation(
    *,
    citations: list[Citation],
    grounding_score: float,
    is_grounded: bool,
    hallucination_risk: float,
    consistency_report: ConsistencyReport,
    consistency_checked: bool,
    medium_threshold: float,
    high_threshold: float,
) -> dict[str, Any]:
    """Build the JSON-serializable primary output from the grounding + consistency results (Q4/Q5).

    ``is_valid`` is a GATE, not a final decision: it is ``True`` only when the answer is grounded,
    the hallucination band is not ``high``, AND no HIGH-severity consistency conflict exists. A
    downstream consumer (Task 50 report generation) may still render evidence with ``is_valid=False``
    -- flagged as "ungrounded" / "inconsistent" -- rather than dropping it. Conflicts are
    ``model_dump``-ed so the whole dict round-trips through ``json.dumps`` (Task 52 forward-compat).

    The band thresholds are passed in (read at the node boundary) so this stays a pure function.
    """
    band = _hallucination_band(
        grounding_score, medium_threshold=medium_threshold, high_threshold=high_threshold
    )

    all_conflicts = (
        list(consistency_report.field_conflicts)
        + list(consistency_report.temporal_conflicts)
        + list(consistency_report.logical_conflicts)
    )
    high_severity_count = sum(1 for c in all_conflicts if c.severity == ConflictSeverity.HIGH)

    # is_valid gates on the band too, so a "grounded" answer in the [min_confidence, medium)
    # grounding range -- which still reads as high hallucination risk -- cannot be declared valid.
    is_valid = is_grounded and band != _RISK_BAND_HIGH and high_severity_count == 0

    findings = _build_findings(
        grounding_score=grounding_score,
        hallucination_risk=hallucination_risk,
        hallucination_band=band,
        is_grounded=is_grounded,
        consistency_report=consistency_report,
        consistency_checked=consistency_checked,
    )

    if is_valid:
        reasoning = "Evidence is grounded in sources with no high-severity inconsistencies."
    elif not is_grounded:
        reasoning = (
            "Evidence flagged as ungrounded -- claims are not sufficiently traced to retrieved "
            "sources (elevated hallucination risk). Review before relying on this answer."
        )
    else:
        reasoning = (
            f"Evidence flagged due to {high_severity_count} high-severity cross-document "
            "inconsistency(ies). Review before relying on this answer."
        )

    return {
        # is_valid is a GATE for downstream routing/flagging, NOT a final accept/reject decision.
        "is_valid": is_valid,
        "is_grounded": is_grounded,
        "grounding_score": grounding_score,
        "hallucination_risk": hallucination_risk,
        "hallucination_band": band,
        "citation_count": len(citations),
        "citations": list(citations),  # ``Citation`` is a JSON-native TypedDict
        "consistency": {
            "checked": consistency_checked,
            "total_conflict_count": consistency_report.total_conflict_count,
            "field_conflicts": len(consistency_report.field_conflicts),
            "temporal_conflicts": len(consistency_report.temporal_conflicts),
            "logical_conflicts": len(consistency_report.logical_conflicts),
            "high_severity_count": high_severity_count,
            "confidence_adjustment": consistency_report.confidence_adjustment,
            "summary": consistency_report.summary,
            "conflicts": [c.model_dump(mode="json") for c in all_conflicts],
        },
        "findings": findings,
        "reasoning": reasoning,
    }


# ===== Graph assembly =====


def build_evidence_validation_graph(
    *,
    citation_service: CitationService | None = None,
    consistency_checker: ConsistencyChecker | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the evidence validation ``StateGraph``.

    The graph is read-only (Q1): no DB session is threaded through state and no ``ConsistencyCheck``
    row is written. It makes no LLM call -- both wrapped services are deterministic and offline.

    Args:
        citation_service: Grounding / citation mapper (injected for testing). Defaults to a real
            ``CitationService`` (offline, no args).
        consistency_checker: Cross-document conflict detector (injected for testing). Defaults to a
            real ``ConsistencyChecker`` (offline, no args).
        checkpointer: Optional LangGraph checkpointer (forward-compat for Task 52).

    Returns:
        A compiled graph supporting ``ainvoke``.
    """
    if citation_service is None:
        citation_service = CitationService()
    if consistency_checker is None:
        consistency_checker = ConsistencyChecker()

    check_grounding = partial(check_grounding_node, citation_service=citation_service)
    check_consistency = partial(check_consistency_node, consistency_checker=consistency_checker)

    builder: StateGraph = StateGraph(EvidenceValidationState)
    builder.add_node("check_grounding", check_grounding)
    builder.add_node("check_consistency", check_consistency)
    builder.add_node("assess_validation", assess_validation_node)

    builder.add_edge(START, "check_grounding")
    # check_grounding (empty answer) and check_consistency (service ValueError) can record a
    # permanent error -> short-circuit to END. assess_validation cannot fail on valid inputs.
    builder.add_conditional_edges("check_grounding", route_after("check_consistency"))
    builder.add_conditional_edges("check_consistency", route_after("assess_validation"))
    builder.add_edge("assess_validation", END)

    return builder.compile(checkpointer=checkpointer)


async def run_evidence_validation(
    initial_state: EvidenceValidationState,
    *,
    graph: CompiledStateGraph | None = None,
) -> EvidenceValidationState:
    """Run the evidence validation graph over ``initial_state``.

    Args:
        initial_state: Caller-supplied state with at least ``answer`` (plus optional
            ``search_results``, ``validated_entities``, ``case_id``).
        graph: Optional pre-built compiled graph (injected for testing). When omitted a default
            graph is built with real (offline) services.

    Returns:
        The final ``EvidenceValidationState`` after execution.
    """
    if graph is None:
        graph = build_evidence_validation_graph()
    result = await graph.ainvoke(initial_state)
    return cast(EvidenceValidationState, result)


__all__ = [
    "EvidenceValidationState",
    "assess_validation_node",
    "build_evidence_validation_graph",
    "check_consistency_node",
    "check_grounding_node",
    "run_evidence_validation",
]
