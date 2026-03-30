# Legal Briefing — Outreach Strategy for Heimdall

**Prepared for:** Legal consultation (Plesner / Kromann Reumert / Bech-Bruun)
**Date:** 2026-03-29
**Meeting:** Week of 2026-03-31
**Prepared by:** Federico Alvarez, Heimdall

---

## What Heimdall Does

Heimdall is an External Attack Surface Management (EASM) service for Danish small businesses. It **passively scans** publicly visible websites — reading HTTP headers, HTML source, DNS records, SSL certificates, and technology fingerprints. This is the same information any browser receives when visiting a website. No crafted probes, no port scanning, no login attempts.

From this passive scan, Heimdall produces a brief per domain: detected CMS (e.g., WordPress 6.9.4), missing security headers, SSL certificate status, plugin versions, and a plain-language risk assessment.

Heimdall also operates a **digital twin** system: it reconstructs a replica of the target's website on its own infrastructure from the passively collected data, then runs vulnerability scanners (Nuclei, WPScan) against the replica. The twin is Heimdall's property — no requests are ever sent to the target's live infrastructure beyond the initial passive observation.

The business model: inform Danish SMBs of their security exposure and offer monitoring subscriptions (199–799 kr./month).

---

## Why We Need Legal Advice

We have built the technical capability to scan ~2,400 businesses in Vejle and produce specific, real findings about their websites. Our challenge is **reaching them legally** to share those findings.

Danish marketing law (Markedsføringsloven §10) prohibits unsolicited electronic communication for direct marketing. The CVR Reklamebeskyttet registry adds further restrictions. We need precise answers on where the boundaries are, because our entire go-to-market depends on it.

---

## Questions for Counsel

### Question 1: Is a security notification "direct marketing" under §10?

**Context:** §10 prohibits unsolicited electronic communication "med henblik på direkte markedsføring." Our proposed first contact contains:

- One specific finding about the recipient's own website (e.g., "Your WordPress version 6.9.4 is publicly visible and has 3 known vulnerabilities")
- A plain-language explanation of the risk
- Heimdall's identity and contact information
- No pricing, no service description, no call-to-action to purchase

The commercial intent exists — we hope they will eventually become a paying customer. But the first message contains zero commercial content. It is functionally identical to a responsible disclosure notification.

**Our reasoning:** The Forbrugerombudsmanden's 2021 spam guidance targets commercial solicitation. A security notification about a recipient's own publicly visible infrastructure may fall outside "direkte markedsføring" because the purpose is to inform, not to sell. The sales conversation only occurs if the recipient initiates contact.

**What we need to know:** Does this framing hold? Would it survive a complaint to the Forbrugerombudsmanden? Does the existence of a commercial entity behind the notification change the classification, even if the message itself contains no commercial content?

---

### Question 2: Does Reklamebeskyttet in CVR block ALL unsolicited contact, or only CVR-sourced contact data?

**Context:** Our research indicates that CVR Reklamebeskyttet only prohibits use of contact information **sourced from the CVR register** for marketing purposes. If we obtain a business's phone number or address from their own website (not from CVR), the Reklamebeskyttet flag may not apply to that data.

**Our reasoning:** The Reklamebeskyttet registration says "other businesses may not use the information registered in CVR for direct marketing." If we derive contact information from the business's own public website, we are not using CVR-registered information.

**What we need to know:** Is this interpretation correct? Can we contact a Reklamebeskyttet business using contact information from their own website, provided we do not use their CVR-registered address, phone, or email? Does this distinction hold for:
- Physical postal mail (using address from their website, not CVR)?
- Phone calls (using phone number from their website, not CVR)?

---

### Question 3: Is a physical letter to a Reklamebeskyttet business lawful if framed as a security notification?

**Context:** Physical mail is not "electronic communication" under §10. However, Reklamebeskyttet businesses have signaled they do not want advertising. If a letter contains a security notification (one finding, no pricing, no service offer), is it:

- (a) Exempt from Reklamebeskyttet because it is not advertising?
- (b) Prohibited because the sender is a commercial entity and the ultimate purpose is commercial?
- (c) A gray area that depends on the content and framing?

**What we need to know:** Can Heimdall send a physical letter containing a factual security finding to a Reklamebeskyttet business, provided the letter contains no pricing, no service description, and no commercial call-to-action? What specific language or disclaimers would strengthen the legal position?

---

### Question 4: Are website contact forms covered by §10's electronic communication ban?

**Context:** Many business websites have a "Kontakt os" (Contact Us) form. We are considering filling out these forms with a security notification about that specific website. The argument:

- The business published the form to receive messages
- We are not sending email — we are using their own contact mechanism
- The message is about their website specifically, not a bulk campaign
- No email address is harvested or stored

**Our reasoning:** A contact form submission is an initiated use of the recipient's own published communication channel. It is not equivalent to unsolicited email sent to a harvested address. The message content (a security finding about their own website) is relevant to their business operations.

