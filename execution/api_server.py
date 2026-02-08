"""
API Server for EDGAR Intelligence UI.

Provides REST endpoints for:
- RAG queries against indexed SEC filings
- Document statistics and status

Run with: python execution/api_server.py
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "execution"))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from utils import TMP_DIR
from vector_store import get_collection_stats, get_all_tickers
from rag_chain import query_with_context as rag_query

app = Flask(__name__, static_folder='../ui', static_url_path='')
CORS(app)

# Collection name
COLLECTION_NAME = "sec_filings"


@app.route('/')
def serve_index():
    """Serve the main UI."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    Get statistics about indexed documents.

    Returns:
        JSON with total_chunks, companies list, and collection info
    """
    try:
        stats = get_collection_stats(COLLECTION_NAME)
        tickers = get_all_tickers(COLLECTION_NAME)

        # Build company list with details
        companies = []
        for ticker_info in tickers:
            companies.append({
                'ticker': ticker_info['ticker'],
                'name': ticker_info.get('company_name', ''),
                'chunk_count': ticker_info.get('count', 0),
            })

        return jsonify({
            'total_chunks': stats.get('count', 0),
            'companies': companies,
            'collection': COLLECTION_NAME,
        })

    except Exception as e:
        return jsonify({
            'total_chunks': 0,
            'companies': [],
            'error': str(e),
        })


@app.route('/api/query', methods=['POST'])
def query_documents():
    """
    Query indexed SEC filings using RAG.

    Request body:
        - query: The question to ask (required)
        - ticker: Filter by company ticker (optional)
        - filing_type: Filter by filing type (optional)
        - top_k: Number of results (optional, default 5)

    Returns:
        JSON with answer, citations, and confidence score
    """
    try:
        data = request.get_json()

        if not data or 'query' not in data:
            return jsonify({'error': 'Missing query parameter'}), 400

        query_text = data['query']
        ticker = data.get('ticker')
        filing_type = data.get('filing_type')
        top_k = data.get('top_k', 5)

        # Execute RAG query
        result = rag_query(
            query=query_text,
            ticker=ticker,
            filing_type=filing_type,
            top_k=top_k,
            collection_name=COLLECTION_NAME,
        )

        return jsonify({
            'answer': result.answer,
            'citations': result.citations,
            'confidence': result.confidence,
            'query': query_text,
            'filter': {
                'ticker': ticker,
                'filing_type': filing_type,
            } if (ticker or filing_type) else None,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'edgar-intelligence'})


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='EDGAR Intelligence API Server')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    EDGAR Intelligence                        ║
║                  SEC Filing Research UI                      ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{args.host}:{args.port}                    ║
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)
