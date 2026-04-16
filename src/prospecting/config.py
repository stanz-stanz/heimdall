"""Pipeline configuration: prospecting-specific settings and JSON-loaded classification data.

Shared constants (PROJECT_ROOT, CONFIG_DIR, etc.) live in ``src.core.config``
and are re-exported here for backwards compatibility within the prospecting
package.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

# --- Re-export shared constants from core ---
from src.core.secrets import get_secret
from src.core.config import (  # noqa: F401
    BRIEFS_DIR,
    CONFIG_DIR,
    DATA_DIR,
    DEFAULT_FILTERS,
    DEFAULT_INPUT,
    PROJECT_ROOT,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

# --- Path not in core (prospecting-only) ---
INDUSTRY_CODES_PATH = CONFIG_DIR / "industry_codes.json"

# --- Excel column indices (0-based) ---
COL_CVR = 0
COL_START_DATE = 1
COL_END_DATE = 2
COL_NAME = 3
COL_ADDRESS = 4
COL_POSTCODE = 5
COL_CITY = 6
COL_COMPANY_FORM = 7
COL_INDUSTRY = 8
COL_PHONE = 9
COL_EMAIL = 10
COL_AD_PROTECTED = 11

# --- External API settings ---
CRT_SH_API_URL = "https://crt.sh"
CRT_SH_DELAY = 2.0  # seconds between requests (avoid 429s from crt.sh)
GRAYHATWARFARE_API_KEY = get_secret("grayhatwarfare_api_key", "GRAYHATWARFARE_API_KEY")

# --- CLI tool timeouts ---
SUBFINDER_TIMEOUT = 300  # 5 min — sufficient for ~23 passive-only domains per batch
DNSX_TIMEOUT = 300  # 5 min

# --- Enrichment pre-scan settings ---
ENRICHMENT_WORKERS = int(os.environ.get("ENRICHMENT_WORKERS", "3"))
ENRICHMENT_STAGGER_SECONDS = int(os.environ.get("ENRICHMENT_STAGGER_SECONDS", "10"))
ENRICHMENT_RETRY_LIMIT = 1
SUBFINDER_THREADS = int(os.environ.get("SUBFINDER_THREADS", "10"))
SUBFINDER_MAX_ENUM_TIME = int(os.environ.get("SUBFINDER_MAX_ENUM_TIME", "3"))  # minutes per domain


# --- Go binary PATH setup (call explicitly, not at import time) ---

def ensure_go_bin_on_path() -> None:
    """Add ~/go/bin to PATH if it exists and is not already present."""
    go_bin = Path.home() / "go" / "bin"
    if go_bin.is_dir() and str(go_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{go_bin}:{os.environ.get('PATH', '')}"


# --- JSON-loaded classification data (lazy via @functools.cache) ---

def _load_json(filename: str):
    """Load a JSON config file from the config/ directory."""
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


@functools.cache
def get_bucket_config() -> tuple[set, set, set]:
    """Return (BUCKET_A_CMS, BUCKET_B_CMS, BUCKET_C_PLATFORMS)."""
    buckets = _load_json("buckets.json")
    return (
        set(buckets["A"]["cms"]),
        set(buckets["B"]["cms"]),
        set(buckets["C"]["platforms"]),
    )


@functools.cache
def get_gdpr_config() -> dict:
    """Return GDPR signal sets."""
    gdpr = _load_json("gdpr_signals.json")
    return {
        "codes": gdpr["industry_codes"],
        "plugins": set(gdpr["data_handling_plugins"]),
        "tracking": set(gdpr["tracking_tech"]),
        "ecommerce": set(gdpr["ecommerce_cms"]),
        "sensitive_tech": set(gdpr["sensitive_tech"]),
    }


@functools.cache
def get_free_webmail() -> frozenset:
    """Return frozenset of free webmail domains."""
    return frozenset(_load_json("free_webmail.json"))


# --- Backwards-compatible module-level constants ---
# These eagerly evaluate on first import to maintain existing behaviour
# within the prospecting package.  Cross-package consumers should import
# shared constants from src.core.config instead.

_buckets = _load_json("buckets.json")
BUCKET_A_CMS = set(_buckets["A"]["cms"])
BUCKET_B_CMS = set(_buckets["B"]["cms"])
BUCKET_C_PLATFORMS = set(_buckets["C"]["platforms"])

_gdpr = _load_json("gdpr_signals.json")
GDPR_SENSITIVE_CODES = _gdpr["industry_codes"]
GDPR_DATA_HANDLING_PLUGINS = set(_gdpr["data_handling_plugins"])
GDPR_TRACKING_TECH = set(_gdpr["tracking_tech"])
GDPR_ECOMMERCE_CMS = set(_gdpr["ecommerce_cms"])
SENSITIVE_TECH = set(_gdpr["sensitive_tech"])

FREE_WEBMAIL = frozenset(_load_json("free_webmail.json"))

HOSTING_PROVIDERS = _load_json("hosting_providers.json")
CMS_KEYWORDS = _load_json("cms_keywords.json")

# Ensure go binaries are discoverable (called here for backwards compat
# — callers that imported prospecting.config relied on this side effect).
ensure_go_bin_on_path()