**What we need to know:** Does submitting a security notification through a business's own website contact form constitute "elektronisk post" under §10? Would this be treated differently from sending an email to their published email address?

---

### Question 5: The digital twin — legal basis for twin-derived findings

**Context:** Heimdall constructs a replica of a prospect's website on its own infrastructure from publicly collected data (Layer 1 scan: HTTP headers, HTML source, DNS, SSL, technology fingerprints). Vulnerability scanners (Nuclei, WPScan) then run against this replica — never against the prospect's live server.

The legal argument: Straffeloven §263, stk. 1 criminalizes unauthorized access to "en andens datasystem" (another person's data system). The digital twin is Heimdall's system, built from lawfully obtained public data. Running scanners against it cannot constitute a §263 violation.

**What we need to know:**
- Does this interpretation hold? Is there any risk under §263 or any other provision?
- Can findings from twin scans be shared with the prospect (with clear labeling that they are inferred from detected versions, not confirmed by direct testing)?
- Does the use of twin-derived findings in commercial outreach create any additional liability?
- Are there any data protection implications (GDPR) in constructing a technical replica from publicly available data?

---

### Question 6: Facebook business page messages — marketing or customer inquiry?

**Context:** Danish micro-businesses (restaurants, clinics, barbershops) commonly have Facebook business pages with Messenger enabled. We are considering sending a message through Facebook Messenger to a business page, containing a security finding about their website.

The Forbrugerombudsmanden's 2021 guidance includes "social media messages" within the scope of the spam ban. However:

- The business chose to enable Messenger on their public page
- The message is about their own business operations (website security)
- It is one-to-one, not a broadcast or sponsored message
- The content is informational, not promotional

**What we need to know:** Is an organic Facebook Messenger message to a business page classified as "elektronisk post" under §10? Does the fact that the business enabled Messenger create an implied consent to receive business-relevant messages? Would the security notification framing (no pricing, no CTA) change the analysis?

---

### Question 7: Responsible disclosure as a legal framework for first contact

**Context:** Responsible disclosure — informing an organization about a security vulnerability discovered in their systems — is a recognized practice in the cybersecurity community. The EU NIS2 Directive encourages coordinated vulnerability disclosure. Denmark's Centre for Cybersikkerhed (CFCS) supports responsible disclosure practices.

We could frame Heimdall's first contact as responsible disclosure of publicly observable security issues.

**What we need to know:**
- Does Denmark have a formal or informal safe harbour for responsible disclosure of passively discovered vulnerabilities?
- Would a responsible disclosure framing protect Heimdall from complaints under §10 (marketing) even when the disclosing entity is a commercial service?
- Does the fact that the vulnerabilities were discovered without authorization (though passively, from public data) create any exposure under §263?

---

### Question 8: Scanning authorization template review

**Context:** When a prospect becomes a paying client (Sentinel or Guardian tier), Heimdall performs active scanning (Layer 2) with written consent. We have drafted a scanning authorization template. We need counsel to review it for:

- Compliance with §263 (clear scope, duration, domains)
- GDPR Article 28 data processing requirements
- Whether the template adequately protects both parties

We will bring the template to the meeting.

---

## Summary of What Hinges on Legal Advice

| Question | If "yes" (favorable) | If "no" (unfavorable) |
|----------|---------------------|----------------------|
| Security notification ≠ marketing | All electronic channels open for non-commercial first touch | Must rely on physical mail + phone only |
| Reklamebeskyttet = CVR data only | Can contact protected businesses via website-sourced data | Can only reach protected businesses through physical mail |
| Physical letter to Reklamebeskyttet | Full prospect list reachable by post | Only non-protected businesses reachable |
| Contact forms ≠ electronic mail | Scalable digital channel available | Must avoid all electronic first contact |
| Digital twin findings shareable | Twin-derived CVE findings usable in outreach | Must limit outreach to Layer 1 findings only |
| Facebook Messenger viable | Primary channel for micro-businesses | Closed for first contact |
| Responsible disclosure framing | Strong legal protection for first contact | Weaker position, must be more cautious |

---

## Documents We Will Bring

1. This briefing
2. Sample security notification (the proposed first-contact message)
3. Scanning authorization template (for consented clients)
4. SCANNING_RULES.md (our internal compliance framework)
5. Sample prospect brief (real scan output, anonymized)
6. Valdí compliance log excerpt (demonstrating the audit trail)

---

## About Heimdall

- Founded by Federico Alvarez (Argentinian, 20-year SAP engineer, in Denmark since 2019)
- Startup Denmark (SIRI) application in progress
- No CVR yet — pending SIRI approval
- Pilot phase: 5 clients in Vejle, free first month
- Technical infrastructure: Raspberry Pi 5, Docker, Claude API
- Compliance agent (Valdí): two-gate validation system with forensic logging for every scan
- Open source tools: httpx, webanalyze, subfinder, dnsx, Nuclei, WPScan (all with public GitHub repositories)
