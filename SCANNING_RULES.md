# SCANNING_RULES.md

**Authoritative constraint document for all Heimdall scanning code.**
**Place in project root. Read before writing or modifying any scanner function.**
**Last updated: March 22, 2026.**

---

## Why This Document Exists

Heimdall operates under Danish criminal law. **Straffeloven §263, stk. 1** criminalizes unauthorized access to another person's data system, with penalties up to 18 months imprisonment (6 years under aggravating circumstances). The boundary between legal passive observation and potentially criminal active probing is not academic — it determines whether the operator of this software is committing a criminal offense.

This document defines what Heimdall scanning code is allowed to do at each consent state. **No scanning function may be written, modified, or executed without conforming to these rules.**

This document is the highest-authority source on scanning legality in the project. If any other document (including `CLAUDE.md`) contains a scanning rule that conflicts with this one, this document wins.

---

## Terminology

**Layer** describes the *type of activity*:
- **Layer 1 (Passive):** Reading publicly served information
- **Layer 2 (Active probing):** Directed requests to paths or services not publicly linked
- **Layer 3 (Exploitation):** Exploiting vulnerabilities — always forbidden

Without written consent, only Layer 1 activities are permitted. With written consent (Sentinel/Guardian clients), Layer 1 and Layer 2 activities are permitted within the agreed scope.

---

## Without Consent — What Is Allowed

Scanning without written consent may **only** read information that the server voluntarily sends to any visitor. The test is: "Would a normal browser visit to the site's public pages produce this data?"

### Allowed Actions

- **HTTP response headers** from the site's public pages (homepage, publicly linked pages). Includes Server, X-Powered-By, Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, etc.
- **HTML source of public pages** — reading meta tags, generator tags, script/link references, inline comments, visible text. This includes detecting CMS and plugin versions from paths like `/wp-content/plugins/[name]/` or `/wp-includes/js/` that appear in the homepage source.
- **DNS records** — A, AAAA, MX, TXT, CNAME, NS, SOA. Public by design.
- **SSL/TLS certificate data** — certificate chain, expiry date, issuer, SANs, protocol versions. Obtained via standard TLS handshake.
- **WHOIS data** — public registration information.
- **Subdomain enumeration via passive sources** — certificate transparency logs, DNS datasets, search engine results. No direct queries to the target's infrastructure beyond DNS.
- **Technology fingerprinting from public page responses** — tools like httpx and webanalyze that analyze the homepage response. These read what the server already sends; they do not send crafted probes.
- **robots.txt and security.txt** — these are explicitly published for public consumption.
- **Publicly linked pages** — any page reachable by following links from the homepage or sitemap.xml.
- **Third-party public indexes** — querying public databases or search engines for information about the target (e.g., Certificate Transparency logs via crt.sh, exposed cloud storage indexes via GrayHatWarfare). No requests are sent to the target's infrastructure.

### Layer 1 Tools (No Consent Required)

| Tool | Permitted Use |
|------|--------------|
| httpx | HTTP probing of public pages, tech fingerprinting from response data |
| webanalyze | CMS/technology detection from public page responses |
| subfinder | Subdomain discovery via passive sources (CT logs, DNS datasets) |
| crt.sh | Certificate Transparency log search (passive, public data) |
| dnsx | DNS resolution and enrichment (A, AAAA, MX, TXT, CNAME, NS) |
| Python ssl module | TLS certificate validity, issuer, expiry analysis (SSLyze deferred to backlog) |
| dig / nslookup | DNS record queries |
| curl / wget | Fetching public pages only (homepage, sitemap.xml, robots.txt, security.txt) |
| GrayHatWarfare | Querying a third-party public index of exposed cloud storage buckets. No direct requests to the target's infrastructure. See Valdí classification note below. |
| WordPress REST API (`/wp-json/`) | Reading the REST API index when the site explicitly advertises it via `<link rel="https://api.w.org/">` in its HTML or HTTP `Link` header. This is a publicly linked URL — the site invites clients to discover it. Reveals plugin namespaces. **Only Layer 1 when advertised. Do NOT probe `/wp-json/` if the site doesn't link to it.** |
| WordPress.org Plugin API | Querying `api.wordpress.org/plugins/info/1.0/{slug}.json` for latest plugin versions. Public API, no auth required. No requests to the target — queries WordPress.org's servers. |

---

## Without Consent — What Is Forbidden

**If the server would not send this data to a normal visitor browsing the site, you cannot request it.**

### Explicitly Forbidden Actions

