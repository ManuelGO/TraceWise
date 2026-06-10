"""Retry prompts for extraction validation and retry.

This module provides improved prompts for retrying failed extractions.
These prompts include information about what failed and specific guidance
to fix the issues identified during validation.
"""

from app.schemas.extraction import ExtractionResult
from app.schemas.validation import ValidationResult, ValidationRuleType

RETRY_SYSTEM_PROMPT = """You are an expert supply chain compliance analyst specializing in extracting structured entity information from documents.

Your task is to IMPROVE a previous extraction that had validation failures. Use the feedback about what failed to make corrections.

IMPORTANT REQUIREMENTS:
- Extract ONLY information explicitly stated in the document
- Pay special attention to the fields that failed validation in the previous attempt
- Fix the issues identified in the validation failures
- For uncertain values, still extract but note your uncertainty in the confidence score
- Use null for any fields not found in the document
- Normalize country names to ISO 3166-1 alpha-2 codes (e.g., "China" → "CN")
- Normalize dates to YYYY-MM-DD format
- Normalize HS codes to 8-10 digit format without spaces or dashes
- Return JSON that exactly matches the specified schema

OUTPUT FORMAT:
Return a JSON object with the exact structure specified below. No markdown, no code blocks, just valid JSON.
"""


def build_retry_prompt(
    original_result: ExtractionResult,
    validation_result: ValidationResult,
    document_text: str,
    context: str = "",
) -> str:
    """Build an improved retry prompt based on validation failures.

    Args:
        original_result: The original (failed) extraction result
        validation_result: The validation result with failure details
        document_text: Original document text for re-extraction
        context: Retrieved context for extraction

    Returns:
        Full retry prompt (system + user) ready for LLM call
    """
    # Build failure details
    failure_details = _format_failure_details(validation_result)

    # Build corrected examples based on failures
    correction_guidance = _build_correction_guidance(validation_result)

    # Format the original extraction for reference
    original_extraction_str = _format_original_extraction(original_result)

    user_prompt = f"""Your previous extraction attempt had the following validation failures:

{failure_details}

GUIDANCE FOR FIXING THESE ISSUES:
{correction_guidance}

ORIGINAL EXTRACTION ATTEMPT (for reference):
{original_extraction_str}

DOCUMENT TEXT (for re-extraction):
{document_text}

RETRIEVED CONTEXT (additional relevant information):
{context if context else "(No additional context provided)"}

Please review the document again and fix the identified issues. Pay special attention to:
- Fields that failed validation (listed above)
- The guidance provided for each type of failure
- The specific requirements for each field type

JSON Schema (return JSON matching this structure exactly):
{{
  "supplier": {{
    "name": <string, required>,
    "country_of_origin": <string (ISO code), required>,
    "registration_number": <string or null>,
    "business_type": <string or null>,
    "certification_status": <string or null>,
    "last_updated": <ISO datetime or null>
  }},
  "product": {{
    "name": <string, required>,
    "hs_code": <string (8-10 digits) or null>,
    "category": <string or null>,
    "origin_country": <string (ISO code) or null>,
    "quantity": <float or null>,
    "unit": <string or null>
  }},
  "location": {{
    "country": <string (ISO code), required>,
    "region": <string or null>,
    "risk_profile": <string or null>,
    "geolocation_verified": <boolean, default false>
  }},
  "shipment": {{
    "shipment_date": <ISO date (YYYY-MM-DD) or null>,
    "arrival_date": <ISO date (YYYY-MM-DD) or null>,
    "origin_port": <string or null>,
    "destination_port": <string or null>,
    "transport_mode": <string or null>,
    "tracking_number": <string or null>
  }},
  "extraction_confidence": <float between 0.0 and 1.0>
}}

CRITICAL: Your extraction_confidence should be higher if you're fixing the identified issues. Return ONLY valid JSON, no explanation."""

    return f"{RETRY_SYSTEM_PROMPT}\n\n{user_prompt}"


def _format_failure_details(validation_result: ValidationResult) -> str:
    """Format validation failures as readable details.

    Args:
        validation_result: Validation result with failures

    Returns:
        Formatted string describing failures
    """
    if not validation_result.failures:
        return "No failures detected (extraction passed validation)."

    failure_groups = {}
    for failure in validation_result.failures:
        rule = failure.rule
        if rule not in failure_groups:
            failure_groups[rule] = []
        failure_groups[rule].append(failure)

    details_lines = []
    for rule, failures in failure_groups.items():
        details_lines.append(f"\n{rule.upper()}:")
        for failure in failures:
            details_lines.append(
                f"  - Field: {failure.field}"
            )
            details_lines.append(
                f"    Message: {failure.message}"
            )
            details_lines.append(
                f"    Severity: {failure.severity}"
            )

    return "\n".join(details_lines)


