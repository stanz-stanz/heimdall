# Legal Briefing — Outreach, Scanning & Operations for Heimdall

**Prepared for:** Legal consultation (Anders Wernblad, Aumento Law)
**Date:** 2026-03-29 (re-targeted to Aumento Law 2026-04-23; originally sent to Plesner / David van Boen 2026-04-14)
**Prepared by:** Federico Alvarez, Heimdall

---

## What is Heimdall 

- Heimdall is an External Attack Surface Management (EASM) service for Danish SMBs. It passively reads publicly visible websites — HTTP headers, HTML source, DNS records, SSL certificates, technology fingerprints — and produces a per-site brief: detected CMS, missing security headers, SSL status, plugin versions, and a plain-language risk assessment.

- Heimdall also operates a **digital twin**: it reconstructs a replica of a customer's website on its own infrastructure from passively collected data, then runs vulnerability scanners (Nuclei) against the replica. No requests touch the live site beyond the initial passive visit. Twin-derived findings are enriched with WPVulnerability API lookups (a public CVE database for WordPress plugins and core).

Business model: inform Danish SMBs of their security exposure and offer monitoring subscriptions.

- Founded by Federico Alvarez — senior software engineer, in Denmark since 2019. LinkedIn: https://www.linkedin.com/in/federico-alvarez-54bb5211/
- Startup Denmark (SIRI) application in preparation.

---

## Why We Need Legal Advice

We can scan ~2,400 businesses in Vejle and produce real findings about their websites. Our challenge is **reaching them legally**. Markedsføringsloven §10 prohibits unsolicited electronic communication for direct marketing, and CVR Reklamebeskyttet adds further restrictions. We also need guidance on the legal boundary of external scanning under Straffeloven §263, on the evidential value of our compliance logging, and on GDPR classification.

---

## Outreach Questions

### Q1 — Is a security notification "direct marketing" under §10?

Our proposed first contact contains a single finding about the recipient's own website, a plain-language risk explanation, and Heimdall's identity. No pricing, service description, or call to action. Commercial intent exists; commercial content does not. See **attachment 1** for the exact wording.

**Framework:** Markedsføringsloven §10. If classified as direct marketing, every electronic first-contact channel is closed.

**We need to know:** Does the absence of commercial content in the message body hold against a Forbrugerombudsmanden complaint? Does sender identity (a commercial entity) change the classification when the body carries no commercial content?

---

### Q2 — Does Reklamebeskyttet block all contact, or only CVR-sourced contact data?

Reklamebeskyttet prohibits "other businesses" from using "information registered in CVR" for direct marketing. We would harvest email addresses and contact-form URLs from the business's own website, not from CVR.

**Framework:** Markedsføringsloven §6. If the restriction blocks all unsolicited contact regardless of source, ~1,200 Vejle businesses become unreachable through any channel.

**We need to know:** Can we contact a Reklamebeskyttet-registered business using website-sourced contact data without violating §6?

---

### Q3 — Which electronic channels are covered by §10 "elektronisk post"?

We need a single answer across candidate first-contact channels. Every channel would carry the same body (see **attachment 1**).

- **(a)** Email to a published business address harvested from the business's own website (not from virk.dk CVR).
- **(b)** Website "Kontakt os" contact form — one submission per business.
- **(c)** Facebook Messenger to a business page with Messenger enabled — organic, one-to-one, not sponsored.
- **(d)** Other non-email electronic channels (LinkedIn InMail, WhatsApp Business).

**Framework:** Markedsføringsloven §10. The 2021 guidance treats "elektronisk post" broadly and names social media messages explicitly.

**We need to know:**

- Which of (a)–(d) qualify as "elektronisk post"?
- Does publishing a contact form or enabling Messenger create implied consent for business-relevant inbound messages?
- Are automated contact-form submissions treated differently from email?

---

### Q4 — Digital twin: legal basis for twin-derived findings

Heimdall reconstructs the customer's website on its own infrastructure from publicly available data and runs vulnerability scanners against the replica. The §263 argument: the twin is Heimdall's system, built from lawfully collected public data. See **attachment 1**, second variant, for how we label twin-derived findings as "inferred, not confirmed".

**Framework:** Straffeloven §263. If the twin is deemed to circumvent §263's intent, twin scans become unauthorised access. Sharing inaccurate unconfirmed findings could create tort liability.

**We need to know:**

