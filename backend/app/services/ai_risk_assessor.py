"""LLM-assisted risk assessment service for nuanced compliance analysis.

This module provides LLM-based risk assessment that goes beyond deterministic
rule-based scoring. The AI Risk Assessor receives extracted entities, rule violations,
and consistency conflicts, then uses an LLM to perform holistic contextual analysis.

Pipeline position:
  Task 38 (Extract) -> Task 39 (Validate) -> Task 40 (Consistency)
  -> Task 41 (Rules) -> Task 42 (THIS) -> Task 43 (Confidence) -> Task 44 (Gaps)

The combined score formula:
  combined_score = 0.40 * rule_based_score + 0.60 * llm_score

Risk level thresholds (matches Task 41):
  0-20: low, 21-40: medium, 41-70: high, 71-100: critical
"""

import json
import logging
import re
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.prompts.risk_assessment_prompts import build_risk_assessment_prompt
from app.schemas.consistency import ConsistencyReport
from app.schemas.extraction import ExtractionResult
from app.services.llm_service import LLMError, LLMProvider
from app.services.risk_scorer import RiskScoreResult

logger = logging.getLogger(__name__)

# Weighting for combined score (coordinator-approved from PHASE_5_ARCHITECTURE.md)
RULE_WEIGHT = 0.40
LLM_WEIGHT = 0.60

# Fallback message when LLM call fails (coordinator-approved in TASK_42_COORDINATOR_DECISIONS.md)
LLM_FALLBACK_REASONING = (
    "LLM risk assessment unavailable due to service error. "
    "Using rule-based scoring only. "
    "Please retry later for full LLM assessment."
)


class AIRiskAssessment(BaseModel):
    """Result of LLM-assisted risk assessment.

    Combines rule-based score from Task 41 with LLM-generated nuanced assessment.
    The combined_score is the weighted average used downstream by Task 43.

    Attributes:
        rule_based_score: Original rule-based score from Task 41 (0-100)
        llm_score: LLM's independent risk assessment (0-100)
        combined_score: Weighted average: 40% rule + 60% LLM, capped at 0-100
        risk_level: Final risk classification derived from combined_score
        llm_reasoning: LLM explanation of the assessment (max 2000 chars)
        llm_confidence: LLM's confidence in its own assessment (0.0-1.0)
        recommended_actions: Prioritized remediation steps from LLM (max 5)
        assessed_at: UTC timestamp of when assessment was performed
        model_used: LLM model identifier used for this assessment
    """

    model_config = ConfigDict(extra="forbid")

    rule_based_score: int = Field(..., ge=0, le=100, description="Rule-based score from Task 41")
    llm_score: int = Field(..., ge=0, le=100, description="LLM risk score (0-100)")
    combined_score: int = Field(..., ge=0, le=100, description="Weighted combined score: 40% rule + 60% LLM")
    risk_level: str = Field(
        ...,
        pattern="^(low|medium|high|critical)$",
        description="Risk level derived from combined_score",
    )
    llm_reasoning: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="LLM explanation of the risk assessment",
    )
    llm_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="LLM confidence in its assessment (0.0-1.0)",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Prioritized remediation actions (up to 5)",
    )
    assessed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of assessment",
    )
    model_used: str = Field(..., min_length=1, description="LLM model identifier")

    @field_validator("recommended_actions")
    @classmethod
    def validate_actions(cls, v: list[str]) -> list[str]:
        """Ensure actions are non-empty strings and bounded to 5."""
        if len(v) > 5:
            raise ValueError("recommended_actions must contain at most 5 items")
        return [a.strip() for a in v if a and a.strip()]


