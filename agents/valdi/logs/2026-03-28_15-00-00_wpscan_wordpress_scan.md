# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-28T15:00:00Z
- **Scan type:** WordPress vulnerability and plugin scanning via WPScan
- **Scan type ID:** wpscan_wordpress_scan
- **Declared Layer:** 2 (Active probing)
- **Declared Level:** 1 (Written consent required)
- **Verdict:** APPROVED
- **Approval token:** c9c5d87c-5500-4840-a737-d071287d072c
- **Function hash:** sha256:6943393dd053eb15ad074b777e65c264222d3579421e8e8ce2dacd295444635c
- **Triggered by:** Claude Code (Sprint 3.2 — WPScan follow-up)

## Function Reviewed

`_run_wpscan(domains: list[str]) -> dict[str, dict]`

**File:** `src/prospecting/scanner.py`

## Tools Invoked

- `wpscan` CLI (Ruby gem) — WordPress security scanner
- Flags: `--format json --no-banner --random-user-agent --disable-tls-checks --enumerate vp,vt,u1-3`
- Optional: `--api-token` for vulnerability database cross-reference

## URLs/Paths Requested

WPScan probes WordPress-specific paths that are NOT linked from public pages:
- `/wp-admin/`, `/wp-login.php` — admin panel detection
- `/wp-content/plugins/*/readme.txt` — plugin version detection
- `/wp-content/themes/*/style.css` — theme version detection
- `/readme.html`, `/license.txt` — WordPress core version detection
- `/wp-includes/` — core file fingerprinting

These are explicitly forbidden at Level 0 per SCANNING_RULES.md: "Requesting paths not linked from public pages."

## robots.txt Handling

**Delegated.** Same enforcement chain as nuclei — worker Gate 2 validates consent before any Level 1 scans execute.

## Reasoning

WPScan is explicitly listed in SCANNING_RULES.md as a **Level 1 tool**: "WPScan — WordPress-specific vulnerability and plugin scanning (requires commercial API license — free tier is non-commercial only)." It is also explicitly **forbidden at Level 0**.

This function:
1. **IS Layer 2 (active probing)** — probes admin paths, plugin version files, and theme files
2. **Requires Level 1 consent** — enforced by the level-gated registry
3. Runs per-domain sequentially (not batched) with 120s timeout per domain
4. Works with or without API token — limited mode (no vuln DB) logs a warning
5. Only accepts exit codes 0 (no vulns) and 5 (vulns found) as valid
6. Returns structured data: vulnerabilities, WP version, plugins, themes

### Commercial API note

SCANNING_RULES.md notes: "requires commercial API license — free tier is non-commercial only." The `WPSCAN_API_TOKEN` env var controls this. Without a token, WPScan still detects versions, plugins, and themes — it just cannot cross-reference the vulnerability database. A warning is logged. The commercial license question is tracked in the decision log as unresolved.

## Violations

None.
