# Sample Valdi Forensic Log Excerpt

**Prepared for:** Legal consultation (see legal briefing Q12, Q13)
**Date:** 2026-04-01
**Status:** Illustrative sample — not from a live scan execution

---

## What This Document Shows

Heimdall operates a programmatic compliance agent called Valdi that validates all scanning code and target authorizations before any scan executes. Valdi produces timestamped forensic logs for every validation decision — both approvals and rejections.

This document contains three sample log entries demonstrating the system's operation:

1. **Gate 1 Approval** — a Layer 1 scanning function is reviewed and approved for execution without client consent (prospecting use)
2. **Gate 1 Rejection** — a scanning function is reviewed and rejected because it contains Layer 2 activity (admin panel probing) that requires client consent but was declared as Layer 1. This entry is based on a real incident where a scanning function crossed the Layer 1 boundary undetected
3. **Gate 2 Pre-Scan Authorization** — a per-target consent check before executing an approved scan type against a consented client domain

All domain names, company names, and technical details are fictional. The log format, reasoning structure, and rule citations are representative of actual Valdi output.

In production, each log entry is stored as an individual timestamped file in the Valdi forensic log directory.

---

## Entry 1: Gate 1 Approval — SSL Certificate Check

---

# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-24T09:15:00Z
- **Scan type:** SSL/TLS certificate validity and configuration check
- **Scan type ID:** ssl_certificate_check
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent required)
- **Verdict:** APPROVED
- **Approval token:** f7a29c83-4e61-4b8d-a912-3dc5e8f01ab7
- **Triggered by:** Claude Code (automatic review on function creation)

## Function Reviewed

Connects to a domain on port 443 using a standard TLS handshake — the same operation every web browser performs when loading an HTTPS page. Reads the publicly served SSL certificate and extracts the following data: certificate expiry date, days until expiry, issuing certificate authority, Subject Alternative Names (SANs), and TLS protocol version. Returns a structured result with these fields plus a validity indicator. If the connection fails or the certificate cannot be verified, the function records the error and returns gracefully. The connection timeout is 10 seconds.

No HTTP requests are made. No data is sent to the target beyond the standard TLS ClientHello message. No paths are requested. Only port 443 (standard HTTPS) is contacted.

## Tools Invoked

- Standard TLS library (Layer 1 — standard TLS handshake, no consent required)
- Standard TCP socket library (Layer 1 — TCP connection to port 443)

## URLs/Paths Requested

- No HTTP paths requested. This function performs a TLS handshake on port 443 only.
- The TLS handshake is identical to what any browser performs when visiting an HTTPS website.

## robots.txt Handling

Not applicable. This function does not make HTTP requests. It performs a TLS handshake to read the publicly served SSL certificate. robots.txt governs HTTP crawling behavior and does not apply to TLS certificate inspection.

Note: The calling pipeline must still check robots.txt before making any HTTP requests to the same domain. This function's exemption applies only to its own TLS handshake, not to the broader scan workflow.

## Reasoning

This function performs a standard TLS handshake on port 443 — the same operation every web browser performs when loading an HTTPS page. The certificate data returned (expiry date, issuer, Subject Alternative Names, protocol version) is publicly served to any TLS client. No crafted probes, no HTTP requests, no path guessing.

Applying the Decision Test from SCANNING_RULES.md: "Does this request go to a URL that a normal person would reach by clicking links on the public website, or does it go to a URL that is being guessed or probed for?" — a TLS handshake is not a URL request at all; it is a prerequisite to any HTTPS connection. Every browser does this. This clearly passes the test.

The function connects only to port 443 (standard HTTPS). No port scanning is performed. The timeout (10 seconds) and error handling are appropriate. No data is sent to the target beyond the standard TLS ClientHello.

**Verdict: APPROVED.** All activities are Layer 1 (passive). No consent required.

---

## Entry 2: Gate 1 Rejection — Admin Panel Probe in Layer 1 Code

---

# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T11:42:00Z
- **Scan type:** Website technology scan with admin panel detection
- **Scan type ID:** website_tech_scan_v1
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent required)
- **Verdict:** REJECTED
- **Approval token:** N/A
- **Triggered by:** Operator review (Federico) after reviewing pipeline output

## Function Reviewed