- Does the §263 interpretation hold?
- Can twin findings be shared with a prospect labelled as inferred?
- If a twin finding is inaccurate (e.g., wrong version detected), does sharing it create liability? Does the "inferred from detected versions, not confirmed" label mitigate?
- Any GDPR implications in constructing a replica from public data?

---

### Q5 — Responsible disclosure as legal framework for first contact

Two regulatory regimes strengthen this framing materially:

- **LOV 434/2025** (Denmark's NIS2 implementation, in force since 2025-07-01) makes coordinated vulnerability disclosure a supervised practice. Covered entities must report significant incidents to the sector CSIRT under SAMSIK.
- **EU CRA Article 14** — vulnerability reporting obligations begin applying on 2026-09-11, normalising coordinated vulnerability disclosure as a regulated EU practice.

We would frame first contact as responsible disclosure under both regimes. See **attachment 1**.

**Framework:** Markedsføringsloven §10 (if the framing does not protect commercial entities, our strongest first-contact argument falls away) and Straffeloven §263 (if passively discovered vulnerabilities are treated as "discovered without authorisation", the disclosure could be evidence of prior access).

**We need to know:**

- Does Denmark (post-NIS2) have an implicit safe harbour for responsible disclosure of passively discovered vulnerabilities?
- Does CRA Article 14 strengthen the framing even if Heimdall is not itself CRA-covered?
- Does the framing protect commercial entities from §10 complaints, or is it only available to non-commercial researchers?
- Does passive discovery of vulnerabilities create §263 exposure regardless of subsequent disclosure?

---

## Scanning, Consent & Operational Questions

### Q6 — Scanning authorisation template review

When a customer subscribes (Sentinel tier), Heimdall performs Layer 2 active scanning with written consent. See **attachment 2** for the draft template.

**Framework:** Straffeloven §263 (inadequate consent = unauthorised access) and GDPR Article 28 (DPA requirements).

**We need to know:** Does the template adequately establish "berettiget adgang"? Are scope, duration, and GDPR provisions sufficient?

---

### Q7 — Does the Layer 1/2 distinction hold under §263?

Heimdall classifies scanning in two layers:

- **Layer 1 (Passive):** reads what the server sends to any visitor — headers, HTML, DNS, SSL, fingerprints.
- **Layer 2 (Active):** crafted requests to detect vulnerabilities (Nuclei, Nmap).

Without consent, only Layer 1 runs. The Aalborg University §263 analysis describes a "reasonableness test" for "uberettiget" access; publicly served HTTP responses are voluntarily provided to any client. The ICLG 2026 Denmark chapter says unsolicited penetration "most likely" violates §263. No Danish court has ruled on external scanning as distinct from hacking.

**We need to know:**

- Does the Layer 1/2 distinction hold as a legal boundary under §263?
- Any risk in Layer 1 activity alone (reading publicly served responses)?
- At what point does automated collection cross from observation to "gaining access"?

---

### Q8 — Is there a Danish safe harbour for security research?

We have found no Danish court ruling on external scanning, no regulatory guidance permitting or prohibiting it, no safe harbour comparable to the US DOJ 2022 CFAA policy or the Dutch CVD framework, and no published guidance from Datatilsynet or SAMSIK on this topic. LOV 434/2025 encourages coordinated vulnerability disclosure but does not create an explicit safe harbour for commercial security research.

**We need to know:**

- Does any Danish provision protect commercial security research in good faith?
- Does LOV 434/2025 create implicit protection?
- What is the practical risk from a §263 complaint about Layer 1 scanning?

---

### Q9 — Who can legally authorise active scanning (including agency delegation)?

Our consent system records the signer's name, role, and email but does not validate legal standing. Two scenarios matter:

1. **Direct customer authorisation** — the CVR-registered representative, or an employee/freelancer/contact with operational control of the website.
2. **Agency delegation (white-label channel)** — a web agency authorises scanning across multiple end-client domains it manages.

**Framework:** Straffeloven §263. If consent comes from someone without legal authority, the defence collapses. In the agency case, one objecting end client could expose Heimdall for all sites scanned under that agency authorisation.

**We need to know:**

- Who has legal standing to authorise active scanning under Danish law — the CVR-registered representative only, or someone with demonstrated domain control?
- If an unauthorised person signs a consent (f.ex. a manager), does §263 liability fall on Heimdall or on the signer?
- Can a web agency legally authorise Heimdall to scan its end-clients' domains, or must each end client consent independently?
- If agency delegation is possible, what contractual language is required between the agency, its clients, and Heimdall?

---

### Q10 — Compliance system and audit trail: what satisfies a Danish court for §263 due diligence?

Heimdall operates an internal program -codename **Valdí**-, a programmatic compliance AI agent we built that validates scanning code before execution at two gates:

1. **Scan-type validation** — reviews code against documented rules and issues approval tokens.
2. **Per-customer authorisation** — verifies consent before each scan batch.

Every decision is forensic-logged with timestamps, reasoning, and rule citations. We currently log scan-type validation, per-customer consent checks, robots.txt decisions, and scan execution metadata. We do not currently capture full HTTP request/response bodies, client IP addresses, or network traces. A sample log excerpt will be brought to the meeting.

**We need to know:**

- Does a programmatic compliance layer with forensic logs reduce §263 liability for inadvertent boundary crossings? Would it satisfy a court's due diligence expectations?
- What documentation does a Danish court or prosecutor expect for external scanning — function-level validation and timestamped approvals, or more (full HTTP capture, IP addresses, network traces)?

---

### Q11 — Consent scope: explicit domains or wildcards?

Our consent system requires explicit per-domain listing. Consent for `test.dk` does not cover `sub.test.dk`; no wildcard mechanism exists. Subdomain discovery during scanning can reveal domains after consent is signed.

**Framework:** Straffeloven §263. Scanning a subdomain not in the consent document is technically unauthorised access.

**We need to know:**

- Is explicit listing legally required, or does `*.company.dk` suffice under §263?
- If we discover `blog.company.dk` during scanning, must we obtain supplementary consent before continuing?

---

### Q12 — What form must scanning consent take?

Our system accepts written consent only (digitally signed or acknowledged document). The template itself is covered in Q6 (attachment 2).

**We need to know:**

- Must consent be in writing, or does recorded verbal consent suffice?
- Does click-to-accept with audit logging equal a wet-ink signature under §263?
- Must the document explicitly reference §263?

---

### Q13 — Is Heimdall a data controller or a processor under GDPR?

When scanning with consent, Heimdall collects technical data that may include personal data (WHOIS emails, SSL certificate names). Classification likely differs by scenario: consented scanning (processor on the customer's behalf) versus prospecting (controller, no customer relationship).

**Framework:** GDPR Articles 5, 6, 28. Fines up to 4% of turnover / €20M.

**We need to know:**

- Controller or processor for consented customer scanning?
- Controller for Layer 1 prospecting scans (no customer relationship yet, passive scanning without consent)?

---

### Q14 — NIS2 and CRA applicability to Heimdall itself

Two regimes may touch Heimdall as an entity — not only the responsible-disclosure argument in Q5:

- **LOV 434/2025** (Denmark's NIS2) — in force since 2025-07-01, supervision under SAMSIK. Covers essential and important entities in listed sectors. An EASM provider monitoring Danish SMB websites and delivering findings may fall under "digital infrastructure" or "ICT service management (B2B)" annexes. 
- **EU CRA** (Regulation 2024/2847) — Article 14 vulnerability reporting begins applying on 2026-09-11; main product obligations from 2027-12-11. Applies to "products with digital elements" placed on the EU market. Whether an EASM SaaS + Telegram alerts qualifies as a "product" is still being clarified by the Commission.

**Framework:** NIS2 — registration duty (deadline was 2025-10-01), incident reporting, risk management, management-board accountability. Fines up to €10M or 2% of global turnover. CRA — vulnerability reporting to CSIRT/ENISA on a 24h/72h/14-day timeline. 

**We need to know:**

- Would Heimdall fall under NIS2 as an important entity in digital infrastructure or ICT service management (B2B)?
- If yes, what minimum compliance steps (Virk registration, security contact, incident reporting channel, risk assessment) are required.
- If CRA applies, how do Article 14 obligations interact with findings about customer websites, where Heimdall is not the manufacturer of the vulnerable software?

---
## Documents Attached

1. **Sample security notification** — `docs/legal/sample-security-notification.md` — proposed first-contact message, two variants (directly observed and twin-derived findings).
2. **Scanning authorisation template** — `docs/legal/scanning-authorization-template.md` — draft consent document for Sentinel-tier subscribers.

Additional internal documents (scanning rules, compliance checklist, legal risk assessment, sample scan output, compliance log excerpt) are available on request.



