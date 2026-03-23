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

---

## 6. Business Model & Unit Economics

### 6.1 Pricing

| Tier | Monthly Price | Scan Frequency | Key Value |
|------|-------------|----------------|-----------|
| Watchman | 499 kr. | Weekly | What is wrong + who should fix it |
| Sentinel | 799 kr. | Daily | How to fix it + drafted messages to forward |
| Guardian | 1,199 kr. | Daily | Active testing + fix verification + quarterly report |

Blended average revenue per client: ~650 kr./month (assuming a mix weighted toward Watchman and Sentinel in early stages).

### 6.2 Unit Economics Per Client (Monthly, at Scale)

| Cost Component | Amount | Notes |
|---------------|--------|-------|
| Revenue (blended) | ~650 kr. | Weighted average across tiers |
| Claude API | ~75 kr. | Interpretation, message composition, follow-up |
| Infrastructure | ~15–30 kr. | At 50+ clients; higher per-client at pilot scale |
| Insurance allocation | ~30–45 kr. | Professional indemnity, pro-rated |
| **Total COGS** | **~120–150 kr.** | |
| **Gross margin** | **~77–82%** | |

The margin improves with scale. Infrastructure cost per client drops from ~112 kr. at 5 clients to ~14 kr. at 50 clients. Claude API cost is roughly linear with client count but benefits from prompt caching and batch processing.

### 6.3 Acquisition Economics

**First Finding Free:** The Layer 1 prospecting scan costs near-zero to run — it reads publicly served information using open-source tools. This produces real findings (outdated CMS, expiring SSL, missing headers) that power a free-sample sales motion. The cost of acquiring a lead is essentially the time spent on the in-person conversation.

**Agency partnerships:** One relationship with a web agency yields access to 10–35 client sites. The pitch is: "I scanned 35 of your client sites. 22 have at least one issue. Your name is on the footer." The agency becomes a channel partner or white-label reseller. This is the highest-leverage acquisition channel.

**No paid advertising in Phase 1–3.** Danish marketing law (Markedsføringsloven) prohibits unsolicited electronic marketing without consent. This constraint eliminates the temptation to burn money on outbound — the model is built on in-person relationships and demonstrated value.

### 6.4 Churn

Expected churn: **30–40% in Year 1**, declining to **20–25% in Year 2+**.

This is honest. SMB churn is high across all SaaS categories. Mitigations:

1. **Persistent memory as switching cost** — a new provider rebuilds the client's security history from scratch
2. **Agency relationships** — if the agency partner stays, their clients stay
3. **Compliance value** — GDPR Article 32 creates an ongoing obligation, not a one-time fix
4. **Follow-up model** — the escalating reminder system keeps the service visible and actionable

### 6.5 Break-Even

At ~650 kr. blended revenue and estimated fixed costs of ~3,500 kr./month (infrastructure + API + insurance), break-even occurs at approximately **5–6 paying clients**. The pilot budget of 12,000 kr. covers 3–4 months of pre-revenue operations.

---

## 7. Go-to-Market Strategy

### 7.1 The Constraint That Becomes an Advantage

Danish marketing law (Markedsføringsloven) prohibits unsolicited electronic marketing — email, SMS, automated messages — without prior consent. Cold calling requires checking the Robinson List. This eliminates the standard SaaS playbook of cold email sequences and LinkedIn automation.

This is an advantage, not a limitation. It forces a high-trust acquisition model that competitors relying on digital outbound cannot easily replicate. Local relationships, demonstrated value, and word-of-mouth create durable competitive advantages that scale ads do not.

### 7.2 Five Phases

**Phase 1 — Vejle Pilot (Month 1–3)**
- 5 pilot clients recruited through in-person visits
- "First finding free" — show a real scan result before asking for anything
- Target: Bucket A businesses (self-hosted WordPress on shared hosting)
- Free first month; convert to paid Watchman (499 kr./mo)
- Human-in-the-loop: Federico reviews every message before delivery
- Validation: Did they read it? Did they understand it? Did they act? Would they pay?

**Phase 2 — Agency Partnerships (Month 3–6)**
- Identify local web agencies from footer credits and meta author tags (the pipeline already detects these)
- Approach agencies with aggregate scan data: "22 of your 35 client sites have issues"
- Agency becomes a channel: white-label reseller or referral partner
- One agency relationship = 10–35 client sites
- Target: 2 agency partnerships in this phase

