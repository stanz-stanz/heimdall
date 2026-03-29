"""Telegram message composer.

Formats interpreted findings for Telegram delivery.
Respects the 4096-character message limit, uses Telegram MarkdownV2,
and splits into multiple messages when needed.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

TELEGRAM_MAX_CHARS = 4096
# Reserve space for message numbering ("1/3\n\n") and safety margin
_MESSAGE_BUDGET = TELEGRAM_MAX_CHARS - 50


def compose_telegram(interpreted: dict, delta_context: dict = None) -> list[str]:
    """Format an interpreted brief into Telegram message(s).

    Parameters
    ----------
    interpreted : dict
        Output from ``interpret_brief``: ``good_news``, ``findings``,
        ``summary``, ``domain``, ``company_name``, ``scan_date``.

    Returns
    -------
    list[str]
        One or more message strings, each within Telegram's 4096 char limit.
        Ready to send via Telegram Bot API (plain text, not MarkdownV2 —
        the bot layer handles formatting).
    """
    domain = interpreted.get("domain", "")
    scan_date = interpreted.get("scan_date", "")

    sections = []

    # Header
    header = f"Security Report — {domain}"
    if scan_date:
        header += f" ({scan_date})"
    sections.append(header)

    # Good news
    good_news = interpreted.get("good_news", [])
    if good_news:
        good_lines = "\n".join(f"  + {item}" for item in good_news)
        sections.append(good_lines)

    # Resolved findings (delta context)
    if delta_context and delta_context.get("resolved"):
        resolved_lines = [f"  + Fixed: {r['description']}" for r in delta_context["resolved"]]
        sections.append("Fixed since last scan:\n" + "\n".join(resolved_lines))

    # Findings — split into confirmed and twin-derived groups
    findings = interpreted.get("findings", [])
    confirmed = [f for f in findings if f.get("provenance") != "twin-derived"]
    twin_derived = [f for f in findings if f.get("provenance") == "twin-derived"]

    def _format_finding(f: dict, idx: int) -> str:
        title = f.get("title", "")
        explanation = f.get("explanation", "")
        action = f.get("action", "")
        who = f.get("who", "")
        effort = f.get("effort", "")

        parts = [f"{idx}. {title}"]
        if explanation:
            parts.append(explanation)
        if action:
            action_line = f"-> {action}"
            if who:
                who_label = {"owner": "You", "web_host": "Your web host",
                             "developer": "Your developer"}.get(who, who)
                action_line += f" ({who_label}"
                if effort:
                    action_line += f", ~{effort}"
                action_line += ")"
            elif effort:
                action_line += f" (~{effort})"
            parts.append(action_line)
        return "\n".join(parts)

    idx = 1
    for f in confirmed:
        sections.append(_format_finding(f, idx))
        idx += 1

    if twin_derived:
        sections.append("--- Probable findings (based on detected versions) ---")
        for f in twin_derived:
            sections.append(_format_finding(f, idx))
            idx += 1

    # Summary
    summary = interpreted.get("summary", "")
    if summary:
        sections.append(f"---\n{summary}")

    # Join and split if needed
    full_message = "\n\n".join(sections)

    if len(full_message) <= _MESSAGE_BUDGET:
        return [full_message]

    return _split_message(sections)


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
