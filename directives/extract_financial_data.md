# Directive: Extract Financial Data

> Use LLM to extract structured financial data from SEC filings.

## Goal

Extract key financial metrics, risk factors, and business summaries from indexed SEC filings into validated structured output.

## Inputs

- **ticker**: Stock ticker symbol (required)
- **filing_type**: "10-K" or "10-Q" (required)
- **filing_date**: Specific filing date YYYY-MM-DD (required)
- **model**: LLM model to use (optional, default: claude-opus-4-5-20250101)

## Tools/Scripts

- `execution/extractor.py` - LLM extraction with structured output
- `execution/validator.py` - Validate extracted data
- `execution/vector_store.py` - Retrieve relevant chunks
- `execution/schemas.py` - Pydantic models for output

## Process

1. **Retrieve chunks**: Get document chunks from vector store for the specified filing
2. **Extract financials**: Call Claude with financial sections (Item 7, Item 8)
3. **Extract risks**: Call Claude with risk factors section (Item 1A)
4. **Build extraction**: Create FilingExtraction object with all data
5. **Run validation**: Validate the extraction for consistency
6. **Handle failures**: If validation fails, retry extraction with error context (max 2 retries)
7. **Save extraction**: Write to `.tmp/extractions/` as JSON

## Outputs

- FilingExtraction JSON at `.tmp/extractions/{ticker}_{filing_type}_{date}.json`
- Validation report at `.tmp/validations/` (if validation run separately)

## Example Usage

```python
from execution.extractor import extract_filing, save_extraction
from execution.validator import validate_extraction, update_extraction_validation

# Extract
extraction = extract_filing(
    ticker="AAPL",
    filing_type="10-K",
    filing_date="2023-10-27"
)

# Validate
validation = validate_extraction(extraction)
extraction = update_extraction_validation(extraction, validation)

# Save
path = save_extraction(extraction)
print(f"Saved to {path}")
print(f"Validation: {extraction.validation_status}")
```

## CLI Usage

```bash
# Extract with save
python execution/extractor.py --ticker AAPL --filing-type 10-K --filing-date 2023-10-27 --save

# Validate existing extraction
python execution/validator.py .tmp/extractions/AAPL_10-K_2023-10-27.json --save
```

## Extracted Data Structure

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "filing_type": "10-K",
  "filing_date": "2023-10-27",
  "fiscal_year": 2023,
  "financial_metrics": {
    "revenue": 383285000000,
    "net_income": 96995000000,
    "total_assets": 352583000000,
    "total_liabilities": 290437000000,
    "total_equity": 62146000000,
    ...
  },
  "risk_factors": [
    {
      "category": "market",
      "title": "Global economic conditions...",
      "description": "...",
      "severity": "high",
      "is_new": false
    }
  ],
  "business_summary": "Apple designs, manufactures...",
  "confidence_score": 0.85,
  "validation_status": "passed"
}
```

## Edge Cases

- **Missing sections**: Some filings lack certain items - extraction continues with available data
- **Multiple currencies**: Values should be converted to USD with noted conversion
- **Restated figures**: Amendments may have different figures - note if detected
- **Low confidence**: Flag for manual review if confidence_score < 0.7
- **No chunks found**: Error if filing hasn't been ingested - run ingest_sec_filing first

## Validation Checks

| Check | Description |
|-------|-------------|
| Required fields | revenue, net_income, total_assets must be present |
| Balance sheet | Assets ≈ Liabilities + Equity (within 1%) |
| Margin consistency | Calculated margins match extracted margins |
| Value ranges | Figures within reasonable bounds |
| Date consistency | Filing date makes sense for fiscal year |

## Learnings

- Claude Opus 4.5 produces the most accurate structured extractions
- Include few-shot examples in prompts for consistent formatting
- Financial tables often have units in headers (millions, thousands) - prompt handles this
- Item 7 (MD&A) often has the clearest financial summaries
- Retry with error context significantly improves extraction success rate
