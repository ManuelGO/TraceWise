"""Unit tests for AIRiskAssessor service.

Tests cover:
1. AIRiskAssessment model validation (score ranges, confidence, actions)
2. Prompt building (entity/violation/consistency serialization)
3. Score combination (40% rule + 60% LLM weighting)
4. LLM response parsing (valid JSON, malformed, out-of-range values)
5. assess() integration (happy path + fallback on LLM failure)
6. Edge cases (all violations, empty actions, boundary scores)

Total: 35+ tests covering all acceptance criteria from validation.md
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.prompts.risk_assessment_prompts import (
    RISK_ASSESSMENT_SYSTEM_PROMPT,
    _serialize_consistency,
    _serialize_entities,
    _serialize_rule_violations,
    build_risk_assessment_prompt,
)
from app.schemas.consistency import (
    ConflictSeverity,
    ConsistencyReport,
    FieldConflict,
    TemporalConflict,
    TemporalConflictType,
)
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.services.ai_risk_assessor import (
    LLM_FALLBACK_REASONING,
    LLM_WEIGHT,
    RULE_WEIGHT,
    AIRiskAssessment,
    AIRiskAssessor,
)
from app.services.llm_service import LLMError, LLMProvider
from app.services.risk_scorer import RiskScoreResult, RuleViolation

# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def doc_id():
    return uuid4()


@pytest.fixture
def case_id():
    return uuid4()


@pytest.fixture
def minimal_entities(doc_id):
    """Minimal valid ExtractionResult for tests."""
    return ExtractionResult(
        document_id=doc_id,
        supplier=SupplierInfo(
            name="Acme Corp",
            country_of_origin="US",
            certification_status="certified",
        ),
        product=ProductInfo(
            name="Steel Coils",
            hs_code="72081100",
            origin_country="US",
        ),
        location=LocationInfo(country="US", geolocation_verified=True),
        shipment=ShipmentInfo(tracking_number="BL123456"),
        extraction_confidence=0.90,
        extracted_at=datetime.now(UTC),
        model_used="openai/gpt-4o-mini",
    )


@pytest.fixture
def low_risk_rule_result():
    """RiskScoreResult with low risk score and no violations."""
    return RiskScoreResult(
        risk_score=10,
        risk_level="low",
        violations=[],
        violation_count=0,
        categories_affected=[],
    )


@pytest.fixture
def high_risk_rule_result():
    """RiskScoreResult with high risk and multiple violations."""
    violations = [
        RuleViolation(
            rule_name="high_risk_country",
            category="geolocation",
            points=20,
            reason="Country is on high-risk list",
            severity="critical",
            remediation="Escalate to compliance team",
        ),
        RuleViolation(
            rule_name="no_certification",
            category="supplier",
            points=15,
            reason="Supplier lacks valid certification",
            severity="high",
            remediation="Request certification documentation",
        ),
        RuleViolation(
            rule_name="missing_required_documentation",
            category="compliance",
            points=25,
            reason="Missing tracking number, HS code, and origin country",
            severity="critical",
            remediation="Obtain missing documentation",
        ),
    ]
    return RiskScoreResult(
        risk_score=60,
        risk_level="high",
        violations=violations,
        violation_count=3,
        categories_affected=["compliance", "geolocation", "supplier"],
    )


@pytest.fixture
def consistency_report(case_id):
    """ConsistencyReport with mixed conflicts."""
    return ConsistencyReport(
        case_id=case_id,
        field_conflicts=[
            FieldConflict(
                field="supplier.country_of_origin",
                values={"doc1": "US", "doc2": "CN"},
                severity=ConflictSeverity.HIGH,
                resolved_value="US",
            )
        ],
        temporal_conflicts=[
            TemporalConflict(
                conflict_type=TemporalConflictType.DATE_ORDER_VIOLATION,
                dates_involved={"doc1": {"shipment_date": "2026-06-01", "arrival_date": "2026-05-01"}},
                severity=ConflictSeverity.HIGH,
                description="Arrival date is before shipment date",
            )
        ],
        logical_conflicts=[],
        total_conflict_count=2,
        confidence_adjustment=0.15,
        summary="2 conflicts detected: 1 field conflict, 1 temporal conflict",
    )


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for unit testing."""

    def __init__(self, response_text: str = "", should_fail: bool = False) -> None:
        self.response_text = response_text
        self.should_fail = should_fail
        self._model = "mock/test-model"

    async def generate(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        if self.should_fail:
            raise LLMError("Mock LLM failure")
        return {
            "text": self.response_text,
            "tokens": {"input": 100, "output": 50, "total": 150},
            "cost": 0.001,
            "model": self._model,
        }

    def get_model_name(self) -> str:
        return self._model

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def make_llm_json(
    llm_score: int = 50,
    reasoning: str = "Test reasoning from LLM.",
    confidence: float = 0.75,
    actions: list[str] | None = None,
) -> str:
    """Build valid LLM JSON response string."""
    return json.dumps({
        "llm_score": llm_score,
        "reasoning": reasoning,
        "confidence": confidence,
        "recommended_actions": actions if actions is not None else ["Review documentation", "Contact supplier"],
    })


# ============================================================================
# 1. AIRiskAssessment Model Validation
# ============================================================================


class TestAIRiskAssessmentModel:
    def test_valid_creation(self):
        assessment = AIRiskAssessment(
            rule_based_score=40,
            llm_score=55,
            combined_score=49,
            risk_level="high",
            llm_reasoning="Moderate risk due to missing documentation.",
            llm_confidence=0.80,
            recommended_actions=["Obtain HS code", "Verify supplier"],
            model_used="openai/gpt-4o-mini",
        )
        assert assessment.combined_score == 49
        assert assessment.risk_level == "high"
        assert assessment.llm_confidence == 0.80

    def test_invalid_llm_score_below_zero(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=-1,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="Test",
                llm_confidence=0.5,
                model_used="test",
            )

    def test_invalid_llm_score_above_100(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=101,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="Test",
                llm_confidence=0.5,
                model_used="test",
            )

    def test_invalid_llm_confidence_below_zero(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=50,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="Test",
                llm_confidence=-0.1,
                model_used="test",
            )

    def test_invalid_llm_confidence_above_one(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=50,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="Test",
                llm_confidence=1.1,
                model_used="test",
            )

    def test_recommended_actions_max_5(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=50,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="Test",
                llm_confidence=0.5,
                recommended_actions=["a", "b", "c", "d", "e", "f"],
                model_used="test",
            )

    def test_recommended_actions_empty_list_allowed(self):
        assessment = AIRiskAssessment(
            rule_based_score=50,
            llm_score=50,
            combined_score=50,
            risk_level="medium",
            llm_reasoning="Test",
            llm_confidence=0.5,
            recommended_actions=[],
            model_used="test",
        )
        assert assessment.recommended_actions == []

    def test_combined_score_boundary_values(self):
        for score, level in [(0, "low"), (20, "low"), (21, "medium"), (40, "medium"),
                              (41, "high"), (70, "high"), (71, "critical"), (100, "critical")]:
            assessment = AIRiskAssessment(
                rule_based_score=score,
                llm_score=score,
                combined_score=score,
                risk_level=level,
                llm_reasoning="Test",
                llm_confidence=0.5,
                model_used="test",
            )
            assert assessment.combined_score == score

    def test_assessed_at_defaults_to_utc(self):
        assessment = AIRiskAssessment(
            rule_based_score=50,
            llm_score=50,
            combined_score=50,
            risk_level="medium",
            llm_reasoning="Test",
            llm_confidence=0.5,
            model_used="test",
        )
        assert assessment.assessed_at.tzinfo is not None

    def test_llm_reasoning_max_length_2000(self):
        with pytest.raises(Exception):
            AIRiskAssessment(
                rule_based_score=50,
                llm_score=50,
                combined_score=50,
                risk_level="medium",
                llm_reasoning="x" * 2001,
                llm_confidence=0.5,
                model_used="test",
            )


# ============================================================================
# 2. Prompt Building
# ============================================================================


class TestPromptBuilding:
    def test_build_returns_tuple_of_two_strings(self, minimal_entities, low_risk_rule_result):
        system, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result)
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_content(self):
        assert "compliance risk analyst" in RISK_ASSESSMENT_SYSTEM_PROMPT.lower()
        assert "JSON" in RISK_ASSESSMENT_SYSTEM_PROMPT

    def test_user_prompt_includes_supplier_name(self, minimal_entities, low_risk_rule_result):
        _, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result)
        assert "Acme Corp" in user

    def test_user_prompt_includes_product_name(self, minimal_entities, low_risk_rule_result):
        _, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result)
        assert "Steel Coils" in user

    def test_user_prompt_includes_rule_score(self, minimal_entities, low_risk_rule_result):
        _, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result)
        assert "10" in user
        assert "low" in user.lower()

    def test_user_prompt_includes_violations(self, minimal_entities, high_risk_rule_result):
        _, user = build_risk_assessment_prompt(minimal_entities, high_risk_rule_result)
        assert "high_risk_country" in user or "high-risk" in user.lower()

    def test_user_prompt_includes_json_schema(self, minimal_entities, low_risk_rule_result):
        _, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result)
        assert "llm_score" in user
        assert "reasoning" in user
        assert "confidence" in user
        assert "recommended_actions" in user

    def test_user_prompt_includes_consistency_conflicts(
        self, minimal_entities, low_risk_rule_result, consistency_report
    ):
        _, user = build_risk_assessment_prompt(
            minimal_entities, low_risk_rule_result, consistency_report
        )
        assert "supplier.country_of_origin" in user
        assert "date_order_violation" in user.lower()

    def test_user_prompt_no_consistency_shows_none_performed(
        self, minimal_entities, low_risk_rule_result
    ):
        _, user = build_risk_assessment_prompt(minimal_entities, low_risk_rule_result, None)
        assert "No cross-document consistency check performed" in user

    def test_serialize_entities_includes_all_sections(self, minimal_entities):
        text = _serialize_entities(minimal_entities)
        assert "Supplier" in text
        assert "Product" in text
        assert "Location" in text
        assert "Shipment" in text

    def test_serialize_rule_violations_shows_clean_record_when_none(self, low_risk_rule_result):
        text = _serialize_rule_violations(low_risk_rule_result)
        assert "clean record" in text.lower() or "None" in text

    def test_serialize_consistency_no_report(self):
        text = _serialize_consistency(None)
        assert "No cross-document" in text


