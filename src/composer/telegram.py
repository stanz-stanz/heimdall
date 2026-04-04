"""Telegram message composer.

Formats interpreted findings for Telegram delivery.
Respects the 4096-character message limit, uses Telegram HTML parse mode,
and splits into multiple messages when needed.
"""

from __future__ import annotations

import html

TELEGRAM_MAX_CHARS = 4096
# Reserve space for message numbering ("(1/3)\n\n") and safety margin
_MESSAGE_BUDGET = TELEGRAM_MAX_CHARS - 50

SEVERITY_LABEL = {
    "critical": "\U0001f534 Critical",
    "high": "\U0001f7e0 High",
}

FOOTER = "<b>The Heimdall team</b>\n<i>We'll keep watching</i>"


def compose_telegram(
    interpreted: dict,
    delta_context: dict | None = None,
    tier: str = "sentinel",
) -> list[str]:
    """Format an interpreted brief into Telegram HTML message(s).

    Parameters
    ----------
    interpreted : dict
        Output from ``interpret_brief``: ``findings``,
        ``domain``, ``company_name``, ``scan_date``.
    delta_context : dict, optional
        Delta context with resolved/new/recurring lists.
    tier : str
        Client tier. "watchman" suppresses the Fix line (defensive filter).

    Returns
    -------
    list[str]
        One or more HTML message strings, each within Telegram's 4096 char limit.
    """
    domain = html.escape(interpreted.get("domain", ""))
    contact_name = html.escape(interpreted.get("contact_name") or "")
    sections = []

    # Greeting
    greeting = f"Hi {contact_name}, " if contact_name else ""
    sections.append(
        f"{greeting}Heimdall has a security alert for <b>{domain}</b>"
    )

    # Findings — split into confirmed and potential
    findings = interpreted.get("findings", [])
    confirmed = [f for f in findings if f.get("provenance") != "unconfirmed"]
    potential = [f for f in findings if f.get("provenance") == "unconfirmed"]

    # Sort each group: critical first, then high
    severity_order = {"critical": 0, "high": 1}
    confirmed.sort(key=lambda f: severity_order.get(f.get("severity", "").lower(), 9))
    potential.sort(key=lambda f: severity_order.get(f.get("severity", "").lower(), 9))

    if confirmed:
        sections.append("<b>Confirmed issues</b>")
        for f in confirmed:
            sections.append(_format_finding(f, tier=tier))

    if potential:
        sections.append("<b>Potential issues</b>\n<i>(i.e. we can't confirm without your explicit consent)</i>")
        for f in potential:
            sections.append(_format_finding(f, tier=tier))

    # Footer
    sections.append(FOOTER)

    # Join and split if needed
    full_message = "\n\n".join(sections)

    if len(full_message) <= _MESSAGE_BUDGET:
        return [full_message]

    return _split_message(sections)


def compose_celebration(domain: str, celebration_text: str, contact_name: str = "") -> list[str]:
    """Format a fix-celebration message in Telegram HTML.

    Parameters
    ----------
    domain : str
        The domain where the fix was confirmed.
    celebration_text : str
        The celebration sentence from the interpreter.
    contact_name : str, optional
        Client's contact name for greeting.

    Returns
    -------
    list[str]
        Single-element list with the celebration message.
    """
    safe_domain = html.escape(domain)
    safe_name = html.escape(contact_name) if contact_name else ""
    safe_text = html.escape(celebration_text)

    greeting = f"Hi {safe_name}, " if safe_name else ""
    message = (
        f"{greeting}good news for <b>{safe_domain}</b>\n\n"
        f"\u2705 {safe_text}\n\n"
        f"{FOOTER}"
    )

    return [message]


def _format_finding(f: dict, tier: str = "sentinel") -> str:
    """Format a single finding as an HTML block.

    For Watchman tier, the Fix line is suppressed (defensive filter —
    the prompt should already omit the action field for Watchman).
    """
    severity = f.get("severity", "high").lower()
    label = SEVERITY_LABEL.get(severity, SEVERITY_LABEL["high"])
    title = html.escape(f.get("title", ""), quote=False)
    explanation = html.escape(f.get("explanation", ""), quote=False)

    parts = [f"<b>{label}: {title}</b>"]
    if explanation:
        parts.append(explanation)

    if (tier or "sentinel").lower() != "watchman":
        action = html.escape(f.get("action", ""), quote=False)
        if action:
            parts.append(f"\u21b3 <b>Fix:</b> {action}")

    return "\n".join(parts)


def _split_message(sections: list[str]) -> list[str]:
    """Split sections across multiple messages, each under the limit."""
    messages = []
    current = ""

    for section in sections:
        candidate = (current + "\n\n" + section).strip() if current else section
        if len(candidate) <= _MESSAGE_BUDGET:
            current = candidate
        else:
            if current:
                messages.append(current)
            # If a single section exceeds the limit, truncate it
            if len(section) > _MESSAGE_BUDGET:
                current = section[:_MESSAGE_BUDGET - 20] + "\n\n[continued...]"
            else:
                current = section

    if current:
        messages.append(current)

    # Add numbering if split
    if len(messages) > 1:
        total = len(messages)
        messages = [f"({i}/{total})\n\n{msg}" for i, msg in enumerate(messages, 1)]

    return messages
