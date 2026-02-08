"""
OpenAI embeddings for SEC filing chunks.

This module handles text embedding generation using OpenAI's text-embedding models.
Supports batching for efficiency and caching to reduce API costs.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Dict
from openai import OpenAI

from utils import get_env, TMP_DIR

# Default embedding model - good balance of cost and quality for financial text
DEFAULT_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # Dimensions for text-embedding-3-small

# Batch limits
MAX_BATCH_SIZE = 100  # OpenAI recommends batches of 100 or fewer
MAX_TOKENS_PER_BATCH = 8191  # Token limit per request

# Simple file-based cache
CACHE_DIR = TMP_DIR / "embedding_cache"


def _get_client() -> OpenAI:
    """Get OpenAI client with API key from environment."""
    return OpenAI(api_key=get_env("OPENAI_API_KEY"))


def _get_cache_key(text: str, model: str) -> str:
    """Generate cache key for text+model combination."""
    content = f"{model}:{text}"
    return hashlib.sha256(content.encode()).hexdigest()


def _load_from_cache(cache_key: str) -> Optional[List[float]]:
    """Load embedding from cache if exists."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            return data.get("embedding")
        except Exception:
            return None

    return None


def _save_to_cache(cache_key: str, embedding: List[float]):
    """Save embedding to cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    data = {
        "embedding": embedding,
        "cached_at": time.time(),
    }
    cache_file.write_text(json.dumps(data))


def embed_single(
    text: str,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True
) -> List[float]:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed
        model: OpenAI embedding model to use
        use_cache: Whether to use file-based caching

    Returns:
        List of embedding floats
    """
    # Check cache first
    if use_cache:
        cache_key = _get_cache_key(text, model)
        cached = _load_from_cache(cache_key)
        if cached is not None:
            return cached

    # Generate embedding
    client = _get_client()

    response = client.embeddings.create(
        input=text,
        model=model,
    )

    embedding = response.data[0].embedding

    # Cache the result
    if use_cache:
        _save_to_cache(cache_key, embedding)

    return embedding


def embed_texts(
    texts: List[str],
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    show_progress: bool = False
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts with batching.

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model to use
        use_cache: Whether to use file-based caching
        show_progress: Whether to print progress

    Returns:
        List of embedding vectors (same order as input texts)
    """
    if not texts:
        return []

    client = _get_client()
    embeddings = [None] * len(texts)
    texts_to_embed = []
    indices_to_embed = []

    # Check cache for each text
    for i, text in enumerate(texts):
        if use_cache:
            cache_key = _get_cache_key(text, model)
            cached = _load_from_cache(cache_key)
            if cached is not None:
                embeddings[i] = cached
                continue

        texts_to_embed.append(text)
        indices_to_embed.append(i)

    if show_progress:
        print(f"Found {len(texts) - len(texts_to_embed)} cached embeddings")
        print(f"Generating {len(texts_to_embed)} new embeddings...")

    # Batch embed uncached texts
    for batch_start in range(0, len(texts_to_embed), MAX_BATCH_SIZE):
        batch_end = min(batch_start + MAX_BATCH_SIZE, len(texts_to_embed))
        batch_texts = texts_to_embed[batch_start:batch_end]
        batch_indices = indices_to_embed[batch_start:batch_end]

        if show_progress:
            print(f"  Processing batch {batch_start // MAX_BATCH_SIZE + 1}...")

        response = client.embeddings.create(
            input=batch_texts,
            model=model,
        )

        # Map results back to original positions
        for j, embedding_data in enumerate(response.data):
            original_index = batch_indices[j]
            embedding = embedding_data.embedding
            embeddings[original_index] = embedding

            # Cache the result
            if use_cache:
                cache_key = _get_cache_key(batch_texts[j], model)
                _save_to_cache(cache_key, embedding)

    return embeddings


def embed_chunks(
    chunks: List[Dict],
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    show_progress: bool = False
) -> List[Dict]:
    """
    Add embeddings to a list of chunk dicts.

    Args:
        chunks: List of chunk dicts with 'text' key
        model: OpenAI embedding model to use
        use_cache: Whether to use caching
        show_progress: Whether to print progress

    Returns:
        Same chunks with 'embedding' key added
    """
    texts = [chunk['text'] for chunk in chunks]
    embeddings = embed_texts(texts, model, use_cache, show_progress)

    for i, chunk in enumerate(chunks):
        chunk['embedding'] = embeddings[i]

    return chunks


def get_embedding_stats(embeddings: List[List[float]]) -> Dict:
    """
    Get statistics about a set of embeddings.

    Args:
        embeddings: List of embedding vectors

    Returns:
        Dict with statistics
    """
    if not embeddings:
        return {'count': 0}

    import math

    dimensions = len(embeddings[0]) if embeddings else 0

    # Calculate norms
    norms = []
    for emb in embeddings:
        norm = math.sqrt(sum(x * x for x in emb))
        norms.append(norm)

    return {
        'count': len(embeddings),
        'dimensions': dimensions,
        'avg_norm': sum(norms) / len(norms),
        'min_norm': min(norms),
        'max_norm': max(norms),
    }


def clear_cache():
    """Clear the embedding cache."""
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            cache_file.unlink()
        print(f"Cleared embedding cache")


def get_cache_stats() -> Dict:
    """Get statistics about the embedding cache."""
    if not CACHE_DIR.exists():
        return {'count': 0, 'size_bytes': 0}

    cache_files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in cache_files)

    return {
        'count': len(cache_files),
        'size_bytes': total_size,
        'size_mb': total_size / (1024 * 1024),
    }


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate embeddings for text")
    parser.add_argument("--text", help="Text to embed")
    parser.add_argument("--file", help="File with texts (one per line)")
    parser.add_argument("--chunks", help="Path to chunks JSON file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--clear-cache", action="store_true", help="Clear embedding cache")

    args = parser.parse_args()

    if args.cache_stats:
        stats = get_cache_stats()
        print(f"Cache statistics:")
        print(f"  Cached embeddings: {stats['count']}")
        print(f"  Cache size: {stats['size_mb']:.2f} MB")
        exit(0)

    if args.clear_cache:
        clear_cache()
        exit(0)

    if args.text:
        print(f"Embedding text with {args.model}...")
        embedding = embed_single(args.text, args.model, not args.no_cache)
        print(f"Embedding dimensions: {len(embedding)}")
        print(f"First 5 values: {embedding[:5]}")

    elif args.file:
        texts = Path(args.file).read_text().strip().split('\n')
        print(f"Embedding {len(texts)} texts with {args.model}...")
        embeddings = embed_texts(texts, args.model, not args.no_cache, show_progress=True)
        stats = get_embedding_stats(embeddings)
        print(f"\nEmbedding statistics:")
        print(f"  Count: {stats['count']}")
        print(f"  Dimensions: {stats['dimensions']}")
        print(f"  Avg norm: {stats['avg_norm']:.4f}")

    elif args.chunks:
        chunks_path = Path(args.chunks)
        chunks = json.loads(chunks_path.read_text())
        print(f"Embedding {len(chunks)} chunks with {args.model}...")
        embedded = embed_chunks(chunks, args.model, not args.no_cache, show_progress=True)

        # Save back
        output_path = chunks_path.with_suffix('.embedded.json')
        output_path.write_text(json.dumps(embedded, indent=2))
        print(f"Saved to: {output_path}")
