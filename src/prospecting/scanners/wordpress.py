"""WordPress-specific passive detection: page meta, plugins, themes, REST API."""

from __future__ import annotations

import re

import requests
from loguru import logger

from src.core.config import REQUEST_TIMEOUT, USER_AGENT

# REST API namespace -> plugin slug mapping
_NAMESPACE_TO_SLUG = {
    "wc": "woocommerce",
    "wc-admin": "woocommerce",
    "gf": "gravityforms",
    "contact-form-7": "contact-form-7",
    "yoast": "wordpress-seo",
    "wp-rocket": "wp-rocket",
    "elementor": "elementor",
    "divi": "divi-builder",
    "et": "divi-builder",
    "jetpack": "jetpack",
    "akismet": "akismet",
    "wordfence": "wordfence",
    "redirection": "redirection",
    "cookieyes": "cookie-law-info",
    "complianz": "complianz-gdpr",
    "monsterinsights": "google-analytics-for-wordpress",
    "wpforms": "wpforms-lite",
    "rankmath": "seo-by-rank-math",
    "smush": "wp-smushit",
    "updraftplus": "updraftplus",
    "ithemes-security": "better-wp-security",
    "sucuri": "sucuri-scanner",
    "tablepress": "tablepress",
    "meow-gallery": "meow-gallery",
}

# Meta generator product name -> plugin slug mapping
_GENERATOR_TO_SLUG = {
    "woocommerce": "woocommerce",
    "flavor starter template": "flavor",
    "flavflavor starter template": "flavor",
    "elementor": "elementor",
    "powered by starter templates": "starter-templates",
    "flavor starter templates": "flavor",
}

# CSS class patterns -> plugin slug mapping (pattern, slug)
_CSS_CLASS_SIGNATURES = [
    (r'\bwoocommerce\b', "woocommerce"),
    (r'\bet_pb_', "divi-builder"),
    (r'\bet_divi_theme\b', "divi-builder"),
    (r'\belementor\b', "elementor"),
    (r'\bjetpack\b', "jetpack"),
]


def extract_page_meta(domain: str) -> tuple[str, str, list[str], dict[str, str], list[str]]:
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
            extract_rest_api_plugins(
                api_url, seen_slugs, plugins, plugin_versions,
            )

        # WordPress theme detection from HTML source
        wp_theme_matches = re.findall(r'/wp-content/themes/([\w-]+)/', html)
        if wp_theme_matches:
            themes = list(dict.fromkeys(wp_theme_matches))  # deduplicate, preserve order

    except requests.RequestException as e:
        logger.debug("Page meta extraction failed for {}: {}", domain, e)

    return meta_author, footer_credit, plugins, plugin_versions, themes


def extract_rest_api_plugins(
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
