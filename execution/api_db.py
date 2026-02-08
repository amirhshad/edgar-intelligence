"""
SQLite database for API key management and usage tracking.

Tables:
    api_keys    - Stores hashed API keys with tier and active status
    daily_usage - Fast counter per key per day (for rate limiting)
    usage_log   - Append-only audit trail of all API requests
"""

import sqlite3
import secrets
import hashlib
from datetime import datetime, date
from pathlib import Path
from contextlib import contextmanager

from utils import TMP_DIR

DB_PATH = TMP_DIR / "edgar_api.db"

TIER_LIMITS = {
    "free": 20,
    "pro": 500,
}


@contextmanager
def get_db():
    """Get a database connection with WAL mode for concurrent access."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash    TEXT    NOT NULL UNIQUE,
                key_prefix  TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                email       TEXT    NOT NULL,
                tier        TEXT    NOT NULL DEFAULT 'free',
                created_at  TEXT    NOT NULL,
                last_used   TEXT,
                is_active   INTEGER NOT NULL DEFAULT 1,
                metadata    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);

            CREATE TABLE IF NOT EXISTS daily_usage (
                key_id      INTEGER NOT NULL REFERENCES api_keys(id),
                date        TEXT    NOT NULL,
                query_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (key_id, date)
            );

            CREATE TABLE IF NOT EXISTS usage_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id      INTEGER NOT NULL REFERENCES api_keys(id),
                endpoint    TEXT    NOT NULL,
                query_text  TEXT,
                ticker      TEXT,
                status_code INTEGER NOT NULL,
                latency_ms  INTEGER,
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_usage_log_key_date ON usage_log(key_id, created_at);
        """)


# --- API Key Management ---

def generate_api_key():
    """Generate a new API key. Returns (plaintext_key, sha256_hash)."""
    random_part = secrets.token_hex(12)
    key = f"sk_edgar_live_{random_part}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def create_key(name: str, email: str, tier: str = "free") -> str:
    """Create a new API key. Returns the plaintext key (shown once, never stored)."""
    if tier not in TIER_LIMITS:
        raise ValueError(f"Invalid tier: {tier}. Must be one of: {list(TIER_LIMITS.keys())}")

    plaintext_key, key_hash = generate_api_key()
    key_prefix = plaintext_key[:15] + "..."

    with get_db() as conn:
        conn.execute(
            "INSERT INTO api_keys (key_hash, key_prefix, name, email, tier, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (key_hash, key_prefix, name, email, tier, datetime.utcnow().isoformat()),
        )

    return plaintext_key


def get_key_by_hash(key_hash: str) -> dict | None:
    """Look up an API key by its hash. Returns dict or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        return dict(row) if row else None


def validate_key(plaintext_key: str) -> dict | None:
    """Validate a plaintext API key. Returns key record if valid and active, else None."""
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    record = get_key_by_hash(key_hash)
    if record and record["is_active"]:
        # Update last_used
        with get_db() as conn:
            conn.execute(
                "UPDATE api_keys SET last_used = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), record["id"]),
            )
        return record
    return None


def revoke_key(key_id: int) -> bool:
    """Revoke an API key by ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,)
        )
        return cursor.rowcount > 0


def list_keys() -> list[dict]:
    """List all API keys."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, key_prefix, name, email, tier, is_active, created_at, last_used FROM api_keys ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]


# --- Usage Tracking ---

def get_daily_usage(key_id: int, date_str: str = None) -> int:
    """Get query count for a key on a given date."""
    if date_str is None:
        date_str = date.today().isoformat()

    with get_db() as conn:
        row = conn.execute(
            "SELECT query_count FROM daily_usage WHERE key_id = ? AND date = ?",
            (key_id, date_str),
        ).fetchone()
        return row["query_count"] if row else 0


def increment_usage(key_id: int, date_str: str = None):
    """Increment daily usage counter (upsert)."""
    if date_str is None:
        date_str = date.today().isoformat()

    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_usage (key_id, date, query_count)
               VALUES (?, ?, 1)
               ON CONFLICT(key_id, date)
               DO UPDATE SET query_count = query_count + 1""",
            (key_id, date_str),
        )


def log_request(key_id: int, endpoint: str, query_text: str = None,
                ticker: str = None, status_code: int = 200, latency_ms: int = None):
    """Log an API request to the audit trail."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO usage_log (key_id, endpoint, query_text, ticker, status_code, latency_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key_id, endpoint, query_text, ticker, status_code, latency_ms, datetime.utcnow().isoformat()),
        )


def get_key_limit(tier: str) -> int:
    """Get the daily query limit for a tier."""
    return TIER_LIMITS.get(tier, 20)


# Initialize on import
init_db()
