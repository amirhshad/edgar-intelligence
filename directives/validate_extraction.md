# Directive: Validate Extraction

> Validate extracted financial data against known sources and internal consistency rules.

## Goal

Ensure extracted data is accurate and internally consistent before pushing to downstream systems.

## Inputs

- **extraction_path**: Path to extraction JSON (required)
- **strict_mode**: Treat warnings as errors (optional, default: false)
- **xbrl_path**: Path to XBRL data for cross-reference (optional)

## Tools/Scripts

- `execution/validator.py` - Validation logic
- `execution/sec_fetcher.py` - Fetch XBRL data for comparison
- `execution/extractor.py` - Load extraction data

## Process

1. **Load extraction**: Load the FilingExtraction from JSON
2. **Run structural checks**: Verify required fields are present
3. **Run mathematical checks**:
   - Balance sheet equation (Assets ≈ Liabilities + Equity)
   - Profit margin consistency
4. **Run range checks**: Ensure values are within reasonable bounds
5. **Run date checks**: Verify date consistency
6. **Cross-reference XBRL**: If available, compare against official XBRL data
7. **Generate report**: Create validation report with pass/fail status
8. **Update extraction**: Mark validation_status as passed/failed/manual_review

## Outputs

- Updated extraction JSON with validation_status
- Validation report at `.tmp/validations/{ticker}_{filing_type}_{date}_validation.json`

## Example Usage

```python
from execution.extractor import load_extraction, save_extraction
from execution.validator import validate_extraction, update_extraction_validation, save_validation_report
from execution.sec_fetcher import fetch_xbrl_facts

# Load extraction
extraction = load_extraction(".tmp/extractions/AAPL_10-K_2023-10-27.json")

# Fetch XBRL for cross-reference (optional)
xbrl_data = fetch_xbrl_facts("AAPL")

# Validate
validation = validate_extraction(extraction, xbrl_data)

# Update and save
extraction = update_extraction_validation(extraction, validation)
save_extraction(extraction)
save_validation_report(extraction, validation)

print(f"Status: {extraction.validation_status}")
```

## CLI Usage

```bash
# Basic validation
python execution/validator.py .tmp/extractions/AAPL_10-K_2023-10-27.json

# Strict mode (warnings become errors)
python execution/validator.py .tmp/extractions/AAPL_10-K_2023-10-27.json --strict

# With XBRL cross-reference
python execution/validator.py .tmp/extractions/AAPL_10-K_2023-10-27.json --xbrl xbrl_data.json

# Save validation report
python execution/validator.py .tmp/extractions/AAPL_10-K_2023-10-27.json --save
```

## Validation Checks Explained

### Required Fields Check
Ensures critical fields are present:
- `revenue` - Must have a value
- `net_income` - Must have a value
- `total_assets` - Must have a value

### Balance Sheet Check
Verifies the accounting equation:
```
Assets = Liabilities + Equity (±1%)
```

### Margin Consistency Check
Calculated margins must match extracted margins:
```
gross_margin = gross_profit / revenue
operating_margin = operating_income / revenue
net_margin = net_income / revenue
```

### Value Range Check
Sanity checks for reasonable values:
| Metric | Range |
|--------|-------|
| Revenue | $0 - $1T |
| Net Income | -$100B - $500B |
| Total Assets | $0 - $5T |
| EPS | -$1000 - $1000 |

### Date Consistency Check
- Filing date should be after fiscal year end
- 10-K filings should be within ~3 months of fiscal year end

### XBRL Cross-Reference (Optional)
Compares extracted values against official XBRL data from SEC:
- Revenue vs XBRL Revenues
- Net Income vs XBRL NetIncomeLoss
- Assets vs XBRL Assets

## Validation Status

| Status | Meaning | Action |
|--------|---------|--------|
| `passed` | All checks passed | Safe to use |
| `failed` | Critical errors found | Do not use, fix extraction |
| `manual_review` | Warnings present | Human review recommended |
| `pending` | Not yet validated | Run validation |

## Edge Cases

- **XBRL not available**: Skip cross-reference, note in warnings
- **Minor discrepancies**: Allow 1% variance for rounding differences
- **Missing optional fields**: Warning only, not an error
- **Failed validation**: Do not push to downstream systems, flag for review
- **Negative equity**: Valid for some companies, flagged as warning

## Learnings

- XBRL data is the gold standard for validation when available
- Most extraction errors are unit issues (thousands vs millions vs raw)
- Balance sheet equation is the most reliable consistency check
- Always cross-reference before pushing to production systems
- Keep validation tolerances at 1% to allow for rounding
