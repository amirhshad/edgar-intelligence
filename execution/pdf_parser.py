"""
Document parsing for SEC filings.

This module handles parsing of HTML and PDF documents into structured text,
preserving section boundaries for semantic chunking.

HTML parsing is preferred as SEC filings have well-structured HTML.
PDF parsing with OCR is available as a fallback.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, NavigableString
import json

from utils import TMP_DIR


# SEC 10-K/10-Q section patterns
SEC_SECTIONS = {
    "item_1": r"(?:ITEM\s*1\.?\s*[-–—]?\s*BUSINESS)",
    "item_1a": r"(?:ITEM\s*1A\.?\s*[-–—]?\s*RISK\s*FACTORS)",
    "item_1b": r"(?:ITEM\s*1B\.?\s*[-–—]?\s*UNRESOLVED\s*STAFF\s*COMMENTS)",
    "item_2": r"(?:ITEM\s*2\.?\s*[-–—]?\s*PROPERTIES)",
    "item_3": r"(?:ITEM\s*3\.?\s*[-–—]?\s*LEGAL\s*PROCEEDINGS)",
    "item_4": r"(?:ITEM\s*4\.?\s*[-–—]?\s*MINE\s*SAFETY)",
    "item_5": r"(?:ITEM\s*5\.?\s*[-–—]?\s*MARKET\s*FOR)",
    "item_6": r"(?:ITEM\s*6\.?\s*[-–—]?\s*(?:RESERVED|\[RESERVED\]|SELECTED\s*FINANCIAL))",
    "item_7": r"(?:ITEM\s*7\.?\s*[-–—]?\s*MANAGEMENT.?S?\s*DISCUSSION)",
    "item_7a": r"(?:ITEM\s*7A\.?\s*[-–—]?\s*QUANTITATIVE)",
    "item_8": r"(?:ITEM\s*8\.?\s*[-–—]?\s*FINANCIAL\s*STATEMENTS)",
    "item_9": r"(?:ITEM\s*9\.?\s*[-–—]?\s*CHANGES\s*IN)",
    "item_9a": r"(?:ITEM\s*9A\.?\s*[-–—]?\s*CONTROLS)",
    "item_9b": r"(?:ITEM\s*9B\.?\s*[-–—]?\s*OTHER\s*INFORMATION)",
    "item_10": r"(?:ITEM\s*10\.?\s*[-–—]?\s*DIRECTORS)",
    "item_11": r"(?:ITEM\s*11\.?\s*[-–—]?\s*EXECUTIVE\s*COMPENSATION)",
    "item_12": r"(?:ITEM\s*12\.?\s*[-–—]?\s*SECURITY\s*OWNERSHIP)",
    "item_13": r"(?:ITEM\s*13\.?\s*[-–—]?\s*CERTAIN\s*RELATIONSHIPS)",
    "item_14": r"(?:ITEM\s*14\.?\s*[-–—]?\s*PRINCIPAL\s*ACCOUNT)",
    "item_15": r"(?:ITEM\s*15\.?\s*[-–—]?\s*EXHIBITS)",
}


@dataclass
class ParsedSection:
    """A parsed section from an SEC filing."""
    name: str  # e.g., "item_1a"
    title: str  # e.g., "ITEM 1A. RISK FACTORS"
    text: str  # Full text content
    tables: List[str] = field(default_factory=list)  # Extracted tables as text
    char_start: int = 0
    char_end: int = 0


@dataclass
class ParsedFiling:
    """Complete parsed SEC filing."""
    ticker: str
    filing_type: str
    filing_date: str
    source_path: str
    sections: Dict[str, ParsedSection]
    full_text: str
    tables: List[Dict]  # All tables with metadata


def clean_text(text: str) -> str:
    """
    Clean extracted text while preserving meaningful whitespace.
    """
    # Replace multiple spaces/tabs with single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Replace multiple newlines with double newline (paragraph break)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # Remove leading/trailing whitespace from lines
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_tables_from_soup(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract tables from HTML and convert to structured format.

    Args:
        soup: BeautifulSoup object

    Returns:
        List of table dicts with 'headers', 'rows', 'text' keys
    """
    tables = []

    for table_elem in soup.find_all('table'):
        try:
            rows = []
            headers = []

            # Try to find header row
            header_row = table_elem.find('thead')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

            # Process all rows
            for tr in table_elem.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells:
                    # If no headers yet and this looks like a header row
                    if not headers and all(c.isupper() or not c for c in cells[:3]):
                        headers = cells
                    else:
                        rows.append(cells)

            if rows:
                # Convert to text representation
                text_lines = []
                if headers:
                    text_lines.append(' | '.join(headers))
                    text_lines.append('-' * 50)
                for row in rows:
                    text_lines.append(' | '.join(str(c) for c in row))

                tables.append({
                    'headers': headers,
                    'rows': rows,
                    'text': '\n'.join(text_lines)
                })
        except Exception:
            continue

    return tables