**Phase 3 — Local Business Networks (Month 6–12)**
- Erhvervsforeninger (local business associations) — speaking events, workshops
- Handelstandsforeninger (merchant associations)
- Referral program: existing clients introduce Heimdall at their industry meetups
- Content: case studies from pilot clients (anonymized as needed)
- Target: 20 paying clients by Month 12

**Phase 4 — Geographic Expansion (Month 12–24)**
- Aarhus, Odense, Aalborg — same playbook, new cities
- Agency partnerships scale: agencies often serve clients across Denmark
- Grant funding (if NCC-DK application succeeds) accelerates hiring and expansion
- Target: 80 paying clients by Month 24

**Phase 5 — EU Expansion (Month 24–36+)**
- GDPR framework translates directly — the compliance argument works in all 27 member states
- Messaging delivery is language-agnostic — Telegram/WhatsApp work everywhere
- The Claude API supports all major European languages
- Entry markets: Germany (largest EU economy, strong SMB sector), Netherlands (high digital adoption)
- Target: 200 paying clients by Month 36 (conservative; Denmark-only achieves this)

---

## 8. Competitive Landscape

### 8.1 Direct Competitors

| Competitor | Starting Price | Interface | Shadow AI Detection | SMB Messaging |
|-----------|---------------|-----------|-------------------|---------------|
| **Heimdall** | 499 kr./mo | Telegram/WhatsApp | Yes | Yes |
| Intruder.io | ~740 kr./mo | Dashboard + Slack/Jira | No | No |
| Detectify | ~610 kr./mo (app) | Dashboard | No | No |
| HostedScan | Free tier; paid ~215 kr./mo | Dashboard + API | No | No |
| Beagle Security | ~885 kr./mo | Dashboard | No | No |
| Sucuri (GoDaddy) | ~1,480 kr./yr | Dashboard + WAF | No | No |

Closest competitor: **Intruder.io** — founded 2015, GCHQ Cyber Accelerator alumni, 1,000+ customers.⁹ Strong product, strong team. Delivers through a web dashboard with Slack and Jira integrations.

Enterprise EASM players (CrowdStrike Falcon Surface, Qualys EASM, Censys) are moving upmarket, not down. They serve enterprises with dedicated security teams. They are not competing for the restaurant owner.

### 8.2 Anticipated Objections

**"Why can't Intruder just add Telegram delivery?"**

They could add a Telegram notification. But notification is not delivery. Heimdall's architecture is built around non-technical users from the ground up — plain-language interpretation, "who should fix this" routing, persistent memory of the client's tech stack, escalating follow-up, drafted messages to forward. Adding a Telegram webhook to a dashboard product does not replicate this. It would require rebuilding the product's entire communication layer, output format, and user model.

**"HostedScan has a free tier — why would someone pay 499 kr.?"**

If the business owner can navigate a vulnerability scanning dashboard, configure scan targets, interpret CVSS scores, and act on the findings — HostedScan is the better choice and Heimdall cannot compete on price. For the majority of SMB owners who cannot do any of those things, the dashboard might as well not exist. Heimdall serves the owner who will never log into a dashboard but will read a Telegram message on their phone.

**"This is just a Telegram bot wrapper around existing tools."**

The tools are commodity — Nuclei, httpx, webanalyze are open source. The value is in the chain: which findings matter for this specific business, explained in language the owner understands, routed to the person who can fix it, with persistent memory that tracks what was fixed and what was not, and follow-up that escalates until the issue is resolved. The bot is the interface; the intelligence is in the interpretation, routing, and persistence.

### 8.3 Three Durable Differentiators

1. **Messaging-first delivery:** Not a feature bolted onto a dashboard — the entire product is built around conversational delivery to non-technical users.

2. **Persistent memory:** The agent builds a longitudinal understanding of each client's infrastructure, findings history, and remediation patterns. This creates switching costs and compounds in value over time.

3. **Shadow AI/agent detection:** Scanning for exposed OpenClaw instances, MCP servers, and rogue AI agents. First-mover position in a rapidly growing attack surface that no SMB-focused competitor currently addresses.¹⁰ ¹¹ ¹³

---

## 9. Infrastructure & Scaling Plan

### 9.1 Scaling Stages

