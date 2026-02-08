# Directive: Build Vector Index

> Embed document chunks and store them in ChromaDB for semantic retrieval.

## Goal

Generate embeddings for document chunks and add them to the vector database, enabling semantic search over SEC filings.

## Inputs

- **chunks_path**: Path to chunks JSON file (required, e.g., `.tmp/chunks/AAPL_10K_2023-10-27_chunks.json`)
- **collection_name**: ChromaDB collection name (optional, default: "sec_filings")
- **embedding_model**: OpenAI embedding model (optional, default: "text-embedding-3-small")

## Tools/Scripts

- `execution/embeddings.py` - Generate embeddings via OpenAI API
- `execution/vector_store.py` - ChromaDB operations (add, query, delete)
- `execution/chunker.py` - Load chunks from JSON

## Process

1. **Load chunks**: Use `chunker.load_chunks(chunks_path)` to load the chunk data
2. **Check for duplicates**: Query collection to see if documents already exist (by ID)
3. **Generate embeddings**: Use `embeddings.embed_chunks(chunks)` to add embeddings
4. **Add to ChromaDB**: Use `vector_store.add_chunks(chunks)` to store in database
5. **Verify insertion**: Check collection stats to confirm documents were added
6. **Return statistics**: Report total docs, new docs added, collection size

## Outputs

- Updated ChromaDB collection at `.tmp/chroma/`
- Embedding cache populated at `.tmp/embedding_cache/`

## Example Usage

```python
from execution.chunker import load_chunks
from execution.embeddings import embed_chunks
from execution.vector_store import add_chunks, get_collection_stats

# 1. Load chunks
chunks = load_chunks(Path(".tmp/chunks/AAPL_10K_2023-10-27_chunks.json"))

# 2. Generate embeddings
embedded_chunks = embed_chunks([c.__dict__ for c in chunks], show_progress=True)

# 3. Add to vector store
added = add_chunks(embedded_chunks)
print(f"Added {added} chunks to vector store")

# 4. Verify
stats = get_collection_stats()
print(f"Collection now has {stats['count']} documents")
```

## CLI Usage

```bash
# Generate embeddings for chunks
python execution/embeddings.py --chunks .tmp/chunks/AAPL_10K_2023-10-27_chunks.json

# Add to vector store
python execution/vector_store.py --add-chunks .tmp/chunks/AAPL_10K_2023-10-27_chunks.embedded.json

# Check collection stats
python execution/vector_store.py --stats
```

## Edge Cases

- **Duplicate documents**: System skips chunks with existing IDs (uses upsert semantics)
- **API rate limits**: Embeddings are batched (100 at a time) with automatic retry
- **Large batches**: Process in chunks of 100 to avoid memory issues
- **Embedding failures**: Failed chunks are logged, others continue processing
- **Cache hit**: Previously embedded texts are loaded from cache (saves API costs)

## Collection Schema

Documents are stored with this metadata structure:
```json
{
  "id": "AAPL_10K_2023-10-27_item_1a_0",
  "ticker": "AAPL",
  "filing_type": "10-K",
  "filing_date": "2023-10-27",
  "section": "item_1a",
  "chunk_index": 0
}
```

## Learnings

- `text-embedding-3-small` is cost-effective ($0.02/1M tokens) and performs well for financial text
- Include section type in metadata for filtered retrieval during RAG
- Chunk IDs are deterministic: `{ticker}_{filing_type}_{date}_{section}_{chunk_num}`
- Embedding cache significantly reduces costs when re-processing
- ChromaDB uses cosine similarity by default (configured in collection metadata)
