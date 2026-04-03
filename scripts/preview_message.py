"""Preview the Telegram message that would be sent for a test brief.

Runs the full interpret -> compose pipeline without Redis or Telegram.
Saves the output to data/output/preview_message.html for inspection.

Run inside the delivery container:

    python3 scripts/preview_message.py

Or with a custom brief:

    python3 scripts/preview_message.py --brief data/output/briefs/jellingkro.dk.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.interpreter.interpreter import interpret_brief
from src.composer.telegram import compose_telegram


# Same sample brief as test_delivery.py
SAMPLE_BRIEF = {
    "domain": "jellingkro.dk",
    "bucket": "A",
    "company_name": "Jelling Kro",
    "industry": "Restaurant with online booking and webshop",
    "scan_date": "2026-04-03",
    "gdpr_sensitive": True,
    "gdpr_reasons": [
        "Data-handling plugins: Woocommerce, Contact Form 7",
        "E-commerce plugin: WooCommerce:9.6.4",
    ],
    "technology": {
        "cms": "WordPress",
        "hosting": "LiteSpeed",
        "server": "LiteSpeed",
        "ssl": {"valid": True, "issuer": "Sectigo Limited", "expiry": "2027-01-21", "days_remaining": 295},
        "detected_plugins": [
            "Woocommerce", "Custom Facebook Feed", "Instagram Feed",
            "Contact Form 7", "Elementor", "Cookie Law Info",
            "Litespeed Cache", "Wordpress Seo",
        ],
        "plugin_versions": {
            "Contact Form 7": "6.0.3",
            "Elementor": "3.27.3",
            "Woocommerce": "9.6.4",
        },
        "detected_themes": [],
        "headers": {
            "x_frame_options": False,
            "content_security_policy": False,
            "strict_transport_security": False,
            "x_content_type_options": False,
        },
    },
    "subdomains": {"count": 0},
    "findings": [
        {
            "severity": "critical",
            "description": "LiteSpeed Cache [litespeed-cache] < 6.4 (CVE-2024-28000)",
            "risk": "CVE-2024-28000: WordPress LiteSpeed Cache Plugin <= 6.3.0.1 is vulnerable to Privilege Escalation",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2024-28000", "confidence": "medium-inference"},
        },
        {
            "severity": "critical",
            "description": "LiteSpeed Cache [litespeed-cache] < 6.5.0.1 (CVE-2024-44000)",
            "risk": "CVE-2024-44000: WordPress LiteSpeed Cache Plugin < 6.5.0.1 is vulnerable to Broken Authentication",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2024-44000", "confidence": "medium-inference"},
        },
        {
            "severity": "high",
            "description": "Data-handling plugins detected: Woocommerce, Contact Form 7",
            "risk": "These plugins collect or process user data (form submissions, payments). If the site or plugin has a vulnerability, this data could be exposed.",
        },
        {
            "severity": "high",
            "description": "Elementor Website Builder [elementor] >= 3.6.0 - <= 3.6.2 (CVE-2022-1329)",
            "risk": "CVE-2022-1329: WordPress Elementor Website Builder plugin <= 3.6.2 - Arbitrary File Upload vulnerability",
            "provenance": "twin-derived",
            "provenance_detail": {"source_layer": 1, "twin_scan_tool": "wpvulnerability",
                                  "template_id": "CVE-2022-1329", "confidence": "high-inference"},
        },
        {
            "severity": "medium",
            "description": "Missing HSTS header (HTTP Strict Transport Security)",
            "risk": "Browsers are not instructed to always use HTTPS.",
        },
        {
            "severity": "medium",
            "description": "Outdated plugin: Contact Form 7 (installed 6.0.3, latest 6.1.5)",
            "risk": "Outdated plugins may contain known vulnerabilities.",
        },
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Preview Telegram message without sending")
    parser.add_argument("--brief", help="Path to a brief JSON file (default: built-in sample)")
    parser.add_argument("--language", default=None, help="Language override (en/da)")
    parser.add_argument("--contact-name", default="Martin", help="Contact name for greeting")
    parser.add_argument("--output", default=None, help="Output file path")
    args = parser.parse_args()

    # Load brief
    if args.brief:
        with open(args.brief) as f:
            brief = json.load(f)
        print(f"Loaded brief: {args.brief}")
    else:
        brief = dict(SAMPLE_BRIEF)
        print("Using built-in sample brief (jellingkro.dk)")

    # Pre-filter: only High/Critical findings go to the interpreter (same as runner)
    all_findings = brief.get("findings", [])
    actionable_input = [f for f in all_findings if f.get("severity", "").lower() in ("critical", "high")]
    brief["findings"] = actionable_input
    print(f"Pre-filtered: {len(all_findings)} findings -> {len(actionable_input)} high/critical")

    # Interpret
    print("Interpreting via LLM...")
    interpreted = interpret_brief(brief, language=args.language)
    interpreted["contact_name"] = args.contact_name

    print(f"Interpreter returned {len(findings)} findings, {len(actionable)} are high/critical")

    # Compose
    messages = compose_telegram(interpreted)

    # Output
    output_path = args.output or _detect_output_path()
    full_message = "\n\n---MESSAGE BREAK---\n\n".join(messages)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_message)

    print(f"\nSaved to: {output_path}")
    print(f"Message length: {sum(len(m) for m in messages)} chars across {len(messages)} chunk(s)")
    print(f"\n{'='*60}")
    print(full_message)
    print(f"{'='*60}")

    # Also save the raw interpreted JSON for debugging
    json_path = output_path.replace(".html", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(interpreted, f, indent=2, ensure_ascii=False)
    print(f"Raw interpretation saved to: {json_path}")


def _detect_output_path():
    if os.path.isdir("/data/output"):
        return "/data/output/preview_message.html"
    return "data/output/preview_message.html"


if __name__ == "__main__":
    main()
