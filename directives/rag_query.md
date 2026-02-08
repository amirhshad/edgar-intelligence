# Directive: RAG Query

> Answer questions about SEC filings using retrieval-augmented generation.

## Goal

Provide accurate, well-cited answers to questions about company filings by retrieving relevant context and generating responses with Claude.

## Inputs

- **query**: User's question (required)
- **ticker**: Limit search to specific company (optional)
- **filing_type**: Limit to specific filing type - "10-K" or "10-Q" (optional)
- **top_k**: Number of context chunks to use (optional, default: 5)

## Tools/Scripts

- `execution/rag_chain.py` - Complete RAG pipeline
- `execution/vector_store.py` - Retrieve relevant chunks
- `execution/embeddings.py` - Generate query embedding
- `execution/prompts.py` - Prompt templates

## Process

1. **Parse query**: Extract implicit filters (company names, years, filing types)
2. **Generate embedding**: Use `embeddings.embed_single(query)` for the query
3. **Retrieve chunks**: Use `vector_store.query()` with filters and embedding
4. **Rerank results**: Score by relevance, section match, and recency
5. **Build context**: Format top chunks with citation markers [1], [2], etc.
6. **Generate answer**: Call Claude with RAG prompt and context
7. **Extract citations**: Map [N] markers to source documents
8. **Return response**: RAGResponse with answer, citations, confidence

## Outputs

- RAGResponse object containing:
  - `answer`: Generated answer with inline citations
  - `citations`: List of sources used with relevance scores
  - `confidence`: 0.0-1.0 confidence in the answer
  - `chunks_retrieved`: Number of chunks found
  - `chunks_used`: Number used in context

## Example Usage

```python
from execution.rag_chain import query_with_context

# Basic query
response = query_with_context("What was Apple's revenue in 2023?")
print(response.answer)
print(f"Confidence: {response.confidence}")

# With filters
response = query_with_context(
    "What are the main risk factors?",
    ticker="MSFT",
    filing_type="10-K",
    top_k=10
)

# Interactive mode
# python execution/rag_chain.py --interactive
```

## CLI Usage

```bash
# Single query
python execution/rag_chain.py "What was Apple's revenue last year?"

# With filters
python execution/rag_chain.py "What are the risk factors?" --ticker AAPL --filing-type 10-K

# Interactive mode
python execution/rag_chain.py --interactive
```

## Example Queries

| Query | Expected Behavior |
|-------|-------------------|
| "What was Apple's revenue in fiscal 2023?" | Retrieves Item 7/8, cites specific figures |
| "What are Microsoft's main risk factors?" | Retrieves Item 1A, summarizes top risks |
| "How did Amazon's profit margin change?" | Compares across filings if multiple indexed |
| "What products does Tesla sell?" | Retrieves Item 1 (Business Description) |

## Edge Cases

- **No relevant documents**: Returns "I don't have information about this" with 0.0 confidence
- **Conflicting information**: Notes conflict, cites both sources with dates
- **Query too vague**: System attempts to extract filters, may retrieve mixed results
- **Forward-looking statements**: System distinguishes projections from reported facts
- **Missing ticker**: Searches all indexed companies

## Low-Hallucination Safeguards

1. **Citation requirement**: Prompts require [N] citations for all claims
2. **Context-only answers**: System prompt forbids information beyond context
3. **Confidence scoring**: Low confidence if "don't have information" in answer
4. **Source validation**: Citations are verified against retrieved chunks

## Learnings

- Retrieve 2x chunks needed, then rerank for better relevance
- Section boosts improve results (risk queries → Item 1A, financial → Item 7/8)
- Company name recognition helps when ticker not explicit
- Including dates in context helps with temporal questions
- Claude Opus 4.5 produces better-structured citations than earlier models
