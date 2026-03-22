# SCANNING_RULES.md

**Authoritative constraint document for all Heimdall scanning code.**
**Place in project root. Read before writing or modifying any scanner function.**
**Last updated: March 22, 2026.**

---

## Why This Document Exists

Heimdall operates under Danish criminal law. **Straffeloven §263, stk. 1** criminalizes unauthorized access to another person's data system, with penalties up to 18 months imprisonment (6 years under aggravating circumstances). The boundary between legal passive observation and potentially criminal active probing is not academic — it determines whether the operator of this software is committing a criminal offense.

This document defines what Heimdall scanning code is allowed to do at each authorization level. **No scanning function may be written, modified, or executed without conforming to these rules.**

This document is the highest-authority source on scanning legality in the project. If any other document (including `CLAUDE.md`) contains a scanning rule that conflicts with this one, this document wins.

---

## Terminology

**Layer** describes the *type of activity*:
- **Layer 1 (Passive):** Reading publicly served information
- **Layer 2 (Active probing):** Directed requests to paths or services not publicly linked
- **Layer 3 (Exploitation):** Exploiting vulnerabilities — always forbidden

**Level** describes the *consent state* of a target:
- **Level 0:** No written consent. Only Layer 1 permitted.
- **Level 1:** Written consent on file. Layer 1 and Layer 2 permitted within agreed scope.

The rule: **a scan's Layer must not exceed what the target's Level permits.**

---

## Level 0 Rules — What Is Allowed

Level 0 scanning may **only** read information that the server voluntarily sends to any visitor. The test is: "Would a normal browser visit to the site's public pages produce this data?"

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

### Allowed Tools at Level 0

| Tool | Permitted Use |
|------|--------------|
| httpx | HTTP probing of public pages, tech fingerprinting from response data |
| webanalyze | CMS/technology detection from public page responses |
| subfinder | Subdomain discovery via passive sources (CT logs, DNS datasets) |
| sslyze / testssl.sh | TLS/SSL certificate and configuration analysis |
| dig / nslookup | DNS record queries |
| curl / wget | Fetching public pages only (homepage, sitemap.xml, robots.txt, security.txt) |

---

## Level 0 Rules — What Is Forbidden

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
- **Any use of Nuclei, Nikto, Nmap, or WPScan.** These are Level 1 tools only.

### robots.txt Denial

**If a target's `robots.txt` denies automated access, skip the target entirely.** Do not scan, probe, or make any automated requests to that domain. Log the reason and move on. This applies at ALL levels including Level 0. No exceptions.

This rule is separate from the Layer classification — it is a blanket respect-the-operator's-wishes constraint.

### The Decision Test

Before writing any function that sends a request to a target, answer this question:

> "Does this request go to a URL that a normal person would reach by clicking links on the public website, or does it go to a URL I am guessing or probing for?"

If the answer is guessing/probing → **it is forbidden at Level 0.**

---

## Level 1 Rules — Written Consent Required

When Heimdall holds a signed scanning authorization from the site owner, the following additional tools and techniques become available:

### Allowed at Level 1 (in addition to all Level 0 actions)

- **Nuclei** — template-based vulnerability scanning within agreed scope
- **Nikto** — web server vulnerability scanning
- **Nmap** — port scanning, service detection
- **WPScan** — WordPress-specific vulnerability and plugin scanning
- **Directory enumeration** of agreed-upon scope
- **Admin panel detection** — checking for `/wp-admin/`, `/administrator/`, etc.
- **API endpoint probing** within agreed scope
- **Authenticated scanning** if credentials are provided in the agreement (Guardian tier only)

### Level 1 Constraints

- Scanning scope must not exceed what the authorization agreement specifies (specific domains, subdomains, IP ranges).
- No exploitation of discovered vulnerabilities. Detection and reporting only.
- No denial-of-service patterns (rate-limit all scanning; respect server capacity).
- All scan results stored encrypted and retained only for the duration specified in the agreement.
- The robots.txt denial rule still applies at Level 1 — if the site operator denies automated access, do not scan even with written consent. Flag for human review (the consent and the robots.txt are contradictory; the operator must resolve this).

---

## Workflow Enforcement

### For Claude Code Agents

1. **Before writing any scanner function**, re-read this document and confirm the Layer the function operates at and the Level it is intended for.
2. **Tag every scanning function** with its Layer and Level in a docstring or comment:
   ```python
   def detect_cms_from_homepage(url: str) -> dict:
       """Layer 1 / Level 0 — Reads homepage HTML to identify CMS from meta tags and asset paths."""
   ```
3. **Never combine Layer 1 and Layer 2 actions in the same function.** If a function does both, split it.
4. **Submit every scanning function to Valdí** (Legal Compliance Agent) for Gate 1 review before execution. No scanning code runs without a valid approval token.
5. **Never execute scans against external targets without a valid Valdí approval token and explicit human go-ahead.**

### For the Operator (Federico)

1. Review Valdí's forensic log entries before approving scan execution.
2. Maintain awareness of which scan types are approved and which targets they run against.
3. Before running Level 1 scans, confirm that a signed authorization is on file for the target.

---

## Incident Response

If a scan is discovered to have performed an action beyond its declared Layer or the target's Level:

1. **Stop the scan immediately.**
2. **Document what happened** — which targets were affected, which forbidden requests were sent, timestamps.
3. **Remove or fix the offending code** before any further scanning.
4. **Assess impact** — determine the practical risk of the unauthorized requests.
5. **Update this document** if the incident reveals an ambiguity in the rules.
6. **Log the incident** in `docs/reference/incidents/` for future reference.

---

## Ambiguous Cases

If you are unsure whether an action is Layer 1 or Layer 2, **treat it as Layer 2.** The conservative default protects the operator from criminal liability. Flag the ambiguity for human review.

Examples of things that might seem passive but are **not allowed at Level 0**:

- Checking if `xmlrpc.php` exists (it's a specific endpoint probe, not a linked page)
- Requesting `/wp-json/wp/v2/users/` to enumerate users (API probing)
- Sending a HEAD request to an admin path "just to check the status code" (still a directed probe)
- Fetching `/.well-known/` paths other than `security.txt` (unless linked)

---

## Legal Reference

- **Straffeloven §263, stk. 1** — https://danskelove.dk/straffeloven/263
- **ICLG Cybersecurity 2026 (Denmark)** — https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark
- **Full legal analysis** — see `docs/Heimdall_Legal_Risk_Assessment.md`

---

*This document is the authoritative source on scanning legality for the Heimdall project. If it conflicts with any other document, this document wins.*
