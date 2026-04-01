# Sample Security Notification — First Contact Message

**Document type:** Draft for lawyer review
**Status:** PENDING LEGAL APPROVAL — do not send before counsel signs off
**Prepared:** 2026-04-01
**Related:** Legal briefing Q1, Q2, Q6

---

## Purpose

This is the proposed first-contact message from Heimdall to a Danish small business. It contains one specific security finding about the recipient's website, framed as a security notification — not marketing.

The message is channel-neutral: it may be delivered via email, website contact form, or Facebook Messenger depending on counsel's guidance on which channels are permissible (legal briefing Q1, Q3, Q5).

The message is intended to be reviewed by legal counsel to determine whether:

1. This framing survives classification as "direkte markedsfoering" under Markedsforingsloven §10 (Q1)
2. This message can lawfully be sent to Reklamebeskyttet businesses using website-sourced contact data (Q2)
3. The responsible disclosure framing provides protection for a commercial sender (Q6)

Two finding variants are included — one for directly observed findings (`provenance: direct`) and one for twin-derived findings (`provenance: twin-derived`). The provenance distinction affects what language is legally defensible.

---

## Message Text

```
Security notification regarding [DOMAIN]

Dear business owner,

We are writing to make you aware of a security issue that we have
observed on your website [DOMAIN].

[FINDING — VARIANT A: DIRECTLY OBSERVED]
Your website exposes [DESCRIPTION OF FINDING, e.g. "WordPress version
6.9.4 in the page source code, which is visible to any visitor" or "an
SSL certificate that expires on [DATE]"]. This means that [EXPLANATION
OF RISK IN PLAIN LANGUAGE, e.g. "attackers can look up known
vulnerabilities for this exact version and target them directly"].

[FINDING — VARIANT B: TWIN-DERIVED]
We have detected that your website uses [SOFTWARE] version [VERSION].
This version is publicly known to be affected by [BRIEF DESCRIPTION OF
VULNERABILITY]. Note: this is based on the detected software version —
we have not tested your system directly, and it is possible that the
vulnerability has already been remediated on your end.

This information is freely available to anyone who visits your website.
In other words, what we have seen can also be seen by persons with
malicious intent.

We recommend that you contact your webmaster or IT provider and ask
them to investigate this.

Heimdall is a Danish cybersecurity company that helps small and
medium-sized businesses monitor their digital security. You are welcome
to contact us if you have questions about this notification.

Best regards,

Federico Alvarez
Founder, Heimdall
Web: [WEBSITE]

---
This notification is based exclusively on publicly available information
that your website transmits to any visitor (HTTP responses, DNS records,
SSL certificates, and visible technology). No login attempts, security
tests, or other active actions were performed against your systems.

You will not be contacted again by us unless you explicitly ask for
further details.
```

---

## Legal Reasoning Notes for Counsel

### 1. No commercial content — §10 defense (Q1)

The message contains one factual finding, a risk explanation, and a recommendation to contact their own IT provider. It does NOT contain pricing, service descriptions, a call-to-action, or promotional language. The one-sentence self-description establishes sender identity without constituting solicitation.

**Question:** Does sender identity as a commercial entity convert this into marketing, even when the message body has no commercial content?

### 2. Provenance distinction — twin-derived vs. directly observed (Q4)

Variant A uses "we have observed" (directly seen in public data). Variant B uses hedged language — "publicly known to be affected by" and "we have not tested your system directly." Presenting twin-derived findings as directly observed would constitute misrepresentation.

**Question:** Is Variant B language sufficient to avoid liability if the finding is inaccurate?

### 3. Responsible disclosure framing (Q6)

The message follows standard responsible disclosure structure: identifies the issue, explains the risk, recommends remediation via the recipient's own resources, identifies the disclosing party. This mirrors NIS2-encouraged practices.

**Question:** Does responsible disclosure framing protect a commercial entity from §10 complaints?

### 4. Passive observation disclaimer

The footer establishes that no §263 violation occurred (only publicly served data) and reassures the recipient their systems were not breached.

### 5. Opt-out

"You will not be contacted again by us unless you explicitly ask for further details." — one-touch, no further action required from the recipient.

---

## Open Decisions (for Federico + Counsel)

1. **Include the Heimdall self-description sentence?** It's the only sentence that could be construed as promotional. Removing it makes the message a pure disclosure but eliminates context.
2. **Twin-derived findings in first contact at all?** More compelling but carry misrepresentation risk if inaccurate. Counsel should confirm whether Variant B language is sufficient.
3. **Channel selection:** Which electronic channels are permissible for this message? (Depends on Q1, Q3, Q5 answers.)
