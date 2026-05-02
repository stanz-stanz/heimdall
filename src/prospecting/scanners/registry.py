"""Scan type registry — maps scan type IDs to their implementing functions.

Split by level:
- Level 0: passive observation only (Layer 1)
- Level 1: active probing (Layer 2), requires written consent
"""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
from collections.abc import Callable

from loguru import logger


# Internal level dicts. Module-private; external code must use the public
# accessors (`get_scan_function`, `get_scan_functions_for_level`,
# `iter_registered_scan_types`). The mutable dispatch map used to be exported
# as `_SCAN_TYPE_FUNCTIONS`, which let runner.py / scan_job.py compose their
# own "lookup then call" path and bypass `valdi.run_gated_scan`. That export
# is intentionally removed — see Valdí runtime hardening (per-thread gate
# context + single execution API).
_LEVEL0_SCAN_FUNCTIONS: dict[str, callable] = {}
_LEVEL1_SCAN_FUNCTIONS: dict[str, callable] = {}

# Reentrant lock guarding init + lookup of the level dicts. Necessary because
# `_init_scan_type_map` does ``clear()`` then ``update()`` — without this
# lock, concurrent ``get_scan_function`` calls from runner pool workers can
# observe a partially-cleared dict and raise ``KeyError`` for a real scan
# type. RLock so that nested public accessors (e.g. an init that internally
# calls another accessor) do not self-deadlock.
_REGISTRY_LOCK = threading.RLock()

# One-shot init flag. Production callers (`worker/main.py`, `runner.py`,
# accessors) all run `_init_scan_type_map()` defensively, but the underlying
# imports are stable for the process lifetime. Without idempotency, every
# `get_scan_function` cache-miss on the worker hot path pays for the full
# import + dict rebuild. Tests that monkeypatch a scanner module call
# `_force_reinit_scan_type_map()` to refresh the registry against the
# patched source.
_INITIALIZED: bool = False


def _init_scan_type_map() -> None:
    """Populate the scan type function maps. One-shot per process.

    Holds ``_REGISTRY_LOCK`` so concurrent ``get_scan_function`` callers
    cannot observe a partial state. Subsequent calls after the first
    successful population are O(1) — they take the lock, see
    ``_INITIALIZED``, and return.

    Tests that monkeypatch a scanner-module attribute (and therefore need
    the registry to re-import) must call ``_force_reinit_scan_type_map()``
    explicitly while their patch is active.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _REGISTRY_LOCK:
        if _INITIALIZED:
            return
        _populate_scan_type_map()
        _INITIALIZED = True


def _force_reinit_scan_type_map() -> None:
    """Test helper: clear + repopulate the level dicts unconditionally.

    Use after activating a monkeypatch on a scanner module so the registry
    re-imports the patched attribute. Production code never calls this.
    """
    global _INITIALIZED
    with _REGISTRY_LOCK:
        _INITIALIZED = False
        _populate_scan_type_map()
        _INITIALIZED = True


def _populate_scan_type_map() -> None:
    """Internal: run the imports and rebuild both level dicts atomically.

    Caller must hold ``_REGISTRY_LOCK``.
    """
    # Import from extracted scanner modules (P2-3)
    from src.prospecting.scanners.tls import check_ssl as _check_ssl
    from src.prospecting.scanners.wordpress import extract_page_meta as _extract_page_meta
    from src.prospecting.scanners.headers import get_response_headers as _get_response_headers
    from src.prospecting.scanners.ct import query_crt_sh as _query_crt_sh
    from src.prospecting.scanners.grayhat import query_grayhatwarfare as _query_grayhatwarfare
    from src.prospecting.scanners.cmseek import run_cmseek as _run_cmseek
    from src.prospecting.scanners.dnsx import run_dnsx as _run_dnsx
    from src.prospecting.scanners.httpx_scan import run_httpx as _run_httpx
    from src.prospecting.scanners.nmap import run_nmap as _run_nmap
    from src.prospecting.scanners.nuclei import run_nuclei as _run_nuclei
    from src.prospecting.scanners.subfinder import run_subfinder as _run_subfinder
    from src.prospecting.scanners.webanalyze import run_webanalyze as _run_webanalyze

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


def _validate_approval_tokens(max_level: int = 0) -> dict | None:
    """Validate scan types have current approval tokens with matching function hashes.

    Only validates functions at or below *max_level*. A Level 0 worker does
    not need approval tokens for Level 1 scan types.

    For approvals that carry `helper_hash` + `helper_function`, the helper is
    re-hashed and compared too. Invariant: the helper must be a module-level
    attribute of the wrapper's own module. Lambdas, non-callables, and
    unsourceable builtins are rejected. Any mismatch fails the whole boot
    and names `scripts/valdi/regenerate_approvals.py --apply` as the remedy.

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

        if not _validate_helper_hash(scan_type_id, func, approval):
            return None

    return data


