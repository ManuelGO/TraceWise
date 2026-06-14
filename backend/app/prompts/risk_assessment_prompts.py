"""Risk assessment prompts for LLM-based nuanced risk analysis.

This module provides LLM prompts for performing nuanced compliance risk assessment
beyond deterministic rule-based scoring. The LLM receives extracted entities,
rule-based violations, and consistency conflicts, then produces:
1. A risk score (0-100) based on holistic analysis
2. Detailed reasoning explaining the assessment
3. Confidence in the assessment (0.0-1.0)
4. Prioritized remediation actions (up to 5)

The prompts are designed to:
- Produce valid JSON matching the expected response schema
- Avoid hallucinating entity data not provided
- Acknowledge uncertainty when information is insufficient
- Complement rule-based scoring with contextual reasoning
"""

from app.schemas.consistency import ConsistencyReport
from app.schemas.extraction import ExtractionResult
from app.services.risk_scorer import RiskScoreResult

RISK_ASSESSMENT_SYSTEM_PROMPT = """You are a senior supply chain compliance risk analyst with expertise in trade regulations, supplier due diligence, and import/export compliance.

Your task is to assess compliance risk for a supply chain entity based on:
1. Extracted supplier, product, location, and shipment information
2. Rule-based risk score and specific violations already detected
3. Cross-document consistency issues (if any)

ASSESSMENT GUIDELINES:
- Holistically evaluate all provided information, not just rule violations
- Consider context: a high-risk country supplier with full documentation is safer than a low-risk supplier with no documentation
- Weight the seriousness of each violation based on regulatory impact
- Your score should reflect nuanced compliance risk, not just violation count
- Be honest about uncertainty: if information is insufficient, reflect that in your confidence score
- Recommend specific, actionable remediation steps ordered by priority

SCORING SCALE:
- 0-20: LOW — Entity appears compliant with minor or no issues
- 21-40: MEDIUM — Some gaps or concerns requiring attention
- 41-70: HIGH — Significant risk, active remediation required
- 71-100: CRITICAL — Likely non-compliant, immediate escalation needed

OUTPUT FORMAT:
Return a JSON object only. No markdown, no code blocks, just valid JSON matching the schema provided."""

RISK_ASSESSMENT_EXAMPLE = """{
  "llm_score": 65,
  "reasoning": "The supplier from Iran (high-risk OFAC country) has certification documentation present, which mitigates some risk. However, the missing tracking number and unverified location create significant compliance exposure under current trade regulations. The recent shipment date (3 days ago) adds volatility risk. Combined with the date misalignment detected across documents, this assessment reflects a HIGH risk level. The certification reduces what would otherwise be a CRITICAL assessment.",
  "confidence": 0.78,
  "recommended_actions": [
    "Escalate Iran supplier relationship to compliance team for OFAC screening review",
    "Obtain and verify bill of lading or AWB tracking number from carrier",
    "Verify location coordinates and update geolocation verification status",
    "Reconcile shipment date discrepancy across all submitted documents",
    "Request updated supplier declaration with current certification status"
  ]
}"""


def _serialize_entities(entities: ExtractionResult) -> str:
    """Serialize ExtractionResult entities to human-readable text for the prompt."""
    supplier = entities.supplier
    product = entities.product
    location = entities.location
    shipment = entities.shipment

    lines = [
        "## EXTRACTED ENTITIES",
        "",
        "### Supplier",
        f"- Name: {supplier.name}",
        f"- Country of Origin: {supplier.country_of_origin}",
        f"- Registration Number: {supplier.registration_number or 'Not provided'}",
        f"- Business Type: {supplier.business_type or 'Not provided'}",
        f"- Certification Status: {supplier.certification_status or 'Not provided'}",
        f"- Last Updated: {supplier.last_updated.isoformat() if supplier.last_updated else 'Unknown'}",
        "",
        "### Product",
        f"- Name: {product.name}",
        f"- HS Code: {product.hs_code or 'Not provided'}",
        f"- Category: {product.category or 'Not provided'}",
        f"- Origin Country: {product.origin_country or 'Not provided'}",
        f"- Quantity: {f'{product.quantity} {product.unit}' if product.quantity else 'Not provided'}",
        "",
        "### Location",
        f"- Country: {location.country}",
        f"- Region: {location.region or 'Not provided'}",
        f"- Risk Profile: {location.risk_profile or 'Not assessed'}",
        f"- Geolocation Verified: {location.geolocation_verified}",
        "",
        "### Shipment",
        f"- Shipment Date: {shipment.shipment_date.isoformat() if shipment.shipment_date else 'Not provided'}",
        f"- Arrival Date: {shipment.arrival_date.isoformat() if shipment.arrival_date else 'Not provided'}",
        f"- Origin Port: {shipment.origin_port or 'Not provided'}",
        f"- Destination Port: {shipment.destination_port or 'Not provided'}",
        f"- Transport Mode: {shipment.transport_mode or 'Not provided'}",
        f"- Tracking Number: {shipment.tracking_number or 'Not provided'}",
        f"- Extraction Confidence: {entities.extraction_confidence:.1%}",
    ]

    return "\n".join(lines)


