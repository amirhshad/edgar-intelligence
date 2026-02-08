"""
Prompt templates for LLM operations.

This module contains all prompt templates used in the system:
- Extraction prompts for structured data extraction
- RAG prompts for question answering
- Validation prompts for checking extracted data

All prompts follow low-hallucination principles:
1. Explicit instruction to only use provided context
2. Required citations for all claims
3. "null over guess" for uncertain values
4. Confidence scoring
"""

# ============================================================================
# EXTRACTION PROMPTS
# ============================================================================

EXTRACTION_SYSTEM_PROMPT = """You are a financial analyst AI assistant specialized in extracting structured data from SEC filings.

CRITICAL RULES:
1. Extract ONLY information explicitly stated in the provided text
2. Use null for any values not found - NEVER guess or estimate
3. All monetary values must be in USD
4. Flag any ambiguous values with low confidence
5. Distinguish between fiscal year and calendar year dates

Your output must be valid JSON matching the provided schema exactly."""

FINANCIAL_EXTRACTION_PROMPT = """Extract financial data from this {filing_type} filing for {ticker} ({company_name}).
Filing date: {filing_date}
Fiscal year: {fiscal_year}

<context>
{context}
</context>

Extract the following information into a JSON object with this structure:

{{
  "financial_metrics": {{
    "revenue": <number or null>,
    "cost_of_revenue": <number or null>,
    "gross_profit": <number or null>,
    "operating_expenses": <number or null>,
    "operating_income": <number or null>,
    "net_income": <number or null>,
    "eps_basic": <number or null>,
    "eps_diluted": <number or null>,
    "total_assets": <number or null>,
    "total_liabilities": <number or null>,
    "total_equity": <number or null>,
    "cash_and_equivalents": <number or null>,
    "total_debt": <number or null>,
    "operating_cash_flow": <number or null>,
    "investing_cash_flow": <number or null>,
    "financing_cash_flow": <number or null>,
    "capital_expenditures": <number or null>,
    "free_cash_flow": <number or null>
  }},
  "business_summary": "<2-3 sentence summary of the business>",
  "confidence_score": <0.0 to 1.0>
}}

IMPORTANT:
- Convert all values to raw USD (not thousands/millions/billions)
- If a table shows "(in millions)", multiply values by 1,000,000
- Return null for any value you cannot find with certainty
- The confidence_score reflects your overall confidence in the extraction

Respond with ONLY the JSON object, no explanation or markdown."""


RISK_EXTRACTION_PROMPT = """Extract risk factors from this SEC filing's Item 1A section.

<context>
{context}
</context>

Extract each risk factor as a JSON object in this array format:

{{
  "risk_factors": [
    {{
      "category": "<market|operational|regulatory|financial|legal|cybersecurity|competitive|macroeconomic|other>",
      "title": "<brief risk title, 1 sentence>",
      "description": "<key points from the risk description, 2-3 sentences>",
      "severity": "<low|medium|high|critical>",
      "is_new": false
    }}
  ]
}}

Guidelines:
- Category should be one of: market, operational, regulatory, financial, legal, cybersecurity, competitive, macroeconomic, other
- Severity assessment based on language intensity and potential impact
- Extract the top 10-15 most significant risks
- Keep descriptions concise but informative

Respond with ONLY the JSON object."""


# ============================================================================
# RAG PROMPTS
# ============================================================================

RAG_SYSTEM_PROMPT = """You are a financial research assistant with access to SEC filings.
Your role is to answer questions accurately using ONLY the provided context.

CRITICAL RULES:
1. ONLY use information from the provided context
2. ALWAYS cite your sources using [1], [2], etc. format
3. If the context doesn't contain the answer, say "I don't have information about this in the provided filings"
4. NEVER make up financial figures - if unsure, say so
5. When comparing across time periods, note the dates of each source
6. Distinguish between forward-looking statements and reported facts
7. Be precise with numbers - include units and time periods

Your answers should be clear, direct, and well-sourced."""


RAG_USER_PROMPT = """Question: {query}

Context from SEC filings:
{context}

Instructions:
- Answer the question using ONLY the context above
- Cite sources using [1], [2], etc. format matching the source numbers
- If the answer isn't in the context, say "I don't have information about this"
- Be precise with numbers and dates
- Keep your answer concise but complete"""


RAG_CONTEXT_TEMPLATE = """[{index}] Source: {ticker} {filing_type} ({filing_date}) - {section}
{text}
"""


