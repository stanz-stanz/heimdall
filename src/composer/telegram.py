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


# Sentinel-tier cert change messages. Three change types × two languages.
# Inlined rather than loaded from .txt files because the strings are short
# and a filesystem indirection adds test surface without benefit.
_CERT_CHANGE_TEMPLATES = {
    "en": {
        "new_cert": (
            "\U0001f504 A new SSL certificate was issued for <b>{domain}</b>\n\n"
            "Issuer: {issuer}\n"
            "Valid from {not_before}\n\n"
            "This is informational, not an incident. If you or your provider renewed "
            "the certificate recently, nothing to do. If you didn't, it's worth a "
            "quick check with whoever maintains your website."
        ),
        "new_san": (
            "\U0001f504 A new hostname appeared on your certificate for <b>{domain}</b>\n\n"
            "New hostname(s): {new_sans}\n"
            "Issuer: {issuer}\n\n"
            "Someone — likely you or your provider — added a subdomain to your "
            "SSL certificate. If that matches a recent change, all good. If it "
            "doesn't ring a bell, worth a moment to verify with your web person."
        ),
        "ca_change": (
            "\U0001f504 Your certificate authority changed for <b>{domain}</b>\n\n"
            "Previous CA: {old_issuer}\n"
            "New CA: {new_issuer}\n\n"
            "Your SSL certificate is now issued by a different company than before. "
            "This usually happens when a hosting provider switches vendors or you "
            "migrated your site. Worth a quick confirmation."
        ),
    },
    "da": {
        "new_cert": (
            "\U0001f504 Et nyt SSL-certifikat er blevet udstedt til <b>{domain}</b>\n\n"
            "Udsteder: {issuer}\n"
            "Gyldigt fra {not_before}\n\n"
            "Dette er til orientering — ikke et sikkerhedsbrud. Hvis du eller din "
            "udbyder fornyede certifikatet for nyligt, er der intet at gøre. "
            "Hvis ikke, er det værd at tjekke med den, der passer jeres hjemmeside."
        ),
        "new_san": (
            "\U0001f504 Et nyt værtsnavn er dukket op på jeres certifikat for <b>{domain}</b>\n\n"
            "Nyt værtsnavn: {new_sans}\n"
            "Udsteder: {issuer}\n\n"
            "Nogen — sandsynligvis dig eller din udbyder — har tilføjet et subdomæne "
            "til jeres SSL-certifikat. Passer det med en nylig ændring, er alt fint. "
            "Hvis ikke, er det værd at bekræfte med jeres webansvarlige."
        ),
        "ca_change": (
            "\U0001f504 Jeres certifikatudsteder er skiftet for <b>{domain}</b>\n\n"
            "Tidligere udsteder: {old_issuer}\n"
            "Ny udsteder: {new_issuer}\n\n"
            "Jeres SSL-certifikat udstedes nu af en anden virksomhed end før. "
            "Det sker typisk når en hostingudbyder skifter leverandør eller I "
            "flyttede hjemmesiden. Værd at bekræfte hurtigt."
        ),
    },
}


def compose_cert_change(
    change: dict,
    lang: str = "en",
    contact_name: str = "",
    prior_issuer: str = "",
) -> list[str]:
    """Format a Sentinel-tier cert change event as a Telegram HTML message.

    Parameters
    ----------
    change : dict
        Must contain ``change_type`` (one of new_cert, new_san, ca_change),
        ``domain``, and a ``details`` dict parsed from ``details_json``.
    lang : str
        ``en`` or ``da``. Falls back to ``en`` for unknown.
    contact_name : str, optional
        Client contact name for greeting.
    prior_issuer : str, optional
        Previous CA name for ca_change messages. Empty if unknown.

    Returns
    -------
    list[str]
        Single-element list with the HTML-formatted message.
    """
    lang = lang if lang in _CERT_CHANGE_TEMPLATES else "en"
    change_type = change.get("change_type", "new_cert")
    templates = _CERT_CHANGE_TEMPLATES[lang]
    if change_type not in templates:
        change_type = "new_cert"

    details = change.get("details") or {}
    domain = html.escape(change.get("domain", ""))
    issuer = html.escape(details.get("issuer_name") or "an unknown authority")
    not_before = html.escape(details.get("not_before") or "")

    prior_sans = set(details.get("prior_sans") or [])
    new_sans_list = [
        s for s in (details.get("dns_names") or []) if s not in prior_sans
    ]
    new_sans = html.escape(", ".join(new_sans_list) or "(none)")

    old_issuer = html.escape(prior_issuer or details.get("prior_issuer") or "previous CA")
    new_issuer = issuer

    body = templates[change_type].format(
        domain=domain,
        issuer=issuer,
        not_before=not_before,
        new_sans=new_sans,
        old_issuer=old_issuer,
        new_issuer=new_issuer,
    )

    greeting = (
        f"Hi {html.escape(contact_name)},\n\n"
        if contact_name and lang == "en"
        else (f"Hej {html.escape(contact_name)},\n\n" if contact_name else "")
    )
    message = f"{greeting}{body}\n\n{FOOTER}"
    # Single cert-change messages are short — no split needed, but enforce
    # the budget as a safety net.
    if len(message) > _MESSAGE_BUDGET:
        message = message[: _MESSAGE_BUDGET - 3] + "..."
    return [message]


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
