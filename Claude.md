# Agent Instructions

> This file is mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Directive (What to do)**
- Basically just SOPs written in Markdown, live in `directives/`
- Define the goals, inputs, tools/scripts to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee

**Layer 2: Orchestration (Decision making)**
- This is you. Your job: intelligent routing.
- Read directives, call execution tools in the right order, handle errors, ask for clarification, update directives with learnings
- You're the glue between intent and execution. E.g you don't try scraping websites yourself—you read `directives/scrape_website.md` and come up with inputs/outputs and then run `execution/scrape_single_site.py`

**Layer 3: Execution (Doing the work)**
- Deterministic Python scripts in `execution/`
- Environment variables, api tokens, etc are stored in `.env`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast. Use scripts instead of manual work.

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution is push complexity into deterministic code. That way you just focus on decision-making.

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits/etc—in which case you check w user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: you hit an API rate limit → you then look into API → find a batch endpoint that would fix → rewrite script to accommodate → test → update directive.

**3. Update directives as you learn**
Directives are living documents. When you discover API constraints, better approaches, common errors, or timing expectations—update the directive. But don't create or overwrite directives without asking unless explicitly told to. Directives are your instruction set and must be preserved (and improved upon over time, not extemporaneously used and then discarded).

## Self-annealing loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool
3. Test tool, make sure it works
4. Update directive to include new flow
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or other cloud-based outputs that the user can access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files (vector DB, parsed filings, embeddings cache). Never commit, always regenerated.
- `execution/` - Python scripts (the deterministic tools)
- `directives/` - SOPs in Markdown (the instruction set)
- `api_landing/` - Static landing page served at `/`
- `ui/` - Chat UI served at `/app`
- `docs/` - GitHub Pages demo (static copy of `ui/`)
- `.env` - Environment variables and API keys
- `credentials.json`, `token.json` - Google OAuth credentials (required files, in `.gitignore`)

**Key principle:** Local files are only for processing. Deliverables live in cloud services (Google Sheets, Slides, etc.) where the user can access them. Everything in `.tmp/` can be deleted and regenerated.

## Cloud Webhooks (Modal)

The system supports event-driven execution via Modal webhooks. Each webhook maps to exactly one directive with scoped tool access.

**When user says "add a webhook that...":**
1. Read `directives/add_webhook.md` for complete instructions
2. Create the directive file in `directives/`
3. Add entry to `execution/webhooks.json`
4. Deploy: `modal deploy execution/modal_webhook.py`
5. Test the endpoint

**Key files:**
- `execution/webhooks.json` - Webhook slug → directive mapping
- `execution/modal_webhook.py` - Modal app (do not modify unless necessary)
- `directives/add_webhook.md` - Complete setup guide

**Endpoints:**
- `https://nick-90891--claude-orchestrator-list-webhooks.modal.run` - List webhooks
- `https://nick-90891--claude-orchestrator-directive.modal.run?slug={slug}` - Execute directive
- `https://nick-90891--claude-orchestrator-test-email.modal.run` - Test email

**Available tools for webhooks:** `send_email`, `read_sheet`, `update_sheet`

**All webhook activity streams to Slack in real-time.**

## EDGAR Intelligence API

This project is a Developer API for querying SEC filings using RAG (Retrieval-Augmented Generation). It's deployed on Render and the code lives on GitHub.

**GitHub:** https://github.com/amirhshad/edgar-intelligence
**GitHub Pages demo:** https://amirhshad.github.io/edgar-intelligence/

### Architecture

```
User → POST /v1/query + API key → Flask API → RAG pipeline → ChromaDB → Claude LLM → Cited answer
```

### Key execution scripts

| Script | Purpose |
|--------|---------|
| `execution/api_server.py` | Flask API server (landing page, chat UI, v1 API) |
| `execution/api_db.py` | SQLite database for API keys + usage tracking |
| `execution/api_auth.py` | `@require_api_key` decorator (auth + rate limiting) |
| `execution/api_keys_cli.py` | CLI to create/list/revoke API keys |
| `execution/add_company.py` | Index a company's SEC filing into ChromaDB |
| `execution/rag_chain.py` | RAG pipeline (embed query → retrieve chunks → LLM answer) |
| `execution/vector_store.py` | ChromaDB operations (add, query, stats) |
| `execution/sec_fetcher.py` | Download filings from SEC EDGAR |
| `execution/pdf_parser.py` | Parse SEC filing HTML into sections |
| `execution/chunker.py` | Split sections into chunks for embedding |
| `execution/embeddings.py` | OpenAI text-embedding-3-small (cached) |

### API endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /` | No | Landing page |
| `GET /app` | No | Chat UI |
| `POST /v1/query` | Bearer token | Ask questions, get cited answers |
| `GET /v1/companies` | No | List indexed companies |
| `GET /v1/usage` | Bearer token | Check rate limit status |
| `GET /v1/health` | No | Health check |

### API key management

```bash
python execution/api_keys_cli.py create --name "Name" --email "email" --tier free
python execution/api_keys_cli.py list
python execution/api_keys_cli.py revoke --id 1
python execution/api_keys_cli.py usage --id 1
```

Key format: `sk_edgar_live_` + 24 hex chars. Only SHA-256 hash stored in SQLite.
Rate limits: free = 20 queries/day, pro = 500 queries/day.

### Adding companies

```bash
python execution/add_company.py AAPL        # Add Apple's latest 10-K
python execution/add_company.py TSLA 10-Q   # Add Tesla's latest 10-Q
```

Currently indexed: 26 S&P 500 companies, 7,122 chunks.

### Databases

- **ChromaDB** (`.tmp/chroma/`) — Vector database for SEC filing chunks + embeddings
- **SQLite** (`.tmp/edgar_api.db`) — API keys, daily usage counters, request audit log

### Deployment

- **Platform:** Render (web service + persistent disk)
- **Config:** `Procfile`, `render.yaml`, `runtime.txt`
- **Persistent disk** mounts at `/data` (set via `RENDER_DATA_DIR` env var)
- **Start command:** `gunicorn execution.api_server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

### MCP servers available

- **Render** — Manage Render services, deploys, logs, env vars directly from Claude Code
- **Supabase** — Database operations (if needed in future)
- **Playwright** — Browser automation for testing

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.