"""HTML and response templates for the digital twin server.

Reads a prospect brief JSON and generates WordPress-like responses that
are detectable by httpx, webanalyze, WPScan, and Nuclei.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SLUG_MAP_PATH = Path(__file__).parent / "slug_map.json"

# Danish lorem ipsum filler (~1 KB block, repeated to reach ~50 KB)
_LOREM_DA = (
    "<p>Vi byder velkommen til vores restaurant, hvor vi serverer friske råvarer "
    "fra lokale leverandører. Vores køkken er inspireret af det danske køkken med "
    "et moderne twist. Book et bord online eller ring til os for reservationer. "
    "Vi glæder os til at byde dig velkommen.</p>\n"
    "<p>Vores menukort skifter med sæsonerne og vi bruger kun de bedste ingredienser. "
    "Fra morgenmad til aftensmad tilbyder vi retter der passer til enhver smag. "
    "Kom og oplev vores hyggelige atmosfære og vores dedikerede personale.</p>\n"
    "<p>Restaurant og café i hjertet af Danmark. Åbningstider: Mandag til lørdag "
    "kl. 11:00 til 22:00. Søndag kl. 10:00 til 20:00. Vi holder lukket på "
    "helligdage. Følg os på sociale medier for nyheder og tilbud.</p>\n"
)


def load_slug_map(path: Path | None = None) -> dict[str, str | None]:
    """Load the display-name to WordPress slug mapping."""
    p = path or SLUG_MAP_PATH
    with open(p) as f:
        return json.load(f)


def _slugify(name: str) -> str:
    """Fallback slug generation: lowercase, spaces to hyphens, strip specials."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    return s.strip("-")


def parse_tech_stack(
    brief: dict, slug_map: dict[str, str | None]
) -> dict[str, str]:
    """Extract {plugin_slug: version} from brief's tech_stack and detected_plugins.

    Returns only entries that map to actual WP plugin slugs (null entries in
    slug_map are non-plugin technologies and are skipped).
    """
    plugins: dict[str, str] = {}

    # Parse tech_stack entries like "Yoast SEO:26.9"
    for entry in brief.get("tech_stack", []):
        if ":" in entry:
            name, version = entry.rsplit(":", 1)
        else:
            name, version = entry, ""

        name = name.strip()
        if name in slug_map:
            slug = slug_map[name]
            if slug is not None and slug not in plugins:
                plugins[slug] = version.strip()
        else:
            slug = _slugify(name)
            if slug and slug not in plugins:
                plugins[slug] = version.strip()

    # Also include detected_plugins that may not be in tech_stack
    for name in brief.get("technology", {}).get("detected_plugins", []):
        name = name.strip()
        if name in slug_map:
            slug = slug_map[name]
        else:
            slug = _slugify(name)
        if slug and slug not in plugins:
            plugins[slug] = ""

    return plugins


def _extract_wp_version(brief: dict) -> str:
    """Extract WordPress version from tech_stack."""
    for entry in brief.get("tech_stack", []):
        if entry.startswith("WordPress:"):
            return entry.split(":", 1)[1].strip()
    return "6.7"


def _extract_php_version(brief: dict) -> str:
    """Check if PHP is in tech_stack and return a plausible version."""
    for entry in brief.get("tech_stack", []):
        if entry.startswith("PHP:"):
            return entry.split(":", 1)[1].strip()
        if entry == "PHP":
            return "8.2"
    return ""


def build_index_html(brief: dict, plugins: dict[str, str]) -> str:
    """Build a realistic WordPress homepage HTML (~50KB)."""
    domain = brief.get("domain", "localhost")
    wp_version = _extract_wp_version(brief)

    # Plugin stylesheet links
    plugin_links = []
    for slug, ver in plugins.items():
        ver_qs = f"?ver={ver}" if ver else ""
        plugin_links.append(
            f'<link rel="stylesheet" href="/wp-content/plugins/{slug}/css/style.css{ver_qs}" />'
        )

    # Plugin script tags
    plugin_scripts = []
    for slug, ver in plugins.items():
        ver_qs = f"?ver={ver}" if ver else ""
        plugin_scripts.append(
            f'<script src="/wp-content/plugins/{slug}/js/frontend.js{ver_qs}"></script>'
        )

    # jQuery Migrate version
    jqm_ver = ""
    for entry in brief.get("tech_stack", []):
        if entry.startswith("jQuery Migrate:"):
            jqm_ver = entry.split(":", 1)[1].strip()
            break
    jqm_ver = jqm_ver or "3.4.1"

    # WP Rocket cache paths
    wp_rocket_block = ""
    if any("wp rocket" in e.lower() or "wp-rocket" in e.lower() for e in brief.get("tech_stack", [])):
        wp_rocket_block = (
            f'<link rel="stylesheet" href="/wp-content/cache/wp-rocket/{domain}/concat.min.css" />\n'
            f'<script src="/wp-content/cache/wp-rocket/{domain}/concat.min.js"></script>\n'
        )

    # Yoast JSON-LD
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Restaurant",
        "name": brief.get("company_name", domain),
        "url": f"https://{domain}",
    })

    # Body filler to reach ~50KB
    filler_repeats = 80
    body_content = _LOREM_DA * filler_repeats

    html = f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta name="generator" content="WordPress {wp_version}" />
