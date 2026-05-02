"""Scanner package — public API re-exports.

Import directly from the submodules (e.g. ``from src.prospecting.scanners.models
import ScanResult``) for clarity, or from this package for convenience.
"""

from __future__ import annotations

# --- Data model ---
from .models import ScanResult  # noqa: F401

# --- Orchestrator ---
from .runner import MAX_WORKERS_HTTP, scan_domains  # noqa: F401

# --- Registry (scan-type map, approval validation) ---
# `_SCAN_TYPE_FUNCTIONS` deliberately not re-exported — external modules must
# go through the public accessors so every registered-scan call funnels through
# `valdi.run_gated_scan`.
from .registry import (  # noqa: F401
    _LEVEL0_SCAN_FUNCTIONS,
    _LEVEL1_SCAN_FUNCTIONS,
    _init_scan_type_map,
    _validate_approval_tokens,
    get_scan_function,
    get_scan_functions_for_level,
    iter_registered_scan_types,
)

# --- Compliance ---
from .compliance import _write_pre_scan_check  # noqa: F401

# --- Tool functions (clean names only) ---
from .tls import check_ssl  # noqa: F401
from .headers import get_response_headers  # noqa: F401
from .robots import check_robots_txt  # noqa: F401
from .httpx_scan import run_httpx  # noqa: F401
from .webanalyze import run_webanalyze  # noqa: F401
from .subfinder import run_subfinder  # noqa: F401
from .dnsx import run_dnsx  # noqa: F401
from .ct import query_crt_sh_single, query_crt_sh  # noqa: F401
from .grayhat import query_grayhatwarfare  # noqa: F401
from .nuclei import run_nuclei  # noqa: F401
from .cmseek import run_cmseek  # noqa: F401
from .nmap import parse_nmap_xml, nmap_ports_to_findings, run_nmap  # noqa: F401
from .wordpress import extract_page_meta, extract_rest_api_plugins  # noqa: F401

# --- Constants ---
from .nuclei import NUCLEI_RATE_LIMIT, NUCLEI_CONCURRENCY, NUCLEI_TIMEOUT  # noqa: F401
from .cmseek import CMSEEK_TIMEOUT, CMSEEK_PATH  # noqa: F401
from .nmap import (  # noqa: F401
    NMAP_TIMEOUT,
    NMAP_TOP_PORTS,
    NMAP_SUPPLEMENT_PORTS,
    _NMAP_PORT_SEVERITY,
    _NMAP_PORT_LABELS,
)
from .cmseek import _DOMAIN_RE  # noqa: F401
from .wordpress import (  # noqa: F401
    _NAMESPACE_TO_SLUG,
    _GENERATOR_TO_SLUG,
    _CSS_CLASS_SIGNATURES,
)
