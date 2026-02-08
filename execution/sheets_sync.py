"""
Google Sheets integration for syncing extracted financial data.

This module handles pushing validated extractions to Google Sheets,
maintaining a live dashboard of financial data for downstream consumption.

Requires:
- credentials.json: OAuth credentials for Google Sheets API
- token.json: Generated after first authentication
"""

import json
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime

from utils import get_env, PROJECT_ROOT
from schemas import FilingExtraction

# Try to import Google Sheets libraries
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.oauth2.credentials import Credentials as UserCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]

# Default column headers for the extractions sheet
EXTRACTION_HEADERS = [
    'Ticker',
    'Company Name',
    'Filing Type',
    'Filing Date',
    'Fiscal Year',
    'Revenue',
    'Net Income',
    'Total Assets',
    'Total Liabilities',
    'Total Equity',
    'Cash',
    'EPS Basic',
    'Operating Cash Flow',
    'Risk Factor Count',
    'Confidence Score',
    'Validation Status',
    'Extraction Timestamp',
]


def _get_credentials():
    """
    Get Google API credentials.

    Tries service account first, then OAuth flow for user credentials.
    """
    if not SHEETS_AVAILABLE:
        raise ImportError(
            "Google Sheets libraries not installed. "
            "Run: pip install gspread google-auth-oauthlib"
        )

    # Try service account credentials first
    service_account_path = PROJECT_ROOT / "credentials.json"
    if service_account_path.exists():
        creds_data = json.loads(service_account_path.read_text())
        if creds_data.get('type') == 'service_account':
            return Credentials.from_service_account_file(
                str(service_account_path),
                scopes=SCOPES
            )

    # Try OAuth credentials
    token_path = PROJECT_ROOT / "token.json"
    creds = None

    if token_path.exists():
        creds = UserCredentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not service_account_path.exists():
                raise FileNotFoundError(
                    "No credentials found. Please add credentials.json to project root. "
                    "See: https://developers.google.com/sheets/api/quickstart/python"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(service_account_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        token_path.write_text(creds.to_json())

    return creds


def get_client() -> 'gspread.Client':
    """
    Get authenticated gspread client.

    Returns:
        Authenticated gspread client
    """
    creds = _get_credentials()
    return gspread.authorize(creds)


def get_or_create_spreadsheet(
    name: str = "SEC Filings Dashboard",
    folder_id: Optional[str] = None
) -> 'gspread.Spreadsheet':
    """
    Get or create a spreadsheet by name.

    Args:
        name: Spreadsheet name
        folder_id: Optional Google Drive folder ID

    Returns:
        gspread Spreadsheet object
    """
    client = get_client()

    try:
        # Try to open existing spreadsheet
        spreadsheet = client.open(name)
    except gspread.SpreadsheetNotFound:
        # Create new spreadsheet
        spreadsheet = client.create(name)
        if folder_id:
            client.move(spreadsheet.id, folder_id)

    return spreadsheet


def setup_extractions_sheet(spreadsheet: 'gspread.Spreadsheet') -> 'gspread.Worksheet':
    """
    Set up or get the Extractions worksheet with headers.

    Args:
        spreadsheet: gspread Spreadsheet object

    Returns:
        Worksheet for extractions
    """
    worksheet_name = "Extractions"

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,
            cols=len(EXTRACTION_HEADERS)
        )
        # Add headers
        worksheet.update('A1', [EXTRACTION_HEADERS])
        # Format headers (bold)
        worksheet.format('A1:Q1', {'textFormat': {'bold': True}})

    return worksheet


def extraction_to_row(extraction: FilingExtraction) -> List[Any]:
    """
    Convert FilingExtraction to a spreadsheet row.

    Args:
        extraction: FilingExtraction object

    Returns:
        List of values for the row
    """
    metrics = extraction.financial_metrics

    return [
        extraction.ticker,
        extraction.company_name,
        extraction.filing_type.value,
        str(extraction.filing_date),
        extraction.fiscal_year,
        metrics.revenue,
        metrics.net_income,
        metrics.total_assets,
        metrics.total_liabilities,
        metrics.total_equity,
        metrics.cash_and_equivalents,
        metrics.eps_basic,
        metrics.operating_cash_flow,
        len(extraction.risk_factors),
        extraction.confidence_score,
        extraction.validation_status,
        extraction.extraction_timestamp,
    ]


def find_existing_row(
    worksheet: 'gspread.Worksheet',
    ticker: str,
    filing_type: str,
    filing_date: str
) -> Optional[int]:
    """
    Find existing row for a filing (to update instead of duplicate).

    Args:
        worksheet: Target worksheet
        ticker: Company ticker
        filing_type: Filing type
        filing_date: Filing date

    Returns:
        Row number if found, None otherwise
    """
    try:
        # Get all values
        all_values = worksheet.get_all_values()

        for i, row in enumerate(all_values[1:], start=2):  # Skip header
            if len(row) >= 4:
                if (row[0] == ticker and
                    row[2] == filing_type and
                    row[3] == filing_date):
                    return i

    except Exception:
        pass

    return None


def sync_extraction(
    extraction: FilingExtraction,
    spreadsheet_name: str = "SEC Filings Dashboard",
    update_existing: bool = True
) -> Dict[str, Any]:
    """
    Sync a FilingExtraction to Google Sheets.

    Args:
        extraction: FilingExtraction to sync
        spreadsheet_name: Target spreadsheet name
        update_existing: If True, update existing rows instead of appending

    Returns:
        Dict with sync results (sheet_url, row_number, action)
    """
    # Only sync validated extractions
    if extraction.validation_status not in ['passed', 'manual_review']:
        raise ValueError(
            f"Cannot sync extraction with status '{extraction.validation_status}'. "
            "Only 'passed' or 'manual_review' extractions can be synced."
        )

    spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
    worksheet = setup_extractions_sheet(spreadsheet)

    row_data = extraction_to_row(extraction)

    # Check for existing row
    existing_row = None
    if update_existing:
        existing_row = find_existing_row(
            worksheet,
            extraction.ticker,
            extraction.filing_type.value,
            str(extraction.filing_date)
        )

    if existing_row:
        # Update existing row
        cell_range = f'A{existing_row}:Q{existing_row}'
        worksheet.update(cell_range, [row_data])
        action = "updated"
        row_number = existing_row
    else:
        # Append new row
        worksheet.append_row(row_data)
        row_number = len(worksheet.get_all_values())
        action = "appended"

    return {
        'spreadsheet_id': spreadsheet.id,
        'spreadsheet_url': spreadsheet.url,
        'worksheet': worksheet.title,
        'row_number': row_number,
        'action': action,
        'ticker': extraction.ticker,
        'filing_type': extraction.filing_type.value,
        'filing_date': str(extraction.filing_date),
    }


def sync_multiple_extractions(
    extractions: List[FilingExtraction],
    spreadsheet_name: str = "SEC Filings Dashboard"
) -> List[Dict[str, Any]]:
    """
    Sync multiple extractions to Google Sheets.

    Args:
        extractions: List of FilingExtraction objects
        spreadsheet_name: Target spreadsheet name

    Returns:
        List of sync results
    """
    results = []

    for extraction in extractions:
        try:
            result = sync_extraction(extraction, spreadsheet_name)
            result['success'] = True
            results.append(result)
        except Exception as e:
            results.append({
                'ticker': extraction.ticker,
                'filing_type': extraction.filing_type.value,
                'success': False,
                'error': str(e),
            })

    return results


def get_sync_stats(spreadsheet_name: str = "SEC Filings Dashboard") -> Dict[str, Any]:
    """
    Get statistics about synced data.

    Args:
        spreadsheet_name: Spreadsheet name

    Returns:
        Dict with statistics
    """
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.worksheet("Extractions")

        all_values = worksheet.get_all_values()
        data_rows = all_values[1:]  # Exclude header

        tickers = set(row[0] for row in data_rows if row)
        filing_types = {}
        validation_statuses = {}

        for row in data_rows:
            if len(row) >= 16:
                ft = row[2]
                vs = row[15]
                filing_types[ft] = filing_types.get(ft, 0) + 1
                validation_statuses[vs] = validation_statuses.get(vs, 0) + 1

        return {
            'spreadsheet_url': spreadsheet.url,
            'total_rows': len(data_rows),
            'unique_tickers': len(tickers),
            'tickers': list(tickers),
            'filing_types': filing_types,
            'validation_statuses': validation_statuses,
        }

    except Exception as e:
        return {'error': str(e)}


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync extractions to Google Sheets")
    parser.add_argument("--sync", help="Path to extraction JSON to sync")
    parser.add_argument("--spreadsheet", default="SEC Filings Dashboard",
                        help="Spreadsheet name")
    parser.add_argument("--stats", action="store_true", help="Show sync stats")
    parser.add_argument("--test", action="store_true", help="Test connection")

    args = parser.parse_args()

    if args.test:
        print("Testing Google Sheets connection...")
        try:
            client = get_client()
            print("✓ Successfully connected to Google Sheets API")

            spreadsheet = get_or_create_spreadsheet(args.spreadsheet)
            print(f"✓ Spreadsheet: {spreadsheet.title}")
            print(f"  URL: {spreadsheet.url}")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            exit(1)

    elif args.stats:
        print(f"Getting stats for '{args.spreadsheet}'...")
        stats = get_sync_stats(args.spreadsheet)

        if 'error' in stats:
            print(f"Error: {stats['error']}")
        else:
            print(f"\nSpreadsheet: {stats['spreadsheet_url']}")
            print(f"Total extractions: {stats['total_rows']}")
            print(f"Unique tickers: {stats['unique_tickers']}")
            print(f"Tickers: {', '.join(sorted(stats['tickers']))}")
            print(f"\nBy filing type:")
            for ft, count in stats['filing_types'].items():
                print(f"  {ft}: {count}")
            print(f"\nBy validation status:")
            for vs, count in stats['validation_statuses'].items():
                print(f"  {vs}: {count}")

    elif args.sync:
        from extractor import load_extraction

        print(f"Loading extraction from {args.sync}...")
        extraction = load_extraction(args.sync)

        print(f"Syncing {extraction.ticker} {extraction.filing_type.value} to '{args.spreadsheet}'...")
        result = sync_extraction(extraction, args.spreadsheet)

        print(f"\n✓ {result['action'].capitalize()} row {result['row_number']}")
        print(f"  Spreadsheet: {result['spreadsheet_url']}")

    else:
        parser.print_help()
