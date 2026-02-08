"""
EDGAR Intelligence API Server.

v1 API endpoints:
    POST /v1/signup     - Self-serve API key creation (public)
    POST /v1/query      - Ask questions about SEC filings (requires API key)
    GET  /v1/companies  - List indexed companies (public)
    GET  /v1/usage      - Check API usage (requires API key)
    GET  /v1/health     - Health check (public)

Legacy UI:
    GET /app            - Chat UI (served from ui/)

Landing page:
    GET /               - API landing page

Run with: python execution/api_server.py --port 8080
"""

import sys
import time
from pathlib import Path
from datetime import date

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "execution"))

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

from vector_store import get_collection_stats, get_all_tickers
from rag_chain import query_with_context as rag_query
from api_auth import require_api_key
from api_db import init_db, increment_usage, log_request, get_daily_usage, get_key_limit, create_key, get_keys_by_email, TIER_LIMITS

app = Flask(__name__, static_folder='../api_landing', static_url_path='/static')
CORS(app)

COLLECTION_NAME = "sec_filings"
API_VERSION = "1.0.0"

# Initialize database
init_db()


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message, "status": status}}), status


# ──────────────── Landing Page ────────────────

@app.route('/')
def landing():
    """Serve API landing page."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/landing/<path:path>')
def landing_static(path):
    """Serve landing page static assets."""
    return send_from_directory(app.static_folder, path)


# ──────────────── Legacy Chat UI ────────────────

@app.route('/app')
def serve_ui():
    """Serve the chat UI."""
    return send_from_directory(str(project_root / 'ui'), 'index.html')


@app.route('/app/<path:path>')
def serve_ui_static(path):
    """Serve UI static files."""
    return send_from_directory(str(project_root / 'ui'), path)


# Legacy endpoints for the chat UI (no auth required)
@app.route('/api/stats', methods=['GET'])
def legacy_stats():
    """Legacy stats endpoint for the chat UI."""
    try:
        stats = get_collection_stats(COLLECTION_NAME)
        tickers = get_all_tickers(COLLECTION_NAME)
        companies = [
            {'ticker': t['ticker'], 'name': t.get('company_name', ''), 'chunk_count': t.get('count', 0)}
            for t in tickers
        ]
        return jsonify({'total_chunks': stats.get('count', 0), 'companies': companies, 'collection': COLLECTION_NAME})
    except Exception:
        return jsonify({'total_chunks': 0, 'companies': []})


@app.route('/api/query', methods=['POST'])
def legacy_query():
    """Legacy query endpoint for the chat UI."""
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Missing query parameter'}), 400

        result = rag_query(
            query=data['query'],
            ticker=data.get('ticker'),
            filing_type=data.get('filing_type'),
            top_k=data.get('top_k', 5),
            collection_name=COLLECTION_NAME,
        )
        return jsonify({
            'answer': result.answer, 'citations': result.citations,
            'confidence': result.confidence, 'query': data['query'],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ──────────────── v1 API ────────────────

@app.route('/v1/health', methods=['GET'])
def v1_health():
    """Health check — used by Render and monitoring."""
    try:
        tickers = get_all_tickers(COLLECTION_NAME)
        company_count = len(tickers)
    except Exception:
        company_count = 0

    return jsonify({
        "status": "healthy",
        "service": "edgar-intelligence",
        "version": API_VERSION,
        "companies_indexed": company_count,
    })


@app.route('/v1/companies', methods=['GET'])
def v1_companies():
    """List all indexed companies. Public endpoint."""
    try:
        tickers = get_all_tickers(COLLECTION_NAME)
        stats = get_collection_stats(COLLECTION_NAME)

        return jsonify({
            "companies": [
                {
                    "ticker": t["ticker"],
                    "name": t.get("company_name", ""),
                    "filings_indexed": t.get("count", 0),
                }
                for t in tickers
            ],
            "total_companies": len(tickers),
            "total_chunks": stats.get("count", 0),
        })
    except Exception as e:
        return _error("internal_error", str(e), 500)


@app.route('/v1/query', methods=['POST'])
@require_api_key
def v1_query():
    """Ask a question about SEC filings. Requires API key."""
    start = time.time()
    data = request.get_json()

    # Validate input
    if not data or "question" not in data:
        return _error("bad_request", "Missing required field: 'question'", 400)

    question = data["question"]
    if not question.strip():
        return _error("bad_request", "Field 'question' cannot be empty", 400)

    company = data.get("company")
    filing_type = data.get("filing_type")
    top_k = min(data.get("top_k", 5), 10)

    try:
        result = rag_query(
            query=question,
            ticker=company,
            filing_type=filing_type,
            top_k=top_k,
            collection_name=COLLECTION_NAME,
        )

        latency_ms = int((time.time() - start) * 1000)

        # Track usage
        today = date.today().isoformat()
        increment_usage(g.api_key["id"], today)
        log_request(g.api_key["id"], "/v1/query", question, company, 200, latency_ms)

        return jsonify({
            "answer": result.answer,
            "confidence": result.confidence,
            "citations": result.citations,
            "meta": {
                "model": result.model_used,
                "chunks_used": result.chunks_used,
                "latency_ms": latency_ms,
            },
        })

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        log_request(g.api_key["id"], "/v1/query", question, company, 500, latency_ms)
        return _error("internal_error", f"Query failed: {str(e)}", 500)


@app.route('/v1/usage', methods=['GET'])
@require_api_key
def v1_usage():
    """Check your API usage. Requires API key."""
    key = g.api_key
    today = date.today().isoformat()
    count = get_daily_usage(key["id"], today)
    limit = get_key_limit(key["tier"])

    return jsonify({
        "tier": key["tier"],
        "limits": {"queries_per_day": limit},
        "usage_today": {"queries": count, "remaining": max(0, limit - count)},
        "key_prefix": key["key_prefix"],
        "member_since": key["created_at"][:10],
    })


# ──────────────── Signup ────────────────

MAX_KEYS_PER_EMAIL = 3

@app.route('/v1/signup', methods=['POST'])
def v1_signup():
    """Self-serve API key signup. Returns a free-tier key instantly."""
    data = request.get_json()
    if not data:
        return _error("bad_request", "Request body must be JSON", 400)

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not name:
        return _error("bad_request", "Name is required", 400)
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return _error("bad_request", "A valid email address is required", 400)

    # Limit keys per email to prevent abuse
    existing = get_keys_by_email(email)
    if len(existing) >= MAX_KEYS_PER_EMAIL:
        return _error("rate_limit_exceeded", f"Maximum {MAX_KEYS_PER_EMAIL} API keys per email address", 429)

    try:
        api_key = create_key(name, email, "free")
        return jsonify({
            "api_key": api_key,
            "name": name,
            "email": email,
            "tier": "free",
            "queries_per_day": TIER_LIMITS["free"],
            "message": "Save this key — it will not be shown again.",
        }), 201
    except Exception as e:
        return _error("internal_error", f"Could not create API key: {str(e)}", 500)


# ──────────────── Main ────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='EDGAR Intelligence API Server')
    parser.add_argument('--port', type=int, default=8080, help='Port to run on')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    EDGAR Intelligence API                    ║
╠══════════════════════════════════════════════════════════════╣
║  Landing:  http://{args.host}:{args.port}                             ║
║  Chat UI:  http://{args.host}:{args.port}/app                         ║
║  API:      http://{args.host}:{args.port}/v1/                         ║
║  Health:   http://{args.host}:{args.port}/v1/health                   ║
╠══════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)
