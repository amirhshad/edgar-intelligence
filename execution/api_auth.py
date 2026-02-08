"""
API authentication and rate limiting middleware for Flask.

Usage:
    @app.route('/v1/query', methods=['POST'])
    @require_api_key
    def query():
        key = g.api_key  # authenticated key record
        ...
"""

import hashlib
from functools import wraps
from flask import request, jsonify, g

from api_db import validate_key, get_daily_usage, get_key_limit


def _error_response(code: str, message: str, status: int):
    """Build a standard error response."""
    return jsonify({"error": {"code": code, "message": message, "status": status}}), status


def require_api_key(f):
    """Flask decorator that enforces API key auth and rate limiting."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Step 1: Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error_response(
                "missing_api_key",
                "Missing or malformed Authorization header. Expected: Bearer sk_edgar_live_...",
                401,
            )

        token = auth_header[7:]  # strip "Bearer "
        if not token.startswith("sk_edgar_live_"):
            return _error_response(
                "invalid_api_key",
                "Invalid API key format.",
                401,
            )

        # Step 2: Validate key
        key_record = validate_key(token)
        if not key_record:
            return _error_response(
                "invalid_api_key",
                "API key not found or has been revoked.",
                401,
            )

        # Step 3: Check rate limit
        usage_count = get_daily_usage(key_record["id"])
        limit = get_key_limit(key_record["tier"])

        if usage_count >= limit:
            return _error_response(
                "rate_limit_exceeded",
                f"Daily query limit reached ({limit}/day on {key_record['tier']} tier). Resets at midnight UTC.",
                429,
            )

        # Attach to request context
        g.api_key = key_record
        g.usage_count = usage_count
        g.usage_limit = limit

        return f(*args, **kwargs)

    return decorated
