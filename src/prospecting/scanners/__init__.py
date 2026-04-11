"""Scanner package — re-exports all public symbols for backward compatibility.

Consumers can import from ``src.prospecting.scanners`` or (via the thin
``scanner.py`` shim) from ``src.prospecting.scanner``.  Both old
underscore-prefixed names and new clean names are exported.
"""

from __future__ import annotations

# --- Data model ---
from .models import ScanResult  # noqa: F401

# --- Orchestrator ---
from .runner import MAX_WORKERS_HTTP, scan_domains  # noqa: F401

# --- Registry (scan-type map, approval validation) ---
from .registry import (  # noqa: F401
    _LEVEL0_SCAN_FUNCTIONS,
    _LEVEL1_SCAN_FUNCTIONS,
    _SCAN_TYPE_FUNCTIONS,
    _init_scan_type_map,
    _validate_approval_tokens,
)

# --- Compliance ---
from .compliance import _write_pre_scan_check  # noqa: F401

# --- Tool functions (new name + underscore-prefixed alias) ---
from .tls import check_ssl  # noqa: F401
from .tls import check_ssl as _check_ssl  # noqa: F401
from .headers import get_response_headers  # noqa: F401
from .headers import get_response_headers as _get_response_headers  # noqa: F401
from .robots import check_robots_txt  # noqa: F401
from .robots import check_robots_txt as _check_robots_txt  # noqa: F401
from .httpx_scan import run_httpx  # noqa: F401
from .httpx_scan import run_httpx as _run_httpx  # noqa: F401
from .webanalyze import run_webanalyze  # noqa: F401
from .webanalyze import run_webanalyze as _run_webanalyze  # noqa: F401
from .subfinder import run_subfinder  # noqa: F401
from .subfinder import run_subfinder as _run_subfinder  # noqa: F401
from .dnsx import run_dnsx  # noqa: F401
from .dnsx import run_dnsx as _run_dnsx  # noqa: F401
from .ct import query_crt_sh_single, query_crt_sh  # noqa: F401
from .ct import query_crt_sh_single as _query_crt_sh_single  # noqa: F401
from .ct import query_crt_sh as _query_crt_sh  # noqa: F401
from .grayhat import query_grayhatwarfare  # noqa: F401
from .grayhat import query_grayhatwarfare as _query_grayhatwarfare  # noqa: F401
from .nuclei import run_nuclei  # noqa: F401
from .nuclei import run_nuclei as _run_nuclei  # noqa: F401
from .cmseek import run_cmseek  # noqa: F401
from .cmseek import run_cmseek as _run_cmseek  # noqa: F401
from .nmap import parse_nmap_xml, nmap_ports_to_findings, run_nmap  # noqa: F401
from .nmap import parse_nmap_xml as _parse_nmap_xml  # noqa: F401
from .nmap import nmap_ports_to_findings as _nmap_ports_to_findings  # noqa: F401
from .nmap import run_nmap as _run_nmap  # noqa: F401
from .wordpress import extract_page_meta, extract_rest_api_plugins  # noqa: F401
from .wordpress import extract_page_meta as _extract_page_meta  # noqa: F401
from .wordpress import extract_rest_api_plugins as _extract_rest_api_plugins  # noqa: F401

# --- Constants re-exported for backward compatibility ---
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

# Explicit __all__ so ``from .scanners import *`` in scanner.py also exports
# underscore-prefixed names (Python's default star-import skips them).
__all__ = [
    # Model
    "ScanResult",
    # Orchestrator
    "MAX_WORKERS_HTTP",
    "scan_domains",
    # Registry
    "_LEVEL0_SCAN_FUNCTIONS",
    "_LEVEL1_SCAN_FUNCTIONS",
    "_SCAN_TYPE_FUNCTIONS",
    "_init_scan_type_map",
    "_validate_approval_tokens",
    # Compliance
    "_write_pre_scan_check",
    # Tool functions — clean names
    "check_ssl",
    "get_response_headers",
    "check_robots_txt",
    "run_httpx",
    "run_webanalyze",
    "run_subfinder",
    "run_dnsx",
    "query_crt_sh_single",
    "query_crt_sh",
    "query_grayhatwarfare",
    "run_nuclei",
    "run_cmseek",
    "parse_nmap_xml",
    "nmap_ports_to_findings",
    "run_nmap",
    "extract_page_meta",
    "extract_rest_api_plugins",
    # Tool functions — underscore-prefixed aliases
    "_check_ssl",
    "_get_response_headers",
    "_check_robots_txt",
    "_run_httpx",
    "_run_webanalyze",
    "_run_subfinder",
    "_run_dnsx",
    "_query_crt_sh_single",
    "_query_crt_sh",
    "_query_grayhatwarfare",
    "_run_nuclei",
    "_run_cmseek",
    "_parse_nmap_xml",
    "_nmap_ports_to_findings",
    "_run_nmap",
    "_extract_page_meta",
    "_extract_rest_api_plugins",
    # Constants
    "NUCLEI_RATE_LIMIT",
    "NUCLEI_CONCURRENCY",
    "NUCLEI_TIMEOUT",
    "CMSEEK_TIMEOUT",
    "CMSEEK_PATH",
    "NMAP_TIMEOUT",
    "NMAP_TOP_PORTS",
    "NMAP_SUPPLEMENT_PORTS",
    "_NMAP_PORT_SEVERITY",
    "_NMAP_PORT_LABELS",
    "_DOMAIN_RE",
    "_NAMESPACE_TO_SLUG",
    "_GENERATOR_TO_SLUG",
    "_CSS_CLASS_SIGNATURES",
]