def _build_correction_guidance(validation_result: ValidationResult) -> str:
    """Build guidance for fixing specific validation failures.

    Args:
        validation_result: Validation result with failures

    Returns:
        Formatted string with correction guidance
    """
    guidance_lines = []

    failed_rules = set(f.rule for f in validation_result.failures)

    if ValidationRuleType.COMPLETENESS in failed_rules:
        guidance_lines.append(
            "COMPLETENESS: Ensure all required fields are present and non-empty:\n"
            "  - supplier.name (required)\n"
            "  - supplier.country_of_origin (required)\n"
            "  - product.name (required)\n"
            "  - location.country (required)"
        )

    if ValidationRuleType.DATE_LOGIC in failed_rules:
        guidance_lines.append(
            "DATE LOGIC: Fix date ordering:\n"
            "  - shipment_date must be <= arrival_date\n"
            "  - If only one date exists, that's acceptable\n"
            "  - Check the document carefully for date values"
        )

    if ValidationRuleType.PORT_VALIDATION in failed_rules:
        guidance_lines.append(
            "PORT VALIDATION: Use recognizable port names:\n"
            "  - Include port keywords: 'port', 'terminal', 'dock', 'harbor'\n"
            "  - Or use known port cities: Shanghai, Rotterdam, Singapore, Los Angeles\n"
            "  - Or leave empty if not clearly specified"
        )

    if ValidationRuleType.COUNTRY_CODE in failed_rules:
        guidance_lines.append(
            "COUNTRY CODES: Use valid ISO 3166-1 alpha-2 codes:\n"
            "  - Examples: CN (China), US (USA), GB (UK), DE (Germany)\n"
            "  - Or use full country names, which will be normalized\n"
            "  - Check the document for country references"
        )

    if ValidationRuleType.HS_CODE_FORMAT in failed_rules:
        guidance_lines.append(
            "HS CODE FORMAT: Format must be 8-10 consecutive digits:\n"
            "  - Valid: '72081100', '1234567890'\n"
            "  - Invalid: '7208-1100' (has dashes), '7208 1100' (has spaces)\n"
            "  - Normalize by removing spaces and dashes"
        )

    if ValidationRuleType.TRACKING_FORMAT in failed_rules:
        guidance_lines.append(
            "TRACKING FORMAT: Use standard tracking formats:\n"
            "  - Length: 5-50 alphanumeric characters\n"
            "  - Allowed characters: letters, numbers, hyphens, slashes, periods\n"
            "  - Examples: BL123456789, AWB00123456789, 1234-5678-9012"
        )

    if not guidance_lines:
        return "No specific guidance needed (all validations passed)."

    return "\n\n".join(guidance_lines)


def _format_original_extraction(result: ExtractionResult) -> str:
    """Format the original extraction result as readable text.

    Args:
        result: ExtractionResult to format

    Returns:
        Formatted string representation
    """
    lines = [
        f"Supplier: {result.supplier.name or 'NOT_EXTRACTED'}",
        f"  Country of Origin: {result.supplier.country_of_origin or 'NOT_EXTRACTED'}",
        f"  Registration: {result.supplier.registration_number or 'not_provided'}",
        f"Product: {result.product.name or 'NOT_EXTRACTED'}",
        f"  HS Code: {result.product.hs_code or 'not_provided'}",
        f"  Category: {result.product.category or 'not_provided'}",
        f"Location Country: {result.location.country or 'NOT_EXTRACTED'}",
        f"  Region: {result.location.region or 'not_provided'}",
        f"Shipment Date: {result.shipment.shipment_date or 'not_provided'}",
        f"Arrival Date: {result.shipment.arrival_date or 'not_provided'}",
        f"Origin Port: {result.shipment.origin_port or 'not_provided'}",
        f"Destination Port: {result.shipment.destination_port or 'not_provided'}",
        f"Tracking Number: {result.shipment.tracking_number or 'not_provided'}",
        f"Extraction Confidence: {result.extraction_confidence:.2f}",
    ]
    return "\n".join(lines)