| Stage | Clients | Infrastructure | Monthly Cost | Cost/Client |
|-------|---------|---------------|-------------|------------|
| Phase 0 (now) | 0 | Laptop (development) | 0 kr. | — |
| Pilot | 5–10 | Raspberry Pi 5 + Tailscale VPN | 175–560 kr. | ~112–56 kr. |
| Early production | 10–50 | VPS + Docker containers | 350–700 kr. | ~35–14 kr. |
| Scale | 50–200 | Multi-container VPS | 700–2,100 kr. | ~14–10.50 kr. |
| Growth | 200+ | Multi-node cloud | 2,100–7,000 kr. | ~10.50–35 kr. |

### 9.2 Architecture Consistency

The same OpenClaw skill architecture runs at every tier. The agent specifications (SKILL.md files), scanning pipeline, Valdí compliance system, and message delivery chain are substrate-independent. Migration from Pi to VPS to cloud is an infrastructure change, not an application rewrite.

### 9.3 Pilot Infrastructure (Internal Detail)

The pilot runs on a Raspberry Pi 5 (8 GB RAM, NVMe SSD) because it is available, cheap, and sufficient for 5–10 clients. It connects via Tailscale VPN (zero inbound ports) and uses the Claude API for finding interpretation.

The Pi is pilot infrastructure, not the production architecture. Client-facing language describes "dedicated secure infrastructure with encrypted communications" and "cloud-based AI interpretation layer." This is accurate — the infrastructure is dedicated, the communications are encrypted (Tailscale), and the AI interpretation runs on Anthropic's cloud API.

### 9.4 Production Migration

Post-pilot migration path:
- **VPS** (Hetzner, DigitalOcean, or similar) for 10–50 clients
- **Docker containerization** for reproducibility and deployment automation
- **Separation** of scanning infrastructure from client communication
- **Multi-node** architecture as client volume exceeds single-server capacity

The migration is planned and straightforward. The skill architecture does not change — only the hardware underneath it.

---

## 10. Risk Analysis & Mitigations

### 10.1 LLM Hallucination

| | |
|---|---|
| **Probability** | Medium |
| **Impact** | High — incorrect advice could cause a client to take wrong action or ignore a real threat |
| **Mitigation** | Tools produce findings, LLM only interprets. The LLM never decides what is vulnerable — it explains what the scanner found. During pilot: human-in-the-loop review of every message. Post-pilot: confidence scoring system flags low-confidence interpretations for human review. Known risk of "false specificity" (plausible advice wrong for the specific environment) is mitigated by separating "what's wrong" from "how to fix" and bounding remediation guidance to generic best practices with authoritative links. |

### 10.2 Legal Gray Zone (Straffeloven §263)

| | |
|---|---|
| **Probability** | Low (for Layer 1); Medium (for Layer 2 without consent) |
| **Impact** | Critical — criminal liability for the operator |
| **Mitigation** | Valdí two-gate compliance system enforces Layer/Level boundaries programmatically. Forensic logging creates a due diligence trail. Layer 2 scanning only activates after written client consent. Legal counsel engagement is a funded milestone in The Ask (15,000–25,000 kr.). The business model is designed so that the free prospecting scan (Layer 1) and the paid service (Layer 2 with consent) align with the legal boundary. |

### 10.3 Solo Founder

| | |
|---|---|
| **Probability** | High (bus factor = 1) |
| **Impact** | High — project stops if founder is unavailable |
| **Mitigation** | Network security partner provides domain expertise and operational backup. Claude Code functions as a force multiplier — a solo developer with AI tooling operates at the output level of a small team. All agent specifications are documented in SKILL.md files, making the system transferable. The entire codebase (14 modules, 10 agent specs, compliance system, legal research) was built in days, not months. Advisory targets include university partners (for grant consortium) and legal counsel. First hire priority (if funded) is a part-time operations person. |

### 10.4 Customer Churn

| | |
|---|---|
| **Probability** | High (30–40% Y1 is the baseline assumption) |
| **Impact** | Medium — manageable if acquisition cost is low |
| **Mitigation** | Persistent memory creates switching costs. Agency partnerships provide cohort retention (if the agency stays, their clients stay). GDPR Article 32 creates an ongoing compliance obligation, not a one-time fix. The follow-up model keeps the service visible. Break-even at 5–6 clients means the business survives high early churn. The financial projections already account for this churn rate. |

### 10.5 Competitive Response

