"""Scan type registry — maps scan type IDs to their implementing functions.

Split by level:
- Level 0: passive observation only (Layer 1)
- Level 1: active probing (Layer 2), requires written consent
"""

from __future__ import annotations

import hashlib
import inspect
import json

from loguru import logger


# Level 0: passive observation only (Layer 1)
_LEVEL0_SCAN_FUNCTIONS: dict[str, callable] = {}

# Level 1: active probing (Layer 2), requires written consent
_LEVEL1_SCAN_FUNCTIONS: dict[str, callable] = {}

# Combined view for backward compatibility
_SCAN_TYPE_FUNCTIONS: dict[str, callable] = {}


def _init_scan_type_map() -> None:
    """Populate the scan type function maps. Called once at module load."""
    # Deferred imports — scan functions still live in scanner.py (moved in P2-3)
    from src.prospecting.scanner import (
        _check_ssl,
        _extract_page_meta,
        _get_response_headers,
        _query_crt_sh,
        _query_grayhatwarfare,
        _run_cmseek,
        _run_dnsx,
        _run_httpx,
        _run_nmap,
        _run_nuclei,
        _run_subfinder,
        _run_webanalyze,
    )

    _LEVEL0_SCAN_FUNCTIONS.clear()
    _LEVEL0_SCAN_FUNCTIONS.update({
        "ssl_certificate_check": _check_ssl,
        "homepage_meta_extraction": _extract_page_meta,
        "httpx_tech_fingerprint": _run_httpx,
        "webanalyze_cms_detection": _run_webanalyze,
        "response_header_check": _get_response_headers,
        "subdomain_enumeration_passive": _run_subfinder,
        "dns_enrichment": _run_dnsx,
        "certificate_transparency_query": _query_crt_sh,
        "cloud_storage_index_query": _query_grayhatwarfare,
    })

    _LEVEL1_SCAN_FUNCTIONS.clear()
    _LEVEL1_SCAN_FUNCTIONS.update({
        "nuclei_vulnerability_scan": _run_nuclei,
        "cmseek_cms_deep_scan": _run_cmseek,
        "nmap_port_scan": _run_nmap,
    })

    # Backward-compat: combined view
    _SCAN_TYPE_FUNCTIONS.clear()
    _SCAN_TYPE_FUNCTIONS.update(_LEVEL0_SCAN_FUNCTIONS)
    _SCAN_TYPE_FUNCTIONS.update(_LEVEL1_SCAN_FUNCTIONS)


def _validate_approval_tokens(max_level: int = 0) -> dict | None:
    """Validate scan types have current approval tokens with matching function hashes.

    Only validates functions at or below *max_level*. A Level 0 worker does
    not need approval tokens for Level 1 scan types.

    Returns the approvals dict on success, None on failure.
    """
    from src.prospecting.config import PROJECT_ROOT

    approvals_path = PROJECT_ROOT / ".claude" / "agents" / "valdi" / "approvals.json"
    try:
        with open(approvals_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("Cannot read approval tokens: {}", e)
        return None

    approvals = {a["scan_type_id"]: a for a in data.get("approvals", [])}

    # Build set of functions that need validation at this level
    required_functions: dict[str, callable] = {}
    required_functions.update(_LEVEL0_SCAN_FUNCTIONS)
    if max_level >= 1:
        required_functions.update(_LEVEL1_SCAN_FUNCTIONS)

    for scan_type_id, func in required_functions.items():
        approval = approvals.get(scan_type_id)
        if not approval:
            logger.error("No approval token for scan type: {}", scan_type_id)
            return None

        current_hash = "sha256:" + hashlib.sha256(
            inspect.getsource(func).encode("utf-8")
        ).hexdigest()
        if current_hash != approval["function_hash"]:
            logger.error(
                "Function hash mismatch for {} — approval token invalidated. "
                "Re-submit to Valdi for Gate 1 review.",
                scan_type_id,
            )
            return None

    return data
