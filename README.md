# EDGAR Intelligence

A RAG-powered SEC filing research system that lets you ask natural language questions about company financial reports.

## What Problem Does This Solve?

When you want to understand a public company's financials, risks, or business strategy, you need to read their SEC filings (10-K annual reports, 10-Q quarterly reports). These documents are:

- **Long** — Often 100-200+ pages of dense legal and financial text
- **Hard to search** — Ctrl+F only finds exact words, not concepts
- **Scattered** — Information about one topic might be spread across multiple sections

Instead of reading the whole filing, you just **ask a question in plain English**:

> "What are Microsoft's key business segments?"

The system:
1. **Downloads** the official SEC filing from the government database
2. **Breaks it into chunks** (small pieces of text)
3. **Understands the meaning** of each chunk using AI embeddings
4. **Finds the most relevant chunks** for your question
5. **Generates an answer** with citations back to the original document

**Before:** Spend hours reading 200-page documents to find one answer.

**After:** Ask a question, get an answer with sources in seconds.

## How It Works (RAG Pipeline)

**RAG** stands for **Retrieval-Augmented Generation**. It makes LLMs smarter by giving them relevant documents to read before answering.

### Why RAG?

LLMs like Claude have a knowledge cutoff and don't know about your specific documents. If you ask "What are Apple's risk factors?", it can only give a generic answer—not from the actual 2024 SEC filing. RAG fixes this by retrieving relevant content first.

### The Two Phases

**Phase 1: Ingestion (one-time per company)**
```
SEC Filing (HTML) → Parse → Chunk → Embed → Store in Vector DB
```

**Phase 2: Query (every question)**
```
Question → Embed → Search Similar Chunks → Build Prompt → LLM Answer
```

### Visual Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         INGESTION (once)                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SEC EDGAR  ──→  HTML  ──→  Sections  ──→  Chunks  ──→  Vectors │
│   (download)    (parse)    (extract)     (split)      (embed)   │
│                                                                  │
│                                           ↓                      │
│                                     ┌──────────┐                 │
│                                     │ ChromaDB │                 │
│                                     │ (vector  │                 │
│                                     │   store) │                 │
│                                     └──────────┘                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      QUERY TIME (every question)                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  "What are the    ──→  Embed   ──→  Search   ──→  Top 5 chunks  │
│   risk factors?"       Query       ChromaDB                      │
│                                                                  │
│                                        ↓                         │
│                                                                  │
│  Answer with      ←──  Claude  ←──  Prompt + Context            │
│  citations [1][2]      (LLM)        "Answer using these docs"   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### What's an Embedding?

An embedding converts text into a list of numbers (a vector) that captures its *meaning*. Similar concepts have similar vectors:

```
"Apple's revenue increased" → [0.12, -0.34, 0.56, ...]
"The company's sales grew"  → [0.11, -0.33, 0.55, ...]  ← Similar!
"Risk factors include..."   → [-0.45, 0.22, 0.08, ...] ← Different
```

This enables **semantic search**—finding conceptually similar text, not just keyword matches.

### Why This Works Better Than Just Asking an LLM

| Without RAG | With RAG |
|-------------|----------|
| LLM guesses from training data | LLM reads actual 2024 SEC filing |
| No citations | Cites specific sections |
| May hallucinate facts | Grounded in real documents |
| Generic knowledge | Company-specific details |

## Overview

EDGAR Intelligence downloads SEC filings (10-K, 10-Q) from the SEC EDGAR database, processes them into searchable chunks, and uses semantic search + LLM to answer questions with citations.

**Current Database:**
- Apple (AAPL) - 50 chunks
- Microsoft (MSFT) - 274 chunks

## Quick Start

```bash
# 1. Activate the environment
cd "/Users/amir/Desktop/My Projects/AI Engineer – Document Intelligence & LLM Systems"
source venv/bin/activate

# 2. Start the UI server
python execution/api_server.py --port 8080

# 3. Open http://127.0.0.1:8080 in your browser
```

## Adding Companies

Use the `add_company.py` script to ingest SEC filings:

```bash
# Add a company's latest 10-K
python execution/add_company.py GOOGL      # Google
python execution/add_company.py AMZN       # Amazon
python execution/add_company.py TSLA       # Tesla
python execution/add_company.py NVDA       # NVIDIA

# Add a quarterly report (10-Q)
python execution/add_company.py AAPL 10-Q

# Add multiple filings
python execution/add_company.py MSFT 10-K 3  # Last 3 annual reports
```

