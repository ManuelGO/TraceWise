"""Extraction prompts for structured entity extraction task.

This module provides LLM prompts for extracting structured entities (supplier,
product, location, shipment information) from compliance documents.

The prompts are designed to:
1. Guide the LLM to produce valid JSON matching Pydantic schemas
2. Extract only information present in the document
3. Mark uncertain values while still attempting extraction
4. Provide confidence scores for each extraction
5. Handle missing or ambiguous information gracefully
"""

# Extraction system prompt - guides LLM on the overall task
EXTRACTION_SYSTEM_PROMPT = """You are an expert supply chain compliance analyst specializing in extracting structured entity information from documents.

Your task is to extract four types of structured information from documents:
1. SUPPLIER: Company name, country of origin, registration number, business type, certification status
2. PRODUCT: Product name, HS code, category, origin country, quantity, unit
3. LOCATION: Country, region, risk profile, geolocation verification status
4. SHIPMENT: Dates, ports, transport mode, tracking numbers

IMPORTANT REQUIREMENTS:
- Extract ONLY information explicitly stated in the document
- For uncertain values, still extract but note your uncertainty in the confidence score
- Use null for any fields not found in the document
- Mark fields as "unknown" only for categorical fields when genuinely unknown
- Normalize country names to ISO 3166-1 alpha-2 codes (e.g., "China" → "CN")
- Normalize dates to YYYY-MM-DD format
- Normalize HS codes to 8-10 digit format without spaces or dashes
- Return JSON that exactly matches the specified schema

OUTPUT FORMAT:
Return a JSON object with the exact structure specified below. No markdown, no code blocks, just valid JSON.
"""

# Example extraction for in-context learning
EXTRACTION_EXAMPLE = """{
  "supplier": {
    "name": "Shanghai Steel Manufacturing Co.",
    "country_of_origin": "CN",
    "registration_number": "CHY-1234567",
    "business_type": "manufacturer",
    "certification_status": "certified",
    "last_updated": "2026-05-30T00:00:00"
  },
  "product": {
    "name": "Hot Rolled Steel Coils",
    "hs_code": "72081100",
    "category": "metals",
    "origin_country": "CN",
    "quantity": 500.0,
    "unit": "kg"
  },
  "location": {
    "country": "CN",
    "region": "Shanghai",
    "risk_profile": "medium-risk",
    "geolocation_verified": false
  },
  "shipment": {
    "shipment_date": "2026-05-15",
    "arrival_date": "2026-06-02",
    "origin_port": "Shanghai Port",
    "destination_port": "Rotterdam Port",
    "transport_mode": "sea",
    "tracking_number": "BL202605001234"
  },
  "extraction_confidence": 0.92
}"""

# User prompt template - filled with document text and context
EXTRACTION_USER_PROMPT_TEMPLATE = """Extract structured entity information from the following document and context.

Document Text:
{document_text}

Retrieved Context (additional relevant information):
{context}

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

FIELD REQUIREMENTS AND NOTES:
- supplier.name and product.name are REQUIRED (must extract or indicate null only if completely missing)
- location.country is REQUIRED (must extract or indicate null if completely missing)
- country_of_origin and origin_country must be ISO 3166-1 alpha-2 codes or full country names (will be normalized to codes)
- Dates must be in YYYY-MM-DD format or ISO datetime format
- HS codes must be 8-10 digit strings (e.g., "72081100" for steel coils)
- extraction_confidence should reflect your confidence in the overall extraction (0.0 = no confidence, 1.0 = full confidence)
- For uncertainty about specific values, still extract them but lower the overall extraction_confidence

EXAMPLE OUTPUT:
{example_extraction}

Now extract the information from the provided document. Return ONLY valid JSON, no explanation."""

def build_extraction_prompt(document_text: str, context: str = "") -> tuple[str, str]:
    """Build system and user prompts for entity extraction.

    Args:
        document_text: The document content to extract from
        context: Optional retrieved context from retrieval service

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    user_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
        document_text=document_text,
        context=context if context else "(No additional context provided)",
        example_extraction=EXTRACTION_EXAMPLE,
    )
    return EXTRACTION_SYSTEM_PROMPT, user_prompt