- **Requesting paths not linked from public pages.** This includes `/wp-admin/`, `/wp-login.php`, `/administrator/`, `/admin/`, `/phpmyadmin/`, `/cpanel/`, `/.env`, `/.git/`, `/xmlrpc.php`, `/server-status`, `/server-info`, or any other path that is not linked from the homepage, sitemap, or robots.txt.
- **Port scanning.** No nmap, masscan, or any tool that probes ports beyond 80/443 (or whatever ports the site publicly serves HTTP/HTTPS on).
- **Sending crafted requests to test for specific vulnerabilities.** No Nuclei templates, no Nikto checks, no requests designed to trigger error messages or version disclosures beyond what the homepage already reveals.
- **Directory brute-forcing or fuzzing.** No dirbuster, gobuster, ffuf, or similar tools.
- **Authentication attempts.** No login attempts, no credential testing, no brute-force attacks.
- **Form submission.** No automated form fills, no contact form submissions, no search queries designed to trigger SQL errors.
- **API endpoint probing.** No requests to `/api/`, `/graphql/`, `/rest/`, or other API paths unless they are publicly documented and linked.
- **WAF/IDS fingerprinting.** No requests designed to identify or bypass security controls.
- **Any use of Nuclei, Nikto, or Nmap.** These are Layer 2 tools (require written consent). Note: WPVulnerability API lookups are Layer 1 (public database queries, no requests to target).

### robots.txt Denial

**If a target's `robots.txt` denies automated access, skip the target entirely.** Do not scan, probe, or make any automated requests to that domain. Log the reason and move on. This applies regardless of consent state. No exceptions.

This rule is separate from the Layer classification — it is a blanket respect-the-operator's-wishes constraint.

### The Decision Test

Before writing any function that sends a request to a target, answer this question:

> "Does this request go to a URL that a normal person would reach by clicking links on the public website, or does it go to a URL I am guessing or probing for?"

If the answer is guessing/probing → **it is forbidden without written consent.**

---

## With Written Consent — What Is Additionally Allowed

When Heimdall holds a signed scanning authorization from the site owner (Sentinel/Guardian clients), the following additional tools and techniques become available:

### Layer 2 Tools (Written Consent Required)

- **Nuclei** — template-based vulnerability scanning within agreed scope
- **Nikto** — web server vulnerability scanning (note: DB rules require commercial license from CIRT.net)
- **Nmap** — port scanning, service detection
- **WPVulnerability API** — WordPress plugin/core CVE lookups with CVSS scores (free, no API key required, Layer 1 database query — not a scanner). Local SQLite cache with 7-day TTL. Replaces WPScan sidecar.
- **CMSeek** — CMS detection including admin panel paths and version-specific URLs
- **Katana** — web crawling for hidden endpoint discovery via JS parsing and dynamic link following
- **FeroxBuster** — directory enumeration and content discovery
- **SecretFinder** — JavaScript analysis for exposed API keys, tokens, and endpoints
- **CloudEnum** — active enumeration of cloud storage buckets (S3, Azure Blob, GCS) using company-name patterns. See Valdí classification note below.
- **Directory enumeration** of agreed-upon scope
- **Admin panel detection** — checking for `/wp-admin/`, `/administrator/`, etc.
- **API endpoint probing** within agreed scope
- **Authenticated scanning** if credentials are provided in the agreement (Guardian tier only)

### Consent-Gated Scan Constraints

- Scanning scope must not exceed what the authorization agreement specifies (specific domains, subdomains, IP ranges).
- No exploitation of discovered vulnerabilities. Detection and reporting only.
- No denial-of-service patterns (rate-limit all scanning; respect server capacity).
- All scan results stored encrypted and retained only for the duration specified in the agreement.
- The robots.txt denial rule still applies with written consent — if the site operator denies automated access, do not scan even with written consent. Flag for human review (the consent and the robots.txt are contradictory; the operator must resolve this).

---

## Heimdall-Owned Test Infrastructure (Digital Twins)

A **digital twin** is a container running on Heimdall's own infrastructure that simulates a target website's technology stack by replaying publicly served data collected during Layer 1 scanning. The twin is built from a prospect brief JSON — the same output the Layer 1 pipeline already produces.

### Legal basis

Straffeloven §263 criminalizes unauthorized access to **another person's data system**. A digital twin is Heimdall's own system, built from lawfully obtained public data. Scanning it cannot constitute a §263 violation because the system belongs to the scanner operator.

### What is permitted against twins

- **All Layer 1 and Layer 2 scanning tools** — Nuclei, CMSeek, and any other Valdí-approved tool may run against a twin. The consent restriction exists to protect external site operators; it does not apply when the target is Heimdall's own infrastructure. WPVulnerability API lookups also apply here (database queries, not scanning).
- **No Layer 3 (exploitation)** — even against twins. This is a tool safety constraint, not a legal one.

### What the twin does NOT change

- **Layer 1 data collection** against the real prospect site still follows all rules for scanning without consent in this document. The twin does not grant permission to collect data that would otherwise be forbidden.
- **Valdí Gate 1 still applies** — every scanning tool must have an approved scan type regardless of target. The twin exempts the target from consent checks, not the tool from validation.
- **robots.txt checks do not apply** to twins — Heimdall controls the twin's robots.txt.

