"""
ChromaDB vector store operations for SEC filings.

This module handles all vector database operations using ChromaDB:
- Creating and managing collections
- Adding documents with embeddings
- Semantic search with metadata filtering
- Collection statistics and maintenance

ChromaDB is stored locally in .tmp/chroma/ for zero-infrastructure setup.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import chromadb
from chromadb.config import Settings

from utils import TMP_DIR

# ChromaDB storage location
CHROMA_PATH = TMP_DIR / "chroma"

# Default collection name
DEFAULT_COLLECTION = "sec_filings"


def get_client() -> chromadb.PersistentClient:
    """
    Get persistent ChromaDB client.

    Returns:
        ChromaDB client with persistent storage
    """
    CHROMA_PATH.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def get_or_create_collection(
    name: str = DEFAULT_COLLECTION,
    metadata: Optional[Dict] = None
) -> chromadb.Collection:
    """
    Get or create a ChromaDB collection.

    Args:
        name: Collection name
        metadata: Optional collection metadata

    Returns:
        ChromaDB collection
    """
    client = get_client()

    if metadata is None:
        metadata = {
            "description": "SEC filing chunks for RAG",
            "hnsw:space": "cosine",  # Use cosine similarity
        }

    return client.get_or_create_collection(
        name=name,
        metadata=metadata,
    )


def add_documents(
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str],
    embeddings: Optional[List[List[float]]] = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """
    Add documents to a collection.

    Args:
        documents: List of document texts
        metadatas: List of metadata dicts for each document
        ids: List of unique IDs for each document
        embeddings: Optional pre-computed embeddings
        collection_name: Target collection name

    Returns:
        Number of documents added
    """
    collection = get_or_create_collection(collection_name)

    # Check for existing documents to avoid duplicates
    existing = set()
    try:
        result = collection.get(ids=ids)
        existing = set(result['ids'])
    except Exception:
        pass

    # Filter out existing documents
    new_docs = []
    new_metas = []
    new_ids = []
    new_embeddings = []

    for i, doc_id in enumerate(ids):
        if doc_id not in existing:
            new_docs.append(documents[i])
            new_metas.append(metadatas[i])
            new_ids.append(doc_id)
            if embeddings:
                new_embeddings.append(embeddings[i])

    if not new_ids:
        return 0

    # Add to collection
    if new_embeddings:
        collection.add(
            documents=new_docs,
            metadatas=new_metas,
            ids=new_ids,
            embeddings=new_embeddings,
        )
    else:
        collection.add(
            documents=new_docs,
            metadatas=new_metas,
            ids=new_ids,
        )

    return len(new_ids)


def add_chunks(
    chunks: List[Dict],
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """
    Add document chunks to the vector store.

    Args:
        chunks: List of chunk dicts with 'id', 'text', 'embedding', and metadata
        collection_name: Target collection name

    Returns:
        Number of chunks added
    """
    documents = [c['text'] for c in chunks]
    ids = [c['id'] for c in chunks]

    # Extract metadata (everything except text, id, embedding)
    metadatas = []
    for chunk in chunks:
        meta = {k: v for k, v in chunk.items() if k not in ['text', 'id', 'embedding']}
        # ChromaDB requires string, int, float, or bool values
        meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in meta.items()}
        metadatas.append(meta)

    # Get embeddings if present
    embeddings = None
    if chunks and 'embedding' in chunks[0]:
        embeddings = [c['embedding'] for c in chunks]

    return add_documents(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
        embeddings=embeddings,
        collection_name=collection_name,
    )


def query(
    query_text: Optional[str] = None,
    query_embedding: Optional[List[float]] = None,
    n_results: int = 5,
    where: Optional[Dict] = None,
    where_document: Optional[Dict] = None,
    collection_name: str = DEFAULT_COLLECTION,
    include: Optional[List[str]] = None,
) -> Dict:
    """
    Query the vector store for similar documents.

    Args:
        query_text: Query text (will be embedded by ChromaDB)
        query_embedding: Pre-computed query embedding
        n_results: Number of results to return
        where: Metadata filter (e.g., {"ticker": "AAPL"})
        where_document: Document content filter
        collection_name: Collection to query
        include: What to include in results (default: documents, metadatas, distances)

    Returns:
        Dict with 'ids', 'documents', 'metadatas', 'distances' keys
    """
    collection = get_or_create_collection(collection_name)

    if include is None:
        include = ["documents", "metadatas", "distances"]

    kwargs = {
        "n_results": n_results,
        "include": include,
    }

    if query_embedding is not None:
        kwargs["query_embeddings"] = [query_embedding]
    elif query_text is not None:
        kwargs["query_texts"] = [query_text]
    else:
        raise ValueError("Either query_text or query_embedding must be provided")

    if where:
        kwargs["where"] = where
    if where_document:
        kwargs["where_document"] = where_document

    results = collection.query(**kwargs)

    # Flatten results (ChromaDB returns nested lists)
    return {
        'ids': results['ids'][0] if results['ids'] else [],
        'documents': results['documents'][0] if results.get('documents') else [],
        'metadatas': results['metadatas'][0] if results.get('metadatas') else [],
        'distances': results['distances'][0] if results.get('distances') else [],
    }


def delete_documents(
    ids: Optional[List[str]] = None,
    where: Optional[Dict] = None,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """
    Delete documents from collection.

    Args:
        ids: List of document IDs to delete
        where: Metadata filter for deletion
        collection_name: Target collection

    Returns:
        Approximate number of documents deleted
    """
    collection = get_or_create_collection(collection_name)

    # Get count before
    count_before = collection.count()

    if ids:
        collection.delete(ids=ids)
    elif where:
        collection.delete(where=where)
    else:
        raise ValueError("Either ids or where must be provided")

    # Get count after
    count_after = collection.count()

    return count_before - count_after


def get_collection_stats(collection_name: str = DEFAULT_COLLECTION) -> Dict:
    """
    Get statistics for a collection.

    Args:
        collection_name: Collection to query

    Returns:
        Dict with collection statistics
    """
    client = get_client()

    try:
        collection = client.get_collection(collection_name)
        count = collection.count()

        # Get sample to understand metadata
        sample = collection.peek(limit=10)
        metadata_keys = set()
        tickers = set()
        filing_types = set()

        for meta in sample.get('metadatas', []):
            if meta:
                metadata_keys.update(meta.keys())
                if 'ticker' in meta:
                    tickers.add(meta['ticker'])
                if 'filing_type' in meta:
                    filing_types.add(meta['filing_type'])

        return {
            'name': collection_name,
            'count': count,
            'metadata_keys': list(metadata_keys),
            'sample_tickers': list(tickers),
            'sample_filing_types': list(filing_types),
        }
    except Exception as e:
        return {
            'name': collection_name,
            'error': str(e),
        }


def list_collections() -> List[str]:
    """
    List all collections in the database.

    Returns:
        List of collection names
    """
    client = get_client()
    collections = client.list_collections()
    return [c.name for c in collections]


def delete_collection(collection_name: str) -> bool:
    """
    Delete an entire collection.

    Args:
        collection_name: Collection to delete

    Returns:
        True if deleted, False if not found
    """
    client = get_client()

    try:
        client.delete_collection(collection_name)
        return True
    except Exception:
        return False


def get_all_tickers(
    collection_name: str = DEFAULT_COLLECTION,
) -> List[Dict]:
    """
    Get all unique tickers in the collection with their document counts.

    Args:
        collection_name: Collection to query

    Returns:
        List of dicts with 'ticker', 'count', and optional 'company_name'
    """
    collection = get_or_create_collection(collection_name)

    # Get all documents with metadata
    total_count = collection.count()
    if total_count == 0:
        return []

    # Get all metadata to count tickers
    results = collection.get(
        limit=total_count,
        include=["metadatas"],
    )

    ticker_counts = {}
    ticker_names = {}

    for meta in results.get('metadatas', []):
        if meta and 'ticker' in meta:
            ticker = meta['ticker']
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
            if 'company_name' in meta and ticker not in ticker_names:
                ticker_names[ticker] = meta['company_name']

    return [
        {
            'ticker': ticker,
            'count': count,
            'company_name': ticker_names.get(ticker, ''),
        }
        for ticker, count in sorted(ticker_counts.items())
    ]


def get_documents_by_ticker(
    ticker: str,
    collection_name: str = DEFAULT_COLLECTION,
    limit: int = 100,
) -> List[Dict]:
    """
    Get all documents for a specific ticker.

    Args:
        ticker: Company ticker symbol
        collection_name: Collection to query
        limit: Maximum documents to return

    Returns:
        List of document dicts with 'id', 'document', 'metadata'
    """
    collection = get_or_create_collection(collection_name)

    results = collection.get(
        where={"ticker": ticker},
        limit=limit,
        include=["documents", "metadatas"],
    )

    documents = []
    for i, doc_id in enumerate(results['ids']):
        documents.append({
            'id': doc_id,
            'document': results['documents'][i] if results.get('documents') else None,
            'metadata': results['metadatas'][i] if results.get('metadatas') else None,
        })

    return documents


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vector store operations")
    parser.add_argument("--list", action="store_true", help="List all collections")
    parser.add_argument("--stats", nargs="?", const=DEFAULT_COLLECTION,
                        help="Show collection stats")
    parser.add_argument("--query", help="Query text")
    parser.add_argument("--ticker", help="Filter by ticker")
    parser.add_argument("--n", type=int, default=5, help="Number of results")
    parser.add_argument("--delete-collection", help="Delete a collection")
    parser.add_argument("--add-chunks", help="Add chunks from JSON file")

    args = parser.parse_args()

    if args.list:
        collections = list_collections()
        print(f"Collections ({len(collections)}):")
        for name in collections:
            stats = get_collection_stats(name)
            print(f"  {name}: {stats.get('count', 'N/A')} documents")

    elif args.stats:
        stats = get_collection_stats(args.stats)
        print(f"Collection: {stats['name']}")
        print(f"  Documents: {stats.get('count', 'N/A')}")
        print(f"  Metadata keys: {stats.get('metadata_keys', [])}")
        print(f"  Tickers: {stats.get('sample_tickers', [])}")
        print(f"  Filing types: {stats.get('sample_filing_types', [])}")

    elif args.query:
        where = {"ticker": args.ticker} if args.ticker else None
        results = query(
            query_text=args.query,
            n_results=args.n,
            where=where,
        )
        print(f"Found {len(results['ids'])} results:")
        for i, doc_id in enumerate(results['ids']):
            print(f"\n[{i+1}] {doc_id}")
            print(f"    Distance: {results['distances'][i]:.4f}")
            print(f"    Metadata: {results['metadatas'][i]}")
            doc_preview = results['documents'][i][:200] if results['documents'] else "N/A"
            print(f"    Preview: {doc_preview}...")

    elif args.delete_collection:
        if delete_collection(args.delete_collection):
            print(f"Deleted collection: {args.delete_collection}")
        else:
            print(f"Collection not found: {args.delete_collection}")

    elif args.add_chunks:
        chunks_path = Path(args.add_chunks)
        chunks = json.loads(chunks_path.read_text())
        print(f"Adding {len(chunks)} chunks...")
        added = add_chunks(chunks)
        print(f"Added {added} new chunks")
