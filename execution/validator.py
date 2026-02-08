"""
Validation logic for extracted financial data.

This module validates FilingExtraction objects to ensure:
- Required fields are present
- Mathematical consistency (balance sheet equation, margins)
- Values are within reasonable ranges
- Cross-reference with XBRL data when available

Validation is critical for accuracy-critical applications.
"""

import json
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from datetime import datetime

from schemas import FilingExtraction, ExtractionValidation, FinancialMetrics
from utils import TMP_DIR

# Tolerance for mathematical checks (1% variance allowed)
TOLERANCE = 0.01

# Reasonable ranges for financial metrics (in USD)
# These are sanity checks to catch obvious extraction errors
METRIC_RANGES = {
    'revenue': (0, 1e12),  # Up to $1 trillion
    'net_income': (-1e11, 5e11),  # Can be negative, up to $500B
    'total_assets': (0, 5e12),  # Up to $5 trillion
    'total_liabilities': (0, 5e12),
    'total_equity': (-5e11, 5e12),  # Can be negative
    'cash_and_equivalents': (0, 5e11),
    'eps_basic': (-1000, 1000),  # EPS per share
    'eps_diluted': (-1000, 1000),
}


def _check_required_fields(extraction: FilingExtraction) -> Tuple[bool, List[str]]:
    """
    Check that required fields are present.

    Args:
        extraction: FilingExtraction to check

    Returns:
        Tuple of (passed, list of missing field errors)
    """
    errors = []
    metrics = extraction.financial_metrics

    # Core required fields for a meaningful extraction
    required_fields = ['revenue', 'net_income', 'total_assets']

    for field in required_fields:
        value = getattr(metrics, field, None)
        if value is None:
            errors.append(f"Missing required field: {field}")

    return len(errors) == 0, errors


def _check_balance_sheet(metrics: FinancialMetrics) -> Tuple[bool, List[str]]:
    """
    Check balance sheet equation: Assets ≈ Liabilities + Equity.

    Args:
        metrics: FinancialMetrics to check

    Returns:
        Tuple of (passed, list of errors)
    """
    errors = []

    assets = metrics.total_assets
    liabilities = metrics.total_liabilities
    equity = metrics.total_equity

    if all(v is not None for v in [assets, liabilities, equity]):
        expected_assets = liabilities + equity
        if assets > 0:
            variance = abs(assets - expected_assets) / assets
            if variance > TOLERANCE:
                errors.append(
                    f"Balance sheet doesn't balance: Assets (${assets:,.0f}) != "
                    f"Liabilities (${liabilities:,.0f}) + Equity (${equity:,.0f}). "
                    f"Variance: {variance:.2%}"
                )

    return len(errors) == 0, errors


def _check_margin_consistency(metrics: FinancialMetrics) -> Tuple[bool, List[str]]:
    """
    Check that profit margins are mathematically consistent.

    Args:
        metrics: FinancialMetrics to check

    Returns:
        Tuple of (passed, list of errors)
    """
    errors = []

    revenue = metrics.revenue
    gross_profit = metrics.gross_profit
    operating_income = metrics.operating_income
    net_income = metrics.net_income

    if revenue and revenue > 0:
        # Gross margin check
        if gross_profit is not None:
            gross_margin = gross_profit / revenue
            if metrics.gross_margin is not None:
                if abs(gross_margin - metrics.gross_margin) > TOLERANCE:
                    errors.append(
                        f"Gross margin inconsistency: calculated {gross_margin:.2%} "
                        f"vs extracted {metrics.gross_margin:.2%}"
                    )

        # Operating margin check
        if operating_income is not None:
            operating_margin = operating_income / revenue
            if metrics.operating_margin is not None:
                if abs(operating_margin - metrics.operating_margin) > TOLERANCE:
                    errors.append(
                        f"Operating margin inconsistency: calculated {operating_margin:.2%} "
                        f"vs extracted {metrics.operating_margin:.2%}"
                    )

        # Net margin check
        if net_income is not None:
            net_margin = net_income / revenue
            if metrics.net_margin is not None:
                if abs(net_margin - metrics.net_margin) > TOLERANCE:
                    errors.append(
                        f"Net margin inconsistency: calculated {net_margin:.2%} "
                        f"vs extracted {metrics.net_margin:.2%}"
                    )

    # Profit hierarchy check: gross >= operating >= net (usually)
    if all(v is not None for v in [gross_profit, operating_income, net_income]):
        if gross_profit < operating_income:
            errors.append(
                f"Gross profit (${gross_profit:,.0f}) should be >= "
                f"operating income (${operating_income:,.0f})"
            )

    return len(errors) == 0, errors


