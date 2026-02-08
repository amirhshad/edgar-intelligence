"""
Shared utilities for execution scripts.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DIRECTIVES_DIR = PROJECT_ROOT / "directives"
EXECUTION_DIR = PROJECT_ROOT / "execution"

# On Render, use persistent disk; locally use .tmp/
_render_data_dir = os.getenv("RENDER_DATA_DIR")
TMP_DIR = Path(_render_data_dir) if _render_data_dir else PROJECT_ROOT / ".tmp"

# Ensure directory exists
TMP_DIR.mkdir(parents=True, exist_ok=True)


def get_env(key: str, default: str = None) -> str:
    """Get environment variable with optional default."""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} not set")
    return value


def read_directive(name: str) -> str:
    """Read a directive file by name."""
    path = DIRECTIVES_DIR / name
    if not path.suffix:
        path = path.with_suffix(".md")

    if not path.exists():
        raise FileNotFoundError(f"Directive not found: {path}")

    return path.read_text()


def load_webhooks() -> dict:
    """Load webhooks configuration."""
    webhooks_path = EXECUTION_DIR / "webhooks.json"
    return json.loads(webhooks_path.read_text())


def save_to_tmp(filename: str, content: str) -> Path:
    """Save content to .tmp directory."""
    path = TMP_DIR / filename
    path.write_text(content)
    return path


def load_from_tmp(filename: str) -> str:
    """Load content from .tmp directory."""
    path = TMP_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Temp file not found: {path}")
    return path.read_text()
