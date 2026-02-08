"""
SEC EDGAR API integration for fetching company filings.

This module handles all interactions with the SEC EDGAR system, including:
- Looking up company CIK numbers from ticker symbols
- Listing available filings for a company
- Downloading filing documents (HTML preferred, PDF fallback)
- Fetching XBRL data for validation

SEC EDGAR API requires a User-Agent header with contact information.
Rate limit: 10 requests per second.
"""

import httpx
import json
import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from utils import get_env, TMP_DIR

# SEC EDGAR endpoints
SEC_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Required by SEC - include your email for contact
USER_AGENT = "DocumentIntelligence research@example.com"

# Rate limiting: SEC allows 10 requests/second
REQUEST_DELAY = 0.1  # 100ms between requests
_last_request_time = 0.0


def _rate_limit():
    """Ensure we don't exceed SEC rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _get_headers() -> Dict[str, str]:
    """Get headers required for SEC requests."""
    return {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


def get_company_cik(ticker: str) -> str:
    """
    Get the CIK (Central Index Key) for a ticker symbol.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")

    Returns:
        CIK number as a zero-padded 10-digit string

    Raises:
        ValueError: If ticker not found
    """
    _rate_limit()

    with httpx.Client() as client:
        response = client.get(COMPANY_TICKERS_URL, headers=_get_headers())
        response.raise_for_status()
        data = response.json()

    # Data is indexed by number, search for ticker
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker") == ticker_upper:
            # CIK needs to be zero-padded to 10 digits
            cik = str(entry["cik_str"]).zfill(10)
            return cik

    raise ValueError(f"Ticker '{ticker}' not found in SEC database")


def get_company_info(ticker: str) -> Dict[str, Any]:
    """
    Get company information including name and CIK.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with 'cik', 'name', 'ticker' keys
    """
    _rate_limit()

    with httpx.Client() as client:
        response = client.get(COMPANY_TICKERS_URL, headers=_get_headers())
        response.raise_for_status()
        data = response.json()

    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker") == ticker_upper:
            return {
                "cik": str(entry["cik_str"]).zfill(10),
                "name": entry.get("title", ""),
                "ticker": ticker_upper,
            }

    raise ValueError(f"Ticker '{ticker}' not found in SEC database")


def list_filings(
    ticker: str,
    filing_type: str = "10-K",
    count: int = 10
) -> List[Dict[str, Any]]:
    """
    List available filings for a company.

    Args:
        ticker: Stock ticker symbol
        filing_type: Type of filing ("10-K", "10-Q", "8-K")
        count: Maximum number of filings to return

    Returns:
        List of filing metadata dicts with keys:
        - accession_number: SEC accession number
        - filing_date: Date filed (YYYY-MM-DD)
        - form: Filing form type
        - primary_document: Main document filename
        - report_date: Period end date
    """
    cik = get_company_cik(ticker)
    _rate_limit()

    # Fetch company submissions
    submissions_url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"

    with httpx.Client() as client:
        response = client.get(submissions_url, headers=_get_headers())
        response.raise_for_status()
        data = response.json()

    filings = []
    recent = data.get("filings", {}).get("recent", {})

    # Parallel arrays in the response
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_documents = recent.get("primaryDocument", [])
    report_dates = recent.get("reportDate", [])

    for i in range(len(forms)):
        if forms[i] == filing_type:
            filings.append({
                "accession_number": accession_numbers[i],
                "filing_date": filing_dates[i],
                "form": forms[i],
                "primary_document": primary_documents[i],
                "report_date": report_dates[i] if i < len(report_dates) else None,
            })

            if len(filings) >= count:
                break

    return filings


def download_filing(
    ticker: str,
    accession_number: str,
    prefer_html: bool = True
) -> Path:
    """
    Download a filing document to .tmp/raw/.

    Args:
        ticker: Stock ticker symbol
        accession_number: SEC accession number
        prefer_html: If True, prefer HTML over PDF

    Returns:
        Path to downloaded file

    Raises:
        httpx.HTTPError: If download fails
    """
    cik = get_company_cik(ticker)
    # Strip leading zeros for archive URLs
    cik_stripped = cik.lstrip('0') or '0'
    _rate_limit()

    # Clean accession number (remove dashes for URL)
    accession_clean = accession_number.replace("-", "")

    # First, get the filing index to find documents
    index_url = f"{SEC_ARCHIVES_URL}/{cik_stripped}/{accession_clean}/index.json"

    with httpx.Client(follow_redirects=True) as client:
        response = client.get(index_url, headers=_get_headers())
        response.raise_for_status()
        index_data = response.json()

    # Find the primary document
    # Strategy: Find largest .htm file that isn't an exhibit or index
    primary_doc = None
    html_docs = []
    pdf_doc = None

    for item in index_data.get("directory", {}).get("item", []):
        name = item.get("name", "")
        size = item.get("size", 0)
        # Convert size to int, handle missing/invalid values
        try:
            size = int(size) if size else 0
        except (ValueError, TypeError):
            size = 0

        name_lower = name.lower()
        if name_lower.endswith(".htm") or name_lower.endswith(".html"):
            # Skip exhibits, index files, and R*.htm files (XBRL reports)
            # Exhibit patterns: starts with "ex", contains "-ex", contains "_ex", contains "exhibit"
            is_exhibit = (
                "exhibit" in name_lower or
                name_lower.startswith("ex") or
                "-ex" in name_lower or
                "_ex" in name_lower
            )
            is_index = "index" in name_lower
            is_xbrl_report = re.match(r'^r\d+\.htm', name_lower)

            if not is_exhibit and not is_index and not is_xbrl_report:
                html_docs.append((name, size))

                # Check if it matches ticker pattern (e.g., aapl-20250927.htm)
                # Only set primary_doc if not already set (first match wins)
                ticker_lower = ticker.lower()
                if ticker_lower in name_lower and primary_doc is None:
                    primary_doc = name

        elif name_lower.endswith(".pdf"):
            pdf_doc = name

    # If no primary doc found by ticker, use largest HTML file
    if not primary_doc and html_docs:
        html_docs.sort(key=lambda x: x[1], reverse=True)  # Sort by size, largest first
        primary_doc = html_docs[0][0]

    # Select document to download
    if prefer_html and primary_doc:
        doc_name = primary_doc
    elif pdf_doc:
        doc_name = pdf_doc
    elif html_docs:
        doc_name = html_docs[0][0]
    else:
        raise ValueError(f"No suitable document found for {accession_number}")

    # Download the document
    _rate_limit()
    doc_url = f"{SEC_ARCHIVES_URL}/{cik_stripped}/{accession_clean}/{doc_name}"

    with httpx.Client(follow_redirects=True) as client:
        response = client.get(doc_url, headers=_get_headers())
        response.raise_for_status()
        content = response.content

    # Save to .tmp/raw/
    raw_dir = TMP_DIR / "raw"
    raw_dir.mkdir(exist_ok=True)

    # Create filename: {ticker}_{form}_{date}_{ext}
    filings = list_filings(ticker, count=50)
    filing_info = next((f for f in filings if f["accession_number"] == accession_number), None)

    if filing_info:
        filing_date = filing_info["filing_date"]
        form_type = filing_info["form"].replace("-", "")
    else:
        filing_date = datetime.now().strftime("%Y-%m-%d")
        form_type = "unknown"

    ext = Path(doc_name).suffix
    filename = f"{ticker.upper()}_{form_type}_{filing_date}{ext}"
    file_path = raw_dir / filename

    file_path.write_bytes(content)
    return file_path


def fetch_xbrl_facts(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch XBRL company facts for validation.

    XBRL provides standardized financial data that can be used to
    validate extracted values.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict of XBRL facts or None if not available
    """
    try:
        cik = get_company_cik(ticker)
        _rate_limit()

        facts_url = f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"

        with httpx.Client() as client:
            response = client.get(facts_url, headers=_get_headers())
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def get_filing_url(ticker: str, accession_number: str, document_name: str) -> str:
    """
    Construct the URL for a specific filing document.

    Args:
        ticker: Stock ticker symbol
        accession_number: SEC accession number
        document_name: Name of the document file

    Returns:
        Full URL to the document
    """
    cik = get_company_cik(ticker)
    accession_clean = accession_number.replace("-", "")
    return f"{SEC_ARCHIVES_URL}/{cik}/{accession_clean}/{document_name}"


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch SEC filings")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--type", default="10-K", help="Filing type (default: 10-K)")
    parser.add_argument("--list", action="store_true", help="List available filings")
    parser.add_argument("--download", action="store_true", help="Download most recent filing")
    parser.add_argument("--accession", help="Specific accession number to download")

    args = parser.parse_args()

    if args.list:
        print(f"\nFetching {args.type} filings for {args.ticker}...")
        filings = list_filings(args.ticker, args.type)
        for f in filings:
            print(f"  {f['filing_date']} - {f['accession_number']}")

    if args.download or args.accession:
        if args.accession:
            accession = args.accession
        else:
            filings = list_filings(args.ticker, args.type, count=1)
            if not filings:
                print(f"No {args.type} filings found for {args.ticker}")
                exit(1)
            accession = filings[0]["accession_number"]

        print(f"\nDownloading {accession}...")
        path = download_filing(args.ticker, accession)
        print(f"Saved to: {path}")
