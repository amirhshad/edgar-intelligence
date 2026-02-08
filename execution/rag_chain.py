"""
RAG (Retrieval-Augmented Generation) pipeline for SEC filings.

This module implements the complete RAG pipeline:
1. Query understanding and filter extraction
2. Semantic retrieval from vector store
3. Context formatting with citations
4. LLM response generation
5. Citation extraction and validation

Uses Claude for generation due to better structured output capabilities.
"""

import json
import re
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime

import anthropic

from utils import get_env
from vector_store import query as vector_query
from embeddings import embed_single
from prompts import RAG_SYSTEM_PROMPT, build_rag_prompt, format_rag_context
from schemas import RAGResponse

# Default model - Claude Opus 4.5 as per project requirements
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _get_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=get_env("ANTHROPIC_API_KEY"))


def _extract_filters_from_query(query: str) -> Dict[str, Any]:
    """
    Extract metadata filters from natural language query.

    Looks for:
    - Ticker mentions (e.g., "Apple" -> AAPL, "Microsoft" -> MSFT)
    - Year mentions (e.g., "2023", "last year")
    - Filing type mentions (e.g., "annual report" -> 10-K)

    Args:
        query: User's query

    Returns:
        Dict of filters for vector query
    """
    filters = {}
    query_lower = query.lower()

    # Common company name to ticker mappings
    company_tickers = {
        'apple': 'AAPL',
        'microsoft': 'MSFT',
        'google': 'GOOGL',
        'alphabet': 'GOOGL',
        'amazon': 'AMZN',
        'meta': 'META',
        'facebook': 'META',
        'nvidia': 'NVDA',
        'tesla': 'TSLA',
        'jpmorgan': 'JPM',
        'johnson': 'JNJ',
        'procter': 'PG',
    }

    # Check for company names
    for name, ticker in company_tickers.items():
        if name in query_lower:
            filters['ticker'] = ticker
            break

    # Check for explicit ticker mentions (all caps, 1-5 letters)
    ticker_match = re.search(r'\b([A-Z]{1,5})\b', query)
    if ticker_match and 'ticker' not in filters:
        potential_ticker = ticker_match.group(1)
        # Avoid common words
        if potential_ticker not in ['A', 'I', 'AND', 'THE', 'FOR', 'OR', 'IN', 'TO']:
            filters['ticker'] = potential_ticker

    # Check for filing type
    if 'annual' in query_lower or '10-k' in query_lower or '10k' in query_lower:
        filters['filing_type'] = '10-K'
    elif 'quarterly' in query_lower or '10-q' in query_lower or '10q' in query_lower:
        filters['filing_type'] = '10-Q'

    return filters


def _rerank_results(
    query: str,
    results: Dict,
    top_k: int
) -> List[Dict]:
    """
    Rerank search results for better relevance.

    Simple reranking based on:
    - Distance score (from vector search)
    - Section relevance to query type
    - Recency

    Args:
        query: Original query
        results: Vector search results
        top_k: Number of results to keep

    Returns:
        List of reranked result dicts
    """
    query_lower = query.lower()

    # Section relevance scores based on query type
    section_boosts = {}
    if any(term in query_lower for term in ['risk', 'threat', 'concern', 'challenge']):
        section_boosts['item_1a'] = 0.1
    if any(term in query_lower for term in ['revenue', 'income', 'profit', 'financial', 'earnings']):
        section_boosts['item_7'] = 0.1
        section_boosts['item_8'] = 0.1
    if any(term in query_lower for term in ['business', 'company', 'product', 'service']):
        section_boosts['item_1'] = 0.1

    # Build scored results
    scored_results = []
    for i in range(len(results['ids'])):
        metadata = results['metadatas'][i] if results.get('metadatas') else {}
        distance = results['distances'][i] if results.get('distances') else 1.0

        # Lower distance is better, apply section boost
        section = metadata.get('section', '')
        boost = section_boosts.get(section, 0)
        score = distance - boost  # Subtract boost to improve score

        scored_results.append({
            'id': results['ids'][i],
            'text': results['documents'][i] if results.get('documents') else '',
            'metadata': metadata,
            'distance': distance,
            'score': score,
        })

    # Sort by score (lower is better)
    scored_results.sort(key=lambda x: x['score'])

    return scored_results[:top_k]


def _extract_citations(answer: str, sources: List[Dict]) -> List[Dict]:
    """
    Extract and validate citations from answer text.

    Args:
        answer: Generated answer with [1], [2] citations
        sources: List of source documents

    Returns:
        List of citation dicts with source info
    """
    # Find all citation markers
    citation_pattern = r'\[(\d+)\]'
    cited_indices = set(int(m) for m in re.findall(citation_pattern, answer))

    citations = []
    for idx in sorted(cited_indices):
        if 1 <= idx <= len(sources):
            source = sources[idx - 1]
            citations.append({
                'index': idx,
                'text': source.get('text', '')[:200] + '...',
                'source': f"{source['metadata'].get('ticker', 'Unknown')} "
                         f"{source['metadata'].get('filing_type', '')} "
                         f"({source['metadata'].get('filing_date', 'Unknown')})",
                'section': source['metadata'].get('section', 'Unknown'),
                'relevance': 1.0 - source.get('distance', 0.5),
            })

    return citations


