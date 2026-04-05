# Valdi Scan-Type Validation

- **Timestamp:** 2026-04-05T12:00:00Z
- **Scan type:** Homepage meta extraction (author, footer credits, plugin detection with versions, themes, REST API namespaces, CSS signatures)
- **Scan type ID:** homepage_meta_extraction
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** c023519a-0894-4959-b878-828517cbf2d2 (re-validated, hash updated)
- **Previous hash:** sha256:93490496855a6df7cf2ffc40b888366772276b6e077822a63573e1da0b9c6d96
- **New hash:** sha256:874bc6dad146af3e71ac5cf7ecb1f6e06bb16f7147e1918ff49c67a74b0ac9c8
- **Helper function hash:** sha256:b92c974af9d5662418daa2bdd10f688b9d5dbe48667a412d64b23d447def91cb (`_extract_rest_api_plugins`)
- **Hash method:** inspect.getsource
- **Triggered by:** Federico (stale hash remediation)

## Context

The function hash became stale after a prior commit added REST API namespace detection, meta generator tags, and CSS class plugin detection. The approval token was not updated at that time, leaving the hash inconsistent. This review re-validates the function in its current state.

## Functions Reviewed

### `_extract_page_meta` (primary)

```python
def _extract_page_meta(domain: str) -> tuple[str, str, list[str], dict[str, str], list[str]]:
    """Fetch the homepage and extract meta author, footer credits, plugin hints with versions, and themes."""
    meta_author = ""
    footer_credit = ""
    plugins: list[str] = []
    plugin_versions: dict[str, str] = {}
    themes: list[str] = []

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

        # WordPress plugin detection with version extraction from ?ver= params
        # Pass 1: extract slugs with versions from ?ver=, &ver=, &#038;ver=, &amp;ver=
        for slug, ver in re.findall(
            r'/wp-content/plugins/([\w-]+)/[^"\'>\s]*(?:[\?&]|&#0?38;|&amp;)ver=([\d.]+)', html
        ):
            if slug not in plugin_versions:
                plugin_versions[slug] = ver

        # Pass 2: extract all plugin slugs (including those without versions)
        seen_slugs: set[str] = set()
        for slug in re.findall(r'/wp-content/plugins/([\w-]+)/', html):
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                plugins.append(slug)

        # Pass 3: meta generator tags — plugins like WooCommerce add their own
        for gen_name, gen_ver in re.findall(
            r'<meta\s+name=["\']generator["\']\s+content=["\']([^"\']+?)(?:\s+([\d.]+))?["\']',
            html, re.IGNORECASE,
        ):
            gen_lower = gen_name.strip().lower()
            slug = _GENERATOR_TO_SLUG.get(gen_lower)
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                plugins.append(slug)
            if slug and gen_ver and slug not in plugin_versions:
                plugin_versions[slug] = gen_ver.strip()

        # Pass 4: CSS class signatures in body/container elements
        for pattern, slug in _CSS_CLASS_SIGNATURES:
            if slug not in seen_slugs and re.search(pattern, html):
                seen_slugs.add(slug)
                plugins.append(slug)

        # Pass 5: REST API namespace enumeration
        # WordPress advertises /wp-json/ via <link rel="https://api.w.org/"> in HTML
        api_match = re.search(
            r'<link\s+rel=["\']https://api\.w\.org/["\']\s+href=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if api_match:
            api_url = api_match.group(1).strip()
            _extract_rest_api_plugins(
                api_url, seen_slugs, plugins, plugin_versions,
            )

        # WordPress theme detection from HTML source
        wp_theme_matches = re.findall(r'/wp-content/themes/([\w-]+)/', html)
        if wp_theme_matches:
            themes = list(dict.fromkeys(wp_theme_matches))  # deduplicate, preserve order

    except requests.RequestException as e:
        logger.debug("Page meta extraction failed for {}: {}", domain, e)

    return meta_author, footer_credit, plugins, plugin_versions, themes
```

### `_extract_rest_api_plugins` (helper, called by primary)

```python
def _extract_rest_api_plugins(
    api_url: str,
    seen_slugs: set[str],
    plugins: list[str],
    plugin_versions: dict[str, str],
) -> None:
    """Fetch the WordPress REST API index and extract plugin slugs from namespaces."""
    try:
        resp = requests.get(
            api_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return
        data = resp.json()
        namespaces = data.get("namespaces", [])
        for ns in namespaces:
            prefix = ns.split("/")[0] if "/" in ns else ns
            slug = _NAMESPACE_TO_SLUG.get(prefix)
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                plugins.append(slug)
    except (requests.RequestException, ValueError):
        pass  # REST API unavailable — not an error
```