def parse_html_filing(file_path: Path) -> ParsedFiling:
    """
    Parse an HTML SEC filing into structured sections.

    Args:
        file_path: Path to HTML file

    Returns:
        ParsedFiling object with sections and full text
    """
    content = file_path.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(content, 'lxml')

    # Remove script and style elements
    for element in soup(['script', 'style', 'meta', 'link']):
        element.decompose()

    # Extract all tables first
    tables = extract_tables_from_soup(soup)

    # Get full text
    full_text = soup.get_text(separator='\n')
    full_text = clean_text(full_text)

    # Parse filename for metadata
    # Expected format: {TICKER}_{FORM}_{DATE}.htm
    filename = file_path.stem
    parts = filename.split('_')
    ticker = parts[0] if parts else "UNKNOWN"
    filing_type = parts[1] if len(parts) > 1 else "UNKNOWN"
    filing_date = parts[2] if len(parts) > 2 else "UNKNOWN"

    # Find sections
    sections = {}
    section_positions = []

    for section_name, pattern in SEC_SECTIONS.items():
        matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
        for match in matches:
            section_positions.append({
                'name': section_name,
                'title': match.group(0),
                'start': match.start(),
            })

    # Sort by position
    section_positions.sort(key=lambda x: x['start'])

    # Extract section text (from one section header to the next)
    for i, section_info in enumerate(section_positions):
        start = section_info['start']
        if i + 1 < len(section_positions):
            end = section_positions[i + 1]['start']
        else:
            end = len(full_text)

        section_text = full_text[start:end]

        sections[section_info['name']] = ParsedSection(
            name=section_info['name'],
            title=section_info['title'],
            text=clean_text(section_text),
            char_start=start,
            char_end=end,
        )

    return ParsedFiling(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date,
        source_path=str(file_path),
        sections=sections,
        full_text=full_text,
        tables=tables,
    )


def parse_pdf_filing(file_path: Path) -> ParsedFiling:
    """
    Parse a PDF SEC filing using PyMuPDF.

    This is a fallback for when HTML is not available.

    Args:
        file_path: Path to PDF file

    Returns:
        ParsedFiling object
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF parsing. Install with: pip install pymupdf")

    doc = fitz.open(file_path)

    # Extract text from all pages
    full_text_parts = []
    tables = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        full_text_parts.append(text)

        # Try to extract tables
        try:
            page_tables = page.find_tables()
            for table in page_tables:
                table_data = table.extract()
                if table_data:
                    tables.append({
                        'headers': table_data[0] if table_data else [],
                        'rows': table_data[1:] if len(table_data) > 1 else [],
                        'text': '\n'.join(' | '.join(str(c) for c in row) for row in table_data),
                        'page': page_num + 1,
                    })
        except Exception:
            pass

    doc.close()

    full_text = '\n\n'.join(full_text_parts)
    full_text = clean_text(full_text)

    # Parse filename for metadata
    filename = file_path.stem
    parts = filename.split('_')
    ticker = parts[0] if parts else "UNKNOWN"
    filing_type = parts[1] if len(parts) > 1 else "UNKNOWN"
    filing_date = parts[2] if len(parts) > 2 else "UNKNOWN"

    # Find sections (same as HTML)
    sections = {}
    section_positions = []

    for section_name, pattern in SEC_SECTIONS.items():
        matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
        for match in matches:
            section_positions.append({
                'name': section_name,
                'title': match.group(0),
                'start': match.start(),
            })

    section_positions.sort(key=lambda x: x['start'])

    for i, section_info in enumerate(section_positions):
        start = section_info['start']
        if i + 1 < len(section_positions):
            end = section_positions[i + 1]['start']
        else:
            end = len(full_text)

        section_text = full_text[start:end]

        sections[section_info['name']] = ParsedSection(
            name=section_info['name'],
            title=section_info['title'],
            text=clean_text(section_text),
            char_start=start,
            char_end=end,
        )

    return ParsedFiling(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date,
        source_path=str(file_path),
        sections=sections,
        full_text=full_text,
        tables=tables,
    )


def parse_filing(file_path: Path) -> ParsedFiling:
    """
    Parse an SEC filing, automatically detecting file type.

    Args:
        file_path: Path to filing document

    Returns:
        ParsedFiling object
    """
    suffix = file_path.suffix.lower()

    if suffix in ['.htm', '.html']:
        return parse_html_filing(file_path)
    elif suffix == '.pdf':
        return parse_pdf_filing(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def save_parsed_filing(parsed: ParsedFiling) -> Path:
    """
    Save parsed filing to JSON in .tmp/parsed/.

    Args:
        parsed: ParsedFiling object

    Returns:
        Path to saved JSON file
    """
    parsed_dir = TMP_DIR / "parsed"
    parsed_dir.mkdir(exist_ok=True)

    filename = f"{parsed.ticker}_{parsed.filing_type}_{parsed.filing_date}.json"
    output_path = parsed_dir / filename

    # Convert to serializable dict
    data = {
        'ticker': parsed.ticker,
        'filing_type': parsed.filing_type,
        'filing_date': parsed.filing_date,
        'source_path': parsed.source_path,
        'sections': {
            name: {
                'name': section.name,
                'title': section.title,
                'text': section.text,
                'char_start': section.char_start,
                'char_end': section.char_end,
            }
            for name, section in parsed.sections.items()
        },
        'full_text_length': len(parsed.full_text),
        'table_count': len(parsed.tables),
        'tables': parsed.tables,
    }

    output_path.write_text(json.dumps(data, indent=2))
    return output_path


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse SEC filing documents")
    parser.add_argument("file", help="Path to filing document (HTML or PDF)")
    parser.add_argument("--save", action="store_true", help="Save parsed output to .tmp/parsed/")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        exit(1)

    print(f"Parsing {file_path}...")
    parsed = parse_filing(file_path)

    print(f"\nTicker: {parsed.ticker}")
    print(f"Filing Type: {parsed.filing_type}")
    print(f"Filing Date: {parsed.filing_date}")
    print(f"Full Text Length: {len(parsed.full_text):,} characters")
    print(f"Tables Found: {len(parsed.tables)}")
    print(f"\nSections Found ({len(parsed.sections)}):")
    for name, section in parsed.sections.items():
        print(f"  {name}: {len(section.text):,} chars - {section.title[:50]}...")

    if args.save:
        output_path = save_parsed_filing(parsed)
        print(f"\nSaved to: {output_path}")
