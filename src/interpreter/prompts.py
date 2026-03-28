"""Prompt templates for finding interpretation.

The system prompt defines the persona, tone, and rules.
The user prompt injects the scan brief data.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a cybersecurity advisor writing a scan report for a small business owner who has no technical background. The owner runs a {industry} business.

TONE: {tone_description}

LANGUAGE: Write entirely in {language_name}. Use natural, everyday language — not translated-from-English phrasing.

RULES:
- Start with what is OK (reassurance first)
- Connect related findings into a single narrative when they compound each other (e.g., a missing security header + a plugin that handles customer data = one combined issue, not two separate bullet points)
- Reduce the number of findings the reader sees by merging related items — fewer important points beat many small ones
- Prioritise: only findings that require action get a paragraph. Low/info findings get one line or are grouped together
- For each actionable finding, say: what is wrong (plain language), what to do, and who should do it (the owner, their web host, or a developer)
- Give time estimates where possible ("5 minutes", "ask your host")
- NEVER use security jargon without immediately explaining it
- NEVER fabricate technical details that are not in the scan data
- NEVER give environment-specific instructions (file paths, server config) — you do not know their setup
- Keep it short. The owner will read this on their phone.

OUTPUT FORMAT: Return valid JSON with this exact structure:
{{
  "good_news": ["Short statement about what is fine", ...],
  "findings": [
    {{
      "title": "Short plain-language title",
      "explanation": "What is wrong and why it matters for THIS business",
      "action": "What to do about it",
      "who": "owner|web_host|developer",
      "effort": "5 minutes|1 hour|etc"
    }}
  ],
  "summary": "One sentence overall assessment"
}}

Return ONLY the JSON object, no markdown fences, no commentary."""


USER_PROMPT = """Scan report for: {company_name} ({domain})
Industry: {industry}
Scan date: {scan_date}

Technology: {cms} on {hosting}, SSL {ssl_status} (expires {ssl_expiry}, {ssl_days} days)
Plugins: {plugins}
GDPR sensitive: {gdpr_sensitive} — {gdpr_reasons}

Findings from scan:
{findings_text}"""


def build_system_prompt(
    industry: str,
    tone: str,
    tone_description: str,
    language: str,
) -> str:
    """Build the system prompt with tone and language injected."""
    language_names = {"da": "Danish", "en": "English"}
    return SYSTEM_PROMPT.format(
        industry=industry or "small business",
        tone_description=tone_description,
        language_name=language_names.get(language, language),
    )


def build_user_prompt(brief: dict) -> str:
    """Build the user prompt from a scan brief dict."""
    tech = brief.get("technology", {})
    ssl = tech.get("ssl", {})
    ssl_status = "valid" if ssl.get("valid") else "EXPIRED/MISSING"

    plugins = tech.get("detected_plugins", [])
    plugin_str = ", ".join(plugins) if plugins else "none detected"

    gdpr_reasons = brief.get("gdpr_reasons", [])
    gdpr_str = "; ".join(gdpr_reasons) if gdpr_reasons else "no signals"

    findings = brief.get("findings", [])
    findings_lines = []
    for f in findings:
        findings_lines.append(
            f"[{f['severity'].upper()}] {f['description']}\n  Risk: {f['risk']}"
        )
    findings_text = "\n\n".join(findings_lines) if findings_lines else "No findings."

    return USER_PROMPT.format(
        company_name=brief.get("company_name", "Unknown"),
        domain=brief.get("domain", "unknown"),
        industry=brief.get("industry", "unknown"),
        scan_date=brief.get("scan_date", "unknown"),
        cms=tech.get("cms") or "Unknown CMS",
        hosting=tech.get("hosting") or "Unknown host",
        ssl_status=ssl_status,
        ssl_expiry=ssl.get("expiry", "unknown"),
        ssl_days=ssl.get("days_remaining", "unknown"),
        plugins=plugin_str,
        gdpr_sensitive=brief.get("gdpr_sensitive", False),
        gdpr_reasons=gdpr_str,
        findings_text=findings_text,
    )
