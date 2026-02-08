"""
LLM-based extraction of structured data from SEC filings.

This module handles extracting structured financial data using Claude:
- Financial metrics (revenue, income, assets, etc.)
- Risk factors with categorization
- Business summaries

Uses structured output with Pydantic validation and retry logic.
"""

import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime

import anthropic

from utils import get_env, TMP_DIR
from schemas import (
    FilingExtraction,
    FinancialMetrics,
    RiskFactor,
    FilingType,
)
from prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    FINANCIAL_EXTRACTION_PROMPT,
    RISK_EXTRACTION_PROMPT,
    format_extraction_context,
)
from vector_store import query as vector_query, get_documents_by_ticker
from embeddings import embed_single

# Default model - Claude Opus 4.5 as per project requirements
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Retry settings
MAX_RETRIES = 2


def _get_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=get_env("ANTHROPIC_API_KEY"))


def _parse_json_response(response_text: str) -> Dict:
    """
    Parse JSON from LLM response, handling common issues.

    Args:
        response_text: Raw LLM response

    Returns:
        Parsed JSON dict
    """
    # Try to find JSON in the response
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (``` markers)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Try to parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not parse JSON from response: {text[:500]}...")


def _get_filing_chunks(
    ticker: str,
    filing_type: str,
    filing_date: str,
    sections: Optional[List[str]] = None,
    collection_name: str = "sec_filings",
) -> List[Dict]:
    """
    Get chunks for a specific filing from vector store.

    Args:
        ticker: Company ticker
        filing_type: Filing type (10-K, 10-Q)
        filing_date: Filing date
        sections: Optional list of sections to retrieve
        collection_name: Vector collection name

    Returns:
        List of chunk dicts
    """
    # Build filter
    where = {
        "$and": [
            {"ticker": ticker},
            {"filing_type": filing_type},
        ]
    }

    # Get all matching documents
    docs = get_documents_by_ticker(ticker, collection_name, limit=500)

    # Filter by filing date and optionally sections
    filtered = []
    for doc in docs:
        meta = doc.get('metadata', {})
        if meta.get('filing_date') == filing_date or meta.get('filing_type') == filing_type:
            if sections is None or meta.get('section') in sections:
                filtered.append({
                    'id': doc['id'],
                    'text': doc['document'],
                    'section': meta.get('section', 'unknown'),
                    'metadata': meta,
                })

    return filtered


def extract_financial_metrics(
    chunks: List[Dict],
    ticker: str,
    company_name: str,
    filing_type: str,
    filing_date: str,
    fiscal_year: int,
    model: str = DEFAULT_MODEL,
) -> tuple[FinancialMetrics, str, float]:
    """
    Extract financial metrics from filing chunks.

    Args:
        chunks: Document chunks with financial data
        ticker: Company ticker
        company_name: Company name
        filing_type: Filing type
        filing_date: Filing date
        fiscal_year: Fiscal year
        model: LLM model to use

    Returns:
        Tuple of (FinancialMetrics, business_summary, confidence_score)
    """
    client = _get_client()

    # Build context from financial sections
    financial_sections = ['item_7', 'item_8', 'item_7a']
    context = format_extraction_context(chunks, sections=financial_sections)

    prompt = FINANCIAL_EXTRACTION_PROMPT.format(
        ticker=ticker,
        company_name=company_name,
        filing_type=filing_type,
        filing_date=filing_date,
        fiscal_year=fiscal_year,
        context=context,
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            result = _parse_json_response(response.content[0].text)

            # Parse financial metrics
            metrics_data = result.get('financial_metrics', {})
            metrics = FinancialMetrics(**metrics_data)

            business_summary = result.get('business_summary', '')
            confidence = result.get('confidence_score', 0.5)

            return metrics, business_summary, confidence

        except Exception as e:
            if attempt < MAX_RETRIES:
                # Add error context for retry
                prompt += f"\n\nPrevious attempt failed with error: {str(e)}. Please fix and try again."
            else:
                raise ValueError(f"Failed to extract financial metrics after {MAX_RETRIES + 1} attempts: {e}")


def extract_risk_factors(
    chunks: List[Dict],
    model: str = DEFAULT_MODEL,
) -> List[RiskFactor]:
    """
    Extract risk factors from filing chunks.

    Args:
        chunks: Document chunks (should include item_1a)
        model: LLM model to use

    Returns:
        List of RiskFactor objects
    """
    client = _get_client()

    # Build context from risk sections
    context = format_extraction_context(chunks, sections=['item_1a'])

    if not context.strip():
        return []

    prompt = RISK_EXTRACTION_PROMPT.format(context=context)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            result = _parse_json_response(response.content[0].text)

            risk_data = result.get('risk_factors', [])
            risks = [RiskFactor(**r) for r in risk_data]

            return risks

        except Exception as e:
            if attempt < MAX_RETRIES:
                prompt += f"\n\nPrevious attempt failed: {str(e)}. Please fix."
            else:
                # Return empty list on failure rather than raising
                return []


def extract_filing(
    ticker: str,
    filing_type: str,
    filing_date: str,
    company_name: Optional[str] = None,
    accession_number: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    model: str = DEFAULT_MODEL,
    collection_name: str = "sec_filings",
) -> FilingExtraction:
    """
    Extract all structured data from an SEC filing.

    This is the main extraction function that orchestrates:
    1. Retrieving chunks from vector store
    2. Extracting financial metrics
    3. Extracting risk factors
    4. Building the complete FilingExtraction

    Args:
        ticker: Company ticker
        filing_type: Filing type (10-K, 10-Q)
        filing_date: Filing date (YYYY-MM-DD)
        company_name: Company name (fetched if not provided)
        accession_number: SEC accession number (optional)
        fiscal_year: Fiscal year (inferred from date if not provided)
        model: LLM model to use
        collection_name: Vector collection name

    Returns:
        FilingExtraction object with all extracted data
    """
    # Get company info if not provided
    if not company_name:
        from sec_fetcher import get_company_info
        info = get_company_info(ticker)
        company_name = info['name']

    # Infer fiscal year from filing date if not provided
    if not fiscal_year:
        year = int(filing_date.split('-')[0])
        # For 10-K filings, fiscal year is usually the prior year
        # (filed in Q1 of following year)
        month = int(filing_date.split('-')[1])
        fiscal_year = year - 1 if month <= 3 else year

    # Get chunks from vector store
    chunks = _get_filing_chunks(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date,
        collection_name=collection_name,
    )

    if not chunks:
        raise ValueError(
            f"No chunks found for {ticker} {filing_type} {filing_date}. "
            "Make sure the filing has been ingested and indexed."
        )

    # Extract financial metrics
    metrics, business_summary, confidence = extract_financial_metrics(
        chunks=chunks,
        ticker=ticker,
        company_name=company_name,
        filing_type=filing_type,
        filing_date=filing_date,
        fiscal_year=fiscal_year,
        model=model,
    )

    # Extract risk factors
    risk_factors = extract_risk_factors(chunks, model)

    # Build extraction
    extraction = FilingExtraction(
        ticker=ticker,
        company_name=company_name,
        filing_type=FilingType(filing_type),
        filing_date=datetime.strptime(filing_date, "%Y-%m-%d").date(),
        fiscal_year=fiscal_year,
        fiscal_quarter=None if filing_type == "10-K" else 1,  # TODO: infer quarter
        accession_number=accession_number or "unknown",
        financial_metrics=metrics,
        risk_factors=risk_factors,
        business_summary=business_summary,
        extraction_timestamp=datetime.now().isoformat(),
        model_used=model,
        confidence_score=confidence,
        validation_status="pending",
    )

    return extraction


def save_extraction(extraction: FilingExtraction) -> str:
    """
    Save extraction to JSON file.

    Args:
        extraction: FilingExtraction object

    Returns:
        Path to saved file
    """
    extractions_dir = TMP_DIR / "extractions"
    extractions_dir.mkdir(exist_ok=True)

    filename = f"{extraction.ticker}_{extraction.filing_type.value}_{extraction.filing_date}.json"
    output_path = extractions_dir / filename

    # Convert to dict for JSON serialization
    data = extraction.model_dump(mode='json')

    output_path.write_text(json.dumps(data, indent=2, default=str))

    return str(output_path)


def load_extraction(file_path: str) -> FilingExtraction:
    """
    Load extraction from JSON file.

    Args:
        file_path: Path to extraction JSON

    Returns:
        FilingExtraction object
    """
    from pathlib import Path
    data = json.loads(Path(file_path).read_text())
    return FilingExtraction(**data)


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extract structured data from SEC filings")
    parser.add_argument("--ticker", required=True, help="Company ticker")
    parser.add_argument("--filing-type", default="10-K", help="Filing type (10-K, 10-Q)")
    parser.add_argument("--filing-date", required=True, help="Filing date (YYYY-MM-DD)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--save", action="store_true", help="Save extraction to file")

    args = parser.parse_args()

    print(f"Extracting {args.filing_type} data for {args.ticker} ({args.filing_date})...")

    try:
        extraction = extract_filing(
            ticker=args.ticker,
            filing_type=args.filing_type,
            filing_date=args.filing_date,
            model=args.model,
        )

        print(f"\n✓ Extraction complete (confidence: {extraction.confidence_score:.2f})")
        print(f"\nCompany: {extraction.company_name}")
        print(f"Fiscal Year: {extraction.fiscal_year}")

        print(f"\nFinancial Metrics:")
        metrics = extraction.financial_metrics
        if metrics.revenue:
            print(f"  Revenue: ${metrics.revenue:,.0f}")
        if metrics.net_income:
            print(f"  Net Income: ${metrics.net_income:,.0f}")
        if metrics.total_assets:
            print(f"  Total Assets: ${metrics.total_assets:,.0f}")
        if metrics.cash_and_equivalents:
            print(f"  Cash: ${metrics.cash_and_equivalents:,.0f}")

        print(f"\nRisk Factors: {len(extraction.risk_factors)}")
        for i, risk in enumerate(extraction.risk_factors[:5], 1):
            print(f"  {i}. [{risk.severity.upper()}] {risk.title[:60]}...")

        print(f"\nBusiness Summary:")
        print(f"  {extraction.business_summary[:200]}...")

        if args.save:
            path = save_extraction(extraction)
            print(f"\nSaved to: {path}")

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
