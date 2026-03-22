# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:11:00Z
- **Scan type:** Passive domain scan orchestrator (batch Layer 1 scanning) — v2 rewrite
- **Scan type ID:** passive_domain_scan_orchestrator
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** b619e44e-9521-4a32-8ee2-9e6ff8bab9cb
- **Function hash:** sha256:44119902f59d78ceddbd54c5d308a985db7f11a8162e14edd11de3b9121b87f2
- **Triggered by:** Claude Code (rewrite to resolve 2026-03-22_10-05-00 rejection)
- **Supersedes:** logs/valdi/2026-03-22_10-05-00_passive_domain_scan_orchestrator.md (REJECTED)

## Previous Rejection

This function was rejected in Gate 1 review on 2026-03-22T10:05:00Z with three violations:

1. No robots.txt check before passing domains to scan functions
2. Batch tools received unfiltered domain list
3. No approval token validation before execution

All three violations have been addressed in this rewrite.

## Function Reviewed

```python
def scan_domains(companies: list[Company]) -> dict[str, ScanResult]:
    """Layer 1 / Level 0 — Run passive technology fingerprinting on all non-discarded companies.

    Validates Valdi approval tokens and function hashes before execution.
    Filters domains through robots.txt before any scanning activity.
    Returns dict keyed by domain.
    """
    _init_scan_type_map()

    # Gate check: validate all approval tokens and function hashes
    if not _validate_approval_tokens():
        log.error("BLOCKED — Valdi approval token validation failed. No scans will execute.")
        return {}

    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    log.info("Scanning %d unique domains (Layer 1 passive only)", len(domains))

    # robots.txt pre-filter — BEFORE any scanning activity
    allowed_domains = []
    skipped_domains = []
    for domain in domains:
        if _check_robots_txt(domain):
            allowed_domains.append(domain)
        else:
            skipped_domains.append(domain)
            log.info("SKIPPED %s — robots.txt denies automated access", domain)

    if skipped_domains:
        log.info(
            "robots.txt filter: %d allowed, %d skipped",
            len(allowed_domains), len(skipped_domains),
        )

    if not allowed_domains:
        log.warning("No domains passed robots.txt filter — nothing to scan")
        return {}

    # Write pre-scan compliance check (Gate 2 batch check)
    pre_scan_path = _write_pre_scan_check(allowed_domains, skipped_domains)
    log.info("Pre-scan check: %s", pre_scan_path)

    # Batch scans with CLI tools — only robots.txt-allowed domains
    httpx_results = _run_httpx(allowed_domains)
    webanalyze_results = _run_webanalyze(allowed_domains)

    # ... per-domain processing (SSL, headers, tech stack, CMS, meta, hosting) ...

    log.info(
        "Layer 1 scanning complete: %d domains scanned, %d skipped (robots.txt)",
        len(results), len(skipped_domains),
    )
    return results
```

(Full source: `pipeline/scanner.py` lines 338-460. Per-domain processing body omitted for brevity — it is unchanged from v1 and uses only approved scan types.)

**File:** `pipeline/scanner.py` (lines 338-460)

## Remediation of Previous Violations

### Violation 1: No robots.txt check (RESOLVED)

Lines 356-370: robots.txt is now checked for every domain BEFORE any scanning activity. Domains that deny automated access are added to `skipped_domains` and logged. Only `allowed_domains` proceed to scanning.

### Violation 2: Batch tools receive unfiltered domain list (RESOLVED)

Lines 380-382: `_run_httpx(allowed_domains)` and `_run_webanalyze(allowed_domains)` now receive only the pre-filtered domain list. No requests are sent to domains that denied automated access.

### Violation 3: No approval token validation (RESOLVED)

Lines 347-350: `_validate_approval_tokens()` is called at function entry. It loads `active_approvals.json`, confirms a valid token exists for every scan type, and verifies each function's SHA-256 hash matches the approved hash. If any check fails, the function returns an empty dict and logs the block. No scanning code executes.

## Tools Invoked

- Calls `_check_robots_txt()` (approved: db78dd3c)
- Calls `_run_httpx()` (approved: 69c956db)
- Calls `_run_webanalyze()` (approved: 474b98c0)
- Calls `_check_ssl()` (approved: 9446c250)
- Calls `_get_response_headers()` (approved: 60ecae45)
- Calls `_extract_page_meta()` (approved: c023519a)
- Calls `_validate_approval_tokens()` (internal compliance function)
- Calls `_write_pre_scan_check()` (internal compliance function)

## URLs/Paths Requested

- `/robots.txt` for each domain (via `_check_robots_txt`) — explicitly published
- `/` (homepage) for allowed domains only (via httpx, webanalyze, `_extract_page_meta`, `_get_response_headers`)
- TLS handshake to port 443 for allowed domains only (via `_check_ssl`)

## robots.txt Handling

Yes. robots.txt is checked for every domain before any scanning activity. Domains that deny automated access are skipped entirely and logged. This check occurs before batch tools receive any domain list.

## Reasoning

The rewritten function addresses all three violations from the prior rejection:

1. **robots.txt enforcement** is now the first gate after token validation. Every domain is checked individually, and only domains that permit automated access proceed to scanning. Skipped domains are logged with the reason.

2. **Batch tool isolation**: `_run_httpx` and `_run_webanalyze` now receive only the filtered `allowed_domains` list. No HTTP requests are sent to denied domains.

3. **Approval token and hash validation**: `_validate_approval_tokens()` runs before any outbound request. It confirms every scan type has a valid token and that every function's current source hash matches the approved hash. If any function has been modified since approval, the entire scan is blocked.

4. **Pre-scan compliance logging**: `_write_pre_scan_check()` writes a JSON record to `data/compliance/` documenting the batch scope, token validation results, and robots.txt filtering. This provides the audit trail specified in SKILL.md's Gate 2 requirements.

The scanning activities themselves remain unchanged — all Layer 1, all targeting only publicly served data on the homepage. The changes are purely compliance infrastructure: validation before execution, filtering before requests, and logging for audit.

## Violations

None.
