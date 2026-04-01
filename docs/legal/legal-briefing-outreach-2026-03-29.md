# Legal Briefing — Outreach, Scanning & Operations for Heimdall

**Prepared for:** Legal consultation (Plesner / Kromann Reumert / Bech-Bruun)
**Date:** 2026-03-29
**Meeting:** Week of 2026-03-31
**Prepared by:** Federico Alvarez, Heimdall

---

## What Heimdall Does

Heimdall is an External Attack Surface Management (EASM) service for Danish small businesses. It **passively scans** publicly visible websites — reading HTTP headers, HTML source, DNS records, SSL certificates, and technology fingerprints. This is the same data any browser receives when visiting a website.

From this, Heimdall produces a brief per domain: detected CMS, missing security headers, SSL status, plugin versions, and a plain-language risk assessment.

Heimdall also operates a **digital twin**: it reconstructs a replica of the target's website on its own infrastructure from passively collected data, then runs vulnerability scanners (Nuclei, WPScan) against the replica — never against the target's live server.

Business model: inform Danish SMBs of their security exposure and offer monitoring subscriptions (199–799 kr./month).

---

## Why We Need Legal Advice

We can scan ~2,400 businesses in Vejle and produce real findings about their websites. Our challenge is **reaching them legally**. Danish marketing law (Markedsføringsloven §10) prohibits unsolicited electronic communication for direct marketing. The CVR Reklamebeskyttet registry adds further restrictions. Our go-to-market depends on knowing exactly where the boundaries are.

We also need guidance on scanning legality. Our passive/active distinction (Layer 1 vs Layer 2) is central to our compliance model but unconfirmed by Danish legal counsel. Questions about consent authority, consent form, our compliance system's evidential value, and GDPR classification remain open.

---

## Outreach Questions

### Question 1: Is a security notification "direct marketing" under §10?

**Context:** Our proposed first contact contains one specific finding about the recipient's own website, a plain-language risk explanation, and Heimdall's identity. No pricing, no service description, no call-to-action. The commercial intent exists — but the message contains zero commercial content.

**Legal framework:** Markedsføringsloven §10 — violation triggers Forbrugerombudsmanden complaint, fines, cease-and-desist. If classified as "direkte markedsføring," every electronic first contact channel is closed.

**Our reasoning:** The 2021 spam guidance targets commercial solicitation. A security notification about the recipient's own infrastructure may fall outside §10 because its purpose is to inform, not sell.

**What we need to know:** Does this framing hold against a Forbrugerombudsmanden complaint? Does sender identity as a commercial entity change the classification when the message itself has no commercial content?

---

### Question 2: Does Reklamebeskyttet block ALL contact, or only CVR-sourced contact data?

**Context:** CVR Reklamebeskyttet states "other businesses may not use the information registered in CVR for direct marketing." If we obtain contact information (e.g., email, contact form URL) from the business's own website (not CVR), the restriction may not apply.

**Legal framework:** Markedsføringsloven §6 — if the restriction blocks all unsolicited contact (not just CVR-sourced), ~1,200 Vejle businesses become unreachable through any channel.

**Our reasoning:** Using website-sourced contact data does not use CVR-registered information.

**What we need to know:** Can we contact a Reklamebeskyttet business using website-sourced data (email address, contact form) if we do not use any CVR-registered information?

---

### Question 3: Are website contact forms covered by §10?

**Context:** Many businesses have a "Kontakt os" form. We would submit a security notification about that specific website — not a bulk campaign. The business published the form to receive messages.

**Legal framework:** Markedsføringsloven §10 — if form submissions count as "elektronisk post," this channel is illegal for unsolicited contact. Automated form submissions could also be characterized as bot activity.

**Our reasoning:** A contact form submission uses the recipient's own published channel. The message is about their own website, not a generic promotion.

**What we need to know:** Does a contact form submission constitute "elektronisk post" under §10? Is it treated differently from email to a published address?

---

### Question 4: Digital twin — legal basis for twin-derived findings

