## Startup Denmark Application

## Project Heimdall
### An AI-Powered Cybersecurity for Small Businesses**
**March 2026 — Vejle, Denmark**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Problem](#2-the-problem)
3. [The Solution](#3-the-solution)
4. [How It Works](#4-how-it-works)
5. [Innovation](#5-innovation)
6. [Market Opportunity](#6-market-opportunity)
7. [Business Model & Unit Economics](#7-business-model--unit-economics)
8. [Go-to-Market Strategy](#8-go-to-market-strategy)
9. [Scalability & Job Creation in Denmark](#9-scalability--job-creation-in-denmark)
10. [Competitive Landscape](#10-competitive-landscape)
11. [Regulatory & Legal Framework](#11-regulatory--legal-framework)
12. [Why Denmark](#12-why-denmark)
13. [Team & Execution Capability](#13-team--execution-capability)
14. [Financial Projections & Self-Sustainability](#14-financial-projections--self-sustainability)
15. [References](#references)

---

## 1. Executive Summary

Forty percent of Danish small and medium businesses do not have a security level matching the severity of the threats they face.¹ The Danish government knows this — in January 2026 it allocated 211 million kr. over four years specifically to close this gap.² Meanwhile, every cybersecurity tool on the market delivers findings through technical dashboards designed for security professionals. The restaurant owner with an online booking system running on outdated WordPress does not have a security professional. She has a Telegram account.

**Heimdall** is an External Attack Surface Management (EASM) service that continuously monitors a business's public-facing digital surface — domains, certificates, web servers, CMS platforms, plugins — and delivers findings as plain-language messages through Telegram and WhatsApp. Not a dashboard. Not a PDF report. A conversation, in the business owner's own language, that tells them what is wrong and why it matters — in language they understand.

**The innovation:** No existing EASM product delivers findings through messaging apps to non-technical business owners. Heimdall's architecture is built from the ground up around conversational delivery, persistent memory of each client's infrastructure, AI-powered interpretation of technical findings, and automated legal compliance governance. Two technical innovations are particularly distinctive. First, a **digital twin** system that reconstructs a prospect's website from publicly available data and runs it on Heimdall's own infrastructure — enabling CVE-level vulnerability scanning without touching the prospect's systems or requiring their consent, because Danish criminal law (Straffeloven §263) only protects "another person's data system." Second, **Valdí**, a programmatic compliance agent with two-gate validation and forensic logging, built as a systemic response to a real compliance incident — demonstrating a governance maturity that most startups never achieve. This is not an incremental improvement — it is a fundamentally different approach to cybersecurity for SMBs.

**Business model:** One paid subscription tier — Sentinel at 399 kr./month (339 kr./month annual). Preceded by Watchman, a FREE 30-day trial (passive Layer 1 only, no payment, no written consent required). Client acquisition starts with a free first scan — a passive analysis that produces real findings (outdated CMS versions, expiring SSL certificates, missing security headers) at near-zero marginal cost. Break-even at ~12 paying clients.

**Current state:** I am building the product. The lead generation pipeline is operational — 14 Python modules, a 10-agent architecture, a programmatic legal compliance system (Valdí) with two-gate validation and forensic logging, and a complete legal risk assessment of Danish scanning law. I have tested the pipeline against 203 live Vejle-area domains.

**Why Denmark:** Denmark's cybersecurity investment, GDPR-first regulatory environment, dense SMB market, and grant ecosystem create the ideal conditions for this business. I have been based in Vejle since 2019 and have already tested the pipeline against local domains.

I am applying for a Startup Denmark residence permit to establish Heimdall ApS in Denmark.

---

## 2. The Problem

### 2.1 The 40% Gap

According to Styrelsen for Samfundssikkerhed (the Danish Agency for Civil Protection), 40% of Danish SMBs lack adequate cybersecurity relative to the threats they face.¹ Lars Sandahl of Dansk Industri called the government's response — a new SMV-CERT for small businesses — "en gamechanger for samfundets samlede beskyttelse."⁴

This is not a theoretical risk. VikingCloud's 2026 report found that 60% of SMBs that suffer a major breach close within six months.⁵ The median cost of a data breach for small businesses exceeds $120,000.⁶

The problem is structural, not just financial. As John McLoughlin, CEO of J2 Software, writes: "Prescriptive technical or procedural mandates that assume large budgets and deep specialist teams disadvantage smaller and mid-sized organisations that must prioritise limited resources."¹⁸ The tools exist — they were simply never built for this audience.

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

Heimdall delivers security findings through Telegram and WhatsApp — the messaging apps the business owner already uses daily. Findings arrive as plain-language messages in their preferred language, not technical reports. Each message explains what was found and why it matters — in language the owner understands.

This delivery model represents a fundamentally new approach to cybersecurity for SMBs — no existing product operates this way.

**Example Telegram message (Watchman tier):**

> **Heimdall Sikkerhedsadvarsel — uge 12**
>
> Vi fandt 2 ting på jeres hjemmeside der kræver opmærksomhed:
>
> **1. Jeres hjemmeside kører på en forældet version**
> Versionen I kører har 47 kendte sikkerhedshuller. Det svarer til at lade hoveddøren stå ulåst.
>
> **2. Jeres SSL-certifikat udløber om 12 dage**
> Når det udløber, vil kunderne se en advarsel i browseren når de prøver at booke bord. Det skræmmer folk væk.

No login portal. No dashboard. The owner reads it on the bus.

### 3.2 Persistent Memory and Follow-Up

Heimdall maintains a persistent memory of each client's technology stack, past findings, and remediation state. Unlike a static report, the agent knows what it told the client last week and what has changed since.

Unresolved findings trigger escalating follow-up:
- **Week 1:** Initial finding delivered with context and routing
- **Week 2:** Reminder with increased urgency ("This is still unresolved")
- **Week 3:** Escalation with alternative remediation paths ("If your developer hasn't responded, here is how to contact your hosting provider directly")

This persistent memory also creates a natural switching cost — a new provider would need to rebuild the client's security history from scratch.

### 3.3 The "First Finding Free" Acquisition Model

Heimdall's prospecting scan (Layer 1 — passive observation) reads publicly served information: HTTP headers, HTML source, DNS records, SSL certificates, CMS versions. This produces real, actionable findings at near-zero cost. The sales motion is not a pitch — it is a demonstration:

"We already scanned your website. Your WordPress is three major versions behind, and your SSL certificate expires in two weeks. Here is what that means for your business. Heimdall monitors this continuously and tells you the moment something changes — 30 days free, then 399 kr./month if you want to continue."

### 3.4 Service Tiers

| Tier | Price | What It Does |
|------|-------|------------|
| **Watchman** (free trial) | FREE — 30 days | Finds problems and explains them in plain language. Zero-friction entry point (no payment, no written consent). |
| **Sentinel** | 399 kr./mo (annual: 339 kr./mo) | Daily monitoring + active vulnerability testing + step-by-step fix instructions (written report) |

*All prices excl. moms (Danish VAT).*

---

## 4. How It Works

### 4.1 The Pipeline

The lead generation and scanning pipeline follows a strict sequence:

```
CVR Extract (manual) → Domain Derivation → robots.txt Check → Layer 1 Scan → Bucketing → Brief Generation
```

1. **Input:** Company data from the Danish CVR register (datacvr.virk.dk — public data).¹⁴ The pipeline does not scrape or access the CVR register directly.
2. **Domain derivation:** Website domains are extracted from company email addresses. Free webmail providers are discarded.
3. **robots.txt compliance:** If a target's robots.txt denies automated access, the target is skipped entirely. No exceptions.
4. **Layer 1 scanning:** Passive observation using open-source tools — webanalyze (https://github.com/rverton/webanalyze), httpx (https://github.com/projectdiscovery/httpx), subfinder (https://github.com/projectdiscovery/subfinder) for subdomain enumeration via Certificate Transparency logs, dnsx (https://github.com/projectdiscovery/dnsx) for DNS enrichment, and TLS certificate analysis via standard handshake (SSLyze integration deferred). Reads only what the server voluntarily sends to any visitor.
5. **Bucketing:** Results are auto-classified by risk profile (A through E).
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
| Reporting | Periodic security reports (Sentinel tier) |

The critical design principle: **tools produce findings, the LLM interprets them.** Nuclei, httpx, and webanalyze generate structured technical data. Claude translates that data into language the restaurant owner understands. The LLM never decides what is vulnerable — it decides how to explain what the tools found.

### 4.3 Valdí — The Compliance System

Heimdall operates under Danish criminal law (Straffeloven §263), which criminalizes unauthorized access to data systems. The legal boundary between permitted passive observation and potentially criminal active probing is not enforced by policy documents or good intentions — it is enforced programmatically by Valdí, the legal compliance agent.

Most compliance systems audit what already happened. Valdí blocks what is about to happen. No scanning function runs without passing through two gates first. The default state is "denied."

**Gate 1 — Scan Type Validation:** Valdí reads the actual scanning function, identifies what requests it makes, and classifies each one by Layer. It applies a decision test derived from Danish law: "Would a normal browser visit produce this data?" If the answer is no, the function is blocked with structured reasoning, full rule citations, and a violation table. If it passes, Valdí issues an approval token. Every review — approval or rejection — produces a timestamped forensic log.

**Gate 2 — Per-Target Authorization:** Before each scan batch, Valdí confirms that the scan type has a valid approval token and that the specific target's consent state permits that scan's Layer. This separation matters: a function can be approved as a valid Layer 2 tool and still be blocked for a domain that has not consented. A consented tool cannot accidentally run against an unconsented target.

**Valdí logs rejections, not just approvals.** This is the subtlety that matters most. The rejection logs — with full reasoning, rule citations, and violation tables — are more valuable as evidence than the approvals. They prove the system catches things. They prove the gatekeeper has teeth. When a scanning function tried to probe admin paths and was declared as Layer 1, Valdí identified eight separate violations, blocked execution, and logged exactly why. That rejection entry is the single strongest piece of compliance evidence Heimdall has.

"Without a documented, well-rehearsed AI governance framework, decisions get made on the fly, oversight slips through the cracks, and records end up incomplete. Those are exactly the weak spots regulators, auditors, and litigators are trained to find."²⁰ Valdí is that documented, well-rehearsed framework.

What Valdí is not: a silver bullet. It is an LLM reviewing code against documented rules — it can be wrong. It is as good as the rules in `SCANNING_RULES.md` and the quality of the model's reasoning. That is why the forensic logs exist — so a human can review the reasoning and catch errors the system misses. The ambition is not perfection. It is demonstrable due diligence: a live, auditable record that the boundary was enforced before every scan, not reconstructed after an incident.

For a pre-revenue, single-founder startup that does not yet have a CVR number, this level of programmatic governance is unusual. Companies at this stage do not typically have compliance systems. They have a plan to figure out legal later. I built a two-gate automated compliance agent with forensic logging before Heimdall has its first paying client. That is a deliberate choice about what kind of company this is.

### 4.4 Governance Maturity

During early pipeline development, I discovered that a scanning function had crossed the Layer 1 boundary undetected. I caught the violation during manual review. My response was immediate: I removed the offending code, scrubbed all tainted data, and documented the root cause.

The systemic response was Valdí — I designed and built it as a direct result, to make this class of error structurally impossible going forward.

**This is stronger evidence of governance maturity than a clean record.** Any organization can claim it has never had a compliance incident. I can demonstrate that when a boundary violation occurred, the system detected it, I corrected it, and built an automated gate to prevent recurrence. The correction mechanism is proven — not theoretical.

---

## 5. Innovation

Heimdall introduces five distinct innovations to the External Attack Surface Management market. These are not incremental improvements to existing products — they represent a fundamentally different approach to delivering cybersecurity to non-technical users.

### 5.1 Messaging-First Delivery Model

Every existing EASM product delivers findings through web dashboards. Heimdall delivers through Telegram and WhatsApp — the apps the business owner already uses. The entire product architecture is built around conversational delivery: plain-language interpretation, actionable next steps, and escalating follow-up. This is not a notification feature bolted onto a dashboard — it is the product.

### 5.2 Digital Twin — CVE-Level Findings Without Consent or Contact

This is the innovation no competitor has.

Heimdall's Layer 1 (passive) scanning collects publicly available data about a prospect's website: CMS version, plugin versions, server software, SSL configuration. From this data, Heimdall constructs a **digital twin** — an exact replica of the prospect's technology stack running on Heimdall's own infrastructure.

The legal foundation is explicit in Straffeloven §263's language: the statute criminalizes unauthorized access to **"another person's data system"** ("en andens datasystem"). A digital twin is Heimdall's own system. It is built from lawfully obtained public data. Running vulnerability scanners against it cannot constitute a §263 violation because the system belongs to the scanner operator.

This transforms the sales conversation. Without the twin, Layer 1 scanning produces surface-level observations: "Your WordPress is version 5.8.3" or "You are missing a Content-Security-Policy header." With the twin, Heimdall runs Nuclei templates against the replica and WPVulnerability API lookups for plugin/core CVEs, producing CVE-level findings: "Your WordPress version and plugin combination has 3 known CVEs, including CVE-2023-XXXXX which allows unauthenticated access to user data."

The difference for a restaurant owner with an online booking system is the difference between "your door is old" and "your door has a known defect that lets strangers walk in." The second message creates urgency. The second message sells.

**What the digital twin enables:**

- **CVE-level prospecting findings** from publicly available data alone — no customer consent required, no contact with their infrastructure
- **Deterministic test fixtures** — twins built from known configurations provide reproducible regression tests for the scanning pipeline, eliminating dependence on live third-party infrastructure for quality assurance
- **Scalable depth** — every prospect in the pipeline gets the same depth of analysis that would traditionally require written consent and active scanning of their live systems

No competitor in the EASM space offers this capability. The standard industry approach is: passive scan produces shallow findings; deep findings require consent and active scanning of the client's live infrastructure. Heimdall eliminates this tradeoff entirely.

### 5.3 Persistent Memory Architecture

Heimdall builds a longitudinal understanding of each client's infrastructure, findings history, and remediation patterns. The agent remembers what it told the client, what changed, what was fixed, and what was ignored. This compounds in value over time and creates switching costs — a new provider would start from zero.

### 5.4 Programmatic Legal Compliance (Valdí)

Heimdall operates on the boundary defined by Straffeloven §263. The distance between "reading a public webpage" and "unauthorized access to a data system" can be a single HTTP request to the wrong path. Most companies in this space manage that boundary with policy documents and training. Heimdall manages it with a programmatic gate that reads every scanning function, classifies its activities against documented legal rules, and blocks execution if it crosses the line — before anything touches a target.

This was not designed in theory. During early development, I discovered that a scanning function had crossed the Layer 1 boundary undetected (see section 4.4). My response was not a policy update — it was Valdí: a two-gate automated compliance system with forensic logging that makes this class of error structurally impossible. The correction mechanism is proven, not theoretical.

### 5.5 AI-Powered Interpretation Chain

Open-source scanning tools produce structured technical data. The Claude API interprets that data in plain language for non-technical users with actionable next steps. The LLM never decides what is vulnerable — it explains what the tools found. This separation of detection from interpretation is a novel architecture for SMB security products.

---

## 6. Market Opportunity

### 6.1 Market Sizing

| Metric | Calculation | Annual Value |
|--------|------------|-------------|
| **TAM** | ~200,000 Danish SMBs with websites × 305 kr./mo blended × 12 | ~732M kr./yr |
| **SAM** | ~80,000 (the 40% with inadequate security) × 305 kr./mo × 12 | ~293M kr./yr |
| **SOM** | 200 clients in 36 months × 305 kr./mo × 12 | ~732K kr./yr |

The TAM is a theoretical ceiling — clearly labeled as such. The SAM applies the 40% gap statistic. The SOM is deliberately conservative: 200 paying clients in three years represents 0.25% of the SAM. The upside depends on agency partnerships (one relationship = 10–35 clients) and tier migration (Watchman trial → Sentinel).

### 6.2 Regulatory Tailwinds

The Danish government is creating the market for this service:

| Initiative | Amount | Timeline |
|-----------|--------|----------|
| National Cybersecurity Strategy | 211M kr. | 2026–2029 |
| Ongoing NIS2 implementation | 275M kr./year | From 2025 |
| NCC-DK total grant budget | 43M kr. | 2026–2029 |
| Industriens Fond Cybersikkerhedsprogram | Ongoing | Active |
| EU Digital Europe Programme | Up to €60,000/SME | Open calls |
| EU SECURE Project | Mentorship + funding | Launched Jan 2026 |

Minister Torsten Schack Pedersen: "Et vigtigt element i strategien er, at vi styrker cybersikkerheden for danskerne og de små og mellemstore virksomheder."²

These grants become accessible to Heimdall once a CVR is established through Startup Denmark approval.

### 6.3 The Expansion Path

Denmark is the starting market, not the ceiling:

1. **GDPR-first:** Denmark enforces GDPR. Any EASM service built for Danish compliance translates directly to all 27 EU member states.
2. **Small enough to validate:** 200 clients in Denmark proves the model. EU expansion is a growth story, not a survival requirement.
3. **Language-agnostic delivery:** Telegram and WhatsApp work in every country. The messaging-first architecture does not need to be rebuilt for new markets — only the language model's output language changes.

The conservative financial projections assume Denmark only. EU expansion is upside.

---

## 7. Business Model & Unit Economics

### 7.1 Pricing

| Tier | Monthly Price | Annual Option | Scanning Type | Key Value |
|------|-------------|---------------|---------------|-----------|
| Watchman (free trial) | FREE — 30 days | N/A | Passive (Layer 1) | What is wrong, in plain language |
| Sentinel | 399 kr. | 339 kr./mo | Passive + Active | What's wrong + how to fix it + daily monitoring + active testing |

*All prices excl. moms.*

Blended average revenue per client (ARPC): ~370 kr./month at mature tier mix (30% annual uptake). Watchman contributes no revenue — it's a zero-friction acquisition surface.

Free Watchman trial eliminates price as the first objection entirely. Every Sentinel competitor charges for any form of ongoing scanning; a free 30-day demonstration of daily passive findings, delivered in plain language, has no direct equivalent in the Danish SMB market.

### 7.2 Unit Economics Per Client (Monthly, at Scale)

| Cost Component | Amount | Notes |
|---------------|--------|-------|
| Revenue (blended) | ~305 kr. | Weighted average, early mix |
| Claude API | ~50 kr. | Interpretation + follow-up (lower tiers = less processing) |
| Infrastructure | ~15–30 kr. | At 50+ clients; higher per-client at pilot scale |
| Tool licensing | ~0 kr. | WPVulnerability API (free) |
| Insurance allocation | ~30–45 kr. | Professional indemnity, pro-rated |
| **Total COGS** | **~95–125 kr.** | |
| **Gross margin** | **~70–76%** | Improves with scale |

Margins are comparable to premium-priced competitors at much lower absolute price. The free 30-day Watchman trial creates a fundamentally different market dynamic: it eliminates price as the first objection entirely, and demonstrates value before any payment ask. Conversion to Sentinel (399 kr./mo) happens on evidence, not on commitment.

Revenue projections are based on Sentinel subscription fees only. Watchman contributes no revenue — it is a zero-friction acquisition surface whose job is to convert trialists to Sentinel.

### 7.3 Acquisition Economics

**First Finding Free:** The Layer 1 prospecting scan costs near-zero to run. This produces real findings that power a free-sample sales motion.

**Agency partnerships:** One relationship with a web agency yields access to 10–35 client sites. The agency becomes a channel partner or white-label reseller. This is the highest-leverage acquisition channel.

**No paid advertising in Phase 1–3.** Danish marketing law prohibits unsolicited electronic marketing without consent. The model is built on in-person relationships and demonstrated value.

### 7.4 Break-Even

At ~305 kr. blended revenue and fixed costs of ~2,600 kr./month (tool licensing removed with WPVulnerability API), break-even occurs at approximately **~13–14 paying clients**. At the aggressive pricing, this requires a larger client base than a premium model — but the lower price point makes each conversion significantly easier. The pipeline has already identified 68 prime targets in Vejle alone; the pilot needs 5–10.

---

## 8. Go-to-Market Strategy

### 8.1 The Constraint That Becomes an Advantage

Danish marketing law (Markedsføringsloven) prohibits unsolicited electronic marketing without prior consent. This eliminates the standard SaaS cold outreach playbook — and forces a high-trust acquisition model that competitors relying on digital outbound cannot easily replicate.

### 8.2 Five Phases

**Phase 1 — Vejle Pilot (Month 1–3)**
- 5 pilot clients recruited through in-person visits
- "First finding free" — show a real scan result before asking for anything
- Free 30-day Watchman trial; convert to paid Sentinel at 399 kr./mo
- Human-in-the-loop: I review every message before delivery

**Phase 2 — Agency Partnerships (Month 3–6)**
- Approach local web agencies with aggregate scan data: "22 of your 35 client sites have issues"
- Agency becomes channel partner or white-label reseller
- One agency relationship = 10–35 client sites

**Phase 3 — Local Business Networks (Month 6–12)**
- Erhvervsforeninger (local business associations) — speaking events, workshops
- Referral program, case studies from pilot clients
- Target: 20 paying clients by Month 12. **First part-time hire (operations).**

**Phase 4 — Geographic Expansion (Month 12–24)**
- Aarhus, Odense, Aalborg — same playbook, new cities
- Agency partnerships scale nationally
- Target: 80 paying clients by Month 24. **Team grows to 3–4.**

**Phase 5 — EU Expansion (Month 24–36+)**
- GDPR framework translates directly to all 27 member states
- Messaging delivery is language-agnostic
- Entry markets: Germany, Netherlands
- Target: 200 paying clients by Month 36. **Team grows to 6+.**

---

## 9. Scalability & Job Creation in Denmark

### 9.1 Infrastructure Scaling

| Stage | Clients | Infrastructure | Monthly Cost | Cost/Client |
|-------|---------|---------------|-------------|------------|
| Establishment | 0 | Development environment | 0 kr. | — |
| Pilot | 5–10 | Dedicated secure infrastructure | 175–560 kr. | ~112–56 kr. |
| Early production | 10–50 | Cloud-hosted containers | 350–700 kr. | ~35–14 kr. |
| Scale | 50–200 | Multi-container cloud | 700–2,100 kr. | ~14–10.50 kr. |
| Growth | 200+ | Multi-node cloud | 2,100–7,000 kr. | ~10.50–35 kr. |

The same agent architecture runs at every tier. The scanning pipeline, Valdí compliance system, and message delivery chain are substrate-independent. Scaling is an infrastructure change, not an application rewrite.

### 9.2 Job Creation in Denmark

| Timeline | Headcount | Roles | Location |
|----------|-----------|-------|----------|
| Year 1 (establishment + pilot) | 1 (founder) | Development, sales, operations | Vejle |
| Year 1–2 | 2–3 | Part-time operations hire, network security partner formalized | Vejle |
| Year 2–3 | 4–6 | Client success manager, junior developer, sales/business development | Vejle / Aarhus |
| Year 3+ | 6–10 | Security analysts, EU expansion team | Denmark |

### 9.3 Danish Economic Contribution

- **Direct employment:** 6–10 positions in Denmark within 3 years, growing with EU expansion
- **Tax revenue:** Employer and employee contributions from Danish-based roles
- **SMB resilience:** Strengthening the cybersecurity posture of Danish small businesses — directly aligned with government policy objectives
- **Grant ecosystem alignment:** Denmark's cybersecurity grant ecosystem (NCC-DK, Digital Europe Programme, Industriens Fond) creates non-dilutive funding pathways for Danish cybersecurity startups
- **Knowledge economy:** Building cybersecurity expertise and AI-powered security tooling in Denmark

---

## 10. Competitive Landscape

### 10.1 Direct Competitors

| Competitor | Starting Price | Interface | SMB Messaging |
|-----------|---------------|-----------|---------------|
| **Heimdall** | FREE trial · 399 kr./mo | Telegram/WhatsApp | Yes |
| Intruder.io | ~740 kr./mo | Dashboard + Slack/Jira | No |
| Detectify | ~610 kr./mo (app) | Dashboard | No |
| HostedScan | Free tier; paid ~215 kr./mo | Dashboard + API | No |
| Beagle Security | ~885 kr./mo | Dashboard | No |
| Sucuri (GoDaddy) | ~1,480 kr./yr | Dashboard + WAF | No |

Closest competitor: **Intruder.io** — founded 2015, GCHQ Cyber Accelerator alumni, 1,000+ customers.⁹ Delivers through a web dashboard with Slack and Jira integrations.

Enterprise EASM players (CrowdStrike, Qualys, Censys) are moving upmarket, not down. They are not competing for the restaurant owner.

### 10.2 Anticipated Objections

**"Why can't Intruder just add Telegram delivery?"**

They could add a Telegram notification. But notification is not delivery. Heimdall's architecture is built around non-technical users from the ground up — plain-language interpretation, persistent memory, escalating follow-up, and actionable next steps. Adding a Telegram webhook to a dashboard product does not replicate this. It would require rebuilding the product's entire communication layer, output format, and user model.

**"HostedScan has a free tier — why pay 399 kr.?"**

If the business owner can navigate a vulnerability scanning dashboard, configure scan targets, interpret CVSS scores, and act on the findings — HostedScan is the better choice. Heimdall offers its own free tier (30-day Watchman trial) to prove value without payment. The paid Sentinel tier at 399 kr./mo adds daily monitoring, active Layer 2 testing under written consent, and step-by-step fix instructions delivered through the channel the owner actually uses. For the majority of SMB owners who cannot navigate a dashboard, the dashboard might as well not exist.

### 10.3 Four Durable Differentiators

1. **Messaging-first delivery:** The entire product is built around conversational delivery to non-technical users — not a feature bolted onto a dashboard.

2. **Digital twin vulnerability analysis:** CVE-level findings from publicly available data alone — no customer consent required, no contact with their live systems. No competitor offers this.

3. **Persistent memory:** Longitudinal understanding of each client's infrastructure, findings history, and remediation patterns. Creates switching costs and compounds in value.

4. **Fix guidance:** Sentinel tier provides step-by-step fix instructions and written reports — closing the gap between "you have a problem" and "here is how to solve it." Competitors stop at raw findings.

---

## 11. Regulatory & Legal Framework

### 11.1 Danish Criminal Law — Straffeloven §263

Straffeloven §263, stk. 1 criminalizes gaining unauthorized access to data systems.¹⁵ Heimdall's Layer 1 scanning (reading publicly served information) carries minimal legal risk — functionally identical to visiting a website in a browser. Layer 2 scanning (active vulnerability probing) requires written client consent before activation. This maps to the business model: free prospecting scan = Layer 1; paid service = Layer 2 with consent.

### 11.2 GDPR Article 32 — The Compliance Driver

GDPR Article 32 requires "appropriate technical and organisational measures" to ensure security appropriate to the risk.⁷ Most Danish SMBs are non-compliant by default. They do not know this. Heimdall makes the gap visible and provides a path to close it.

### 11.3 Digital Twin — Legal Foundation Under §263

Heimdall's digital twin system constructs replicas of prospect websites on Heimdall's own infrastructure, built entirely from publicly available data collected during Layer 1 scanning. The legal basis for running vulnerability scanners (Nuclei templates, WPVulnerability API lookups) against these twins rests directly on the language of §263, stk. 1, which criminalizes unauthorized access to **"en andens datasystem"** — another person's data system.¹⁵

A digital twin is not another person's data system. It is built by Heimdall, hosted by Heimdall, and owned by Heimdall. The data used to construct it — CMS versions, plugin versions, server software, SSL configuration — is publicly served information that any browser visitor receives. Running Layer 2 scanning tools against this self-owned replica cannot constitute a §263 violation.

This distinction enables Heimdall to produce CVE-level vulnerability findings for prospecting purposes without requiring customer consent and without making any active probes against the prospect's live infrastructure. The input is lawful (Layer 1 public data), the scanning target is self-owned (the twin), and the output is high-confidence inference (marked with `provenance: "unconfirmed"` throughout the pipeline).

Confirmation of this legal interpretation is included in the planned legal counsel engagement (see Section 11.5).

### 11.4 Valdí as Demonstrable Due Diligence

The Valdí compliance system — two-gate validation, forensic logging, approval tokens — demonstrates due diligence under §263. Every scan type is validated before execution. Every validation is logged. Valdí was built as a systemic response to a real boundary violation during early development (Section 4.4), providing concrete evidence that the governance mechanism works. If Heimdall is ever questioned by regulators, the forensic log trail provides timestamped evidence of what was scanned, approved, rejected, and why.

### 11.5 Open Questions for Counsel

Legal counsel engagement is underway with **Anders Wernblad, Aumento Law** — a Danish IT law specialist (member of the Association of Danish IT Attorneys, IT Society, Network for IT contracts, and Danish Bar). A 16-question briefing covers: the Layer 1 / Layer 2 boundary under §263, the digital twin's legal basis (self-owned system built from public data does not constitute "another person's data system" under §263), the scanning authorisation template, the GDPR DPA, Markedsføringsloven §10 on outreach, NIS2/CRA duty-to-report interaction, and agency delegation rights.

---

## 12. Why Denmark

Denmark is not an arbitrary choice. It is the strategically optimal market for launching Heimdall.

### 12.1 Regulatory Alignment

The Danish government allocated 211 million kr. for cybersecurity over 2026–2029.² The strategy explicitly targets SMBs. SMV-CERT — a new Computer Emergency Response Team specifically for small businesses — is being created as a public-private partnership.⁴ Heimdall is positioned as the delivery layer that makes government-funded security warnings actionable for the businesses that receive them. The government is creating the market; Heimdall serves it.

### 12.2 Grant Ecosystem

Once Heimdall ApS is established with a CVR through Startup Denmark, the following non-dilutive funding sources become accessible:

| Source | Amount | Status |
|--------|--------|--------|
| NCC-DK grants | 43M kr. pool (2026–2029) | Requires CVR — accessible post-establishment |
| EU Digital Europe Programme | Up to €60,000/SME | Open calls for cybersecurity solutions |
| Industriens Fond | Ongoing | Cybersikkerhedsprogram active |
| EU SECURE Project | Mentorship + funding | Launched January 2026 |

These grants fund growth, not survival. The business model is self-sustaining on subscription revenue.

### 12.3 GDPR-First Strategy

Building in Denmark means building for the strictest data protection regime in the world. The compliance framework translates directly to all 27 EU member states. A product built for Danish GDPR compliance is EU-ready by default.

### 12.4 SMB Density and Digital Adoption

Denmark has over 200,000 SMBs with websites, high digital adoption rates, and high regulatory requirements — the ideal first market for messaging-first cybersecurity delivery. The market is large enough to build a sustainable business and small enough to validate the model before EU expansion.

### 12.5 Danish Marketing Law as Moat

Markedsføringsloven prohibits unsolicited electronic marketing. This forces a high-trust, in-person acquisition model — and creates a barrier to entry for remote-first competitors who rely on digital outbound at scale. Being physically present in Denmark is a competitive advantage.

### 12.6 Founder's Existing Presence

I have been based in Vejle since 2019 — seven years in Denmark by the time of this application. I have worked at LEGO and JYSK, am embedded in the local business environment, and have already tested the Heimdall pipeline against 203 Vejle-area domains. I am building the product here, for this market.

---

## 13. Team & Execution Capability

### 13.1 Founder — Federico Alvarez

I bring nearly 20 years of enterprise software engineering experience to Heimdall, with a track record of delivering complex technical solutions across multiple industries and geographies.

**Current role:** I am a Senior SAP Engineer at LEGO (Vejle, Denmark, since January 2023). I arrived in Denmark on the Fast-Track employment scheme — a government-approved path for highly skilled workers.

**Enterprise engineering career:**
- **LEGO (2023–present):** I architected SAP BTP integrations, built syslog drain pipelines (Cloud Foundry → Elastic stack), developed Databricks ingestion pipelines in Python, led S/4HANA clean core transformation, and mentored teams on SAP CAP adoption.
- **JYSK (2020–2022):** Delivered SAP CAR developments for POS migration, built OData services, enhanced HANA calculation views, optimized forecast reports.
- **LEGO via Hays (2019–2020):** Led application architecture review and ABAP solution redesign, defined REST API integration patterns, achieved 90% runtime reduction in database stored procedures.
- **Medtronic via IBM (2018):** Coordinated worldwide SAP deployment activities across multiple geographies.
- **Grupo Bancolombia via Deloitte (2009–2011):** I led a team of approximately 30 SAP CRM consultants through a full implementation, managing over 170 developments — sprint planning, workload distribution, stakeholder communication.
- **Earlier career at Deloitte (2006–2008):** Multi-client, multi-country SAP consulting across Argentina, Mexico, and Colombia.
- **NIS National Insurance Board (Barbados, 2013–2017):** Led full SAP CRM and Social Services implementation for a national public-sector institution.

**Technical skills relevant to Heimdall:** Python, REST API development, cloud platforms (SAP BTP, Cloud Foundry), CI/CD, test automation (Mocha, Chai, Jest), data pipelines (Databricks), SQL data modelling, infrastructure (Elastic stack, Docker).

**Education:** Computer Systems Analyst (Instituto Superior del Milagro).

**Languages:** Spanish (native), English (professional).

**In Denmark since 2019.** Based in Vejle.

### 13.2 What Has Already Been Built

This is not a slide deck. I have built and am running:

- **Lead generation pipeline** — 20+ module Python pipeline processing CVR company data, resolving domains, scanning, bucketing, and generating per-site briefs. Tested against 204 live Vejle-area domains in 8.5 minutes.
- **AI-powered finding interpreter** — Claude API agent translates raw scan data into plain-language findings, tier-aware (Watchman trial: what's wrong, Sentinel: + how to fix it). No plugin names in client-facing text.
- **Telegram delivery bot** — full pipeline from scan completion to client notification. Redis pub/sub, operator approval flow, inline acknowledge button, HTML formatting with severity labels and confirmed/potential separation.
- **Client database** — SQLite schema with 11 tables, normalised findings (definitions + occurrences), delivery log, consent registry. 150+ tests.
- **Digital twin framework** — reconstructs client WordPress environments locally for safe vulnerability testing without touching real sites. Legal foundation documented.
- **Valdí legal compliance system** — two-gate validation (scan-type approval + consent check), forensic logging, approval token registry. Born from a real compliance boundary violation — correction mechanism proven.
- **WordPress passive detection** — plugin version extraction via HTML `?ver=` params, REST API namespace enumeration, meta generator tags, CSS class signatures. Outdated plugin checks against wordpress.org.
- **Vulnerability enrichment** — WPVulnerability API integration for plugin/core CVE lookups with local SQLite cache. Certificate Transparency coverage via crt.sh for prospecting (SAN subdomain enrichment) and SSLMate CertSpotter for Sentinel-tier per-client certificate change monitoring.
- **CVR enrichment tool** — 7-step pipeline: Excel ingestion → static enrichments → email domain extraction → name-match validation → search-based discovery → deduplication → summary. SQLite output.
- **Docker Compose deployment** — Pi5 production stack with two-phase architecture (subfinder batch → per-domain scans), warm caching, smoke tests, version pinning.
- **12 agent specifications** with documented boundaries, handoff protocols, and chain architecture.
- **Complete legal risk assessment** of Danish scanning law under Straffeloven §263.
- **690+ automated tests** across the full codebase.

### 13.3 Network Security Partner

A network security specialist provides domain expertise, technical credibility, and operational support. This partnership addresses the single-founder constraint and adds professional depth for agency conversations and grant applications.

### 13.4 Claude Code as Force Multiplier

I built the codebase with Claude Code — Anthropic's AI development assistant. With Claude Code, I operate at the output level of a small team for code generation, documentation, research, and specification writing. The agent specifications encode domain knowledge in a structured, transferable format — new team members onboard by reading the specifications.

### 13.5 Post-Establishment Advisory

| Role | Purpose | Status |
|------|---------|--------|
| University partner (AAU/SDU/DTU) | Research validation, technical credibility | Outreach post-establishment |
| Legal counsel (Anders Wernblad, Aumento Law) | §263 confirmation, scanning-authorisation template, DPA, Markedsføringsloven, NIS2/CRA | Active; 16-Q briefing in review |
| Industriens Fond | Cybersikkerhedsprogram alignment | Research stage |
| Operations hire (part-time) | Client communication, pilot support | First hire priority |

---

## 14. Financial Projections & Self-Sustainability

### 14.1 Three Scenarios

All scenarios use the aggressive pricing. Blended ARPC: ~305 kr./month (early, Watchman-heavy mix, 30% annual uptake), growing to ~370 kr./month as tier mix matures. Churn: 30–40% Year 1. Tool licensing costs eliminated (WPVulnerability API is free).

**Conservative (base case):**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 10 | 50 | 100 |
| MRR | 3,050 kr. | 17,500 kr. | 37,000 kr. |
| ARR | 36,600 kr. | 210,000 kr. | 444,000 kr. |
| Gross margin | ~58% | ~65% | ~68% |

Assumptions: Organic growth only. No agency partnerships beyond 1. Weighted toward Watchman tier.

**Moderate:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 20 | 80 | 200 |
| MRR | 6,100 kr. | 29,600 kr. | 74,000 kr. |
| ARR | 73,200 kr. | 355,200 kr. | 888,000 kr. |
| Gross margin | ~62% | ~68% | ~70% |

Assumptions: 2 agency partnerships. Tier mix shifts toward Sentinel. Local business association traction.

**Optimistic:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 30 | 120 | 300 |
| MRR | 9,150 kr. | 44,400 kr. | 111,000 kr. |
| ARR | 109,800 kr. | 532,800 kr. | 1,332,000 kr. |
| Gross margin | ~64% | ~69% | ~72% |

Assumptions: 3+ agency partnerships. Strong tier migration. EU pilot begins in Month 24.

### 14.2 Break-Even Analysis

| Metric | Value |
|--------|-------|
| Fixed monthly costs (infra + API + insurance + legal retainer amortised) | ~4,650 kr. |
| ARPC (Sentinel only; Watchman is free) | ~370 kr. |
| Margin per Sentinel client | ~245–275 kr. |
| **Break-even point** | **~12 paying Sentinel clients** |

The trade-off is explicit: aggressive pricing requires ~12 paying clients to break even instead of 5–6 at premium pricing. But with a free 30-day Watchman trial preceding every paid conversion, each Sentinel sale is backed by 30 days of demonstrated value — not a cold ask. The pipeline has identified 68 prime targets in Vejle alone — a ~5× surplus over the break-even requirement.

Tool licensing costs have been eliminated by replacing the WPScan commercial API with the free WPVulnerability API.

### 14.3 Self-Sustainability

The business model is designed to be self-sustaining on subscription revenue alone. I have proof of financial capacity for the establishment phase as required by Startup Denmark.

The financial projections are based on subscription revenue only. They do not account for:
- **Grant funding** (Digital Europe Programme, Industriens Fond, and similar programmes) — non-dilutive growth capital available to Danish cybersecurity companies
- **Upsell revenue** from tier migration (Watchman trial → Sentinel)
- **Annual discounts** (Watchman 169, Sentinel 339 kr./mo × 12) — locks in recurring revenue and improves cash flow predictability

These are excluded deliberately. The conservative case stands on subscription revenue alone.

---

## References

1. Styrelsen for Samfundssikkerhed — 40% of Danish SMBs lack adequate security. https://samsik.dk
2. Danish Government — Cybersecurity Strategy 2026–2029 ("Aftale om strategi for cyber- og informationssikkerhed 2026-2029"). https://mssb.dk/nyheder/nyhedsarkiv/2026/januar/aftale-ny-strategi-for-cyber-og-informationssikkerhed/
3. NCC-DK — Grant pool for innovative cybersecurity solutions. https://samsik.dk/artikler/2026/02/ny-pulje-55-mio-kr-til-innovative-loesninger-paa-cybertruslen/
4. DI Digital — SMV-CERT proposal (Lars Sandahl quote). https://www.danskindustri.dk/brancher/di-digital/nyhedsarkiv/nyheder/2025/12/di-vil-samle-krafterne-mod-cyberangreb-ny-enhed-skal-styrke-beskyttelsen-af-sma-og-mellemstore-virksomheder/
5. VikingCloud 2026 SMB Statistics — 60% breach closure rate. Cited via https://digacore.com/blog/managed-cybersecurity-services-smb-2026/
6. NCSA / Getastra — SMB breach survival data. Cited via https://www.getastra.com/blog/dast/vulnerability-scanning-for-smbs/
7. GDPR Article 32 / Vectra compliance guide. https://www.vectra.ai/topics/gdpr-compliance
8. Qualys — Dashboard documentation. https://blog.qualys.com/product-tech/2020/02/04/actionable-searching-and-data-download-with-vulnerability-management-dashboards
9. Intruder.io / Bugcrowd — Vulnerability scanning tools. https://www.intruder.io/blog/the-top-vulnerability-scanning-tools / https://www.bugcrowd.com/glossary/intruder-vulnerability-scanner/
10. SecurityScorecard STRIKE Team — 21,000+ exposed OpenClaw instances. Cited via https://pbxscience.com/openclaw-2026s-first-major-ai-agent-security-crisis-explained/
11. Koi Security / Bitdefender — ClawHub malicious skills. Cited via https://blog.cyberdesserts.com/openclaw-malicious-skills-security/
12. Kaspersky — OpenClaw security audit (512 vulnerabilities). Cited via https://www.institutionalinvestor.com/article/openclaw-ai-agent-institutional-investors-need-understand-shouldnt-touch
13. Dark Reading / Kiteworks — 48% agentic AI attack vector poll. Cited via https://www.kiteworks.com/cybersecurity-risk-management/agentic-ai-attack-surface-enterprise-security-2026/
14. Danish CVR Register — Public company data. https://datacvr.virk.dk
15. Straffeloven §263 — Danish Penal Code hacking provision. https://danskelove.dk/straffeloven/263
16. ICLG Cybersecurity Report 2026 — Denmark chapter. https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark
17. Startup Denmark programme. https://www.nyidanmark.dk/en-GB/You-want-to-apply/Work/Start-up-Denmark
18. McLoughlin, J. (2025) — "The Rules & Regulations That Make Us Less Safe." Cyber Security Intelligence. https://www.cybersecurityintelligence.com/blog/the-rules-and-regulations-that-make-us-less-safe-8796.html
19. Microsoft UK (2025) — Shadow AI research: 71% of UK employees used unapproved AI tools at work. Cited via Cyber Security Intelligence. https://www.cybersecurityintelligence.com/blog/ai-adoption-in-law---the-case-for-stronger-accountability-9127.html
20. Cyber Security Intelligence (2025) — "Can The EU AI Act & ISO 42001 Bring Order To The Digital Wild West?" https://www.cybersecurityintelligence.com/blog/the-eu-ai-act-and-iso42001-bring-order-to-the-digital-wild-west-8733.html

---

*This document was prepared in March 2026 as part of a Startup Denmark residence permit application. Financial projections are forward-looking estimates based on stated assumptions. All scanning activities described comply with Danish law as analyzed in the project's legal risk assessment — confirmation by qualified legal counsel is planned for the establishment phase.*
