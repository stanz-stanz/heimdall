# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:05:00Z
- **Scan type:** Passive domain scan orchestrator (batch Layer 1 scanning)
- **Scan type ID:** passive_domain_scan_orchestrator
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** REJECTED
- **Approval token:** N/A
- **Function hash:** sha256:e5318a8b6b168c6dbcdf305a705b4b08cb6dfa2fc1bb19885aea80d3974215b2
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def scan_domains(companies: list[Company]) -> dict[str, ScanResult]:
    """Run Layer 1 scanning on all non-discarded companies. Returns dict keyed by domain."""
    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    log.info("Scanning %d unique domains (Layer 1 passive only)", len(domains))

    # Batch scans with CLI tools
    httpx_results = _run_httpx(domains)
    webanalyze_results = _run_webanalyze(domains)

    results: dict[str, ScanResult] = {}

    for i, domain in enumerate(domains, 1):
        scan = ScanResult(domain=domain)

        # SSL check
        ssl_info = _check_ssl(domain)
        scan.ssl_valid = ssl_info["valid"]
        scan.ssl_issuer = ssl_info["issuer"]
        scan.ssl_expiry = ssl_info["expiry"]
        scan.ssl_days_remaining = ssl_info["days_remaining"]

        # Response headers
        scan.headers = _get_response_headers(domain)

        # httpx results
        httpx_data = httpx_results.get(domain, {})
        if httpx_data:
            scan.raw_httpx = httpx_data
            scan.server = httpx_data.get("webserver", "")
            tech = httpx_data.get("tech", [])
            if tech:
                scan.tech_stack.extend(tech)

        # webanalyze results
        wa_techs = webanalyze_results.get(domain, [])
        if wa_techs:
            scan.tech_stack.extend(wa_techs)

        # Deduplicate tech stack
        scan.tech_stack = list(dict.fromkeys(scan.tech_stack))

        # Derive CMS from tech stack
        cms_keywords = {
            "wordpress": "WordPress", "joomla": "Joomla", "drupal": "Drupal",
            "prestashop": "PrestaShop", "magento": "Magento", "shopify": "Shopify",
            "squarespace": "Squarespace", "wix": "Wix", "weebly": "Weebly",
            "webflow": "Webflow", "typo3": "TYPO3", "craft cms": "Craft CMS",
            "umbraco": "Umbraco", "sitecore": "Sitecore", "woocommerce": "WordPress",
        }
        for tech in scan.tech_stack:
            for keyword, cms_name in cms_keywords.items():
                if keyword in tech.lower():
                    scan.cms = cms_name
                    break
            if scan.cms:
                break

        # Page meta extraction (author, footer credit, plugins)
        meta_author, footer_credit, plugins = _extract_page_meta(domain)
        scan.meta_author = meta_author
        scan.footer_credit = footer_credit
        if plugins:
            scan.detected_plugins = plugins

        # Derive hosting from server header and tech stack
        hosting_hints = {
            "one.com": "one.com", "simply.com": "simply.com", "gigahost": "Gigahost",
            "unoeuro": "UnoEuro/Simply", "amazonaws": "AWS", "cloudflare": "Cloudflare",
            "nginx": "", "apache": "", "litespeed": "LiteSpeed",
        }
        combined = (scan.server + " " + " ".join(scan.tech_stack)).lower()
        for hint, provider in hosting_hints.items():
            if hint in combined and provider:
                scan.hosting = provider
                break

        results[domain] = scan

        if i % 25 == 0:
            log.info("Scanned %d/%d domains", i, len(domains))

    log.info("Layer 1 scanning complete: %d domains scanned", len(results))
    return results