| | |
|---|---|
| **Probability** | Medium |
| **Impact** | Medium |
| **Mitigation** | Adding messaging delivery to a dashboard product requires rebuilding the communication layer, user model, and output format — not shipping a webhook. Intruder and HostedScan are optimized for security-literate users; pivoting to non-technical SMBs means changing the product, not adding a feature. Local in-person relationships (forced by Markedsføringsloven) create a moat that remote-first competitors cannot replicate easily. First-mover advantage in shadow AI detection adds differentiation. |

### 10.6 Danish Market Size

| | |
|---|---|
| **Probability** | N/A (this is a structural constraint, not a risk event) |
| **Impact** | Low — if the model works, 200 clients in Denmark is a viable business |
| **Mitigation** | Denmark-first is a strategy, not a limitation. It means GDPR-first — the compliance framework translates to all 27 EU member states. 200 paying clients at 650 kr./month blended = 1.56M kr./year ARR. That is a real business. EU expansion is the growth story, funded by revenue and grants. The conservative projections assume Denmark only. |

### 10.7 Shadow AI Detection Commoditization

| | |
|---|---|
| **Probability** | Medium (within 12–24 months) |
| **Impact** | Low |
| **Mitigation** | Shadow AI detection is one of three differentiators — not the only one. If competitors add it, Heimdall still has messaging-first delivery and persistent memory. The first-mover window (estimated 12–18 months) is enough to establish market position and client relationships. The real moat is the delivery model + local trust, not any single detection capability. |

---

## 11. Regulatory & Legal Framework

### 11.1 Danish Criminal Law — Straffeloven §263

Straffeloven §263, stk. 1 criminalizes gaining unauthorized access ("uberettiget adgang") to another person's data system. Penalty: fine or up to 18 months imprisonment; up to 6 years under aggravating circumstances.¹⁵

The ICLG Cybersecurity Report 2026 (Denmark) states: "Unsolicited penetration of an IT system (without permission from the owner) will — most likely — be considered a violation under section 263 of the Danish Penal Code."¹⁶

**Heimdall's position:** Layer 1 scanning (reading publicly served information) carries minimal legal risk — it is functionally identical to visiting a website in a browser. Layer 2 scanning (active vulnerability probing) operates in the gray zone and requires written client consent before activation. This maps cleanly to the business model: free prospecting scan = Layer 1; paid service = Layer 2 with consent.

A full legal risk assessment has been prepared (see project documentation) and will be presented to legal counsel as a funded milestone.

### 11.2 GDPR Article 32 — The Compliance Driver

GDPR Article 32 requires "appropriate technical and organisational measures" to ensure security appropriate to the risk.⁷ This applies to every business handling personal data — including the restaurant collecting booking information, the physiotherapy clinic with patient records, and the e-commerce shop processing payments.

Most Danish SMBs are non-compliant with Article 32 by default. They do not know this. Heimdall makes the gap visible and provides a path to close it. The subscription is not a cost — it is a compliance measure.

### 11.3 Markedsføringsloven — Outreach Constraint as Advantage

Danish marketing law prohibits unsolicited electronic marketing without prior consent. Cold calling requires Robinson List compliance. This eliminates the standard SaaS cold outreach playbook.

Reframed: this forces a high-trust, in-person acquisition model. Heimdall's "first finding free" approach — showing a business owner a real scan of their actual website — works in person. It does not need email. The constraint creates a barrier to entry for remote-first competitors who rely on digital outbound at scale.

### 11.4 Valdí as Demonstrable Due Diligence

The Valdí compliance system — two-gate validation, forensic logging, approval tokens, documented incident response — was built specifically to demonstrate due diligence under §263. Every scan type is validated before execution. Every validation is logged. Every rejection is preserved alongside approvals.

If Heimdall is ever questioned by regulators, the forensic log trail provides timestamped evidence of what was scanned, what was approved, what was rejected, and why.

### 11.5 Open Questions for Counsel

The following questions are documented and will be addressed as a funded milestone:

1. Confirm the Layer 1/Layer 2 boundary under §263
2. Draft/review a scanning authorization template
3. Clarify whether a web agency can authorize scanning of their clients' sites, or whether each end client must consent independently
4. Assess whether Valdí's forensic logs meet due diligence expectations under Danish law

Recommended firms: Plesner, Kromann Reumert, Bech-Bruun (all with IT law / cybersecurity practices).

---

## 12. Team & Execution Capability

### 12.1 Founder

