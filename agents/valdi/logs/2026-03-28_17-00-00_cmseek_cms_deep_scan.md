# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-28T17:00:00Z
- **Scan type:** CMS deep fingerprinting via CMSeek
- **Scan type ID:** cmseek_cms_deep_scan
- **Declared Layer:** 2 (Active probing)
- **Declared Level:** 1 (Written consent required)
- **Verdict:** APPROVED
- **Approval token:** bf921a05-dc95-4ff9-99cf-0b9f8630aaf3
- **Function hash:** sha256:f4ae289a1b3933a9452ccca10244b43e9d18eb42cd8a2e1599a7d491826526d3
- **Triggered by:** Claude Code (Sprint 3.2 — CMSeek)

## Function Reviewed

`_run_cmseek(domains: list[str]) -> dict[str, dict]`

**File:** `src/prospecting/scanner.py`

## Tools Invoked

- CMSeek (Python, git clone at `/opt/cmseek`)
- Flags: `--batch --follow-redirect --user-agent "Heimdall-EASM/1.0 (authorised-scan)"`

## URLs/Paths Requested

CMSeek probes paths not linked from public pages:
- `/admin/`, `/manager/`, `/administrator/` — admin panel detection
- `/readme.html`, `/license.txt` — CMS version fingerprinting
- `/wp-content/plugins/*/readme.txt` — plugin detection (WordPress deep scan)
- `/wp-json/wp/v2/users` — user enumeration (WordPress deep scan)

These are explicitly forbidden at Level 0 per SCANNING_RULES.md.

## Output Pattern

CMSeek writes results to `Result/<domain>/cms.json` (file-based, not stdout). The function reads this file, parses JSON, then cleans up the result directory.

## Enforcement Chain

1. `_LEVEL1_SCAN_FUNCTIONS` registry — only called when `max_level >= 1`
2. `execute_scan_job` Level 1 gate — `job_level >= 1`
3. Worker Gate 2 — `check_consent()` blocks without valid consent
4. `_validate_approval_tokens(max_level=1)` — requires this token

## Violations

None.