The script will:
1. Download the filing from SEC EDGAR
2. Parse sections (Item 1, 1A, 7, 8, etc.)
3. Chunk into ~1500 character pieces
4. Generate embeddings via OpenAI
5. Store in ChromaDB vector database

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Query                           │
│            "What are Microsoft's business segments?"        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG Pipeline                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Embed     │→ │   Vector    │→ │   Rerank &          │  │
│  │   Query     │  │   Search    │  │   Format Context    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Claude LLM                               │
│         Answer with citations from SEC filings              │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
execution/
├── api_server.py      # Flask API server for UI
├── rag_chain.py       # RAG pipeline orchestration
├── vector_store.py    # ChromaDB operations
├── embeddings.py      # OpenAI embedding generation
├── prompts.py         # LLM prompt templates
├── sec_fetcher.py     # SEC EDGAR API integration
├── pdf_parser.py      # HTML/PDF document parsing
├── chunker.py         # Semantic text chunking
├── add_company.py     # CLI to add new companies
├── schemas.py         # Data models
└── utils.py           # Shared utilities

ui/
├── index.html         # Chat interface
├── styles.css         # Styling
└── app.js             # Frontend logic

directives/            # SOP documentation
├── ingest_sec_filing.md
├── build_vector_index.md
└── rag_query.md

.tmp/                  # Temporary/intermediate files
├── raw/               # Downloaded SEC filings
├── parsed/            # Parsed document JSON
├── chunks/            # Chunked documents + embeddings
├── chroma/            # ChromaDB vector database
└── embedding_cache/   # Cached embeddings
```

## API Reference

### Health Check
```
GET /api/health
```

### Get Stats
```
GET /api/stats

Response:
{
  "total_chunks": 324,
  "companies": [
    {"ticker": "AAPL", "name": "Apple Inc", "chunk_count": 50},
    {"ticker": "MSFT", "name": "Microsoft Corp", "chunk_count": 274}
  ]
}
```

### Query Documents
```
POST /api/query
Content-Type: application/json

{
  "query": "What are the key risk factors?",
  "ticker": "AAPL",           // optional filter
  "filing_type": "10-K",      // optional filter
  "top_k": 5                  // optional, default 5
}

Response:
{
  "answer": "Based on the SEC filings...",
  "citations": [...],
  "confidence": 0.85,
  "query": "What are the key risk factors?"
}
```

## CLI Tools

### Query via Command Line
```bash
python execution/rag_chain.py "What is Apple's revenue?"
python execution/rag_chain.py "Compare risk factors" --ticker MSFT
python execution/rag_chain.py -i  # Interactive mode
```

### Vector Store Operations
```bash
python execution/vector_store.py --stats
python execution/vector_store.py --list
python execution/vector_store.py --query "business segments" --n 5
```

### SEC Fetcher
```bash
python execution/sec_fetcher.py --ticker AAPL --type 10-K --list
python execution/sec_fetcher.py --ticker AAPL --download
```

## Configuration

### Environment Variables (.env)

```bash
# Required
OPENAI_API_KEY=sk-...        # For embeddings
ANTHROPIC_API_KEY=sk-ant-... # For Claude LLM

# Optional
MODAL_TOKEN_ID=              # For webhook deployments
MODAL_TOKEN_SECRET=
SLACK_WEBHOOK_URL=           # For notifications
```

### Chunking Parameters

In `execution/chunker.py`:
```python
DEFAULT_CHUNK_SIZE = 1500    # Target chars per chunk
DEFAULT_CHUNK_OVERLAP = 200  # Overlap between chunks
MIN_CHUNK_SIZE = 100         # Minimum chunk size
```

### RAG Parameters

In `execution/rag_chain.py`:
```python
DEFAULT_MODEL = "claude-sonnet-4-20250514"
top_k = 5                    # Chunks to retrieve
retrieve_k = 10              # Initial retrieval (before rerank)
```

## SEC Filing Sections

| Section | Name | Content |
|---------|------|---------|
| Item 1 | Business | Company description, products, strategy |
| Item 1A | Risk Factors | Key risks facing the company |
| Item 1B | Unresolved Staff Comments | SEC comment issues |
| Item 7 | MD&A | Management's analysis |
| Item 7A | Quantitative Disclosures | Market risk |
| Item 8 | Financial Statements | Balance sheet, income, cash flow |

## Troubleshooting

### "Context section appears to be empty"
- Chunks may be too large. The system auto-truncates to 2000 chars per chunk.
- Check if the filing was properly parsed: `ls .tmp/parsed/`

### Embedding errors (token limit)
- Large chunks are auto-split during chunking
- If issues persist, check `.tmp/chunks/` for oversized chunks

### Wrong document downloaded
- SEC filings have multiple documents. The system selects the main filing by:
  1. Matching ticker name in filename
  2. Selecting largest HTML file

### Rate limiting
- SEC EDGAR limits to 10 requests/second (auto-handled)
- OpenAI embeddings are batched (100 per request)

## Development

### Install Dependencies
```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Tests
```bash
pytest
```

### Key Files to Modify

- **Add new company mappings**: `execution/rag_chain.py` → `company_tickers` dict
- **Change LLM model**: `execution/rag_chain.py` → `DEFAULT_MODEL`
- **Modify prompts**: `execution/prompts.py`
- **Adjust chunking**: `execution/chunker.py`

## License

Internal use only.
