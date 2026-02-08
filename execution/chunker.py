"""
Semantic chunking for SEC filings.

This module splits parsed SEC filings into chunks suitable for embedding
and vector storage. Chunking is done semantically by:
1. Respecting section boundaries (Item 1, Item 1A, etc.)
2. Splitting on paragraph breaks within sections
3. Maintaining overlap between chunks for context continuity
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from utils import TMP_DIR
from schemas import DocumentChunk


# Default chunking parameters
DEFAULT_CHUNK_SIZE = 1500  # Target characters per chunk
DEFAULT_CHUNK_OVERLAP = 200  # Overlap between chunks
MIN_CHUNK_SIZE = 100  # Minimum chunk size to keep


@dataclass
class ChunkingConfig:
    """Configuration for chunking behavior."""
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    min_chunk_size: int = MIN_CHUNK_SIZE
    respect_sections: bool = True  # Don't merge chunks across sections
    include_tables: bool = True  # Include table text in chunks


def split_into_paragraphs(text: str) -> List[str]:
    """
    Split text into paragraphs on double newlines.

    Args:
        text: Input text

    Returns:
        List of paragraph strings
    """
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r'\n\s*\n', text)
    # Filter empty paragraphs
    return [p.strip() for p in paragraphs if p.strip()]


def merge_small_paragraphs(
    paragraphs: List[str],
    target_size: int,
    min_size: int
) -> List[str]:
    """
    Merge small paragraphs to approach target chunk size.

    Args:
        paragraphs: List of paragraphs
        target_size: Target characters per chunk
        min_size: Minimum size for standalone chunk

    Returns:
        List of merged text chunks
    """
    if not paragraphs:
        return []

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para)

        # If adding this paragraph exceeds target and we have content, save current
        if current_size + para_size > target_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = []
            current_size = 0

        current_chunk.append(para)
        current_size += para_size

    # Don't forget the last chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def add_overlap(
    chunks: List[str],
    overlap_size: int
) -> List[str]:
    """
    Add overlap between consecutive chunks for context continuity.

    Args:
        chunks: List of text chunks
        overlap_size: Number of characters to overlap

    Returns:
        List of chunks with overlap added
    """
    if len(chunks) <= 1 or overlap_size <= 0:
        return chunks

    overlapped_chunks = []

    for i, chunk in enumerate(chunks):
        if i == 0:
            # First chunk: add end of chunk to beginning of next
            overlapped_chunks.append(chunk)
        else:
            # Get overlap from previous chunk
            prev_chunk = chunks[i - 1]
            overlap_text = prev_chunk[-overlap_size:] if len(prev_chunk) > overlap_size else prev_chunk

            # Find a clean break point (space or newline)
            for j in range(len(overlap_text)):
                if overlap_text[j] in ' \n':
                    overlap_text = overlap_text[j + 1:]
                    break

            overlapped_chunks.append(f"...{overlap_text}\n\n{chunk}")

    return overlapped_chunks


def split_large_text(text: str, max_size: int) -> List[str]:
    """
    Split large text into smaller chunks by sentences or hard limit.

    Args:
        text: Text to split
        max_size: Maximum characters per chunk

    Returns:
        List of text chunks
    """
    if len(text) <= max_size:
        return [text]

    chunks = []
    current_chunk = ""

    # Try to split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_size:
            current_chunk = f"{current_chunk} {sentence}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If single sentence is too long, split by hard limit
            if len(sentence) > max_size:
                for i in range(0, len(sentence), max_size - 100):
                    chunks.append(sentence[i:i + max_size - 100])
                current_chunk = ""
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def chunk_section(
    section_text: str,
    section_name: str,
    config: ChunkingConfig
) -> List[Dict]:
    """
    Chunk a single section of a filing.

    Args:
        section_text: Text content of the section
        section_name: Name of the section (e.g., "item_1a")
        config: Chunking configuration

    Returns:
        List of chunk dicts with 'text', 'section', 'index' keys
    """
    paragraphs = split_into_paragraphs(section_text)

    if not paragraphs:
        return []

    # If paragraphs are too large (no proper paragraph breaks), split them further
    split_paragraphs = []
    for para in paragraphs:
        if len(para) > config.chunk_size * 2:
            # This paragraph is too large, split it
            split_paragraphs.extend(split_large_text(para, config.chunk_size))
        else:
            split_paragraphs.append(para)
    paragraphs = split_paragraphs

    # Merge paragraphs into target-sized chunks
    chunks = merge_small_paragraphs(
        paragraphs,
        config.chunk_size,
        config.min_chunk_size
    )

    # Add overlap
    chunks = add_overlap(chunks, config.chunk_overlap)

    # Filter out chunks that are too small
    chunks = [c for c in chunks if len(c) >= config.min_chunk_size]

    # Create chunk dicts with metadata
    result = []
    char_offset = 0

    for i, chunk_text in enumerate(chunks):
        result.append({
            'text': chunk_text,
            'section': section_name,
            'index': i,
            'char_start': char_offset,
            'char_end': char_offset + len(chunk_text),
        })
        char_offset += len(chunk_text)

    return result


def chunk_document(
    parsed_filing: Dict,
    config: Optional[ChunkingConfig] = None
) -> List[DocumentChunk]:
    """
    Chunk a parsed SEC filing into DocumentChunk objects.

    Args:
        parsed_filing: Dict from parse_filing() or loaded JSON
        config: Optional chunking configuration

    Returns:
        List of DocumentChunk objects ready for embedding
    """
    if config is None:
        config = ChunkingConfig()

    ticker = parsed_filing['ticker']
    filing_type = parsed_filing['filing_type']
    filing_date = parsed_filing['filing_date']

    all_chunks = []
    sections = parsed_filing.get('sections', {})

    # Process each section
    for section_name, section_data in sections.items():
        if isinstance(section_data, dict):
            section_text = section_data.get('text', '')
        else:
            section_text = str(section_data)

        if not section_text or len(section_text) < config.min_chunk_size:
            continue

        section_chunks = chunk_section(section_text, section_name, config)

        for chunk_data in section_chunks:
            chunk_id = f"{ticker}_{filing_type}_{filing_date}_{section_name}_{chunk_data['index']}"

            doc_chunk = DocumentChunk(
                id=chunk_id,
                text=chunk_data['text'],
                ticker=ticker,
                filing_type=filing_type,
                filing_date=filing_date,
                section=section_name,
                chunk_index=chunk_data['index'],
                char_start=chunk_data['char_start'],
                char_end=chunk_data['char_end'],
            )
            all_chunks.append(doc_chunk)

    return all_chunks


def save_chunks(
    chunks: List[DocumentChunk],
    ticker: str,
    filing_type: str,
    filing_date: str
) -> Path:
    """
    Save chunks to JSON in .tmp/chunks/.

    Args:
        chunks: List of DocumentChunk objects
        ticker: Company ticker
        filing_type: Filing type
        filing_date: Filing date

    Returns:
        Path to saved JSON file
    """
    chunks_dir = TMP_DIR / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    filename = f"{ticker}_{filing_type}_{filing_date}_chunks.json"
    output_path = chunks_dir / filename

    # Convert to serializable list
    data = [
        {
            'id': chunk.id,
            'text': chunk.text,
            'ticker': chunk.ticker,
            'filing_type': chunk.filing_type,
            'filing_date': chunk.filing_date,
            'section': chunk.section,
            'chunk_index': chunk.chunk_index,
            'char_start': chunk.char_start,
            'char_end': chunk.char_end,
        }
        for chunk in chunks
    ]

    output_path.write_text(json.dumps(data, indent=2))
    return output_path


def load_chunks(file_path: Path) -> List[DocumentChunk]:
    """
    Load chunks from a JSON file.

    Args:
        file_path: Path to chunks JSON file

    Returns:
        List of DocumentChunk objects
    """
    data = json.loads(file_path.read_text())

    return [
        DocumentChunk(**chunk_data)
        for chunk_data in data
    ]


def get_chunk_stats(chunks: List[DocumentChunk]) -> Dict:
    """
    Get statistics about a set of chunks.

    Args:
        chunks: List of DocumentChunk objects

    Returns:
        Dict with statistics
    """
    if not chunks:
        return {'count': 0}

    sizes = [len(c.text) for c in chunks]
    sections = set(c.section for c in chunks)
    section_counts = {}
    for c in chunks:
        section_counts[c.section] = section_counts.get(c.section, 0) + 1

    return {
        'count': len(chunks),
        'total_chars': sum(sizes),
        'avg_size': sum(sizes) / len(sizes),
        'min_size': min(sizes),
        'max_size': max(sizes),
        'sections': list(sections),
        'section_counts': section_counts,
    }


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chunk parsed SEC filings")
    parser.add_argument("file", help="Path to parsed filing JSON")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"Target chunk size (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=DEFAULT_CHUNK_OVERLAP,
                        help=f"Chunk overlap (default: {DEFAULT_CHUNK_OVERLAP})")
    parser.add_argument("--save", action="store_true", help="Save chunks to .tmp/chunks/")

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        exit(1)

    print(f"Loading parsed filing from {file_path}...")
    parsed = json.loads(file_path.read_text())

    config = ChunkingConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.overlap,
    )

    print(f"Chunking with size={config.chunk_size}, overlap={config.chunk_overlap}...")
    chunks = chunk_document(parsed, config)

    stats = get_chunk_stats(chunks)
    print(f"\nChunk Statistics:")
    print(f"  Total chunks: {stats['count']}")
    print(f"  Total characters: {stats['total_chars']:,}")
    print(f"  Average size: {stats['avg_size']:.0f} chars")
    print(f"  Size range: {stats['min_size']} - {stats['max_size']} chars")
    print(f"\nChunks by section:")
    for section, count in stats['section_counts'].items():
        print(f"  {section}: {count} chunks")

    if args.save:
        output_path = save_chunks(
            chunks,
            parsed['ticker'],
            parsed['filing_type'],
            parsed['filing_date']
        )
        print(f"\nSaved to: {output_path}")