# ============================================================================
# 3. Score Combination (40% rule + 60% LLM)
# ============================================================================


class TestScoreCombination:
    @pytest.fixture
    def assessor(self):
        return AIRiskAssessor(provider=MockLLMProvider())

    def test_combine_scores_formula(self, assessor):
        # 40 * 0.4 + 60 * 0.6 = 16 + 36 = 52
        assert assessor._combine_scores(40, 60) == 52

    def test_combine_scores_both_zero(self, assessor):
        assert assessor._combine_scores(0, 0) == 0

    def test_combine_scores_both_100(self, assessor):
        assert assessor._combine_scores(100, 100) == 100

    def test_combine_scores_capped_at_100(self, assessor):
        # Edge: could only exceed if weights summed > 1, but they sum to 1.0
        assert assessor._combine_scores(100, 100) == 100

    def test_combine_scores_rule_only_high(self, assessor):
        # 80 * 0.4 + 20 * 0.6 = 32 + 12 = 44
        assert assessor._combine_scores(80, 20) == 44

    def test_combine_scores_llm_only_high(self, assessor):
        # 20 * 0.4 + 80 * 0.6 = 8 + 48 = 56
        assert assessor._combine_scores(20, 80) == 56

    def test_weight_constants(self):
        assert RULE_WEIGHT == 0.40
        assert LLM_WEIGHT == 0.60
        assert RULE_WEIGHT + LLM_WEIGHT == 1.0

    def test_classify_risk_level_boundaries(self, assessor):
        assert assessor._classify_risk_level(0) == "low"
        assert assessor._classify_risk_level(20) == "low"
        assert assessor._classify_risk_level(21) == "medium"
        assert assessor._classify_risk_level(40) == "medium"
        assert assessor._classify_risk_level(41) == "high"
        assert assessor._classify_risk_level(70) == "high"
        assert assessor._classify_risk_level(71) == "critical"
        assert assessor._classify_risk_level(100) == "critical"


