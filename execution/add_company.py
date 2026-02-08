#!/usr/bin/env python3
"""
Add a company's SEC filings to the EDGAR Intelligence system.

Usage:
    python add_company.py MSFT           # Add Microsoft's latest 10-K
    python add_company.py GOOGL 10-Q     # Add Google's latest 10-Q
    python add_company.py TSLA 10-K 3    # Add Tesla's last 3 10-Ks
"""

import sys
import json
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from sec_fetcher import list_filings, download_filing, get_company_info
from pdf_parser import parse_filing, save_parsed_filing
from chunker import chunk_document, save_chunks
from embeddings import embed_chunks
from vector_store import add_chunks, get_collection_stats


def add_company(ticker: str, filing_type: str = "10-K", count: int = 1):
    """
    Add a company's SEC filings to the vector database.

    Args:
        ticker: Stock ticker (e.g., "MSFT", "GOOGL")
        filing_type: Filing type ("10-K" or "10-Q")
        count: Number of filings to process
    """
    ticker = ticker.upper()

    print(f"\n{'='*60}")
    print(f"Adding {ticker} {filing_type} filing(s) to EDGAR Intelligence")
    print(f"{'='*60}\n")

    # Step 1: Verify company exists
    print(f"1. Verifying ticker {ticker}...")
    try:
        company_info = get_company_info(ticker)
        print(f"   Found: {company_info.get('name', ticker)}")
    except Exception as e:
        print(f"   Error: Could not find company with ticker {ticker}")
        print(f"   {e}")
        return False

    # Step 2: List available filings
    print(f"\n2. Finding {filing_type} filings...")
    try:
        filings = list_filings(ticker, filing_type, count=count)
        if not filings:
            print(f"   No {filing_type} filings found for {ticker}")
            return False
        print(f"   Found {len(filings)} filing(s)")
        for f in filings:
            print(f"   - {f['filing_date']}: {f['accession_number']}")
    except Exception as e:
        print(f"   Error listing filings: {e}")
        return False

    total_chunks = 0

    for filing in filings:
        accession = filing["accession_number"]
        filing_date = filing["filing_date"]
        print(f"\n{'─'*60}")
        print(f"Processing {ticker} {filing_type} ({filing_date})")
        print(f"{'─'*60}")

        # Step 3: Download filing
        print(f"\n3. Downloading filing...")
        try:
            file_path = download_filing(ticker, accession)
            print(f"   Saved to: {file_path}")
        except Exception as e:
            print(f"   Error downloading: {e}")
            continue

        # Step 4: Parse filing
        print(f"\n4. Parsing document...")
        try:
            parsed = parse_filing(file_path)
            save_parsed_filing(parsed)
            sections = list(parsed.sections.keys()) if hasattr(parsed, 'sections') else []
            print(f"   Sections found: {len(sections)}")
            for s in sections[:5]:
                print(f"   - {s}")
            if len(sections) > 5:
                print(f"   - ... and {len(sections) - 5} more")
        except Exception as e:
            print(f"   Error parsing: {e}")
            continue

        # Step 5: Chunk document
        print(f"\n5. Creating chunks...")
        try:
            chunks = chunk_document(parsed.__dict__ if hasattr(parsed, '__dict__') else parsed)
            print(f"   Created {len(chunks)} chunks")

            # Save chunks (expects DocumentChunk objects)
            chunks_path = save_chunks(chunks, ticker, filing_type.replace("-", ""), filing_date)
            print(f"   Saved to: {chunks_path}")

            # Convert to dict format for embeddings
            chunk_dicts = []
            for c in chunks:
                if hasattr(c, '__dict__'):
                    chunk_dicts.append(c.__dict__)
                elif hasattr(c, 'id'):
                    chunk_dicts.append({
                        'id': c.id, 'text': c.text, 'ticker': c.ticker,
                        'filing_type': c.filing_type, 'filing_date': c.filing_date,
                        'section': c.section, 'chunk_index': c.chunk_index,
                        'char_start': c.char_start, 'char_end': c.char_end,
                    })
                else:
                    chunk_dicts.append(c)
        except Exception as e:
            print(f"   Error chunking: {e}")
            continue

        # Step 6: Generate embeddings
        print(f"\n6. Generating embeddings...")
        try:
            embedded_chunks = embed_chunks(chunk_dicts, show_progress=True)

            # Save embedded chunks
            embedded_path = Path(str(chunks_path).replace('.json', '.embedded.json'))
            embedded_path.write_text(json.dumps(embedded_chunks, indent=2))
            print(f"   Saved embeddings to: {embedded_path}")
        except Exception as e:
            print(f"   Error generating embeddings: {e}")
            continue

        # Step 7: Add to vector store
        print(f"\n7. Adding to vector database...")
        try:
            added = add_chunks(embedded_chunks)
            print(f"   Added {added} chunks to ChromaDB")
            total_chunks += added
        except Exception as e:
            print(f"   Error adding to vector store: {e}")
            continue

    # Final summary
    print(f"\n{'='*60}")
    print(f"COMPLETE: Added {total_chunks} chunks for {ticker}")
    print(f"{'='*60}")

    # Show updated stats
    stats = get_collection_stats()
    print(f"\nVector database now contains:")
    print(f"  - Total documents: {stats.get('count', 0)}")
    print(f"  - Tickers: {stats.get('sample_tickers', [])}")

    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCurrently indexed companies:")
        stats = get_collection_stats()
        print(f"  Tickers: {stats.get('sample_tickers', [])}")
        print(f"  Total chunks: {stats.get('count', 0)}")
        sys.exit(1)

    ticker = sys.argv[1]
    filing_type = sys.argv[2] if len(sys.argv) > 2 else "10-K"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    # Normalize filing type
    filing_type = filing_type.upper()
    if filing_type in ["10K", "10-K"]:
        filing_type = "10-K"
    elif filing_type in ["10Q", "10-Q"]:
        filing_type = "10-Q"

    success = add_company(ticker, filing_type, count)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