**Context:** Heimdall reconstructs a prospect's website on its own infrastructure from Layer 1 data, then runs vulnerability scanners against the replica. The legal argument: §263 criminalizes access to "en andens datasystem" — the twin is Heimdall's system, built from public data.

**Legal framework:** Straffeloven §263 (18 months / 6 years) — if the twin is deemed to circumvent §263's intent, twin scans become unauthorized access. Sharing inaccurate twin-derived findings could also create tort liability.

**Our reasoning:** The twin is demonstrably our infrastructure. Input data was lawfully collected. No requests touch the prospect's live systems beyond the initial passive visit.

**What we need to know:**
- Does the interpretation hold? Any risk under §263 or other provisions?
- Can twin findings be shared with the prospect (labeled as inferred, not confirmed)?
- If twin findings are inaccurate (wrong version detected), does sharing them create liability? Does labeling them as "inferred from detected versions, not confirmed" mitigate?
- Any GDPR implications in constructing a replica from public data?

---

### Question 5: Facebook Messenger to business pages

**Context:** Danish micro-businesses commonly have Facebook business pages with Messenger enabled. We would send a one-to-one security finding through Messenger — not a broadcast or sponsored message.

**Legal framework:** Markedsføringsloven §10 — the 2021 guidance explicitly includes "social media messages" in the spam ban scope.

**Our reasoning:** The business chose to enable Messenger. The message is about their own website, not a promotion.

**What we need to know:** Is an organic Messenger message to a business page "elektronisk post" under §10? Does enabling Messenger create implied consent for business-relevant messages?

---

### Question 6: Responsible disclosure as legal framework for first contact

**Context:** Responsible disclosure is a recognized cybersecurity practice. NIS2 encourages coordinated vulnerability disclosure. Denmark's CFCS supports it. We could frame first contact as responsible disclosure.

**Legal framework:** Markedsføringsloven §10 — if responsible disclosure framing doesn't protect commercial entities, our strongest first-contact argument falls away. Straffeloven §263 — if passively discovered vulnerabilities are treated as "discovered without authorization," the disclosure could be evidence of prior access.

**What we need to know:**
- Does Denmark have a safe harbour for responsible disclosure of passively discovered vulnerabilities?
- Does the framing protect commercial entities from §10 complaints?
- Does passive discovery of vulnerabilities create §263 exposure?

---

### Question 7: Scanning authorization template review

**Context:** When a client subscribes, Heimdall performs active scanning with written consent. We have drafted a template (attached).

**Legal framework:** Straffeloven §263 — if missing required elements, signed consents may be insufficient and scans retroactively become unauthorized access. GDPR Article 28 — DPA requirements.

**What we need to know:** Does the template adequately establish "berettiget adgang"? Are scope, duration, and GDPR provisions sufficient?

---

## Scanning, Consent & Operational Questions

### Question 8: Does Heimdall's passive/active distinction hold under §263?

**Context:** Heimdall classifies scanning into three layers:
- **Layer 1 (Passive):** Reads only what the server sends to any visitor (headers, HTML, DNS, SSL, fingerprints)
- **Layer 2 (Active):** Crafted requests to detect vulnerabilities (Nuclei, WPScan, Nmap)
- **Layer 3 (Exploitation):** Permanently forbidden

Without consent, only Layer 1 is performed.

**Legal framework:** Straffeloven §263 (18 months / 6 years) — if Layer 1 constitutes "gaining access to another person's data system," the entire business model is criminal. No Danish court has ruled on external scanning as distinct from hacking.

**Our reasoning:** The Aalborg University §263 analysis describes a "reasonableness test" for "uberettiget." Publicly served HTTP responses are voluntarily provided to any client. The ICLG 2026 Denmark chapter says unsolicited penetration "most likely" violates §263 — the boundary is unsettled.

**What we need to know:**
- Does the Layer 1/2 distinction hold as a legal boundary under §263?
- Is there any risk in Layer 1 activity (reading publicly served responses)?
- At what point does automated collection cross from observation to "gaining access"?

---