# ============================================================================
# 4. LLM Response Parsing
# ============================================================================


class TestLLMResponseParsing:
    @pytest.fixture
    def assessor(self):
        return AIRiskAssessor(provider=MockLLMProvider())

    def test_parse_valid_json(self, assessor):
        json_text = make_llm_json(llm_score=65, confidence=0.85)
        score, reasoning, confidence, actions = assessor._parse_llm_response(json_text)
        assert score == 65
        assert confidence == 0.85
        assert len(actions) > 0

    def test_parse_valid_json_reasoning(self, assessor):
        json_text = make_llm_json(reasoning="Clear risk due to missing documentation.")
        _, reasoning, _, _ = assessor._parse_llm_response(json_text)
        assert "Clear risk" in reasoning

    def test_parse_clamps_score_above_100(self, assessor):
        json_text = json.dumps({"llm_score": 150, "reasoning": "Test", "confidence": 0.5, "recommended_actions": []})
        score, _, _, _ = assessor._parse_llm_response(json_text)
        assert score == 100

    def test_parse_clamps_score_below_zero(self, assessor):
        json_text = json.dumps({"llm_score": -10, "reasoning": "Test", "confidence": 0.5, "recommended_actions": []})
        score, _, _, _ = assessor._parse_llm_response(json_text)
        assert score == 0

    def test_parse_clamps_confidence_above_one(self, assessor):
        json_text = json.dumps({"llm_score": 50, "reasoning": "Test", "confidence": 1.5, "recommended_actions": []})
        _, _, confidence, _ = assessor._parse_llm_response(json_text)
        assert confidence == 1.0

    def test_parse_clamps_confidence_below_zero(self, assessor):
        json_text = json.dumps({"llm_score": 50, "reasoning": "Test", "confidence": -0.5, "recommended_actions": []})
        _, _, confidence, _ = assessor._parse_llm_response(json_text)
        assert confidence == 0.0

    def test_parse_non_json_returns_defaults(self, assessor):
        score, reasoning, confidence, actions = assessor._parse_llm_response("This is not JSON at all.")
        assert score == 50
        assert confidence == 0.3
        assert "could not be parsed" in reasoning.lower() or reasoning

    def test_parse_markdown_code_block(self, assessor):
        wrapped = f"```json\n{make_llm_json(llm_score=72)}\n```"
        score, _, _, _ = assessor._parse_llm_response(wrapped)
        assert score == 72

    def test_parse_missing_fields_uses_defaults(self, assessor):
        json_text = json.dumps({"llm_score": 45})
        score, reasoning, confidence, actions = assessor._parse_llm_response(json_text)
        assert score == 45
        assert reasoning  # has a default
        assert 0.0 <= confidence <= 1.0

    def test_parse_actions_truncated_to_5(self, assessor):
        json_text = json.dumps({
            "llm_score": 50,
            "reasoning": "Test",
            "confidence": 0.6,
            "recommended_actions": ["a", "b", "c", "d", "e", "f", "g"],
        })
        _, _, _, actions = assessor._parse_llm_response(json_text)
        assert len(actions) <= 5