### Data provenance requirement

Any finding produced by scanning a twin must carry a `provenance: "unconfirmed"` marker. This indicates the finding was inferred from passive data, not confirmed by direct scanning of the prospect's live infrastructure. This distinction must be preserved through the interpretation and message composition pipeline.

Client-facing language must reflect this: use "is known to be affected by" or "detected version is associated with," not "has this vulnerability." Twin-derived findings are high-confidence inferences, not confirmed observations.

### Synthetic Target Registry

Twins are registered in `config/synthetic_targets.json`. The consent validator checks this registry before performing consent checks. Registered synthetic targets bypass Gate 2 consent validation but remain subject to Gate 1 tool validation.

If the registry file is missing or malformed, the validator treats all targets as external (fail-closed).

---

## Workflow Enforcement

### For Claude Code Agents

1. **Before writing any scanner function**, re-read this document and confirm the Layer the function operates at and the consent state it is intended for.
2. **Tag every scanning function** with its Layer in a docstring or comment:
   ```python
   def detect_cms_from_homepage(url: str) -> dict:
       """Layer 1 / No consent required — Reads homepage HTML to identify CMS from meta tags and asset paths."""
   ```
3. **Never combine Layer 1 and Layer 2 actions in the same function.** If a function does both, split it.
4. **Submit every scanning function to Valdí** (Legal Compliance Agent) for Gate 1 review before execution. No scanning code runs without a valid approval token.
5. **Never execute scans against external targets without a valid Valdí approval token and explicit human go-ahead.**

### For the Operator (Federico)

1. Review Valdí's forensic log entries before approving scan execution.
2. Maintain awareness of which scan types are approved and which targets they run against.
3. Before running Layer 2 scans, confirm that a signed authorization is on file for the target.

---

## Incident Response

If a scan is discovered to have performed an action beyond its declared Layer or the target's consent state:

1. **Stop the scan immediately.**
2. **Document what happened** — which targets were affected, which forbidden requests were sent, timestamps.
3. **Remove or fix the offending code** before any further scanning.
4. **Assess impact** — determine the practical risk of the unauthorized requests.
5. **Update this document** if the incident reveals an ambiguity in the rules.
6. **Log the incident** in `docs/reference/incidents/` for future reference.

---

## Ambiguous Cases

If you are unsure whether an action is Layer 1 or Layer 2, **treat it as Layer 2.** The conservative default protects the operator from criminal liability. Flag the ambiguity for human review.

Examples of things that might seem passive but are **not allowed without consent**:

- Checking if `xmlrpc.php` exists (it's a specific endpoint probe, not a linked page)
- Requesting `/wp-json/wp/v2/users/` to enumerate users (API probing)
- Sending a HEAD request to an admin path "just to check the status code" (still a directed probe)
- Fetching `/.well-known/` paths other than `security.txt` (unless linked)

---

## Valdí Classification Notes

### GrayHatWarfare — Classified Layer 1 (no consent required)

**Date:** 2026-03-26
**Classification:** Layer 1 — Passive
**Reasoning:** GrayHatWarfare queries a third-party public index of exposed cloud storage buckets. It does not send any requests to the target's infrastructure. It is functionally equivalent to a search engine query ("does company X have publicly exposed S3 buckets?"). The data is already indexed and public. This passes the Decision Test: no request is sent to a URL that is being "guessed or probed for" on the target's servers.
**Constraint:** The free tier is limited (~2,936 of 19.5B files). Premium tier (~230 EUR/yr) required for production use.
**Approved for:** Prospecting pipeline (Layer 1 only — reading a public index, no consent required).

### CloudEnum — Classified Layer 2 (written consent required)

**Date:** 2026-03-26
**Classification:** Layer 2 — Active Probing
**Reasoning:** CloudEnum actively constructs URL patterns using the company name (e.g., `companyname.s3.amazonaws.com`, `companyname.blob.core.windows.net`) and sends HTTP requests to cloud provider endpoints to check if those buckets exist. While the requests go to AWS/Azure/GCP infrastructure (not the target's servers), the tool is actively probing for assets associated with a specific company. This is directed enumeration — it probes for resources that are not publicly linked or advertised. Under the conservative default (SCANNING_RULES.md: "If you are unsure whether an action is Layer 1 or Layer 2, treat it as Layer 2"), this is classified as active probing.
**Approved for:** Sentinel/Guardian tiers only (written consent required).

---

## Legal Reference

- **Straffeloven §263, stk. 1** — https://danskelove.dk/straffeloven/263
- **ICLG Cybersecurity 2026 (Denmark)** — https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark
- **Full legal analysis** — see `docs/legal/Heimdall_Legal_Risk_Assessment.md`

---

*This document is the authoritative source on scanning legality for the Heimdall project. If it conflicts with any other document, this document wins.*
