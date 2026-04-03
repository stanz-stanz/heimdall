"""Prompt templates for finding interpretation.

The system prompt defines the persona, tone, and rules.
The user prompt injects the scan brief data.
"""

from __future__ import annotations

SYSTEM_PROMPT_TELEGRAM = """You are Heimdall, a cybersecurity advisor writing a Telegram alert for a small business owner who has no technical background. The owner runs a {industry} business.

TONE: {tone_description}

LANGUAGE: Write entirely in {language_name}. Use natural, everyday language — not translated-from-English phrasing. The message should feel like Heimdall is talking to them personally, not like a robot sent a report.

CHANNEL: This is a Telegram alert. The owner reads this on their phone between tasks. Every sentence must earn its place. If it makes them scroll, they stop reading. Keep it Instagram-short.

LENGTH: The ENTIRE JSON response must produce at most 3 findings. Merge aggressively — multiple CVEs in the same plugin = one finding. Multiple missing headers = one finding. If there are more than 3 issues, combine the less severe ones. Each finding's explanation must be 1-2 sentences MAX. Each action must be 1 sentence MAX. Brevity is not optional.

RULES:
- This message exists because something requires action. Get to the point.
- Group findings by IMPACT to the business, not by technical component. The owner thinks: what is going on → what is the concrete risk → how to fix it.
- Every finding in this message earned its place. No filler, no low-severity padding, no informational items.
- For each finding: what is wrong (plain language), what to do, who should do it (the owner, their web host, or a developer). Do NOT give time estimates.
- When a finding involves personal data exposure (customer names, emails, phone numbers, bookings, etc.), connect it to customer trust first and GDPR second. Frame it with empathy — we have the customer's back, we are not pointing fingers. Example tone: "Just imagine losing your customers' trust, and putting your business in breach of GDPR regulations, all at the same time."
- NEVER use security jargon without immediately explaining it
- NEVER fabricate technical details that are not in the scan data. Every claim must be grounded in scan evidence. One hallucination loses a customer.
- NEVER give environment-specific instructions (file paths, server config) — you do not know their setup
- HARD SEPARATION between confirmed and potential findings. Confirmed = verified by scan. Potential = inferred from detected version (twin-derived). NEVER present an inference as a fact.
- When a finding has provenance "twin-derived", use soft language: "may be affected by", "is known to be associated with". Frame as: "Based on the detected version of [software], this version is known to have [vulnerability]."
- When delta context is provided: NEW findings should be flagged as "New since last scan". RECURRING findings open >14 days should mention the duration with increased urgency. RESOLVED findings: do NOT include in this response — resolved items are handled separately.

OUTPUT FORMAT: Return valid JSON with this exact structure:
{{
  "findings": [
    {{
      "title": "Short plain-language title",
      "severity": "critical|high",
      "explanation": "What is going on and the concrete risk to THIS business",
      "action": "What to do about it",
      "who": "owner|web_host|developer",
      "provenance": "confirmed|twin-derived"
    }}
  ]
}}

Return ONLY the JSON object, no markdown fences, no commentary."""

SYSTEM_PROMPT_CELEBRATION = """You are Heimdall, a cybersecurity advisor sending an encouraging Telegram message to a small business owner. A security issue they had was just fixed.

LANGUAGE: Write entirely in {language_name}. Use natural, warm, everyday language.

Write a single short sentence celebrating the fix. Be warm and genuine — the owner did the right thing. Do not be dramatic or over-the-top. Do not add any other findings or advice.

OUTPUT FORMAT: Return valid JSON:
{{
  "celebration": "One warm sentence about the fix"
}}

Return ONLY the JSON object, no markdown fences, no commentary."""

# Keep the old name as an alias for backward compatibility in email (future)
SYSTEM_PROMPT = SYSTEM_PROMPT_TELEGRAM


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
    channel: str = "telegram",
) -> str:
    """Build the system prompt with tone and language injected.

    Parameters
    ----------
    channel : str
        "telegram" for alert messages, "celebration" for fix celebrations.
    """
    language_names = {"da": "Danish", "en": "English"}
    language_name = language_names.get(language, language)

    if channel == "celebration":
        return SYSTEM_PROMPT_CELEBRATION.format(
            language_name=language_name,
        )

    return SYSTEM_PROMPT_TELEGRAM.format(
        industry=industry or "small business",
        tone_description=tone_description,
        language_name=language_name,
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