# ============================================================================
# 5. assess() Integration Tests
# ============================================================================


class TestAssessIntegration:
    @pytest.mark.asyncio
    async def test_happy_path_returns_assessment(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=15, confidence=0.90))
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result)

        assert isinstance(result, AIRiskAssessment)
        assert result.rule_based_score == 10
        assert result.llm_score == 15
        assert result.llm_confidence == 0.90
        assert result.model_used == "mock/test-model"

    @pytest.mark.asyncio
    async def test_combined_score_computed_correctly(self, minimal_entities, high_risk_rule_result):
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=70, confidence=0.80))
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, high_risk_rule_result)

        # 60 * 0.4 + 70 * 0.6 = 24 + 42 = 66
        assert result.combined_score == 66
        assert result.risk_level == "high"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self, minimal_entities, high_risk_rule_result):
        provider = MockLLMProvider(should_fail=True)
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, high_risk_rule_result)

        assert isinstance(result, AIRiskAssessment)
        assert result.llm_confidence == 0.0
        assert result.combined_score == high_risk_rule_result.risk_score
        assert result.model_used == "fallback"
        assert "unavailable" in result.llm_reasoning.lower()

    @pytest.mark.asyncio
    async def test_fallback_no_exception_raised(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(should_fail=True)
        assessor = AIRiskAssessor(provider=provider)

        # Must not raise
        result = await assessor.assess(minimal_entities, low_risk_rule_result)
        assert result is not None

    @pytest.mark.asyncio
    async def test_no_consistency_result_handled(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(response_text=make_llm_json())
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result, consistency_result=None)
        assert isinstance(result, AIRiskAssessment)

    @pytest.mark.asyncio
    async def test_with_consistency_result(
        self, minimal_entities, high_risk_rule_result, consistency_report
    ):
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=75))
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, high_risk_rule_result, consistency_report)
        assert isinstance(result, AIRiskAssessment)
        assert result.llm_score == 75

    @pytest.mark.asyncio
    async def test_returns_correct_type(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(response_text=make_llm_json())
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result)
        assert type(result).__name__ == "AIRiskAssessment"

    @pytest.mark.asyncio
    async def test_no_entities_raises_value_error(self, low_risk_rule_result):
        provider = MockLLMProvider(response_text=make_llm_json())
        assessor = AIRiskAssessor(provider=provider)

        with pytest.raises(ValueError, match="ExtractionResult is required"):
            await assessor.assess(None, low_risk_rule_result)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_no_rule_result_raises_value_error(self, minimal_entities):
        provider = MockLLMProvider(response_text=make_llm_json())
        assessor = AIRiskAssessor(provider=provider)

        with pytest.raises(ValueError, match="RiskScoreResult is required"):
            await assessor.assess(minimal_entities, None)  # type: ignore[arg-type]