def _serialize_rule_violations(rule_score_result: RiskScoreResult) -> str:
    """Serialize RiskScoreResult violations to human-readable text for the prompt."""
    lines = [
        "## RULE-BASED ASSESSMENT",
        "",
        f"Rule-Based Score: {rule_score_result.risk_score}/100 ({rule_score_result.risk_level.upper()})",
        f"Total Violations: {rule_score_result.violation_count}",
        f"Categories Affected: {', '.join(rule_score_result.categories_affected) if rule_score_result.categories_affected else 'None'}",
    ]

    if rule_score_result.violations:
        lines.append("")
        lines.append("### Violations Detected")
        for v in rule_score_result.violations:
            lines.append(
                f"- [{v.category.upper()} +{v.points}pts | {v.severity}] {v.reason}"
            )
            if v.remediation:
                lines.append(f"  Suggested fix: {v.remediation}")
    else:
        lines.append("")
        lines.append("### Violations Detected")
        lines.append("- None (clean record)")

    return "\n".join(lines)


def _serialize_consistency(consistency_report: ConsistencyReport | None) -> str:
    """Serialize ConsistencyReport to human-readable text for the prompt."""
    if not consistency_report:
        return "## CONSISTENCY ANALYSIS\n\nNo cross-document consistency check performed."

    total = consistency_report.total_conflict_count
    lines = [
        "## CONSISTENCY ANALYSIS",
        "",
        f"Total Conflicts: {total}",
        f"Confidence Adjustment: -{consistency_report.confidence_adjustment:.0%}",
        f"Summary: {consistency_report.summary}",
    ]

    if consistency_report.field_conflicts:
        lines.append("")
        lines.append("### Field Conflicts")
        for fc in consistency_report.field_conflicts:
            lines.append(f"- Field '{fc.field}' [{fc.severity}]: conflicting values across documents")

    if consistency_report.temporal_conflicts:
        lines.append("")
        lines.append("### Temporal Conflicts")
        for tc in consistency_report.temporal_conflicts:
            lines.append(f"- {tc.conflict_type} [{tc.severity}]: {tc.description}")

    if consistency_report.logical_conflicts:
        lines.append("")
        lines.append("### Logical Conflicts")
        for lc in consistency_report.logical_conflicts:
            lines.append(f"- {lc.conflict_type} [{lc.severity}]: {lc.description}")

    return "\n".join(lines)


def build_risk_assessment_prompt(
    entities: ExtractionResult,
    rule_score_result: RiskScoreResult,
    consistency_report: ConsistencyReport | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for LLM risk assessment.

    Assembles a complete prompt containing extracted entities, rule-based violations,
    and consistency conflicts to enable the LLM to perform nuanced risk analysis.

    Args:
        entities: ExtractionResult with supplier, product, location, shipment data
        rule_score_result: RiskScoreResult from Task 41 rule-based scoring
        consistency_report: ConsistencyReport from Task 40 (optional)

    Returns:
        Tuple of (system_prompt, user_prompt) ready for LLM call
    """
    entities_text = _serialize_entities(entities)
    violations_text = _serialize_rule_violations(rule_score_result)
    consistency_text = _serialize_consistency(consistency_report)

    user_prompt = f"""{entities_text}

{violations_text}

{consistency_text}

## YOUR TASK

Based on all information above, provide a nuanced compliance risk assessment.

Consider:
- The rule-based score of {rule_score_result.risk_score}/100 is a starting point — your assessment should reflect holistic context
- The presence or absence of documentation is a key compliance indicator
- Country risk, certification status, and consistency issues compound each other
- Recent changes or activity may indicate higher volatility

JSON Schema (return JSON matching this structure exactly):
{{
  "llm_score": <integer 0-100>,
  "reasoning": <string, 200-300 words maximum explaining your assessment>,
  "confidence": <float 0.0-1.0, your confidence in this assessment>,
  "recommended_actions": <array of up to 5 strings, prioritized remediation steps>
}}

EXAMPLE OUTPUT:
{RISK_ASSESSMENT_EXAMPLE}

Return ONLY valid JSON. No explanation outside the JSON object."""

    return RISK_ASSESSMENT_SYSTEM_PROMPT, user_prompt