<title>{domain}</title>
<link rel="https://api.w.org/" href="/wp-json/" />
<link rel="alternate" type="application/json+oembed" href="/wp-json/oembed/1.0/embed?url=https%3A%2F%2F{domain}%2F" />
<link rel="stylesheet" href="/wp-content/themes/flavor/style.css?ver={wp_version}" />
{chr(10).join(plugin_links)}
{wp_rocket_block}<script src="/wp-includes/js/jquery/jquery.min.js?ver=3.7.1"></script>
<script src="/wp-includes/js/jquery/jquery-migrate.min.js?ver={jqm_ver}"></script>
<script>
window._wpemojiSettings = {{"baseUrl":"https:\\/\\/s.w.org\\/images\\/core\\/emoji\\/15.0.3\\/72x72\\/","ext":".png"}};
!function(e,a,t){{var n=a.createElement("canvas"),r;if(n.getContext&&n.getContext("2d")){{r=n.getContext("2d");r.textBaseline="top";r.font="600 32px Arial"}}}}(window,document,"script");
</script>
<script type="application/ld+json">{jsonld}</script>
</head>
<body class="home page-template-default page">
<header id="masthead" class="site-header">
<div class="site-branding">
<h1 class="site-title"><a href="https://{domain}">{brief.get("company_name", domain)}</a></h1>
</div>
</header>
<main id="primary" class="site-main">
<article class="page type-page status-publish">
<div class="entry-content">
{body_content}
</div>
</article>
</main>
<!-- This site is optimized with the Yoast SEO plugin v26.9 - https://yoast.com/wordpress/plugins/seo/ -->
<footer id="colophon" class="site-footer">
<div class="site-info">
<p>&copy; 2026 {brief.get("company_name", domain)}. Alle rettigheder forbeholdes.</p>
</div>
</footer>
<!-- / Yoast SEO plugin. -->
{chr(10).join(plugin_scripts)}
</body>
</html>"""
    return html


def build_plugin_readme(name: str, version: str) -> str:
    """WordPress.org standard readme.txt for a plugin."""
    return f"""=== {name} ===
Contributors: pluginauthor
Tags: plugin
Requires at least: 5.0
Tested up to: 6.9
Stable tag: {version}
License: GPLv2

== Description ==
{name} plugin.

== Changelog ==
= {version} =
* Release.
"""


def build_wpjson_root(domain: str) -> dict:
    """Minimal /wp-json/ root index."""
    return {
        "name": domain,
        "description": "",
        "url": f"https://{domain}",
        "home": f"https://{domain}",
        "gmt_offset": "1",
        "timezone_string": "Europe/Copenhagen",
        "namespaces": ["wp/v2", "oembed/1.0", "yoast/v1"],
        "authentication": [],
        "routes": {
            "/wp/v2": {"methods": ["GET"]},
            "/wp/v2/users": {"methods": ["GET"]},
        },
    }


def build_wpjson_users() -> list:
    """Minimal /wp-json/wp/v2/users/ response."""
    return [{"id": 1, "name": "admin", "slug": "admin", "link": "/author/admin/"}]


def build_xmlrpc_response() -> str:
    """Standard WordPress XML-RPC server stub."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<methodResponse>
  <params>
    <param>
      <value><string>XML-RPC server accepts POST requests only.</string></value>
    </param>
  </params>
</methodResponse>"""


def build_wp_login_html(domain: str) -> str:
    """Minimal WordPress login page."""
    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8" />
<title>Log ind &lsaquo; {domain} &#8212; WordPress</title>
<meta name="robots" content="max-image-preview:large, noindex, noarchive" />
<link rel="stylesheet" href="/wp-admin/css/login.min.css" />
</head>
<body class="login login-action-login wp-core-ui">
<div id="login">
<h1><a href="https://wordpress.org/">Powered by WordPress</a></h1>
<form name="loginform" id="loginform" action="/wp-login.php" method="post">
<p><label for="user_login">Brugernavn eller e-mail</label>
<input type="text" name="log" id="user_login" /></p>
<p><label for="user_pass">Adgangskode</label>
<input type="password" name="pwd" id="user_pass" /></p>
<p class="submit"><input type="submit" name="wp-submit" value="Log ind" /></p>
</form>
</div>
</body>
</html>"""


def build_readme_html(version: str) -> str:
    """WordPress core /readme.html."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8" /><title>WordPress &rsaquo; ReadMe</title></head>
<body>
<h1>WordPress</h1>
<p>Version {version}</p>
<p>Semantic personal publishing platform.</p>
</body>
</html>"""


def build_rss_feed(domain: str, wp_version: str) -> str:
    """WordPress RSS 2.0 feed with generator tag for version detection."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:atom="http://www.w3.org/2005/Atom"
    xmlns:sy="http://purl.org/rss/1.0/modules/syndication/">
<channel>
    <title>{domain}</title>
    <link>https://{domain}</link>
    <description></description>
    <lastBuildDate>Sat, 29 Mar 2026 12:00:00 +0000</lastBuildDate>
    <language>da</language>
    <sy:updatePeriod>hourly</sy:updatePeriod>
    <sy:updateFrequency>1</sy:updateFrequency>
    <generator>https://wordpress.org/?v={wp_version}</generator>
    <atom:link href="https://{domain}/feed/" rel="self" type="application/rss+xml" />
</channel>
</rss>"""


def build_theme_style_css() -> str:
    """Theme style.css with required Theme Name header."""
    return """/*
Theme Name: flavor
Theme URI: https://flavor.developer.test/
Author: flavor developer
Description: A custom WordPress theme.
Version: 1.0.0
License: GPLv2 or later
Text Domain: flavor
*/

body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
"""