def _check_value_ranges(metrics: FinancialMetrics) -> Tuple[bool, List[str], List[str]]:
    """
    Check that values are within reasonable ranges.

    Args:
        metrics: FinancialMetrics to check

    Returns:
        Tuple of (passed, errors, warnings)
    """
    errors = []
    warnings = []

    for field, (min_val, max_val) in METRIC_RANGES.items():
        value = getattr(metrics, field, None)
        if value is not None:
            if value < min_val or value > max_val:
                if abs(value) > max_val * 10:
                    # Way out of range - likely an error
                    errors.append(
                        f"{field} value ${value:,.0f} is outside reasonable range "
                        f"(${min_val:,.0f} to ${max_val:,.0f})"
                    )
                else:
                    # Somewhat out of range - warning
                    warnings.append(
                        f"{field} value ${value:,.0f} may be unusual "
                        f"(expected ${min_val:,.0f} to ${max_val:,.0f})"
                    )

    return len(errors) == 0, errors, warnings


def _check_date_consistency(extraction: FilingExtraction) -> Tuple[bool, List[str]]:
    """
    Check date consistency in the extraction.

    Args:
        extraction: FilingExtraction to check

    Returns:
        Tuple of (passed, list of errors)
    """
    errors = []

    filing_date = extraction.filing_date
    fiscal_year = extraction.fiscal_year

    # Filing should be after fiscal year end (typically)
    if filing_date.year < fiscal_year:
        errors.append(
            f"Filing date {filing_date} is before fiscal year {fiscal_year}"
        )

    # For 10-K, filing should be within ~3 months of fiscal year end
    if extraction.filing_type.value == "10-K":
        if filing_date.year > fiscal_year + 1:
            errors.append(
                f"10-K filing date {filing_date} is too far from fiscal year {fiscal_year}"
            )

    return len(errors) == 0, errors


def _cross_reference_xbrl(
    extraction: FilingExtraction,
    xbrl_data: Optional[Dict]
) -> Tuple[bool, List[str], List[str]]:
    """
    Cross-reference extraction with XBRL data if available.

    Args:
        extraction: FilingExtraction to validate
        xbrl_data: XBRL company facts from SEC API

    Returns:
        Tuple of (passed, errors, warnings)
    """
    if not xbrl_data:
        return True, [], ["XBRL data not available for cross-reference"]

    errors = []
    warnings = []

    # Map our field names to XBRL concepts
    xbrl_mappings = {
        'revenue': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax'],
        'net_income': ['NetIncomeLoss', 'ProfitLoss'],
        'total_assets': ['Assets'],
        'total_liabilities': ['Liabilities'],
        'total_equity': ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    }

    # Get US-GAAP facts
    us_gaap = xbrl_data.get('facts', {}).get('us-gaap', {})

    metrics = extraction.financial_metrics
    fiscal_year = extraction.fiscal_year

    for our_field, xbrl_concepts in xbrl_mappings.items():
        our_value = getattr(metrics, our_field, None)
        if our_value is None:
            continue

        for concept in xbrl_concepts:
            if concept in us_gaap:
                units = us_gaap[concept].get('units', {})
                usd_values = units.get('USD', [])

                # Find value for the same fiscal year
                for entry in usd_values:
                    fy = entry.get('fy')
                    if fy == fiscal_year:
                        xbrl_value = entry.get('val')
                        if xbrl_value:
                            variance = abs(our_value - xbrl_value) / xbrl_value if xbrl_value else 0
                            if variance > TOLERANCE:
                                warnings.append(
                                    f"{our_field}: extracted ${our_value:,.0f} vs "
                                    f"XBRL ${xbrl_value:,.0f} (variance: {variance:.2%})"
                                )
                            break

    return len(errors) == 0, errors, warnings