### Question 9: Is there a Danish safe harbor for security research?

**Context:** We found no Danish court ruling on external scanning, no regulatory guidance permitting or prohibiting it, no safe harbor comparable to the US DOJ 2022 CFAA policy or Dutch CVD framework, and no guidance from Datatilsynet or CFCS on this topic. NIS2 encourages disclosure but Denmark's implementation creates no explicit safe harbor.

**Legal framework:** Straffeloven §263 — without a safe harbor, a single police complaint could trigger a criminal investigation with no established defense precedent.

**What we need to know:**
- Any Danish provision or practice protecting commercial security research in good faith?
- Does the NIS2 implementation create any implicit safe harbor?
- If no safe harbor exists, what practical risk from a complaint about Layer 1 scanning?

---

### Question 10: Who can legally authorize active scanning?

**Context:** Our consent system records the authorizing person's name, role, and email, but deliberately does not validate who signs — the role field is "informational only," deferred to legal counsel.

**Legal framework:** Straffeloven §263 — if consent comes from someone without legal authority, the defense collapses. A business owner who says "I never authorized that" invalidates the consent.

**Our reasoning:** We assumed the CVR-registered legal representative can authorize. But for small businesses, the person managing the website is often an employee, freelancer, or agency contact.

**What we need to know:**
- Who has legal standing to authorize active scanning under Danish law?
- Must it be the CVR-registered representative, or can someone with domain control suffice?
- If an unauthorized person signs, does §263 liability fall on Heimdall or the signer?

---

### Question 11: Can a web agency authorize scanning of their clients' sites?

**Context:** Heimdall's model includes a white-label channel where agencies authorize scanning across multiple client domains they manage. Our legal risk assessment notes this depends on the agency-client contractual relationship.

**Legal framework:** Straffeloven §263 — if agency consent doesn't transfer, all scans under an agency authorization are unauthorized. One objecting client could expose Heimdall for all agency-managed sites.

**Our reasoning:** Agencies typically have admin access, but authorizing a third party (Heimdall) may exceed a standard agency-client agreement.

**What we need to know:**
- Can an agency legally authorize Heimdall to scan their clients' domains?
- Must each end client consent independently?
- If delegation is possible, what contractual language is required?

---

### Question 12: Does our compliance system reduce liability for inadvertent boundary crossings?

**Context:** Heimdall operates Valdí, a programmatic compliance agent that validates all scanning code before execution at two gates: scan-type validation (reviews code against documented rules, issues approval tokens) and per-target authorization (verifies consent before each scan batch). Every decision — approval or rejection — is forensic-logged with timestamps, reasoning, and rule citations. We will bring a sample log excerpt.

**Legal framework:** Straffeloven §263 — without legal recognition of the compliance system, an inadvertent boundary crossing is treated as plain unauthorized access with no mitigation.

**Our reasoning:** If a function inadvertently crosses the Layer 1/2 boundary, forensic logs demonstrate systematic compliance, pre-execution review, and no intent to exceed the boundary.

**What we need to know:**
- Does a programmatic compliance layer with forensic logs reduce §263 liability for inadvertent crossings?
- Would this satisfy a court's due diligence expectations?
- What improvements would strengthen its evidential value?

---

### Question 13: What audit trail would a Danish court expect?

**Context:** Heimdall logs: scan-type validation (approval/rejection), per-target consent checks, robots.txt decisions, scan execution metadata (timestamps, targets, tools). We built this proactively but don't know what courts actually expect.

**Legal framework:** Straffeloven §263 — if our logs lack what courts expect (e.g., full request/response captures, IP addresses), the due diligence argument weakens.

**What we need to know:**
- What documentation would a court or prosecutor expect for external scanning?
- Are function-level validation, consent checks, and timestamped approvals/rejections sufficient?
- Should we log additional data (full HTTP logs, IP addresses, network traces)?

---

### Question 14: Consent scope — explicit domains or wildcards?

**Context:** Our consent system requires explicit per-domain listing. Consent for `test.dk` does NOT cover `sub.test.dk`. No wildcard mechanism exists. This creates onboarding friction when clients don't know all their subdomains.

