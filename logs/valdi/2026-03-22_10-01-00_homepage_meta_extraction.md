# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:01:00Z
- **Scan type:** Homepage meta extraction (author, footer credits, plugin detection)
- **Scan type ID:** homepage_meta_extraction
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** c023519a-0894-4959-b878-828517cbf2d2
- **Function hash:** sha256:6818b848066874a41aa08a340e5a6db0d4d2ea951ca63601848071472f38a88c
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def _extract_page_meta(domain: str) -> tuple[str, str, list[str]]:
    """Fetch the homepage and extract meta author, footer credits, and plugin hints."""
    meta_author = ""
    footer_credit = ""
    plugins = []

    try:
        resp = requests.get(
            f"https://{domain}",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        html = resp.text

        # Meta author
        match = re.search(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            meta_author = match.group(1).strip()

        # Footer credits — look for common patterns in last portion of HTML
        footer_section = html[-5000:] if len(html) > 5000 else html
        credit_patterns = [
            r'(?:website|webdesign|design|lavet|udviklet|skabt)\s+(?:by|af|:)\s*["\']?([^"\'<\n,]{3,50})',
            r'(?:powered\s+by)\s+([^"\'<\n,]{3,50})',
        ]
        for pattern in credit_patterns:
            match = re.search(pattern, footer_section, re.IGNORECASE)
            if match:
                footer_credit = match.group(1).strip()
                break

        # WordPress plugin detection from HTML source
        wp_plugin_matches = re.findall(r'/wp-content/plugins/([^/]+)/', html)
        if wp_plugin_matches:
            plugins = list(set(wp_plugin_matches))

    except requests.RequestException as e:
        log.debug("Page meta extraction failed for %s: %s", domain, e)

    return meta_author, footer_credit, plugins
```

**File:** `pipeline/scanner.py` (lines 68-108)

## Tools Invoked

- Python `requests` library (HTTP GET)

No external CLI scanning tools invoked.

## URLs/Paths Requested

- `https://{domain}/` (homepage) — permitted: publicly served page

No other paths requested. The function only fetches the homepage and analyses the HTML that the server returns.

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) designed to be called from the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level before any per-domain functions are invoked.

**Condition:** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance. Direct invocation without prior robots.txt validation would violate SCANNING_RULES.md.

## Reasoning

This function fetches the homepage (`/`) of the target domain with a standard GET request — the same request any browser makes when visiting a website. It then analyses the HTML source code that the server returns, extracting:

1. **Meta author tag** — a standard HTML meta tag publicly embedded in the page source
2. **Footer credits** — visible text content in the page footer ("design by", "powered by", etc.)
3. **WordPress plugin slugs** — paths like `/wp-content/plugins/[name]/` that appear in `<script>` and `<link>` tags in the publicly served HTML

All three data points are derived from publicly served page content. SCANNING_RULES.md Level 0 explicitly allows: "HTML source of public pages — reading meta tags, generator tags, script/link references, inline comments, visible text. This includes detecting CMS and plugin versions from paths like `/wp-content/plugins/[name]/` or `/wp-includes/js/` that appear in the homepage source."

The function:
1. Only requests the homepage (`/`) — a publicly served page
2. Does NOT probe any hidden paths, admin panels, or API endpoints
3. Does NOT send crafted requests or vulnerability probes
4. Analyses only the HTML the server voluntarily serves to any visitor
5. Uses a standard User-Agent header

All activity is within Layer 1. No Layer 2 or Layer 3 activity present.

## Violations

None.