Iterates through a hardcoded list of five common administrative panel paths (`/wp-admin/`, `/wp-login.php`, `/administrator/`, `/admin/`, `/user/login`) and sends an HTTP GET request to each one on the target domain. If any path returns a successful response (HTTP 200), it records that path as an exposed admin panel. The function follows redirects, uses a 10-second timeout, and disables TLS certificate verification. It does not check robots.txt before sending requests.

The function's internal documentation incorrectly declares it as "Layer 1 / No consent required."

## Tools Invoked

- httpx (Layer 1 tool — but used here for Layer 2 activity)

## URLs/Paths Requested

- `/wp-admin/` — **FORBIDDEN without consent.** Not linked from public pages.
- `/wp-login.php` — **FORBIDDEN without consent.** Not linked from public pages.
- `/administrator/` — **FORBIDDEN without consent.** Not linked from public pages.
- `/admin/` — **FORBIDDEN without consent.** Not linked from public pages.
- `/user/login` — **FORBIDDEN without consent.** Not linked from public pages.

## robots.txt Handling

**No.** The function does not check robots.txt before sending requests. This is an independent violation — even if the paths were permissible, the absence of robots.txt checking would be a compliance failure.

## Reasoning

This function is declared as Layer 1 (passive, no consent required), but its actual behavior is Layer 2 (active probing). The five hardcoded paths (`/wp-admin/`, `/wp-login.php`, `/administrator/`, `/admin/`, `/user/login`) are not publicly linked from any website's homepage or sitemap. They are specific endpoints being guessed and probed for.

Applying the Decision Test from SCANNING_RULES.md: "Does this request go to a URL that a normal person would reach by clicking links on the public website, or does it go to a URL that is being guessed or probed for?" — a normal visitor does not navigate to `/wp-admin/` by clicking links on a public website. These paths are being actively probed. This fails the Decision Test.

SCANNING_RULES.md explicitly lists these paths as forbidden without consent:

> "Requesting paths not linked from public pages. This includes `/wp-admin/`, `/wp-login.php`, `/administrator/`, `/admin/`, `/phpmyadmin/`, `/cpanel/`, `/.env`, `/.git/`, `/xmlrpc.php`, `/server-status`, `/server-info`, or any other path that is not linked from the homepage, sitemap, or robots.txt."

The function's docstring incorrectly declares this as "Layer 1 / No consent required." The declared Layer does not match the actual behavior. This is a material compliance failure.

Additionally, the function disables TLS certificate verification on its own outbound connections. While not a Layer violation, this suppresses security warnings and is poor practice for a security scanning tool.

**Verdict: REJECTED.** The function performs Layer 2 activity (directed path probing) while declaring Layer 1. It cannot execute without written consent from each target domain's owner.

## Violations

| # | Action | Rule Violated | Risk |
|---|--------|--------------|------|
| 1 | Hardcoded admin paths for probing | SCANNING_RULES.md: "Requesting paths not linked from public pages [...] /wp-admin/, /wp-login.php, /administrator/, /admin/" | Straffeloven SS263: directed probes to non-public paths constitute unauthorized access without written consent |
| 2 | GET request to `/wp-admin/` | SCANNING_RULES.md: "If the server would not send this data to a normal visitor browsing the site, you cannot request it." | Same as above — each path probe is a separate potential SS263 violation per target |
| 3 | GET request to `/wp-login.php` | Same rule as #2 | Same risk as #2 |
| 4 | GET request to `/administrator/` | Same rule as #2 | Same risk as #2 |
| 5 | GET request to `/admin/` | Same rule as #2 | Same risk as #2 |
| 6 | GET request to `/user/login` | Same rule as #2 | Same risk as #2 |
| 7 | No robots.txt check | SCANNING_RULES.md: "If a target's robots.txt denies automated access, skip the target entirely." | Independent compliance failure — function will scan targets that have explicitly denied automated access |
| 8 | Declared Layer (1) does not match actual Layer (2) | SCANNING_RULES.md: "Tag every scanning function with its Layer" / "Never combine Layer 1 and Layer 2 actions in the same function" | Mislabeled function could pass automated layer checks and execute without appropriate consent |

## Suggested Remediation

1. **Remove this function entirely from the Layer 1 pipeline.** Admin panel detection is a Layer 2 activity. It cannot be made compliant for use without written consent.

2. **If admin panel detection is needed for consented clients (Sentinel):** Create a separate function, declare it as Layer 2, require a valid consent check (Gate 2) before execution, and add robots.txt checking.

3. **Remove all downstream references** to admin panel detection results in brief generation, risk summaries, and sales hooks. Data derived from Layer 2 activity cannot be used in prospecting materials.