def validate_extraction(
    extraction: FilingExtraction,
    xbrl_data: Optional[Dict] = None,
    strict: bool = False
) -> ExtractionValidation:
    """
    Validate a FilingExtraction.

    Args:
        extraction: FilingExtraction to validate
        xbrl_data: Optional XBRL data for cross-reference
        strict: If True, treat warnings as errors

    Returns:
        ExtractionValidation with results
    """
    all_errors = []
    all_warnings = []

    # Run all checks
    required_ok, required_errors = _check_required_fields(extraction)
    all_errors.extend(required_errors)

    balance_ok, balance_errors = _check_balance_sheet(extraction.financial_metrics)
    all_errors.extend(balance_errors)

    margins_ok, margin_errors = _check_margin_consistency(extraction.financial_metrics)
    all_errors.extend(margin_errors)

    ranges_ok, range_errors, range_warnings = _check_value_ranges(extraction.financial_metrics)
    all_errors.extend(range_errors)
    all_warnings.extend(range_warnings)

    dates_ok, date_errors = _check_date_consistency(extraction)
    all_errors.extend(date_errors)

    xbrl_ok, xbrl_errors, xbrl_warnings = _cross_reference_xbrl(extraction, xbrl_data)
    all_errors.extend(xbrl_errors)
    all_warnings.extend(xbrl_warnings)

    # In strict mode, warnings become errors
    if strict:
        all_errors.extend(all_warnings)
        all_warnings = []

    is_valid = len(all_errors) == 0

    return ExtractionValidation(
        is_valid=is_valid,
        errors=all_errors,
        warnings=all_warnings,
        required_fields_present=required_ok,
        balance_sheet_balances=balance_ok,
        margins_consistent=margins_ok,
        values_in_range=ranges_ok,
        dates_consistent=dates_ok,
    )


def update_extraction_validation(
    extraction: FilingExtraction,
    validation: ExtractionValidation
) -> FilingExtraction:
    """
    Update extraction with validation results.

    Args:
        extraction: Original extraction
        validation: Validation results

    Returns:
        Updated extraction
    """
    if validation.is_valid:
        extraction.validation_status = "passed"
    elif validation.errors:
        extraction.validation_status = "failed"
    else:
        extraction.validation_status = "manual_review"

    extraction.validation_errors = validation.errors
    extraction.validation_warnings = validation.warnings

    return extraction


def save_validation_report(
    extraction: FilingExtraction,
    validation: ExtractionValidation
) -> str:
    """
    Save validation report to file.

    Args:
        extraction: The extraction that was validated
        validation: Validation results

    Returns:
        Path to saved report
    """
    validations_dir = TMP_DIR / "validations"
    validations_dir.mkdir(exist_ok=True)

    filename = f"{extraction.ticker}_{extraction.filing_type.value}_{extraction.filing_date}_validation.json"
    output_path = validations_dir / filename

    report = {
        "ticker": extraction.ticker,
        "filing_type": extraction.filing_type.value,
        "filing_date": str(extraction.filing_date),
        "validation_timestamp": datetime.now().isoformat(),
        "is_valid": validation.is_valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "checks": {
            "required_fields_present": validation.required_fields_present,
            "balance_sheet_balances": validation.balance_sheet_balances,
            "margins_consistent": validation.margins_consistent,
            "values_in_range": validation.values_in_range,
            "dates_consistent": validation.dates_consistent,
        }
    }

    output_path.write_text(json.dumps(report, indent=2))

    return str(output_path)


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate extracted financial data")
    parser.add_argument("extraction_file", help="Path to extraction JSON file")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--xbrl", help="Path to XBRL data JSON (optional)")
    parser.add_argument("--save", action="store_true", help="Save validation report")

    args = parser.parse_args()

    # Load extraction
    extraction_path = Path(args.extraction_file)
    if not extraction_path.exists():
        print(f"File not found: {extraction_path}")
        exit(1)

    from extractor import load_extraction
    extraction = load_extraction(str(extraction_path))

    # Load XBRL if provided
    xbrl_data = None
    if args.xbrl:
        xbrl_path = Path(args.xbrl)
        if xbrl_path.exists():
            xbrl_data = json.loads(xbrl_path.read_text())

    print(f"Validating {extraction.ticker} {extraction.filing_type.value} ({extraction.filing_date})...")

    # Run validation
    validation = validate_extraction(extraction, xbrl_data, strict=args.strict)

    # Print results
    status = "✓ PASSED" if validation.is_valid else "✗ FAILED"
    print(f"\nValidation: {status}")

    print(f"\nChecks:")
    print(f"  Required fields: {'✓' if validation.required_fields_present else '✗'}")
    print(f"  Balance sheet: {'✓' if validation.balance_sheet_balances else '✗'}")
    print(f"  Margins consistent: {'✓' if validation.margins_consistent else '✗'}")
    print(f"  Values in range: {'✓' if validation.values_in_range else '✗'}")
    print(f"  Dates consistent: {'✓' if validation.dates_consistent else '✗'}")

    if validation.errors:
        print(f"\nErrors ({len(validation.errors)}):")
        for error in validation.errors:
            print(f"  ✗ {error}")

    if validation.warnings:
        print(f"\nWarnings ({len(validation.warnings)}):")
        for warning in validation.warnings:
            print(f"  ⚠ {warning}")

    if args.save:
        report_path = save_validation_report(extraction, validation)
        print(f"\nReport saved to: {report_path}")

    # Exit with error code if validation failed
    exit(0 if validation.is_valid else 1)
