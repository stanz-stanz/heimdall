# Heimdall — Angel Investor Business Plan

**External Attack Surface Management for Small Businesses**
**March 2026 — Vejle, Denmark**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Problem](#2-the-problem)
3. [The Solution](#3-the-solution)
4. [How It Works](#4-how-it-works)
5. [Market Opportunity](#5-market-opportunity)
6. [Business Model & Unit Economics](#6-business-model--unit-economics)
7. [Go-to-Market Strategy](#7-go-to-market-strategy)
8. [Competitive Landscape](#8-competitive-landscape)
9. [Infrastructure & Scaling Plan](#9-infrastructure--scaling-plan)
10. [Risk Analysis & Mitigations](#10-risk-analysis--mitigations)
11. [Regulatory & Legal Framework](#11-regulatory--legal-framework)
12. [Team & Execution Capability](#12-team--execution-capability)
13. [Financial Projections](#13-financial-projections)
14. [The Ask](#14-the-ask)
15. [Why Now?](#15-why-now)
16. [References](#references)

---

## 1. Executive Summary

Forty percent of Danish small and medium businesses do not have a security level matching the severity of the threats they face.¹ The Danish government knows this — in January 2026 it allocated 211 million kr. over four years specifically to close this gap.² Meanwhile, every cybersecurity tool on the market delivers findings through technical dashboards designed for security professionals. The restaurant owner with an online booking system running on outdated WordPress does not have a security professional. She has a Telegram account.

**Heimdall** is an External Attack Surface Management (EASM) service that continuously monitors a business's public-facing digital surface — domains, certificates, web servers, CMS platforms, plugins — and delivers findings as plain-language messages through Telegram and WhatsApp. Not a dashboard. Not a PDF report. A conversation, in Danish, that tells the owner what is wrong, who should fix it, and what to say to that person.

**Business model:** Three subscription tiers at 499, 799, and 1,199 kr./month. Client acquisition starts with a free first scan — a Layer 1 passive analysis that produces real findings (outdated CMS versions, expiring SSL certificates, missing security headers) at near-zero marginal cost.

**Current state:** The lead generation pipeline is built and operational — 14 Python modules, a 10-agent architecture, a programmatic legal compliance system (Valdí) with two-gate validation and forensic logging, and a complete legal risk assessment of Danish scanning law. The pipeline has been tested against 353 live Vejle-area domains.

**The ask:** 150,000–250,000 kr. in angel funding to cover legal confirmation, pilot execution, first revenue, and an NCC-DK grant consortium application.

**The timing:** The Nationale Koordinationscenter for Cybersikkerhed (NCC-DK) opened a 5.5 million kr. grant pool on February 26, 2026 for innovative cybersecurity solutions. The deadline is **April 15, 2026**. A consortium application (Heimdall + a university partner) developing AI-powered EASM for Danish SMBs fits their stated criteria directly.³

---

## 2. The Problem

### 2.1 The 40% Gap

According to Styrelsen for Samfundssikkerhed (the Danish Agency for Civil Protection), 40% of Danish SMBs lack adequate cybersecurity relative to the threats they face.¹ Lars Sandahl of Dansk Industri called the government's response — a new SMV-CERT for small businesses — "en gamechanger for samfundets samlede beskyttelse."⁴

This is not a theoretical risk. VikingCloud's 2026 report found that 60% of SMBs that suffer a major breach close within six months.⁵ The median cost of a data breach for small businesses exceeds $120,000.⁶

### 2.2 The Compliance Obligation

GDPR Article 32 requires every organization handling personal data to implement "appropriate technical and organisational measures" to ensure a level of security appropriate to the risk.⁷ A restaurant collecting customer names, phone numbers, and email addresses through an online booking system is a data controller under GDPR. If that restaurant runs WordPress 5.8 on shared hosting with an expired SSL certificate and three unpatched plugins, it is not meeting Article 32. It simply does not know this.

NIS2 (implemented in Denmark via the Danish NIS Act, effective July 1, 2025) is expanding the scope of mandatory security requirements further into the SMB space, adding supply chain security obligations that pull smaller businesses into compliance scope through their relationships with larger organizations.

### 2.3 The Dashboard Gap

Every existing EASM tool delivers findings through web dashboards designed for security teams.

Qualys offers "interactive, customizable widgets" with "drill-down to details on events" and "QQL queries."⁸ Intruder provides "risk trends, cyber hygiene scoring, and audit-ready report generation."⁹ These are powerful tools for the security professional who logs into them. They are impenetrable for a restaurant owner who has never heard the phrase "attack surface."

The market assumption is that the buyer of a security product has someone on staff who reads security dashboards. For the 200,000+ Danish SMBs with websites, this assumption fails. The owner, the office manager, or a part-time IT generalist is the entire security team. They do not log into dashboards. They read messages on their phone.

### 2.4 The "Who Do I Send This To?" Problem

Even when a small business owner learns about a vulnerability, the next question is always: "What do I do with this information?"

The owner of a restaurant with an online booking system does not know how to patch WordPress. She does not know whether this is a hosting problem, a developer problem, or a plugin problem. She may not even have a developer. Findings without routing are useless — and every existing tool stops at the finding.

| Client Scenario | What They Need |
|----------------|---------------|
| Has a web developer | A message they can forward directly to the developer |
| Self-manages WordPress | Step-by-step wp-admin instructions |
| Fully hosted (Shopify/Squarespace) | Platform-specific settings guidance |
| Nobody manages it | A drafted support ticket for the hosting provider |

The problem is not just discovery. It is the last mile between "you have a vulnerability" and "here is exactly what to do about it, and here is the message to send."

---

## 3. The Solution

### 3.1 Conversational Delivery

Heimdall delivers security findings through Telegram and WhatsApp — the messaging apps the business owner already uses daily. Findings arrive as plain-language messages in Danish, not technical reports. Each message explains what was found, why it matters, and who should fix it.

**Example Telegram message (Watchman tier):**

> **Heimdall Sikkerhedsrapport — uge 12**
>
> Vi fandt 2 ting på jeres hjemmeside der kræver opmærksomhed:
>
> **1. Jeres WordPress-version er forældet**
> I kører version 5.8.3 — den nuværende er 6.5. De versioner imellem indeholder 47 sikkerhedsrettelser. Det er som at lade hoveddøren stå ulåst.
>
> *Hvem skal fikse det:* Den der har adgang til jeres WordPress admin-panel (wp-admin). Hvis I ikke ved hvem det er, så spørg jeres webhoster.
>
> **2. SSL-certifikatet udløber om 12 dage**
> Når det udløber, vil kunderne se en advarsel i browseren når de prøver at booke bord. Det skræmmer folk væk.
>
> *Hvem skal fikse det:* Jeres webhoster (det er ofte automatisk — men jeres er det ikke).

No login portal. No dashboard. The owner reads it on the bus.

### 3.2 Persistent Memory and Follow-Up

Heimdall maintains a persistent memory of each client's technology stack, past findings, and remediation state. Unlike a static report, the agent knows what it told the client last week and what has changed since.

Unresolved findings trigger escalating follow-up:
- **Week 1:** Initial finding delivered with context and routing
- **Week 2:** Reminder with increased urgency ("This is still unresolved")
- **Week 3:** Escalation with alternative remediation paths ("If your developer hasn't responded, here is how to contact your hosting provider directly")

This persistent memory also creates a natural switching cost — a new provider would need to rebuild the client's security history from scratch.

### 3.3 Shadow AI and Agent Detection

As of March 2026, over 21,000 OpenClaw instances are publicly exposed on the internet, many running agent skills with access to internal tools and APIs.¹⁰ ¹¹ Kaspersky's security audit of OpenClaw identified 512 vulnerabilities in the platform.¹² No SMB-focused security tool currently scans for exposed AI agent infrastructure.

Heimdall detects:
- Exposed OpenClaw instances and MCP servers
- Rogue AI agents operating on client infrastructure
- Shadow AI tools deployed without organizational awareness

This is a first-mover position. The attack surface created by AI agent adoption is growing faster than the security industry's response.¹³

### 3.4 The "First Finding Free" Acquisition Model

Heimdall's prospecting scan (Layer 1 — passive observation) reads publicly served information: HTTP headers, HTML source, DNS records, SSL certificates, CMS versions. This produces real, actionable findings at near-zero cost. The sales motion is not a pitch — it is a demonstration:

"We already scanned your website. Your WordPress is three major versions behind, and your SSL certificate expires in two weeks. Here is what that means for your business. Heimdall monitors this continuously and tells you the moment something changes — starting at 499 kr./month."

### 3.5 Service Tiers

| Tier | Price | What It Does |
|------|-------|-------------|
| **Watchman** | 499 kr./mo | Finds problems, explains them, tells you who should fix them |
| **Sentinel** | 799 kr./mo | Daily monitoring + step-by-step fix instructions + draft messages to forward to your developer or hosting provider |
| **Guardian** | 1,199 kr./mo | Active defence testing (with written consent) + fix verification + quarterly security report for your accountant or insurer |

The tiers are structured around how much Heimdall takes off the client's plate:
- **Watchman** tells you *what* is wrong
- **Sentinel** tells you *how* to fix it and writes the message for you
- **Guardian** *tests* your defences, *verifies* fixes, and *documents* your security posture

---

## 4. How It Works

### 4.1 The Pipeline

The lead generation and scanning pipeline follows a strict sequence:

```
CVR Extract (manual) → Domain Derivation → robots.txt Check → Layer 1 Scan → Bucketing → Brief Generation
```

1. **Input:** Federico manually extracts a company list from the Danish CVR register (datacvr.virk.dk — public data).¹⁴ The pipeline does not scrape or access the CVR register.
2. **Domain derivation:** Website domains are extracted from company email addresses. Free webmail providers are discarded.
3. **robots.txt compliance:** If a target's robots.txt denies automated access, the target is skipped entirely. No exceptions.
4. **Layer 1 scanning:** Passive observation using webanalyze (https://github.com/rverton/webanalyze) and httpx (https://github.com/projectdiscovery/httpx) — reading what the server voluntarily sends to any visitor.
5. **Bucketing:** Results are auto-classified by risk profile:
   - **Bucket A (Highest):** Self-hosted WordPress on shared hosting
   - **Bucket B (High):** Other self-hosted CMS (Joomla, Drupal, PrestaShop)
   - **Bucket E (Medium):** Custom-built or unidentifiable stack
   - **Bucket C (Lower):** Shopify / Squarespace / Wix (platform handles infrastructure security)
   - **Bucket D (Skip):** No website or parked domain
6. **Brief generation:** Per-site JSON briefs containing CMS, hosting provider, SSL status, detected plugins, risk profile, and agency credits.

### 4.2 The Agent Architecture

Heimdall runs on a 10-agent chain, each with a documented specification (SKILL.md) defining its responsibilities, boundaries, inputs, and outputs:

| Agent | Role |
|-------|------|
| Prospecting | Lead generation pipeline, CVR processing, domain resolution |
| Scanner | Layer 1/Layer 2 scan execution (tools produce findings) |
| Interpreter | Claude API — translates raw findings into plain language |
| Message Composer | Formats findings for Telegram/WhatsApp delivery |
| Follow-Up | Persistent memory, remediation tracking, escalation |
| Legal Compliance (Valdí) | Scan validation, forensic logging, approval tokens |
| Agency Detector | Identifies web agencies from footer credits and meta tags |
| Brief Generator | Produces per-site technical briefs |
| Grant & Funding | Grant applications, budget tables, consortium narratives |
| Reporting | Quarterly security reports (Guardian tier) |

The critical design principle: **tools produce findings, the LLM interprets them.** Nuclei, httpx, and webanalyze generate structured technical data. Claude translates that data into language the restaurant owner understands. The LLM never decides what is vulnerable — it decides how to explain what the tools found.

### 4.3 Valdí — The Compliance System

Heimdall operates under Danish criminal law (Straffeloven §263), which criminalizes unauthorized access to data systems. The legal boundary between permitted passive observation and potentially criminal active probing is enforced programmatically by Valdí, the legal compliance agent.

**Gate 1 — Scan Type Validation:** Every scanning function is reviewed against documented rules before it can execute. Valdí classifies the function's activities by Layer, confirms they do not exceed what the target's consent level permits, and issues an approval token. Rejected functions are blocked with structured reasoning. Every review — approval or rejection — produces a timestamped forensic log.

**Gate 2 — Per-Target Authorization:** Before each scan batch, Valdí confirms that the scan type has a valid approval token and that each target's consent level permits the scan's Layer. Targets without written consent are restricted to Layer 1 (passive observation only).

**No scanning code executes without a valid Valdí approval token.**

### 4.4 Governance Maturity — The Incident

During early pipeline development, a function was written that probed specific admin paths (`/wp-admin/`, `/administrator/`) on target domains — active probing that crosses the Layer 1 boundary into Layer 2. The function was integrated into the pipeline and executed against 353 domains before the violation was identified.

It was caught by the project owner's manual review, not by automated checks. The response was immediate: the code was removed, all tainted data was scrubbed from output files, a full code review confirmed no other boundary violations, and the incident was documented in a formal post-incident report.

**Valdí was built as a direct result of this incident.** The two-gate compliance system with forensic logging exists because a human caught what the code did not. An investor should read this as a strength: the team identifies compliance failures, responds with systemic fixes rather than patches, and documents everything. The forensic log trail is designed to demonstrate due diligence to regulators and legal counsel.

---

## 5. Market Opportunity

### 5.1 Market Sizing

| Metric | Calculation | Annual Value |
|--------|------------|-------------|
| **TAM** | ~200,000 Danish SMBs with websites × 650 kr./mo blended × 12 | ~1.56B kr./yr |
| **SAM** | ~80,000 (the 40% with inadequate security) × 650 kr./mo × 12 | ~624M kr./yr |
| **SOM** | 200 clients in 36 months × 650 kr./mo × 12 | ~1.56M kr./yr |

The TAM is a theoretical ceiling — clearly labeled as such. The SAM applies the 40% gap statistic. The SOM is deliberately conservative: 200 paying clients in three years represents 0.25% of the SAM. The upside scenario depends on agency partnerships (one relationship = 10–35 clients) and grant-funded acceleration.

### 5.2 Regulatory Tailwinds

The Danish government is spending money on this problem right now:

| Initiative | Amount | Timeline |
|-----------|--------|----------|
| National Cybersecurity Strategy | 211M kr. | 2026–2029 |
| Ongoing NIS2 implementation | 275M kr./year | From 2025 |
| NCC-DK grant pool (current round) | 5.5M kr. | Deadline April 15, 2026 |
| NCC-DK total grant budget | 43M kr. | 2026–2029 |
| Industriens Fond Cybersikkerhedsprogram | Ongoing | Active |
| EU Digital Europe Programme | Up to €60,000/SME | Open calls |
| EU SECURE Project | Mentorship + funding | Launched Jan 2026 |

The government's strategy explicitly names SMBs as the priority. Minister Torsten Schack Pedersen: "Et vigtigt element i strategien er, at vi styrker cybersikkerheden for danskerne og de små og mellemstore virksomheder."²

SMV-CERT — a new Computer Emergency Response Team specifically for SMBs — will provide early warnings and practical prevention tools.⁴ Heimdall is positioned as the delivery layer that makes those warnings actionable for the businesses that receive them.

### 5.3 The Expansion Path

Denmark is the starting market, not the ceiling. The reasons to start here are strategic:

1. **GDPR-first:** Denmark enforces GDPR. Any EASM service built for Danish compliance translates directly to all 27 EU member states.
2. **Small enough to validate:** 200 clients in Denmark proves the model. EU expansion is a growth story, not a survival requirement.
3. **Grant ecosystem:** Danish and EU grant funding creates non-dilutive capital for growth.
4. **Language-agnostic delivery:** Telegram and WhatsApp work in every country. The messaging-first architecture does not need to be rebuilt for new markets — only the language model's output language changes.

The conservative financial projections in this plan assume Denmark only. EU expansion is upside.