**Federico** — Vejle-based. Technical background: Claude Code, React/TSX, self-hosted infrastructure, Raspberry Pi experience. Building Heimdall alongside the Fjordleather brand (leather goods — separate business, shared entrepreneurial infrastructure).

What Federico built in the first weeks of development:
- 14-module Python pipeline for lead generation
- 10 agent specifications with documented boundaries and handoff protocols
- Valdí legal compliance system with two-gate validation and forensic logging
- Complete legal risk assessment of Danish scanning law under §263
- Post-incident report and remediation for a compliance boundary violation
- Prospecting pipeline tested against 353 live Vejle-area domains

This is not a slide deck. The product is being built.

### 12.2 Network Security Partner

A network security specialist provides domain expertise, technical credibility, and operational support. This partnership addresses the "solo founder" risk and adds professional depth that matters in conversations with agencies, business associations, and grant consortiums.

### 12.3 Claude Code as Force Multiplier

The codebase was built with Claude Code — Anthropic's AI development assistant. This is a deliberate architectural choice, not a shortcut. A solo developer with Claude Code operates at the output level of a small team for code generation, documentation, research, and specification writing.

The agent specifications (SKILL.md files) encode domain knowledge in a structured, transferable format. If the team grows, new developers onboard by reading the specifications — the knowledge is in the system, not in one person's head.

### 12.4 Advisory Targets

| Role | Purpose | Status |
|------|---------|--------|
| University partner (AAU/SDU/DTU) | Grant consortium, research validation | Target for NCC-DK application |
| Legal counsel (Plesner/Kromann/Bech-Bruun) | §263 confirmation, authorization template | Funded milestone |
| Industriens Fond | Cybersikkerhedsprogram alignment | Research stage |
| Operations hire (part-time) | Client communication, pilot support | Post-funding priority |

---

## 13. Financial Projections

### 13.1 Three Scenarios

All scenarios assume blended ARPC (average revenue per client) of 650 kr./month and account for 30–40% Y1 churn.

**Conservative (base case):**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 10 | 50 | 100 |
| MRR | 6,500 kr. | 32,500 kr. | 65,000 kr. |
| ARR | 78,000 kr. | 390,000 kr. | 780,000 kr. |
| Gross margin | ~73% | ~81% | ~83% |
| Monthly infra cost | ~560 kr. | ~700 kr. | ~1,400 kr. |
| Monthly API cost | ~750 kr. | ~3,750 kr. | ~7,500 kr. |

Assumptions: Organic growth only. No agency partnerships beyond 1. No grant funding. Weighted toward Watchman tier.

**Moderate:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 20 | 80 | 200 |
| MRR | 13,000 kr. | 52,000 kr. | 130,000 kr. |
| ARR | 156,000 kr. | 624,000 kr. | 1,560,000 kr. |
| Gross margin | ~77% | ~82% | ~84% |

Assumptions: 2 agency partnerships. Tier mix shifts toward Sentinel. Local business association traction.

**Optimistic:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 30 | 120 | 300 |
| MRR | 19,500 kr. | 78,000 kr. | 195,000 kr. |
| ARR | 234,000 kr. | 936,000 kr. | 2,340,000 kr. |
| Gross margin | ~79% | ~83% | ~85% |

Assumptions: NCC-DK grant awarded. 3+ agency partnerships. EU pilot begins in Month 24. Tier mix includes Guardian clients.

### 13.2 Break-Even Analysis

| Metric | Value |
|--------|-------|
| Fixed monthly costs (infra + API + insurance) | ~3,500 kr. |
| Blended ARPC | ~650 kr. |
| Gross margin per client | ~500–535 kr. |
| **Break-even point** | **~5–6 paying clients** |
| Pilot budget (self-funded) | 12,000 kr. |
| Pre-revenue runway | 3–4 months |

The low break-even point is a structural advantage. Heimdall does not need 1,000 clients to be viable. Five clients paying 499 kr./month cover operating costs. Everything above that is margin.

### 13.3 What the Numbers Do Not Include

These projections do not account for:
- Grant funding (NCC-DK, Digital Europe Programme, Industriens Fond) — all non-dilutive upside
- Consulting revenue from agency partnerships (implementation services for findings)
- Upsell revenue from Watchman → Sentinel → Guardian tier migration
- Quarterly report fees (Guardian tier, priced into subscription but high-margin)

These are excluded deliberately. The conservative case must stand on subscription revenue alone.

---

## 14. The Ask

### 14.1 Amount

