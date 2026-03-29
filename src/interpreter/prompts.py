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
- When a finding has provenance "twin-derived", it was inferred from the detected software version, not confirmed by direct testing. Frame these as: "Based on the detected version of [software], this version is known to have [vulnerability]." Use "is known to be affected by", "is associated with", or "may be affected by" — never present twin-derived findings as confirmed vulnerabilities.
- When delta context is provided (comparison to previous scan): NEW findings should be introduced as "New since last scan:". RECURRING findings that have been open >14 days should mention the duration with increased urgency. RESOLVED findings should be celebrated briefly ("Good news: [issue] is now fixed").

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


def build_user_prompt(brief: dict, delta_context: dict = None) -> str:
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
        sev = f.get("severity", "unknown").upper()
        desc = f.get("description", "")
        risk = f.get("risk", "")
        provenance = f.get("provenance", "")
        line = f"[{sev}] {desc}\n  Risk: {risk}"
        if provenance == "twin-derived":
            line += "\n  (Provenance: inferred from detected version, not confirmed by direct testing)"
        findings_lines.append(line)
    findings_text = "\n\n".join(findings_lines) if findings_lines else "No findings."

    # Delta section (if comparing to previous scan)
    delta_text = ""
    if delta_context:
        delta_parts = []
        if delta_context.get("resolved"):
            resolved_descs = [f"- {r['description']}" for r in delta_context["resolved"]]
            delta_parts.append("RESOLVED since last scan (good news):\n" + "\n".join(resolved_descs))
        if delta_context.get("new"):
            new_descs = [f"- [{n['severity'].upper()}] {n['description']}" for n in delta_context["new"]]
            delta_parts.append("NEW since last scan:\n" + "\n".join(new_descs))
        if delta_context.get("recurring"):
            rec_descs = [f"- [{r['severity'].upper()}] {r['description']}" for r in delta_context["recurring"]]
            delta_parts.append("Still open (recurring):\n" + "\n".join(rec_descs))
        if delta_parts:
            delta_text = "\n\nDelta since last scan:\n" + "\n\n".join(delta_parts)

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
    ) + delta_text