4. **If this function was already executed against targets:** Treat as an incident. Document affected targets, destroy probe-derived data, and log the incident per SCANNING_RULES.md incident response protocol.

---

## Entry 3: Gate 2 Pre-Scan Authorization — Consented Client

---

# Valdi Pre-Scan Authorisation Check

- **Timestamp:** 2026-03-28T10:05:00Z
- **Scan type:** wordpress_vulnerability_scan
- **Approval token:** 2d8f4a91-7c3e-4b52-9a16-e8b72cf30d45
- **Target:** cafe-strandvejen.dk
- **Client ID:** client-003
- **Target Level:** 1 (written consent on file)
- **Result:** APPROVED

## Checks

- [x] **Approval token valid and current** — Token `2d8f4a91-7c3e-4b52-9a16-e8b72cf30d45` is present in the approval token registry, issued 2026-03-26T16:20:00Z. Function hash matches current version (no modifications since approval).

- [x] **Target authorisation level determined** — Client `client-003` (Cafe Strandvejen ApS, CVR 87654321) has an active authorisation record on file. Written consent granted. Layers permitted: [1, 2].

- [x] **Domain in scope** — `cafe-strandvejen.dk` is listed in the client's authorised domains: `cafe-strandvejen.dk` and `bestilling.cafe-strandvejen.dk`.

- [x] **Scan type Layer (2) does not exceed what target Level (1) permits** — Scan type `wordpress_vulnerability_scan` is Layer 2. Target's consent state permits Layer 1 and Layer 2 activities. Layer 2 <= permitted layers. Compatible.

- [x] **Consent current** — Consent date: 2026-03-15. Consent expiry: 2027-03-15. Current date: 2026-03-28. Consent is within its validity period.

- [x] **Consent document on file** — Signed authorisation document is on file and accessible.

- [x] **robots.txt does not deny automated access** — Checked `cafe-strandvejen.dk/robots.txt` on 2026-03-28. robots.txt permits automated access (no blanket `Disallow: /` directive). Specific disallowed paths (`/wp-admin/`) noted — the scan will respect per-path directives.

## Authorisation Summary

```
Client:             Cafe Strandvejen ApS
CVR:                87654321
Domain:             cafe-strandvejen.dk
Consent type:       Written
Consent signed by:  Marie Jensen (Owner)
Consent date:       2026-03-15
Consent expiry:     2027-03-15
Layer scope:        1, 2
Scan type:          wordpress_vulnerability_scan (Layer 2)
Approval token:     2d8f4a91-7c3e-4b52-9a16-e8b72cf30d45
```

## Notes

All checks passed. The scan type's Layer (2) is within the target's consented scope. The consent document is on file, signed by the domain owner (Marie Jensen, registered owner in CVR), and is not expired.

One item noted for the operator: the target's robots.txt disallows `/wp-admin/`. While the scanning authorization covers Layer 2 activity including admin panel paths, Heimdall's robots.txt policy requires respecting per-path directives regardless of consent. The `wordpress_vulnerability_scan` function's WPScan configuration should exclude paths denied by robots.txt. This is enforced at the tool level and does not affect the overall authorization.

Scan batch may proceed.

---

## How These Logs Are Used

### Evidence of due diligence

Every scanning function Heimdall executes has a corresponding Gate 1 forensic log demonstrating that the code was reviewed against documented legal constraints before execution. Every target has a corresponding Gate 2 check confirming authorization was verified before scanning began.

### Rejection logs prove the system works

Entry 2 above demonstrates that Valdi catches and blocks non-compliant code. The rejection log — with its detailed function description, rule citations, violation table, and remediation instructions — shows that the compliance system is not a rubber stamp. This is as important as the approval logs: it proves the gatekeeper has teeth.

### Audit trail continuity

The combination of Gate 1 (scan-type validation) and Gate 2 (per-target authorization) creates a complete audit chain: from code review, through approval token issuance, to per-target consent verification, to scan execution. Every link in the chain is timestamped and logged.

### What we need from counsel (legal briefing Q12, Q13)

- Does this level of forensic logging satisfy a Danish court's expectations for due diligence in automated external scanning?
- Would the existence of rejection logs (demonstrating the system catches violations) mitigate liability if an inadvertent boundary crossing occurred?
- Are there additional data points we should be logging (e.g., full HTTP request/response captures, IP addresses)?