**Legal framework:** Straffeloven §263 — scanning a subdomain not in the consent document is technically unauthorized access.

**Our reasoning:** Strict matching is the conservative default. But subdomain discovery may reveal domains after consent is signed.

**What we need to know:**
- Is explicit listing legally required, or would `*.company.dk` suffice under §263?
- If we discover `blog.company.dk` during scanning, must we get supplementary consent?
- How should consent handle dynamically discovered subdomains?

---

### Question 15: What form must scanning consent take?

**Context:** Our system accepts written consent only (digitally signed or acknowledged document). The authorization template is one of the meeting items (Q8).

**Legal framework:** Straffeloven §263 — if electronic consent (click-to-accept) doesn't hold up, all digitally onboarded clients have insufficient authorization.

**What we need to know:**
- Must consent be in writing, or would recorded verbal consent suffice?
- Does click-to-accept with audit logging equal a wet-ink signature?
- Must the document explicitly reference §263?

---

### Question 16: Is Heimdall a data controller or data processor under GDPR?

**Context:** When scanning (with consent), Heimdall collects technical data about websites. Some may include personal data (WHOIS emails, SSL certificate names). Classification likely differs by scenario: in consented scanning, Heimdall processes on the client's behalf (processor); in prospecting, Heimdall determines purposes and means (controller).

**Legal framework:** GDPR Articles 5, 6, 28 — fines up to 4% of turnover / €20M. Misclassification means processing without legal basis. Datatilsynet can order deletion of all collected data.

**What we need to know:**
- Controller or processor for consented client scanning?
- Controller for Layer 1 prospecting scans (no client relationship)?
- Separate GDPR obligations for the digital twin?
- Required DPA provisions for consented scanning?

---

## Summary of What Hinges on Legal Advice

### Outreach

| Question | If favorable | If unfavorable |
|----------|-------------|----------------|
| Q1: Notification ≠ marketing | Electronic channels open | No viable first-contact channel |
| Q2: Reklamebeskyttet = CVR data only | Website-sourced data usable | ~1,200 businesses unreachable |
| Q3: Contact forms ≠ electronic mail | Scalable digital channel | Must avoid electronic first contact |
| Q4: Twin findings shareable | CVE-level findings in outreach | Layer 1 findings only |
| Q5: Messenger viable | Primary micro-business channel | Closed for first contact |
| Q6: Responsible disclosure framing | Strong first-contact protection | Must be more cautious |

### Scanning & Operations

| Question | If favorable | If unfavorable |
|----------|-------------|----------------|
| Q8: Layer 1/2 holds under §263 | Business model validated | Must restrict or abandon scanning |
| Q9: Safe harbor exists | Additional protection layer | Rely solely on "reasonableness" argument |
| Q11: Agency can delegate consent | White-label channel viable | Individual consent per end client |
| Q12: Compliance system reduces liability | Investment justified | Must add controls beyond Valdí |
| Q14: Wildcard consent scope | Simpler onboarding | Update consent per new subdomain |
| Q15: Electronic consent sufficient | Digital onboarding viable | Physical signatures required |
| Q16: Data processor for client scanning | Standard DPA covers it | Separate controller obligations |

---

## Documents Attached

1. **Sample security notification** — `docs/legal/sample-security-notification.md` — the proposed first-contact letter (two variants: directly observed and twin-derived findings)
2. **Scanning authorization template** — `docs/legal/scanning-authorization-template.md` — draft consent document for active scanning clients

Additional internal documents (scanning rules, compliance checklist, legal risk assessment, sample scan output, compliance log excerpt) are available on request.

---

## About Heimdall

- Created by Federico Alvarez (senior software engineer, in Denmark since 2019). Linkedin: https://www.linkedin.com/in/federico-alvarez-54bb5211/ 
- Startup Denmark (SIRI) application in the making
- No CVR yet — pending the above
- Technical infrastructure: Raspberry Pi 5, Docker, Claude API