**150,000–250,000 kr.** — deliberately modest. This is not a bet on a vision. It is funding for specific, near-term milestones that convert a working prototype into a revenue-generating business.

### 14.2 Use of Funds

| Use | Amount | Why |
|-----|--------|-----|
| Legal counsel (§263 + consent template) | 15,000–25,000 kr. | Confirm the legal framework. Draft client authorization template. Clarify agency delegation rights. |
| Professional indemnity insurance (Year 1) | 5,500 kr. | Required before scanning client sites commercially. |
| Pilot hardware (Raspberry Pi 5 + accessories) | 2,500 kr. | Dedicated always-on scanning infrastructure for 5–10 pilot clients. |
| Claude API (6 months) | 4,500 kr. | Finding interpretation, message composition, follow-up generation. |
| Domain + marketing materials | 3,000 kr. | Landing page, business cards, one-pagers for in-person sales. |
| Founder runway (3–6 months part-time) | 60,000–120,000 kr. | Enables focused execution alongside existing business (Fjordleather). |
| VPS migration | 10,000 kr. | Move from Pi to production hosting when client count exceeds pilot capacity. |
| Grant consortium costs | 20,000 kr. | NCC-DK application preparation, university partner coordination, travel. |
| Contingency | 20,000–40,000 kr. | Unforeseen costs, extended timeline, additional legal review. |

### 14.3 Milestone-Gated Deployment

The funding is not a lump sum. It is deployed against specific milestones:

| Milestone | Timeline | Funded By |
|-----------|----------|-----------|
| Legal confirmation + authorization template | Month 1–2 | Legal counsel budget |
| Pilot launch (5 clients, Vejle) | Month 2 | Hardware + insurance + API |
| Pilot validation data collected | Month 3 | Founder runway |
| First paying clients | Month 3–4 | Founder runway + marketing |
| NCC-DK grant application submitted | Before April 15 | Grant consortium budget |
| First agency partnership | Month 4–6 | Founder runway + marketing |
| Break-even (5–6 clients) | Month 4–6 | — |
| 10 paying clients | Month 6 | — |
| VPS migration | Month 6–8 | VPS budget |
| 20 paying clients | Month 12 | — |

### 14.4 Why This Amount

The ask is small because the cost structure is small. There is no office, no team of 10, no enterprise sales cycle. The infrastructure is a Raspberry Pi transitioning to a VPS. The sales motion is in-person conversations powered by free scans. The AI interpretation runs on a pay-per-use API.

The largest line item is founder runway — enabling Federico to dedicate meaningful time to the pilot alongside his existing business. Without it, the project progresses at evenings-and-weekends pace. With it, the timeline compresses from 12 months to 6.

A larger raise is possible but not necessary. If the NCC-DK grant is awarded, the funding picture changes significantly — the 5.5M kr. pool could fund 12–18 months of accelerated development and expansion. The angel investment positions Heimdall to apply for that grant from a position of strength (working product, paying clients, legal confirmation).

---

## 15. Why Now?

Five forces are converging in 2026 that make this the right moment — not 2024, not 2028.

### 15.1 Government Spending Starts Now

The Danish government allocated 211 million kr. for cybersecurity over 2026–2029, plus 275 million kr./year for NIS2 implementation.² This is not a proposal — it is a signed cross-party agreement backed by nearly every party in the Folketing. SMV-CERT, the new SMB-focused Computer Emergency Response Team, is being built as a public-private partnership.⁴ The money is flowing and the infrastructure is being created for exactly the type of service Heimdall provides.

### 15.2 The NCC-DK Grant Window Is Open

The 5.5 million kr. NCC-DK grant pool opened on February 26, 2026 with a deadline of April 15, 2026.³ The stated criteria — "innovative cybersecurity solutions" with a cited example of "an AI-based tool that uses pattern recognition to simulate attacker behaviour" — describe Heimdall's architecture almost exactly. This is a time-limited opportunity. Total NCC-DK grant budget for 2026–2029: 43 million kr. Missing the first round means waiting for the next.

### 15.3 NIS2 Compliance Pressure Is Mounting

NIS2 (effective in Denmark since July 1, 2025) expands mandatory security requirements into the SMB space through supply chain obligations. Larger enterprises must ensure their suppliers meet security standards — pulling their SMB vendors into compliance scope. A restaurant may not care about NIS2 directly, but the booking platform it uses, or the payment processor it relies on, may start requiring security attestations from its business clients.