def _load_approvals_data() -> dict:
    from src.prospecting.config import PROJECT_ROOT

    approvals_path = PROJECT_ROOT / ".claude" / "agents" / "valdi" / "approvals.json"
    with open(approvals_path, encoding="utf-8") as f:
        return json.load(f)


def get_scan_functions_for_level(max_level: int) -> dict[str, Callable]:
    _init_scan_type_map()
    with _REGISTRY_LOCK:
        functions: dict[str, Callable] = {}
        functions.update(_LEVEL0_SCAN_FUNCTIONS)
        if max_level >= 1:
            functions.update(_LEVEL1_SCAN_FUNCTIONS)
    return functions


def get_scan_function(scan_type_id: str) -> Callable:
    _init_scan_type_map()
    with _REGISTRY_LOCK:
        if scan_type_id in _LEVEL0_SCAN_FUNCTIONS:
            return _LEVEL0_SCAN_FUNCTIONS[scan_type_id]
        return _LEVEL1_SCAN_FUNCTIONS[scan_type_id]


def iter_registered_scan_types(max_level: int = 1) -> tuple[str, ...]:
    """Public: ordered tuple of every scan-type ID registered up to *max_level*.

    Replaces direct iteration over the (now-private) dispatch dicts. Used by
    callers that need to enumerate authorised scan types — operator summary,
    Valdí envelope catalog, gate `allowed_scan_types` construction in tests.
    """
    _init_scan_type_map()
    with _REGISTRY_LOCK:
        types = list(_LEVEL0_SCAN_FUNCTIONS)
        if max_level >= 1:
            types.extend(_LEVEL1_SCAN_FUNCTIONS)
    return tuple(sorted(types))


def build_validated_scan_catalog(max_level: int) -> dict[str, dict]:
    """Return the validated scan-type catalog for *max_level*.

    Raises:
        RuntimeError: Approval tokens are missing or invalid.
    """
    _init_scan_type_map()
    data = _validate_approval_tokens(max_level=max_level)
    if data is None:
        raise RuntimeError("Valdi approval token validation failed")

    approvals = {a["scan_type_id"]: a for a in data.get("approvals", [])}
    catalog: dict[str, dict] = {}
    for scan_type_id, func in get_scan_functions_for_level(max_level).items():
        approval = approvals[scan_type_id]
        catalog[scan_type_id] = {
            "function_hash": approval["function_hash"],
            "helper_hash": approval.get("helper_hash"),
            "level": approval["level"],
            "approval_token": approval["token"],
            "module": func.__module__,
            "function_name": func.__name__,
        }
    return catalog


def _validate_helper_hash(scan_type_id: str, func: callable, approval: dict) -> bool:
    """Enforce approval[helper_hash] when present.

    Fails closed on missing helper_function, helper not co-located with the
    wrapper's module, non-callable helper, lambda, unsourceable helper, or
    hash mismatch. Returns True if the approval has no helper_hash (the
    common case) or the helper matches.
    """
    helper_hash = approval.get("helper_hash")
    if not helper_hash:
        return True

    remedy = "`python scripts/valdi/regenerate_approvals.py --apply`"
    helper_name = approval.get("helper_function")
    if not helper_name:
        logger.error(
            "Approval for {} has helper_hash but no helper_function — "
            "malformed entry. Re-submit to Valdi: {}",
            scan_type_id, remedy,
        )
        return False

    module = inspect.getmodule(func)
    helper = getattr(module, helper_name, None)
    if helper is None:
        logger.error(
            "helper_function `{}` is not a module-level attribute of `{}` "
            "for scan type {} — approval invalid. "
            "(Invariant: helpers must co-locate with their wrapper module.) "
            "Re-submit to Valdi: {}",
            helper_name,
            module.__name__ if module else "<unknown>",
            scan_type_id,
            remedy,
        )
        return False

    if not callable(helper):
        logger.error(
            "helper_function `{}` for {} resolves to a non-callable — "
            "approval invalid. Re-submit to Valdi: {}",
            helper_name, scan_type_id, remedy,
        )
        return False

    if getattr(helper, "__name__", "") == "<lambda>":
        logger.error(
            "helper_function `{}` for {} is a lambda — lambdas are not "
            "approval-gated. Refactor to a named function. "
            "Re-submit to Valdi: {}",
            helper_name, scan_type_id, remedy,
        )
        return False

    try:
        helper_source = inspect.getsource(helper).encode("utf-8")
    except (TypeError, OSError) as e:
        logger.error(
            "Cannot read source of helper `{}` for {} ({}). "
            "Approval invalid. Re-submit to Valdi: {}",
            helper_name, scan_type_id, e, remedy,
        )
        return False

    current_helper_hash = "sha256:" + hashlib.sha256(helper_source).hexdigest()
    if current_helper_hash != helper_hash:
        logger.error(
            "Helper hash mismatch for {}::{} — approval token invalidated. "
            "Re-submit to Valdi: {}",
            scan_type_id, helper_name, remedy,
        )
        return False

    return True