# ============================================================================
# 6. Edge Cases
# ============================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_high_rule_score_100(self, minimal_entities):
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=100))
        assessor = AIRiskAssessor(provider=provider)

        max_rule_result = RiskScoreResult(
            risk_score=100,
            risk_level="critical",
            violations=[],
            violation_count=0,
            categories_affected=[],
        )
        result = await assessor.assess(minimal_entities, max_rule_result)

        assert result.combined_score == 100
        assert result.risk_level == "critical"

    @pytest.mark.asyncio
    async def test_low_rule_score_zero(self, minimal_entities):
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=0, confidence=0.99))
        assessor = AIRiskAssessor(provider=provider)

        zero_rule_result = RiskScoreResult(
            risk_score=0,
            risk_level="low",
            violations=[],
            violation_count=0,
            categories_affected=[],
        )
        result = await assessor.assess(minimal_entities, zero_rule_result)

        assert result.combined_score == 0
        assert result.risk_level == "low"

    @pytest.mark.asyncio
    async def test_many_violations_does_not_crash(self, minimal_entities):
        violations = [
            RuleViolation(
                rule_name=f"rule_{i}",
                category="compliance",
                points=5,
                reason=f"Violation {i}",
                severity="medium",
            )
            for i in range(10)
        ]
        many_violations_result = RiskScoreResult(
            risk_score=75,
            risk_level="critical",
            violations=violations,
            violation_count=10,
            categories_affected=["compliance"],
        )
        provider = MockLLMProvider(response_text=make_llm_json(llm_score=80))
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, many_violations_result)
        assert isinstance(result, AIRiskAssessment)

    @pytest.mark.asyncio
    async def test_empty_recommended_actions_in_response(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(
            response_text=make_llm_json(actions=[])
        )
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result)
        assert result.recommended_actions == []

    def test_fallback_reasoning_constant_is_meaningful(self):
        assert "unavailable" in LLM_FALLBACK_REASONING.lower()
        assert len(LLM_FALLBACK_REASONING) > 20

    @pytest.mark.asyncio
    async def test_reasoning_truncated_to_2000_chars(self, minimal_entities, low_risk_rule_result):
        long_reasoning = "x" * 3000
        provider = MockLLMProvider(
            response_text=json.dumps({
                "llm_score": 30,
                "reasoning": long_reasoning,
                "confidence": 0.5,
                "recommended_actions": [],
            })
        )
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result)
        assert len(result.llm_reasoning) <= 2000

    def test_constructor_raises_without_provider(self):
        with pytest.raises(ValueError, match="LLMProvider is required"):
            AIRiskAssessor(provider=None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_malformed_json_does_not_raise(self, minimal_entities, low_risk_rule_result):
        provider = MockLLMProvider(response_text="{invalid json here}")
        assessor = AIRiskAssessor(provider=provider)

        result = await assessor.assess(minimal_entities, low_risk_rule_result)
        assert isinstance(result, AIRiskAssessment)
        assert result.llm_score == 50  # default

    @pytest.mark.asyncio
    async def test_assess_fallback_risk_level_matches_rule(self, minimal_entities):
        provider = MockLLMProvider(should_fail=True)
        assessor = AIRiskAssessor(provider=provider)

        critical_result = RiskScoreResult(
            risk_score=85,
            risk_level="critical",
            violations=[],
            violation_count=0,
            categories_affected=[],
        )
        result = await assessor.assess(minimal_entities, critical_result)
        assert result.risk_level == "critical"