class AIRiskAssessor:
    """LLM-assisted risk assessment service.

    Takes rule-based scoring results from Task 41 and uses an LLM to provide
    nuanced, contextual risk analysis. Produces a combined risk score that
    weights LLM assessment more heavily (60%) than rules (40%).

    This is a pure computation service: no database writes, no caching,
    no state. The same inputs always produce structurally valid output
    (though LLM content will vary).

    Attributes:
        provider: LLM provider for making API calls
        settings: Application settings for temperature and token limits
    """

    def __init__(self, provider: LLMProvider, settings=None) -> None:
        """Initialize AIRiskAssessor.

        Args:
            provider: LLMProvider instance (OpenRouter or mock)
            settings: Application settings (defaults to get_settings())

        Raises:
            ValueError: If provider is None
        """
        if not provider:
            raise ValueError("LLMProvider is required")

        self.provider = provider
        self.settings = settings or get_settings()

    async def assess(
        self,
        entities: ExtractionResult,
        rule_score_result: RiskScoreResult,
        consistency_result: ConsistencyReport | None = None,
    ) -> AIRiskAssessment:
        """Perform LLM-assisted risk assessment.

        Builds a prompt from extracted entities, rule violations, and consistency
        conflicts, calls the LLM, parses the JSON response, and returns a combined
        risk assessment. If the LLM call fails, falls back to rule-based score only.

        Args:
            entities: ExtractionResult with supplier/product/location/shipment data
            rule_score_result: RiskScoreResult from Task 41 rule-based scoring
            consistency_result: ConsistencyReport from Task 40 (optional)

        Returns:
            AIRiskAssessment with combined score, LLM reasoning, and confidence

        Example:
            >>> assessor = AIRiskAssessor(provider=llm_provider)
            >>> result = await assessor.assess(entities, rule_score_result)
            >>> print(f"Combined Risk: {result.combined_score} ({result.risk_level})")
        """
        if not entities:
            raise ValueError("ExtractionResult is required")
        if not rule_score_result:
            raise ValueError("RiskScoreResult is required")

        logger.debug(
            f"Starting LLM risk assessment for document {entities.document_id}, "
            f"rule_score={rule_score_result.risk_score}"
        )

        system_prompt, user_prompt = build_risk_assessment_prompt(
            entities=entities,
            rule_score_result=rule_score_result,
            consistency_report=consistency_result,
        )
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            raw = await self.provider.generate(
                prompt=full_prompt,
                temperature=self.settings.EXTRACTION_TEMPERATURE,
                max_tokens=self.settings.LLM_MAX_TOKENS,
            )
            llm_score, reasoning, confidence, actions = self._parse_llm_response(raw["text"])
            model_used = raw.get("model", self.provider.get_model_name())

            logger.info(
                f"LLM assessment complete: llm_score={llm_score}, "
                f"confidence={confidence:.2f}, model={model_used}"
            )

        except LLMError as e:
            logger.warning(f"LLM assessment failed, using fallback: {e}")
            return self._build_fallback(rule_score_result)

        combined = self._combine_scores(rule_score_result.risk_score, llm_score)
        risk_level = self._classify_risk_level(combined)

        return AIRiskAssessment(
            rule_based_score=rule_score_result.risk_score,
            llm_score=llm_score,
            combined_score=combined,
            risk_level=risk_level,
            llm_reasoning=reasoning[:2000],
            llm_confidence=confidence,
            recommended_actions=actions[:5],
            model_used=model_used,
        )

    def _parse_llm_response(
        self, response_text: str
    ) -> tuple[int, str, float, list[str]]:
        """Parse and validate LLM JSON response.

        Attempts to extract JSON from the response text. If parsing fails or
        required fields are missing, returns safe defaults so the assessment
        can continue with partial LLM data.

        Args:
            response_text: Raw text response from LLM

        Returns:
            Tuple of (llm_score, reasoning, confidence, recommended_actions)
            with all values clamped to valid ranges
        """
        # Try to extract JSON from response (handle markdown code blocks)
        json_text = response_text.strip()
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", json_text)
        if code_block_match:
            json_text = code_block_match.group(1).strip()

        try:
            data = json.loads(json_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("LLM returned non-JSON response, using defaults")
            return 50, "LLM response could not be parsed. Defaulting to midpoint score.", 0.3, []

        # Extract and clamp llm_score
        raw_score = data.get("llm_score", 50)
        try:
            llm_score = max(0, min(100, int(raw_score)))
        except (TypeError, ValueError):
            logger.warning(f"Invalid llm_score from LLM: {raw_score!r}, defaulting to 50")
            llm_score = 50

        # Extract reasoning
        reasoning = str(data.get("reasoning", "No reasoning provided by LLM.")).strip()
        if not reasoning:
            reasoning = "No reasoning provided by LLM."

        # Extract and clamp confidence
        raw_confidence = data.get("confidence", 0.5)
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            logger.warning(f"Invalid confidence from LLM: {raw_confidence!r}, defaulting to 0.5")
            confidence = 0.5

        # Extract recommended_actions (list of strings, max 5)
        raw_actions = data.get("recommended_actions", [])
        if not isinstance(raw_actions, list):
            raw_actions = []
        actions = [str(a).strip() for a in raw_actions if a and str(a).strip()][:5]

        return llm_score, reasoning, confidence, actions

    def _combine_scores(self, rule_score: int, llm_score: int) -> int:
        """Compute weighted combined score.

        Formula (coordinator-approved): 40% rule-based + 60% LLM.
        Result is capped to [0, 100].

        Args:
            rule_score: Rule-based score from Task 41 (0-100)
            llm_score: LLM score from parsed response (0-100)

        Returns:
            Combined score as integer in [0, 100]
        """
        raw = rule_score * RULE_WEIGHT + llm_score * LLM_WEIGHT
        return max(0, min(100, int(raw)))

    def _classify_risk_level(self, score: int) -> str:
        """Map combined score to risk level.

        Uses coordinator-approved thresholds (matches Task 41 RiskScorer).

        Args:
            score: Combined risk score (0-100)

        Returns:
            Risk level string: "low", "medium", "high", or "critical"
        """
        if score <= 20:
            return "low"
        elif score <= 40:
            return "medium"
        elif score <= 70:
            return "high"
        else:
            return "critical"

    def _build_fallback(self, rule_score_result: RiskScoreResult) -> AIRiskAssessment:
        """Build fallback assessment when LLM call fails.

        Uses rule-based score as both llm_score and combined_score.
        Sets llm_confidence to 0.0 to signal that LLM was unavailable.

        Args:
            rule_score_result: Rule-based scoring result from Task 41

        Returns:
            AIRiskAssessment with rule-based score substituted for LLM score
        """
        score = rule_score_result.risk_score
        return AIRiskAssessment(
            rule_based_score=score,
            llm_score=score,
            combined_score=score,
            risk_level=rule_score_result.risk_level,
            llm_reasoning=LLM_FALLBACK_REASONING,
            llm_confidence=0.0,
            recommended_actions=[],
            model_used="fallback",
        )