**File:** `src/prospecting/scanner.py` (lines 158-273)

## Tools Invoked

- Python `requests` library (HTTP GET) — two calls maximum per domain

No external CLI scanning tools invoked.

## URLs/Paths Requested

| URL | Method | Source | Permitted? |
|-----|--------|--------|-----------|
| `https://{domain}/` (homepage) | GET | Hardcoded | Yes — publicly served page |
| `{api_url}` (from `<link rel="https://api.w.org/">`) | GET | Extracted from homepage HTML | Yes — site explicitly advertises this URL. SCANNING_RULES.md Layer 1 tool: "WordPress REST API (`/wp-json/`)" |

No other paths requested. No paths guessed or probed.

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) called from the `scan_domains` orchestrator, which enforces robots.txt compliance at the domain level before any per-domain functions are invoked.

**Condition (carried forward from original approval):** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance. Direct invocation without prior robots.txt validation would violate SCANNING_RULES.md.

## Changes Since Previous Approval (token c023519a, 2026-04-02)

| Change | New Requests? | Layer Assessment |
|--------|--------------|-----------------|
| Plugin version extraction from `?ver=` params | No — regex on already-fetched HTML | Layer 1: reading publicly served content |
| Meta generator tag extraction (Pass 3) | No — regex on already-fetched HTML | Layer 1: "reading meta tags, generator tags" per SCANNING_RULES.md |
| CSS class signature detection (Pass 4) | No — regex on already-fetched HTML | Layer 1: reading publicly served content |
| REST API namespace enumeration (Pass 5) | Yes — one conditional GET to URL from `<link rel="https://api.w.org/">` | Layer 1: explicitly permitted by SCANNING_RULES.md tool table |
| Return type expanded (added dict, list) | No — internal data structure | N/A |
| `_extract_rest_api_plugins` helper added | Encapsulates the REST API GET | Layer 1: same as Pass 5 above |

## Reasoning

All five extraction passes operate within Layer 1:

**Passes 1-4** perform regex analysis on the homepage HTML that was already fetched with a single GET request. No additional network requests are made. SCANNING_RULES.md explicitly permits: "HTML source of public pages -- reading meta tags, generator tags, script/link references, inline comments, visible text. This includes detecting CMS and plugin versions from paths like `/wp-content/plugins/[name]/` or `/wp-includes/js/` that appear in the homepage source."

**Pass 5** (REST API namespace enumeration) sends one additional GET request, but only when the site explicitly advertises the endpoint via `<link rel="https://api.w.org/">` in its HTML `<head>`. SCANNING_RULES.md explicitly classifies this as Layer 1: "WordPress REST API (`/wp-json/`) -- Reading the REST API index when the site explicitly advertises it via `<link rel="https://api.w.org/">` in its HTML or HTTP Link header. This is a publicly linked URL -- the site invites clients to discover it." The code correctly guards this with a conditional check (lines 228-236): it only fetches the URL if the `<link>` tag is present in the HTML.

The helper function `_extract_rest_api_plugins` reads only the `namespaces` array from the REST API index JSON. It does NOT enumerate users, posts, or other API endpoints. It does NOT follow namespace URLs. It maps namespace prefixes to known plugin slugs via a static lookup table. This is passive reading of advertised data.

The Decision Test for each request:
1. Homepage (`/`): A normal person would reach this by typing the domain — **not guessing/probing**.
2. REST API index (from `<link>` tag): A normal person (or browser) would follow this link — **not guessing/probing**. The site explicitly advertises it.

No Layer 2 activity present. No Layer 3 activity present. No forbidden paths accessed. No crafted vulnerability probes. No external CLI tools. No port scanning. No directory enumeration.

## Violations

None.

## Note on Helper Function Tracking

The `inspect.getsource` hash method captures only `_extract_page_meta` itself, not the `_extract_rest_api_plugins` helper it calls. The helper's hash is recorded above for completeness. If the helper is modified independently, a re-validation should be triggered even though the primary function's hash would not change. This is a known limitation of per-function hashing.
