# Directive: Ingest SEC Filing

> Download, parse, and chunk SEC filings for embedding and retrieval.

## Goal

Fetch SEC filings from EDGAR, parse the document into sections, and prepare semantic chunks for the vector database.

## Inputs

- **ticker**: Stock ticker symbol (required, e.g., "AAPL", "MSFT")
- **filing_type**: Type of filing (required: "10-K", "10-Q", or "8-K")
- **filing_date**: Specific filing date in YYYY-MM-DD format (optional, defaults to most recent)
- **count**: Number of filings to process (optional, default: 1)

## Tools/Scripts

- `execution/sec_fetcher.py` - Downloads filings from SEC EDGAR
- `execution/pdf_parser.py` - Parses HTML/PDF documents into structured text
- `execution/chunker.py` - Splits documents into embedding-ready chunks

## Process

1. **Validate ticker**: Use `sec_fetcher.get_company_info(ticker)` to verify the ticker exists
2. **List available filings**: Use `sec_fetcher.list_filings(ticker, filing_type)` to get recent filings
3. **Download filing**: Use `sec_fetcher.download_filing(ticker, accession_number)` to fetch the document
4. **Parse document**: Use `pdf_parser.parse_filing(file_path)` to extract text and sections
5. **Save parsed filing**: Use `pdf_parser.save_parsed_filing(parsed)` to store in `.tmp/parsed/`
6. **Chunk document**: Use `chunker.chunk_document(parsed)` to create semantic chunks
7. **Save chunks**: Use `chunker.save_chunks(chunks, ...)` to store in `.tmp/chunks/`
8. **Return results**: Report chunk count, sections found, and file paths

## Outputs

- Raw filing saved to: `.tmp/raw/{ticker}_{form}_{date}.htm`
- Parsed sections saved to: `.tmp/parsed/{ticker}_{form}_{date}.json`
- Chunks saved to: `.tmp/chunks/{ticker}_{form}_{date}_chunks.json`

## Example Usage

```python
# Ingest Apple's most recent 10-K
from execution.sec_fetcher import list_filings, download_filing
from execution.pdf_parser import parse_filing, save_parsed_filing
from execution.chunker import chunk_document, save_chunks

# 1. Find the filing
filings = list_filings("AAPL", "10-K", count=1)
accession = filings[0]["accession_number"]

# 2. Download
file_path = download_filing("AAPL", accession)

# 3. Parse
parsed = parse_filing(file_path)
save_parsed_filing(parsed)

# 4. Chunk
chunks = chunk_document(parsed.__dict__)
save_chunks(chunks, "AAPL", "10-K", filings[0]["filing_date"])
```

## Edge Cases

- **Ticker not found**: Return clear error message with suggestion to verify ticker symbol
- **No filings available**: Return message indicating no filings of requested type exist
- **HTML vs PDF**: System prefers HTML (better structure); falls back to PDF with OCR if needed
- **Rate limiting**: SEC limits to 10 requests/second - scripts handle this automatically
- **Large filings**: 10-Ks can be 200+ pages; chunking handles this efficiently
- **Missing sections**: Some filings may lack certain items - proceed with available sections

## SEC Section Reference

| Section | Name | Typical Content |
|---------|------|-----------------|
| Item 1 | Business | Company description, products, strategy |
| Item 1A | Risk Factors | Key risks facing the company |
| Item 1B | Unresolved Staff Comments | SEC comment letter issues |
| Item 7 | MD&A | Management's analysis of financial condition |
| Item 7A | Quantitative Disclosures | Market risk, derivatives |
| Item 8 | Financial Statements | Balance sheet, income statement, cash flow |

## Learnings

- SEC EDGAR requires User-Agent header with contact email (configured in sec_fetcher.py)
- Most 10-K/10-Q filings are available in HTML format (easier to parse than PDF)
- Item numbers in filings are standardized across all companies
- Some companies file amended versions (10-K/A) - these supersede originals
- Fiscal year end dates vary by company (not all are December 31)
