# Directive: Sync to Google Sheets

> Push validated extractions to Google Sheets for downstream consumption.

## Goal

Maintain a live Google Sheet dashboard with extracted financial data from SEC filings.

## Inputs

- **extraction_path**: Path to validated extraction JSON (required)
- **spreadsheet_name**: Google Sheet name (optional, default: "SEC Filings Dashboard")
- **update_existing**: Whether to update existing rows (optional, default: true)

## Tools/Scripts

- `execution/sheets_sync.py` - Google Sheets operations

## Prerequisites

1. **Google Cloud Project** with Sheets API enabled
2. **OAuth Credentials** saved as `credentials.json` in project root
3. **First-time authentication** will open browser for consent

## Process

1. **Load extraction**: Load the FilingExtraction from JSON
2. **Verify validation**: Only sync if validation_status is "passed" or "manual_review"
3. **Connect to Sheets**: Authenticate with Google Sheets API
4. **Get/create spreadsheet**: Open existing or create new spreadsheet
5. **Setup worksheet**: Ensure "Extractions" sheet exists with headers
6. **Check for duplicates**: Find existing row by ticker/filing_type/filing_date
7. **Sync data**: Update existing row or append new row
8. **Return result**: Report row number, action taken, and sheet URL

## Outputs

- Updated Google Sheet row
- Sync confirmation with spreadsheet URL

## Example Usage

```python
from execution.extractor import load_extraction
from execution.sheets_sync import sync_extraction

# Load validated extraction
extraction = load_extraction(".tmp/extractions/AAPL_10-K_2023-10-27.json")

# Sync to sheets
result = sync_extraction(extraction)

print(f"Action: {result['action']}")
print(f"Row: {result['row_number']}")
print(f"URL: {result['spreadsheet_url']}")
```

## CLI Usage

```bash
# Test connection
python execution/sheets_sync.py --test

# Sync an extraction
python execution/sheets_sync.py --sync .tmp/extractions/AAPL_10-K_2023-10-27.json

# Custom spreadsheet name
python execution/sheets_sync.py --sync extraction.json --spreadsheet "My Dashboard"

# Get sync stats
python execution/sheets_sync.py --stats
```

## Sheet Structure

### Extractions Worksheet

| Column | Field | Description |
|--------|-------|-------------|
| A | Ticker | Company ticker symbol |
| B | Company Name | Full company name |
| C | Filing Type | 10-K, 10-Q, etc. |
| D | Filing Date | YYYY-MM-DD |
| E | Fiscal Year | Fiscal year number |
| F | Revenue | Total revenue (USD) |
| G | Net Income | Net income (USD) |
| H | Total Assets | Total assets (USD) |
| I | Total Liabilities | Total liabilities (USD) |
| J | Total Equity | Stockholders equity (USD) |
| K | Cash | Cash and equivalents (USD) |
| L | EPS Basic | Basic earnings per share |
| M | Operating Cash Flow | Cash from operations (USD) |
| N | Risk Factor Count | Number of risk factors |
| O | Confidence Score | Extraction confidence (0-1) |
| P | Validation Status | passed/failed/manual_review |
| Q | Extraction Timestamp | When extraction was run |

## Edge Cases

- **Spreadsheet doesn't exist**: Creates new spreadsheet with headers
- **Duplicate detection**: Uses ticker + filing_type + filing_date as unique key
- **Validation not passed**: Refuses to sync, returns error message
- **API quota exceeded**: Retry with exponential backoff
- **No credentials**: Returns clear error with setup instructions

## Setup Instructions

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Sheets API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download and save as `credentials.json` in project root
6. First run will open browser for authentication
7. `token.json` will be created for future runs

## Learnings

- Batch updates are more efficient than individual cell updates
- Include extraction_timestamp to track data freshness
- Use unique key (ticker/type/date) to prevent duplicates
- Only sync validated extractions to maintain data quality
- Consider using service account for automated/webhook use cases