def query_with_context(
    query: str,
    ticker: Optional[str] = None,
    filing_type: Optional[str] = None,
    top_k: int = 5,
    model: str = DEFAULT_MODEL,
    collection_name: str = "sec_filings",
) -> RAGResponse:
    """
    Answer a question using RAG over SEC filings.

    Args:
        query: User's question
        ticker: Optional ticker filter
        filing_type: Optional filing type filter
        top_k: Number of chunks to use in context
        model: LLM model to use
        collection_name: Vector store collection

    Returns:
        RAGResponse with answer, citations, and confidence
    """
    # Extract filters from query if not explicitly provided
    auto_filters = _extract_filters_from_query(query)
    if ticker:
        auto_filters['ticker'] = ticker
    if filing_type:
        auto_filters['filing_type'] = filing_type

    # Build where clause for vector query
    where = {}
    if auto_filters.get('ticker'):
        where['ticker'] = auto_filters['ticker']
    if auto_filters.get('filing_type'):
        where['filing_type'] = auto_filters['filing_type']

    # Generate query embedding
    query_embedding = embed_single(query)

    # Retrieve more than needed for reranking
    retrieve_k = top_k * 2

    results = vector_query(
        query_embedding=query_embedding,
        n_results=retrieve_k,
        where=where if where else None,
        collection_name=collection_name,
    )

    # Handle no results
    if not results['ids']:
        return RAGResponse(
            query=query,
            answer="I don't have any information about this in the indexed SEC filings. "
                   "Please make sure the relevant filings have been ingested.",
            confidence=0.0,
            citations=[],
            chunks_retrieved=0,
            chunks_used=0,
            model_used=model,
        )

    # Rerank results
    reranked = _rerank_results(query, results, top_k)

    # Build prompt
    prompt = build_rag_prompt(query, reranked)

    # Call Claude
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=RAG_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    answer = response.content[0].text

    # Extract citations
    citations = _extract_citations(answer, reranked)

    # Estimate confidence based on:
    # - Number of citations used
    # - Average relevance of sources
    # - Presence of "I don't have information" phrases
    confidence = 0.8
    if "don't have information" in answer.lower() or "not found" in answer.lower():
        confidence = 0.3
    elif not citations:
        confidence = 0.5
    else:
        avg_relevance = sum(c['relevance'] for c in citations) / len(citations)
        confidence = min(0.95, 0.6 + (avg_relevance * 0.4))

    return RAGResponse(
        query=query,
        answer=answer,
        confidence=confidence,
        citations=citations,
        chunks_retrieved=len(results['ids']),
        chunks_used=len(reranked),
        model_used=model,
    )


def batch_query(
    queries: List[str],
    ticker: Optional[str] = None,
    filing_type: Optional[str] = None,
    top_k: int = 5,
    model: str = DEFAULT_MODEL,
) -> List[RAGResponse]:
    """
    Process multiple queries.

    Args:
        queries: List of questions
        ticker: Optional ticker filter (applies to all)
        filing_type: Optional filing type filter (applies to all)
        top_k: Chunks per query
        model: LLM model

    Returns:
        List of RAGResponse objects
    """
    return [
        query_with_context(q, ticker, filing_type, top_k, model)
        for q in queries
    ]


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG query over SEC filings")
    parser.add_argument("query", nargs="?", help="Question to ask")
    parser.add_argument("--ticker", help="Filter by ticker")
    parser.add_argument("--filing-type", help="Filter by filing type (10-K, 10-Q)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to use")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    if args.interactive:
        print("RAG Query System - Interactive Mode")
        print("Type 'quit' to exit\n")

        while True:
            query = input("Question: ").strip()
            if query.lower() in ['quit', 'exit', 'q']:
                break
            if not query:
                continue

            print("\nSearching...")
            response = query_with_context(
                query,
                ticker=args.ticker,
                filing_type=args.filing_type,
                top_k=args.top_k,
                model=args.model,
            )

            print(f"\nAnswer (confidence: {response.confidence:.2f}):")
            print(response.answer)

            if response.citations:
                print(f"\nSources ({len(response.citations)}):")
                for cite in response.citations:
                    print(f"  [{cite['index']}] {cite['source']} - {cite['section']}")

            print()

    elif args.query:
        response = query_with_context(
            args.query,
            ticker=args.ticker,
            filing_type=args.filing_type,
            top_k=args.top_k,
            model=args.model,
        )

        print(f"\nQuery: {args.query}")
        print(f"Confidence: {response.confidence:.2f}")
        print(f"Chunks retrieved: {response.chunks_retrieved}")
        print(f"Chunks used: {response.chunks_used}")
        print(f"\nAnswer:\n{response.answer}")

        if response.citations:
            print(f"\nCitations:")
            for cite in response.citations:
                print(f"  [{cite['index']}] {cite['source']}")
                print(f"      Section: {cite['section']}")
                print(f"      Relevance: {cite['relevance']:.2f}")

    else:
        parser.print_help()