# ============================================================================
# VALIDATION PROMPTS
# ============================================================================

VALIDATION_PROMPT = """Review this extracted financial data for accuracy and consistency.

Extracted Data:
{extraction_json}

Original Context:
{context}

Check for:
1. Mathematical consistency (e.g., gross_profit = revenue - cost_of_revenue)
2. Balance sheet equation (assets ≈ liabilities + equity, within 1%)
3. Sign correctness (expenses should be positive, losses may be negative)
4. Reasonable ranges for the company size
5. Any values that seem incorrect or suspicious

Respond with JSON:
{{
  "is_valid": <true or false>,
  "errors": ["<critical errors that must be fixed>"],
  "warnings": ["<non-critical issues to note>"],
  "suggested_corrections": {{
    "<field_name>": <corrected_value>
  }}
}}"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_rag_context(
    chunks: list,
    max_chars: int = 8000,
    max_chunk_chars: int = 2000
) -> str:
    """
    Format retrieved chunks into context string for RAG.

    Args:
        chunks: List of dicts with 'text', 'metadata', 'id' keys
        max_chars: Maximum characters for total context
        max_chunk_chars: Maximum characters per individual chunk (truncate if larger)

    Returns:
        Formatted context string with numbered sources
    """
    context_parts = []
    total_chars = 0

    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get('metadata', {})
        text = chunk.get('text', chunk.get('document', ''))

        # Truncate oversized chunks to prevent single chunk from exceeding limits
        if len(text) > max_chunk_chars:
            text = text[:max_chunk_chars] + "... [truncated]"

        formatted = RAG_CONTEXT_TEMPLATE.format(
            index=i,
            ticker=metadata.get('ticker', 'Unknown'),
            filing_type=metadata.get('filing_type', 'Unknown'),
            filing_date=metadata.get('filing_date', 'Unknown'),
            section=metadata.get('section', 'Unknown'),
            text=text,
        )

        if total_chars + len(formatted) > max_chars:
            break

        context_parts.append(formatted)
        total_chars += len(formatted)

    return "\n---\n".join(context_parts)


def format_extraction_context(
    chunks: list,
    sections: list = None,
    max_chars: int = 12000
) -> str:
    """
    Format chunks for extraction, optionally filtering by section.

    Args:
        chunks: List of chunk dicts
        sections: Optional list of sections to include (e.g., ['item_7', 'item_8'])
        max_chars: Maximum characters

    Returns:
        Formatted context string
    """
    filtered = chunks
    if sections:
        filtered = [c for c in chunks if c.get('section') in sections or
                    c.get('metadata', {}).get('section') in sections]

    context_parts = []
    total_chars = 0

    for chunk in filtered:
        text = chunk.get('text', chunk.get('document', ''))
        section = chunk.get('section', chunk.get('metadata', {}).get('section', 'Unknown'))

        formatted = f"[{section.upper()}]\n{text}\n"

        if total_chars + len(formatted) > max_chars:
            break

        context_parts.append(formatted)
        total_chars += len(formatted)

    return "\n".join(context_parts)


def build_extraction_prompt(
    chunks: list,
    ticker: str,
    company_name: str,
    filing_type: str,
    filing_date: str,
    fiscal_year: int,
) -> str:
    """
    Build a complete extraction prompt with context.

    Args:
        chunks: Document chunks
        ticker: Company ticker
        company_name: Company name
        filing_type: Filing type (10-K, 10-Q)
        filing_date: Filing date
        fiscal_year: Fiscal year

    Returns:
        Complete prompt string
    """
    # For extraction, prioritize financial sections
    financial_sections = ['item_7', 'item_8', 'item_7a']
    context = format_extraction_context(chunks, sections=financial_sections)

    return FINANCIAL_EXTRACTION_PROMPT.format(
        ticker=ticker,
        company_name=company_name,
        filing_type=filing_type,
        filing_date=filing_date,
        fiscal_year=fiscal_year,
        context=context,
    )


def build_rag_prompt(
    query: str,
    chunks: list,
) -> str:
    """
    Build a complete RAG prompt with context.

    Args:
        query: User's question
        chunks: Retrieved document chunks

    Returns:
        Complete prompt string
    """
    context = format_rag_context(chunks)

    return RAG_USER_PROMPT.format(
        query=query,
        context=context,
    )