```

**File:** `pipeline/scanner.py` (lines 235-318)

## Tools Invoked

- Calls `_run_httpx()` (httpx CLI — permitted at Level 0)
- Calls `_run_webanalyze()` (webanalyze CLI — permitted at Level 0)
- Calls `_check_ssl()` (Python ssl/socket — permitted at Level 0)
- Calls `_get_response_headers()` (Python requests HEAD — permitted at Level 0)
- Calls `_extract_page_meta()` (Python requests GET — permitted at Level 0)

## URLs/Paths Requested

- Homepage (`/`) of each domain (via httpx, webanalyze, _extract_page_meta, _get_response_headers)
- TLS handshake to port 443 of each domain (via _check_ssl)

All paths are publicly served. No hidden paths, admin panels, or API endpoints are probed.

## robots.txt Handling

**The function does NOT check robots.txt.** This is the critical violation.

`scan_domains` is the entry point and orchestrator for all scanning activity. It receives a list of companies, extracts their domains, and passes them directly to scanning functions without any robots.txt verification. A domain whose robots.txt denies automated access would be scanned anyway.

Furthermore, the batch functions `_run_httpx` and `_run_webanalyze` receive the full domain list before any per-domain robots.txt check could occur. Even if a per-domain check were added in the loop, the batch CLI tools would have already scanned all domains including those that should have been skipped.

## Reasoning

The individual scanning activities this function orchestrates are all Layer 1 and compliant with Level 0 rules. The tools used (httpx, webanalyze, ssl, requests) are all permitted at Level 0. The paths accessed (homepage only) are all publicly served. **The scanning activities themselves are lawful.**

However, the function violates a mandatory constraint in SCANNING_RULES.md:

> "If a target's robots.txt denies automated access, skip the target entirely. Do not scan, probe, or make any automated requests to that domain. Log the reason and move on. This applies at ALL levels including Level 0. No exceptions."

This is a hard constraint, not a recommendation. The function must check robots.txt for every domain before any scanning activity — including before passing domains to batch tools.

Additionally, the function has no mechanism to:
1. Check approval tokens before executing (required by the Valdi workflow)
2. Log skipped domains (required: "log the reason and move on")
3. Reference a Valdi approval token for the scan types it invokes

## Violations

| # | Line | Action | Rule Violated | Risk |
|---|------|--------|--------------|------|
| 1 | 238-239 | Passes all domains to scanning functions without robots.txt check | SCANNING_RULES.md: "If a target's robots.txt denies automated access, skip the target entirely [...] No exceptions." | Automated requests sent to domains that have explicitly denied automated access. Violates the operator's expressed wishes and weakens the legal position under SS263 ("uberettiget adgang" argument). |
| 2 | 242-243 | Batch tools (_run_httpx, _run_webanalyze) receive full domain list before any filtering | SCANNING_RULES.md: "Do not scan, probe, or make any automated requests to that domain." | Even if per-domain checking were added later in the loop, batch tools have already sent requests to all domains. |
| 3 | N/A | No approval token check before execution | CLAUDE.md / Valdi workflow: "The scanning code must check active_approvals.json for a valid token matching its scan type before executing." | Scan executes without Valdi authorisation verification. |

## Suggested Remediation

1. **Add robots.txt pre-filtering before any scanning:**
   ```python
   def _check_robots_txt(domain: str) -> bool:
       """Return True if robots.txt allows automated access, False if denied."""
       try:
           resp = requests.get(
               f"https://{domain}/robots.txt",
               timeout=REQUEST_TIMEOUT,
               headers={"User-Agent": USER_AGENT},
           )
           if resp.status_code == 200:
               # Check for blanket Disallow: /
               content = resp.text.lower()
               # Parse for User-agent: * with Disallow: /
               # (implement proper robots.txt parsing)
               ...
           return True  # No robots.txt or no blanket deny
       except requests.RequestException:
           return True  # No robots.txt accessible — proceed
   ```

2. **Filter domains BEFORE passing to batch tools:**
   ```python
   # Pre-filter for robots.txt compliance
   allowed_domains = []
   skipped_domains = []
   for domain in domains:
       if _check_robots_txt(domain):
           allowed_domains.append(domain)
       else:
           skipped_domains.append(domain)
           log.info("SKIPPED %s — robots.txt denies automated access", domain)

   # Only pass allowed domains to batch tools
   httpx_results = _run_httpx(allowed_domains)
   webanalyze_results = _run_webanalyze(allowed_domains)
   ```

3. **Add approval token validation at the start of the function:**
   ```python
   # Verify Valdi approval tokens exist for all scan types used
   import json
   with open("data/valdi/active_approvals.json") as f:
       approvals = json.load(f)
   # Check that tokens for each scan type are valid
   ```

4. After rewriting, submit the modified function through a fresh Gate 1 review. The previous function hash is invalidated.
