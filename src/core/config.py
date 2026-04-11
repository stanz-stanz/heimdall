"""Shared project configuration: paths, HTTP settings, and technology lookups.

Constants used by multiple packages (worker, scheduler, api, prospecting)
live here.  Domain-specific config (Excel columns, bucket rules, GDPR signals)
stays in the owning package.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/core/config.py → repo root
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data" / "output"
BRIEFS_DIR = DATA_DIR / "briefs"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "input" / "CVR-extract.xlsx"
DEFAULT_FILTERS = CONFIG_DIR / "filters.json"

# --- HTTP settings ---
REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# --- Technology detection lookups (lazy-loaded) ---

def _load_json(filename: str):
    """Load a JSON config file from the config/ directory."""
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


@functools.cache
def _cms_keywords() -> dict:
    return _load_json("cms_keywords.json")


@functools.cache
def _hosting_providers() -> dict:
    return _load_json("hosting_providers.json")


# Module-level constants backed by lazy loaders.
# These are properties of a module-level object would be ideal, but for
# backwards compatibility we keep them as plain names that evaluate once
# on first access via __getattr__.

def __getattr__(name: str):
    """Lazy module-level constants for JSON-loaded data."""
    if name == "CMS_KEYWORDS":
        return _cms_keywords()
    if name == "HOSTING_PROVIDERS":
        return _hosting_providers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
