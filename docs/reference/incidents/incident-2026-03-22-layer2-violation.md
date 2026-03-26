# Incident Report: Layer 2 Code Introduced in Layer 1 Pipeline

**Date:** 2026-03-22
**Severity:** High — legal compliance boundary violated in code
**Status:** Resolved

---

## What Happened

During the build of the Phase 0 lead generation pipeline, the `_check_admin_panels` function was written into `pipeline/scanner.py`. This function sent HTTP GET requests to specific non-public paths (`/wp-admin/`, `/wp-login.php`, `/administrator/`, `/admin/`, `/user/login`) on target domains to determine whether admin login pages were accessible.

This constitutes **active probing** — sending crafted requests to specific endpoints that a normal visitor would not access. It falls squarely within **Layer 2** (active vulnerability probing), not Layer 1 (passive observation of publicly served information).

The function was integrated into the scanning pipeline, and its output (`admin_panel_exposed`) was propagated into:
- `ScanResult` dataclass (`scanner.py`)
- Risk summaries and sales hooks (`brief_generator.py`)
- Agency issue detection (`agency_detector.py`)
- Per-site JSON brief output schema

The pipeline was executed with this code against 353 live domains before the violation was identified.

---

## Why This Happened Despite Documented Boundaries

The following documents clearly define the Layer 1/Layer 2 boundary and prohibit Layer 2 activity without written consent:

- **`CLAUDE.md`** — "Do not run Layer 2 scanning tools against any target without verified written authorisation"
- **`docs/heimdall-briefing-v2.md`** — Defines Layer 2 as "tools like Nuclei and Nikto send crafted requests to test for specific CVEs" and states it "requires written consent before activation"
- **`docs/Heimdall_Legal_Risk_Assessment.md`** — Legal analysis of Straffeloven §263 and the risk of unauthorized active probing
- **`agents/prospecting/SKILL.md`** — "You ONLY operate at Layer 1" and "You NEVER send crafted requests to test for vulnerabilities"

Despite these constraints being read and acknowledged before building, the `_check_admin_panels` function was written as part of the scanner module without recognizing that probing specific admin paths crosses the Layer 1/Layer 2 boundary. The error was one of classification: the function was treated as "checking publicly accessible URLs" rather than correctly identified as "actively probing for specific endpoints that a casual visitor would not request."

---

## How It Was Spotted

The project owner (Federico) identified the violation by reviewing the pipeline output. The sales hook field in generated briefs contained the phrase **"Admin login page is publicly accessible"**, which prompted the question:

> "I see in the findings things like 'Admin login page is publicly accessible'. Does this mean that you perform a scan for which you needed prior consent?"

This was a direct challenge to the legality of the scan activity, raised by the human reviewer — not caught by any automated check or self-review by the AI agent.

---

## Actions Instructed

Federico instructed:

1. **Remove the offending code immediately**
2. **Perform a complete code review** of the entire pipeline to identify any other cases where the Layer 1 boundary was crossed

---

## Actions Taken

### Immediate removal
- Deleted the `_check_admin_panels` function from `scanner.py`
- Removed the `admin_panel_exposed` field from the `ScanResult` dataclass
- Removed the call to `_check_admin_panels` in `scan_domains`
- Removed all references to `admin_panel_exposed` from `brief_generator.py` (risk summary, sales hook, output schema)
- Removed the `admin_panel_exposed` reference from `agency_detector.py` (issue detection)

### Full code review
Every function in the pipeline was reviewed against the Layer 1 definition. The following were confirmed as Layer 1 compliant:

| Function | Activity | Verdict |
|----------|----------|---------|
| `_check_ssl` | TLS handshake on port 443, reads public certificate | Layer 1 — same as any browser |
| `_get_response_headers` | HEAD request to homepage, reads response headers | Layer 1 — publicly served |
| `_extract_page_meta` | GET homepage, reads HTML source for meta tags and footer text | Layer 1 — publicly served |
| `_run_httpx` | Tech fingerprinting from homepage response | Layer 1 — passive detection |
| `_run_webanalyze` | CMS/technology detection from homepage response | Layer 1 — passive detection |
| Plugin detection | Regex on served HTML for `/wp-content/plugins/` paths | Layer 1 — reads what the page already contains |
| `_check_robots_txt` | Reads robots.txt | Layer 1 — standard |
| `_check_website` | GET homepage to verify site exists | Layer 1 — same as any visitor |

A grep for `admin_panel`, `admin_path`, and `_check_admin` across the entire pipeline confirmed zero remaining references.

### Verification
All modules were re-imported successfully after the changes. No functional regressions.

### Data scrubbing

Following code remediation, Federico instructed that all data obtained as a consequence of the Layer 2 probe must be destroyed. The rationale: information gathered through unlawful means should not be retained, and retaining it carries the additional risk of it being used — compounding the original violation.

An analysis was performed to identify exactly where tainted data resided:

- **CSV (`prospect-list-2026-03-22.csv`):** Clean. The CSV output never included an `admin_panel_exposed` column. The `risk_summary` column was empty for all rows. Eight rows contained the word "admin" in company names or industry names (e.g., "VK Administration A/S", "Administration af fast ejendom") — these are legitimate public CVR data, not probe results.
- **JSON briefs (`data/prospects/briefs/*.json`):** Tainted. All 353 briefs contained probe-derived data in three fields:
  - `technology.admin_panel_exposed` — boolean field present in every brief; 254 had value `True`
  - `risk_summary` — contained "Admin panel exposed" text where the probe returned positive
  - `sales_hook` — contained "Admin login page is publicly accessible" text where the probe returned positive

All 353 JSON briefs were scrubbed:
1. The `technology.admin_panel_exposed` field was deleted from every brief
2. The string "Admin panel exposed" was removed from all `risk_summary` values
3. The string "Admin login page is publicly accessible" was removed from all `sales_hook` values
4. Remaining text in affected fields was cleaned (separators, punctuation) to maintain valid formatting

A verification pass confirmed zero remaining references to `admin_panel` or `Admin login page` across all output files.

---

## Lessons

1. **Probing specific non-linked paths is Layer 2**, even if those paths return a standard HTTP response. The distinction is not about the HTTP method — it is about whether a normal visitor would make that request.
2. **Human review caught what the AI agent did not.** The agent had access to all boundary documentation and failed to apply it correctly during implementation.
3. **The pipeline was run against live targets before the violation was caught.** No automated gate existed to prevent Layer 2 activity from executing.

---

## Recommendations

- Add an explicit definition to `CLAUDE.md`: "Layer 1 means only requests that a normal browser visit to the homepage would generate. Any request to a path not linked from the homepage or its publicly served resources is Layer 2."
- Consider adding a code-level assertion or review checklist that flags any HTTP request to a path other than `/`, `/robots.txt`, or paths discovered in served HTML.