### 15.4 The Shadow AI Attack Surface Is Exploding

Over 21,000 OpenClaw instances are publicly exposed.¹⁰ Kaspersky found 512 vulnerabilities in the platform.¹² A Dark Reading poll found 48% of security professionals consider agentic AI a top attack vector for 2026.¹³ Businesses are deploying AI agents — chatbots, workflow automation, data processing — without understanding the security implications. No SMB-focused security tool scans for this. Heimdall does.

### 15.5 The Delivery Gap Is Still Open

As of March 2026, no EASM product delivers findings through messaging apps to non-technical business owners. Every competitor uses a dashboard. The window for establishing messaging-first delivery as a category is open now. It will not stay open indefinitely — but the first mover who builds a client base with persistent memory and local trust relationships creates a position that is expensive to replicate.

---

These five forces do not individually guarantee success. Together, they create a convergence: government money, grant opportunity, regulatory pressure, a new attack surface, and an unserved delivery model — all in 2026. The question for an investor is not whether the cybersecurity market for Danish SMBs will grow. The government has already decided it will. The question is who will serve it.

---

## References

1. Styrelsen for Samfundssikkerhed — 40% of Danish SMBs lack adequate security. https://samsik.dk
2. Danish Government — Cybersecurity Strategy 2026–2029 ("Aftale om strategi for cyber- og informationssikkerhed 2026-2029"). https://mssb.dk/nyheder/nyhedsarkiv/2026/januar/aftale-ny-strategi-for-cyber-og-informationssikkerhed/
3. NCC-DK — 5.5M kr. grant pool for innovative cybersecurity solutions. https://samsik.dk/artikler/2026/02/ny-pulje-55-mio-kr-til-innovative-loesninger-paa-cybertruslen/
4. DI Digital — SMV-CERT proposal (Lars Sandahl quote). https://www.danskindustri.dk/brancher/di-digital/nyhedsarkiv/nyheder/2025/12/di-vil-samle-krafterne-mod-cyberangreb-ny-enhed-skal-styrke-beskyttelsen-af-sma-og-mellemstore-virksomheder/
5. VikingCloud 2026 SMB Statistics — 60% breach closure rate. Cited via https://digacore.com/blog/managed-cybersecurity-services-smb-2026/
6. NCSA / Getastra — SMB breach survival data. Cited via https://www.getastra.com/blog/dast/vulnerability-scanning-for-smbs/
7. GDPR Article 32 / Vectra compliance guide. https://www.vectra.ai/topics/gdpr-compliance
8. Qualys — Dashboard documentation ("interactive customizable widgets"). https://blog.qualys.com/product-tech/2020/02/04/actionable-searching-and-data-download-with-vulnerability-management-dashboards
9. Intruder.io / Bugcrowd — Vulnerability scanning tools, Intruder profile. https://www.intruder.io/blog/the-top-vulnerability-scanning-tools / https://www.bugcrowd.com/glossary/intruder-vulnerability-scanner/
10. SecurityScorecard STRIKE Team — 21,000+ exposed OpenClaw instances. Cited via https://pbxscience.com/openclaw-2026s-first-major-ai-agent-security-crisis-explained/
11. Koi Security / Bitdefender — ClawHub malicious skills. Cited via https://blog.cyberdesserts.com/openclaw-malicious-skills-security/
12. Kaspersky — OpenClaw security audit (512 vulnerabilities). Cited via https://www.institutionalinvestor.com/article/openclaw-ai-agent-institutional-investors-need-understand-shouldnt-touch
13. Dark Reading / Kiteworks — 48% agentic AI attack vector poll; Gravitee State of AI Agent Security 2026. Cited via https://www.kiteworks.com/cybersecurity-risk-management/agentic-ai-attack-surface-enterprise-security-2026/ and https://beam.ai/agentic-insights/ai-agent-security-in-2026-the-risks-most-enterprises-still-ignore
14. Danish CVR Register — Public company data. https://datacvr.virk.dk
15. Straffeloven §263 — Danish Penal Code hacking provision. https://danskelove.dk/straffeloven/263
16. ICLG Cybersecurity Report 2026 — Denmark chapter. https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark

---

*This document was prepared in March 2026. Financial projections are forward-looking estimates based on stated assumptions. All scanning activities described comply with Danish law as analyzed in the project's legal risk assessment — confirmation by qualified legal counsel is a funded milestone.*
