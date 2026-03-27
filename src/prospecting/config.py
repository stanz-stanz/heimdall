"""Pipeline configuration: paths, runtime settings, and JSON-loaded classification data."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Ensure Go binaries are discoverable
_go_bin = Path.home() / "go" / "bin"
if _go_bin.is_dir() and str(_go_bin) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_go_bin}:{os.environ.get('PATH', '')}"

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/prospecting/config.py → repo root
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data" / "output"
BRIEFS_DIR = DATA_DIR / "briefs"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "input" / "CVR-extract.xlsx"
DEFAULT_FILTERS = CONFIG_DIR / "filters.json"
INDUSTRY_CODES_PATH = CONFIG_DIR / "industry_codes.json"

# --- Excel column indices (0-based) ---
COL_CVR = 0
COL_NAME = 1
COL_ADDRESS = 2
COL_POSTCODE = 3
COL_CITY = 4
COL_COMPANY_FORM = 5
COL_INDUSTRY = 6
COL_PHONE = 7
COL_EMAIL = 8
COL_AD_PROTECTED = 9

# --- HTTP settings ---
REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# --- External API settings ---
CRT_SH_API_URL = "https://crt.sh"
CRT_SH_DELAY = 2.0  # seconds between requests (avoid 429s from crt.sh)
GRAYHATWARFARE_API_KEY = os.environ.get("GRAYHATWARFARE_API_KEY", "")

# --- CLI tool timeouts ---
SUBFINDER_TIMEOUT = 300  # 5 min — sufficient for ~23 passive-only domains per batch
DNSX_TIMEOUT = 300  # 5 min

# --- Enrichment pre-scan settings ---
ENRICHMENT_WORKERS = int(os.environ.get("ENRICHMENT_WORKERS", "3"))
ENRICHMENT_STAGGER_SECONDS = int(os.environ.get("ENRICHMENT_STAGGER_SECONDS", "10"))
ENRICHMENT_RETRY_LIMIT = 1
SUBFINDER_THREADS = int(os.environ.get("SUBFINDER_THREADS", "10"))
SUBFINDER_MAX_ENUM_TIME = int(os.environ.get("SUBFINDER_MAX_ENUM_TIME", "3"))  # minutes per domain


# --- JSON-loaded classification data ---
def _load_json(filename: str):
    """Load a JSON config file from the config/ directory."""
    with open(CONFIG_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# Bucket classification rules
_buckets = _load_json("buckets.json")
BUCKET_A_CMS = set(_buckets["A"]["cms"])
BUCKET_B_CMS = set(_buckets["B"]["cms"])
BUCKET_C_PLATFORMS = set(_buckets["C"]["platforms"])

# GDPR signals
_gdpr = _load_json("gdpr_signals.json")
GDPR_SENSITIVE_CODES = _gdpr["industry_codes"]
GDPR_DATA_HANDLING_PLUGINS = set(_gdpr["data_handling_plugins"])
GDPR_TRACKING_TECH = set(_gdpr["tracking_tech"])
GDPR_ECOMMERCE_CMS = set(_gdpr["ecommerce_cms"])
SENSITIVE_TECH = set(_gdpr["sensitive_tech"])

# Free webmail providers
FREE_WEBMAIL = frozenset(_load_json("free_webmail.json"))

# Technology detection lookups
HOSTING_PROVIDERS = _load_json("hosting_providers.json")
CMS_KEYWORDS = _load_json("cms_keywords.json")
