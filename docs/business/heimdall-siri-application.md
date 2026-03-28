# Heimdall — Startup Denmark Application

**External Attack Surface Management for Small Businesses**
**March 2026 — Vejle, Denmark**

*Application for Startup Denmark residence permit to establish Heimdall ApS*

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

**Heimdall** is an External Attack Surface Management (EASM) service that continuously monitors a business's public-facing digital surface — domains, certificates, web servers, CMS platforms, plugins — and delivers findings as plain-language messages through Telegram and WhatsApp. Not a dashboard. Not a PDF report. A conversation, in Danish, that tells the owner what is wrong, who should fix it, and what to say to that person.

**The innovation:** No existing EASM product delivers findings through messaging apps to non-technical business owners. Heimdall's architecture is built from the ground up around conversational delivery, persistent memory of each client's infrastructure, AI-powered interpretation of technical findings, and automated legal compliance governance. Two technical innovations are particularly distinctive. First, a **digital twin** system that reconstructs a prospect's website from publicly available data and runs it on Heimdall's own infrastructure — enabling CVE-level vulnerability scanning without touching the prospect's systems or requiring their consent, because Danish criminal law (Straffeloven §263) only protects "another person's data system." Second, **Valdí**, a programmatic compliance agent with two-gate validation and forensic logging, built as a systemic response to a real compliance incident — demonstrating a governance maturity that most startups never achieve. This is not an incremental improvement — it is a fundamentally different approach to cybersecurity for SMBs.

**Business model:** Three subscription tiers at 199, 399, and 799 kr./month — Watchman is cheaper than every competitor's entry tier. Client acquisition starts with a free first scan — a passive analysis that produces real findings (outdated CMS versions, expiring SSL certificates, missing security headers) at near-zero marginal cost. Break-even at ~10 paying clients.

**Current state:** The product is being built. The lead generation pipeline is operational — 14 Python modules, a 10-agent architecture, a programmatic legal compliance system (Valdí) with two-gate validation and forensic logging, and a complete legal risk assessment of Danish scanning law. The pipeline has been tested against 353 live Vejle-area domains.

**Why Denmark:** Denmark's cybersecurity investment, GDPR-first regulatory environment, dense SMB market, and grant ecosystem create the ideal conditions for this business. The founder has been based in Vejle since 2019 and has already tested the pipeline against local domains.

This application is for a Startup Denmark residence permit to establish Heimdall ApS in Denmark.

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

This delivery model represents a fundamentally new approach to cybersecurity for SMBs — no existing product operates this way.

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

"We already scanned your website. Your WordPress is three major versions behind, and your SSL certificate expires in two weeks. Here is what that means for your business. Heimdall monitors this continuously and tells you the moment something changes — starting at 199 kr./month."

### 3.5 Service Tiers

| Tier | Price | What It Does |
|------|-------|-------------|
| **Watchman** | 199 kr./mo | Finds problems, explains them, tells you who should fix them |
| **Sentinel** | 399 kr./mo | Daily monitoring + step-by-step fix instructions + draft messages to forward to your developer or hosting provider |
| **Guardian** | 799 kr./mo (annual: 599 kr./mo) | Active defence testing (with written consent) + fix verification + quarterly security report for your accountant or insurer |

*All prices excl. moms (Danish VAT).*

### 3.6 Remediation Service (Optional, Billed Per Event)

Every tier tells the client what is wrong and who should fix it. Sentinel and Guardian add the how. But many small business owners have no developer, no IT contact, and no idea how to apply even step-by-step instructions. When the guide says "log into wp-admin and update WordPress," there is nobody to do it.

Heimdall offers an optional, per-event remediation service: we fix it for you. This is billed separately from the subscription — the client pays only when they choose to use it, and only for the specific fix performed. It is not a retainer. It is not bundled. The client can always choose to follow the guide themselves, forward the drafted message to their own developer, or engage Heimdall to handle it directly.

**Neither of the two closest competitors offers this.** Intruder.io and HostedScan are scanning and advisory platforms only — they identify vulnerabilities and provide guidance, but the actual fix is the customer's problem. For an SMB owner with no technical resources, this is where the process breaks down. Heimdall closes the loop: find it, explain it, fix it.

**Reference pricing (indicative — subject to adjustment during pilot, excl. moms):**

| Component | Price |
|-----------|-------|
| Minimum charge (first hour) | 599 kr. |
| Each additional hour | 399 kr./hr |

This positions Heimdall between a general web developer (~325 kr./hr in Denmark) and a cybersecurity specialist (~500 kr./hr). Most common SMB fixes (WordPress update, SSL renewal, security header configuration) resolve within one hour. More complex work (malware cleanup, server hardening) is quoted transparently.

| Scenario | Typical Resolution | Without Remediation | With Remediation |
|----------|-------------------|---------------------|-----------------|
| WordPress update | 30 min – 1 hr | Guide sent → client forwards to developer (if they have one) | Heimdall applies the update directly |
| SSL certificate renewal | 30 min – 1 hr | Hosting provider contact instructions sent | Heimdall coordinates with host or renews |
| Plugin removal/replacement | 1 – 3 hrs | Removal/replacement steps sent | Heimdall removes or replaces the plugin |
| Security headers config | 1 – 2 hrs | Technical configuration guide sent | Heimdall configures the headers |

This creates an additional high-margin revenue stream while deepening the client relationship. Clients who use the remediation service have a stronger reason to stay subscribed — Heimdall becomes their de facto security team, not just their scanner.

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
4. **Layer 1 scanning:** Passive observation using open-source tools — webanalyze (https://github.com/rverton/webanalyze), httpx (https://github.com/projectdiscovery/httpx), subfinder (https://github.com/projectdiscovery/subfinder) for subdomain enumeration via Certificate Transparency logs, dnsx (https://github.com/projectdiscovery/dnsx) for DNS enrichment, and sslyze for TLS analysis. Reads only what the server voluntarily sends to any visitor.
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
| Reporting | Quarterly security reports (Guardian tier) |

The critical design principle: **tools produce findings, the LLM interprets them.** Nuclei, httpx, and webanalyze generate structured technical data. Claude translates that data into language the restaurant owner understands. The LLM never decides what is vulnerable — it decides how to explain what the tools found.

### 4.3 Valdí — The Compliance System

Heimdall operates under Danish criminal law (Straffeloven §263), which criminalizes unauthorized access to data systems. The legal boundary between permitted passive observation and potentially criminal active probing is enforced programmatically by Valdí, the legal compliance agent.

**Gate 1 — Scan Type Validation:** Every scanning function is reviewed against documented rules before it can execute. Valdí classifies the function's activities by Layer, confirms they do not exceed what the target's consent level permits, and issues an approval token. Rejected functions are blocked with structured reasoning. Every review — approval or rejection — produces a timestamped forensic log.

**Gate 2 — Per-Target Authorization:** Before each scan batch, Valdí confirms that the scan type has a valid approval token and that each target's consent level permits the scan's Layer.

**No scanning code executes without a valid Valdí approval token.**

Valdí constitutes **demonstrable due diligence** under Danish law. If Heimdall's scanning activities are ever questioned by regulators, the forensic log trail provides timestamped, machine-generated evidence of every scan type validated, every approval issued, every rejection recorded, and every pre-scan authorization check performed. This is not a retrospective compliance narrative — it is a live, auditable record that exists before any scan executes. For a company operating on the boundary defined by §263, this level of programmatic governance is a concrete legal asset.

### 4.4 Governance Maturity — The March 22 Incident

On March 22, 2026, during early pipeline development, a function was written that probed specific admin paths (`/wp-admin/`, `/wp-login.php`, `/administrator/`) on target domains — active probing that crosses the Layer 1 boundary into Layer 2. The function was integrated into the pipeline and executed against 353 live domains before the violation was identified.

The violation was caught by the project owner's manual review of pipeline output. The response was immediate and systematic:

1. **Detection:** The project owner challenged a sales hook ("Admin login page is publicly accessible") and identified that the underlying function constituted Layer 2 activity running without consent.
2. **Containment:** The offending function was removed from the codebase. All tainted data — output files, briefs, and cached results containing the unauthorized findings — was scrubbed.
3. **Verification:** A full code review of the entire scanning pipeline confirmed no other boundary violations existed.
4. **Documentation:** A formal post-incident report was written, documenting the root cause (a classification error where admin path probing was treated as "checking publicly accessible URLs" rather than correctly identified as directed probing), the timeline, and the remediation steps.
5. **Systemic response:** Valdí was designed and built as a direct result — a two-gate automated compliance system that makes this class of error structurally impossible going forward.

**This incident history is stronger evidence of governance maturity than a clean record.** Any organization can claim it has never had a compliance incident. Heimdall can demonstrate that when a boundary violation occurred, the system detected it, scrubbed all tainted data, documented the root cause, and built an automated gate to prevent recurrence. The correction mechanism is proven — not theoretical. This is precisely the kind of evidence that regulators and legal counsel assess when evaluating due diligence.

---

## 5. Innovation

Heimdall introduces seven distinct innovations to the External Attack Surface Management market. These are not incremental improvements to existing products — they represent a fundamentally different approach to delivering cybersecurity to non-technical users.

### 5.1 Messaging-First Delivery Model

Every existing EASM product delivers findings through web dashboards. Heimdall delivers through Telegram and WhatsApp — the apps the business owner already uses. The entire product architecture is built around conversational delivery: plain-language interpretation, "who should fix this" routing, drafted messages to forward, and escalating follow-up. This is not a notification feature bolted onto a dashboard — it is the product.

### 5.2 Shadow AI and Agent Detection

Over 21,000 OpenClaw instances are publicly exposed.¹⁰ Kaspersky found 512 vulnerabilities in the platform.¹² Businesses are deploying AI agents without understanding the security implications. No SMB-focused security tool scans for exposed AI agent infrastructure. Heimdall is the first to address this attack surface for small businesses.

### 5.3 Digital Twin — CVE-Level Findings Without Consent or Contact

This is the innovation no competitor has.

Heimdall's Layer 1 (passive) scanning collects publicly available data about a prospect's website: CMS version, plugin versions, server software, SSL configuration. From this data, Heimdall constructs a **digital twin** — an exact replica of the prospect's technology stack running on Heimdall's own infrastructure.

The legal foundation is explicit in Straffeloven §263's language: the statute criminalizes unauthorized access to **"another person's data system"** ("en andens datasystem"). A digital twin is Heimdall's own system. It is built from lawfully obtained public data. Running vulnerability scanners against it cannot constitute a §263 violation because the system belongs to the scanner operator.

This transforms the sales conversation. Without the twin, Layer 1 scanning produces surface-level observations: "Your WordPress is version 5.8.3" or "You are missing a Content-Security-Policy header." With the twin, Heimdall runs Nuclei templates and WPScan against the replica and produces CVE-level findings: "Your WordPress version and plugin combination has 3 known CVEs, including CVE-2023-XXXXX which allows unauthenticated access to user data."

The difference for a restaurant owner with an online booking system is the difference between "your door is old" and "your door has a known defect that lets strangers walk in." The second message creates urgency. The second message sells.

**What the digital twin enables:**

- **CVE-level prospecting findings** from publicly available data alone — no customer consent required, no contact with their infrastructure
- **Remediation verification** — when the prospect becomes a paying client and applies a fix, Heimdall can reconstruct the twin with the updated configuration and re-scan to confirm the vulnerability is resolved
- **Deterministic test fixtures** — twins built from known configurations provide reproducible regression tests for the scanning pipeline, eliminating dependence on live third-party infrastructure for quality assurance
- **Scalable depth** — every prospect in the pipeline gets the same depth of analysis that would traditionally require written consent and active scanning of their live systems

No competitor in the EASM space offers this capability. The standard industry approach is: passive scan produces shallow findings; deep findings require consent and active scanning of the client's live infrastructure. Heimdall eliminates this tradeoff entirely.

### 5.4 Persistent Memory Architecture

Heimdall builds a longitudinal understanding of each client's infrastructure, findings history, and remediation patterns. The agent remembers what it told the client, what changed, what was fixed, and what was ignored. This compounds in value over time and creates switching costs — a new provider would start from zero.

### 5.5 Programmatic Legal Compliance (Valdí)

Automated governance of scanning operations using a two-gate validation system with forensic logging and approval tokens. Every scan type is validated against documented legal rules before execution. Every validation is logged. This was built in response to a real compliance incident, demonstrating a mature approach to governance.

### 5.6 AI-Powered Interpretation Chain

Open-source scanning tools produce structured technical data. The Claude API interprets that data in plain language for non-technical users, including routing ("who should fix this") and actionable next steps. The LLM never decides what is vulnerable — it explains what the tools found. This separation of detection from interpretation is a novel architecture for SMB security products.

### 5.7 End-to-End Remediation (Find It, Explain It, Fix It)

Every existing competitor stops at advisory — the customer must find someone to execute the fix. Heimdall offers an optional, per-event remediation service that closes the loop entirely. For the SMB owner with no developer and no IT resources, this is the difference between receiving advice they cannot act on and having the problem solved. No EASM competitor currently offers this.

---

## 6. Market Opportunity

### 6.1 Market Sizing

| Metric | Calculation | Annual Value |
|--------|------------|-------------|
| **TAM** | ~200,000 Danish SMBs with websites × 350 kr./mo blended × 12 | ~840M kr./yr |
| **SAM** | ~80,000 (the 40% with inadequate security) × 350 kr./mo × 12 | ~336M kr./yr |
| **SOM** | 200 clients in 36 months × 350 kr./mo × 12 | ~840K kr./yr |

The TAM is a theoretical ceiling — clearly labeled as such. The SAM applies the 40% gap statistic. The SOM is deliberately conservative: 200 paying clients in three years represents 0.25% of the SAM. The upside depends on agency partnerships (one relationship = 10–35 clients) and post-CVR grant funding.

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

| Tier | Monthly Price | Annual Option | Scan Frequency | Key Value |
|------|-------------|---------------|----------------|-----------|
| Watchman | 199 kr. | — | Weekly | What is wrong + who should fix it |
| Sentinel | 399 kr. | — | Daily | How to fix it + drafted messages to forward |
| Guardian | 799 kr. | 599 kr./mo × 12 | Daily | Active testing + fix verification + quarterly report |

*All prices excl. moms.*

Blended average revenue per client: ~350 kr./month (early mix weighted toward Watchman). Increases to ~420 kr./month as tier mix matures.

At 199 kr./mo, Watchman is cheaper than every competitor's entry tier — including HostedScan's paid plan (~215 kr./mo). For a restaurant owner, 199 kr./month is less than a single dinner delivery. Price is eliminated as an objection.

### 7.2 Unit Economics Per Client (Monthly, at Scale)

| Cost Component | Amount | Notes |
|---------------|--------|-------|
| Revenue (blended) | ~350 kr. | Weighted average, early mix |
| Claude API | ~50 kr. | Interpretation + follow-up (lower tiers = less processing) |
| Infrastructure | ~15–30 kr. | At 50+ clients; higher per-client at pilot scale |
| Tool licensing | ~10–20 kr. | WPScan commercial API (Sentinel/Guardian only, pro-rated); amortised across client base |
| Insurance allocation | ~30–45 kr. | Professional indemnity, pro-rated |
| **Total COGS** | **~105–145 kr.** | |
| **Gross margin** | **~59–70%** | Improves with scale, tier migration, and licensing amortisation |

The margin is lower than premium-priced competitors but the pricing creates a fundamentally different market dynamic: 199 kr./mo eliminates price as an objection. Volume compensates for margin.

**Remediation consultancy revenue** (per-event, optional) is not included in these unit economics. It is billed separately when clients choose to have Heimdall execute a fix directly. This creates an additional high-margin revenue stream: the subscription finds the problem, the consultancy fixes it. Neither Intruder.io nor HostedScan offers this — it is unique to Heimdall.

### 7.3 Acquisition Economics

**First Finding Free:** The Layer 1 prospecting scan costs near-zero to run. This produces real findings that power a free-sample sales motion.

**Agency partnerships:** One relationship with a web agency yields access to 10–35 client sites. The agency becomes a channel partner or white-label reseller. This is the highest-leverage acquisition channel.

**No paid advertising in Phase 1–3.** Danish marketing law prohibits unsolicited electronic marketing without consent. The model is built on in-person relationships and demonstrated value.

### 7.4 Break-Even

At ~350 kr. blended revenue and fixed costs of ~2,800 kr./month (including tool licensing), break-even occurs at approximately **11–12 paying clients**. At the aggressive pricing, this requires a larger client base than a premium model — but the lower price point makes each conversion significantly easier. The pipeline has already identified 68 prime targets in Vejle alone; the pilot needs 5–10.

---

## 8. Go-to-Market Strategy

### 8.1 The Constraint That Becomes an Advantage

Danish marketing law (Markedsføringsloven) prohibits unsolicited electronic marketing without prior consent. This eliminates the standard SaaS cold outreach playbook — and forces a high-trust acquisition model that competitors relying on digital outbound cannot easily replicate.

### 8.2 Five Phases

**Phase 1 — Vejle Pilot (Month 1–3)**
- 5 pilot clients recruited through in-person visits
- "First finding free" — show a real scan result before asking for anything
- Free first month; convert to paid Watchman (199 kr./mo)
- Human-in-the-loop: founder reviews every message before delivery

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
- **Grant ecosystem participation:** Post-CVR access to NCC-DK, Digital Europe Programme, and Industriens Fond — keeping grant funding productive within the Danish economy
- **Knowledge economy:** Building cybersecurity expertise and AI-powered security tooling in Denmark

---

## 10. Competitive Landscape

### 10.1 Direct Competitors

| Competitor | Starting Price | Interface | Shadow AI | SMB Messaging | Remediation Service |
|-----------|---------------|-----------|-----------|---------------|-------------------|
| **Heimdall** | 199 kr./mo | Telegram/WhatsApp | Yes | Yes | **Yes (per-event)** |
| Intruder.io | ~740 kr./mo | Dashboard + Slack/Jira | No | No | No |
| Detectify | ~610 kr./mo (app) | Dashboard | No | No | No |
| HostedScan | Free tier; paid ~215 kr./mo | Dashboard + API | No | No | No |
| Beagle Security | ~885 kr./mo | Dashboard | No | No | No |
| Sucuri (GoDaddy) | ~1,480 kr./yr | Dashboard + WAF | No | No | No |

Closest competitor: **Intruder.io** — founded 2015, GCHQ Cyber Accelerator alumni, 1,000+ customers.⁹ Delivers through a web dashboard with Slack and Jira integrations.

Enterprise EASM players (CrowdStrike, Qualys, Censys) are moving upmarket, not down. They are not competing for the restaurant owner.

### 10.2 Anticipated Objections

**"Why can't Intruder just add Telegram delivery?"**

They could add a Telegram notification. But notification is not delivery. Heimdall's architecture is built around non-technical users from the ground up — plain-language interpretation, "who should fix this" routing, persistent memory, escalating follow-up, drafted messages to forward. Adding a Telegram webhook to a dashboard product does not replicate this. It would require rebuilding the product's entire communication layer, output format, and user model.

**"HostedScan has a free tier — why pay 199 kr.?"**

If the business owner can navigate a vulnerability scanning dashboard, configure scan targets, interpret CVSS scores, and act on the findings — HostedScan is the better choice. At 199 kr./mo, Heimdall costs less than HostedScan's own paid tier (~215 kr./mo) while delivering through the channel the owner actually uses. For the majority of SMB owners who cannot navigate a dashboard, the dashboard might as well not exist.

### 10.3 Five Durable Differentiators

1. **Messaging-first delivery:** The entire product is built around conversational delivery to non-technical users — not a feature bolted onto a dashboard.

2. **Digital twin vulnerability analysis:** CVE-level findings from publicly available data alone — no customer consent required, no contact with their live systems. No competitor offers this.

3. **Persistent memory:** Longitudinal understanding of each client's infrastructure, findings history, and remediation patterns. Creates switching costs and compounds in value.

4. **Shadow AI/agent detection:** Scanning for exposed OpenClaw instances, MCP servers, and rogue AI agents. First-mover position in a rapidly growing attack surface.¹⁰ ¹¹ ¹³

5. **Optional remediation service:** No competitor offers hands-on fixes. Intruder.io and HostedScan stop at guidance — the client must find someone to execute. Heimdall closes the loop with per-event consultancy, becoming the client's de facto security team.

---

## 11. Regulatory & Legal Framework

### 11.1 Danish Criminal Law — Straffeloven §263

Straffeloven §263, stk. 1 criminalizes gaining unauthorized access to data systems.¹⁵ Heimdall's Layer 1 scanning (reading publicly served information) carries minimal legal risk — functionally identical to visiting a website in a browser. Layer 2 scanning (active vulnerability probing) requires written client consent before activation. This maps to the business model: free prospecting scan = Layer 1; paid service = Layer 2 with consent.

### 11.2 GDPR Article 32 — The Compliance Driver

GDPR Article 32 requires "appropriate technical and organisational measures" to ensure security appropriate to the risk.⁷ Most Danish SMBs are non-compliant by default. They do not know this. Heimdall makes the gap visible and provides a path to close it.

### 11.3 Digital Twin — Legal Foundation Under §263

Heimdall's digital twin system constructs replicas of prospect websites on Heimdall's own infrastructure, built entirely from publicly available data collected during Layer 1 scanning. The legal basis for running vulnerability scanners (Nuclei, WPScan) against these twins rests directly on the language of §263, stk. 1, which criminalizes unauthorized access to **"en andens datasystem"** — another person's data system.¹⁵

A digital twin is not another person's data system. It is built by Heimdall, hosted by Heimdall, and owned by Heimdall. The data used to construct it — CMS versions, plugin versions, server software, SSL configuration — is publicly served information that any browser visitor receives. Running Layer 2 scanning tools against this self-owned replica cannot constitute a §263 violation.

This distinction enables Heimdall to produce CVE-level vulnerability findings for prospecting purposes without requiring customer consent and without making any active probes against the prospect's live infrastructure. The input is lawful (Layer 1 public data), the scanning target is self-owned (the twin), and the output is high-confidence inference (marked with `provenance: "twin-derived"` throughout the pipeline).

Confirmation of this legal interpretation is included in the planned legal counsel engagement (see Section 11.5).

### 11.4 Valdí as Demonstrable Due Diligence

The Valdí compliance system — two-gate validation, forensic logging, approval tokens, documented incident response — demonstrates due diligence under §263. Every scan type is validated before execution. Every validation is logged. The March 22, 2026 incident (Section 4.4) and Valdí's construction as a systemic response provide concrete evidence that the governance mechanism works: a boundary violation was detected, all tainted data was scrubbed, the root cause was documented, and an automated prevention system was built. If Heimdall is ever questioned by regulators, the forensic log trail provides timestamped evidence of what was scanned, approved, rejected, and why — including evidence that the system catches and corrects its own failures.

### 11.5 Open Questions for Counsel

Legal counsel engagement is planned for the establishment phase to confirm the Layer 1/Layer 2 boundary under §263, validate the digital twin's legal basis (self-owned system built from public data does not constitute "another person's data system" under §263), draft a scanning authorization template, and clarify agency delegation rights. Recommended firms: Plesner, Kromann Reumert, Bech-Bruun (all with IT law / cybersecurity practices).

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

Federico has been based in Vejle since 2019 — seven years in Denmark by the time of this application. He has worked at LEGO and JYSK, is embedded in the local business environment, and has already tested the Heimdall pipeline against 353 Vejle-area domains. The product is being built here, for this market.

---

## 13. Team & Execution Capability

### 13.1 Founder — Federico Alvarez

Federico brings nearly 20 years of enterprise software engineering experience to Heimdall, with a track record of delivering complex technical solutions across multiple industries and geographies.

**Current role:** Senior SAP Engineer at LEGO (Vejle, Denmark, since January 2023). Arrived in Denmark on the Fast-Track employment scheme — a government-approved path for highly skilled workers.

**Enterprise engineering career:**
- **LEGO (2023–present):** Architected SAP BTP integrations, built syslog drain pipelines (Cloud Foundry → Elastic stack), developed Databricks ingestion pipelines in Python, led S/4HANA clean core transformation, mentored teams on SAP CAP adoption.
- **JYSK (2020–2022):** Delivered SAP CAR developments for POS migration, built OData services, enhanced HANA calculation views, optimized forecast reports.
- **LEGO via Hays (2019–2020):** Led application architecture review and ABAP solution redesign, defined REST API integration patterns, achieved 90% runtime reduction in database stored procedures.
- **Medtronic via IBM (2018):** Coordinated worldwide SAP deployment activities across multiple geographies.
- **Grupo Bancolombia via Deloitte (2009–2011):** Led a team of approximately 30 SAP CRM consultants through a full implementation, managing over 170 developments — sprint planning, workload distribution, stakeholder communication.
- **Earlier career at Deloitte (2006–2008):** Multi-client, multi-country SAP consulting across Argentina, Mexico, and Colombia.
- **NIS National Insurance Board (Barbados, 2013–2017):** Led full SAP CRM and Social Services implementation for a national public-sector institution.

**Technical skills relevant to Heimdall:** Python, REST API development, cloud platforms (SAP BTP, Cloud Foundry), CI/CD, test automation (Mocha, Chai, Jest), data pipelines (Databricks), SQL data modelling, infrastructure (Elastic stack, Docker).

**Education:** Computer Systems Analyst (Instituto Superior del Milagro).

**Languages:** Spanish (native), English (professional).

**Entrepreneurial experience:** Building the Fjordleather brand alongside Heimdall — leather goods, separate business, shared entrepreneurial drive.

**In Denmark since 2019.** Based in Vejle.

### 13.2 What Has Already Been Built

This is not a slide deck. The product is being built:

- 14-module Python pipeline for lead generation
- 10 agent specifications with documented boundaries and handoff protocols
- Valdí legal compliance system with two-gate validation and forensic logging
- Complete legal risk assessment of Danish scanning law under §263
- Post-incident report and remediation for a compliance boundary violation
- Prospecting pipeline tested against 353 live Vejle-area domains

### 13.3 Network Security Partner

A network security specialist provides domain expertise, technical credibility, and operational support. This partnership addresses the single-founder constraint and adds professional depth for agency conversations and grant applications.

### 13.4 Claude Code as Force Multiplier

The codebase was built with Claude Code — Anthropic's AI development assistant. A solo developer with Claude Code operates at the output level of a small team for code generation, documentation, research, and specification writing. The agent specifications encode domain knowledge in a structured, transferable format — new team members onboard by reading the specifications.

### 13.5 Post-Establishment Advisory

| Role | Purpose | Status |
|------|---------|--------|
| University partner (AAU/SDU/DTU) | Research validation, grant consortium | Target for post-CVR grants |
| Legal counsel (Plesner/Kromann/Bech-Bruun) | §263 confirmation, authorization template | Planned post-establishment |
| Industriens Fond | Cybersikkerhedsprogram alignment | Research stage |
| Operations hire (part-time) | Client communication, pilot support | First hire priority |

---

## 14. Financial Projections & Self-Sustainability

### 14.1 Three Scenarios

All scenarios use the aggressive pricing. Blended ARPC: ~350 kr./month (early, Watchman-heavy mix), growing to ~420 kr./month as tier mix matures. Churn: 30–40% Year 1. Tool licensing (WPScan commercial API) included in COGS.

**Conservative (base case):**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 10 | 50 | 100 |
| MRR | 3,500 kr. | 19,000 kr. | 40,000 kr. |
| ARR | 42,000 kr. | 228,000 kr. | 480,000 kr. |
| Gross margin | ~58% | ~65% | ~68% |

Assumptions: Organic growth only. No agency partnerships beyond 1. Weighted toward Watchman tier.

**Moderate:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 20 | 80 | 200 |
| MRR | 7,000 kr. | 30,400 kr. | 84,000 kr. |
| ARR | 84,000 kr. | 364,800 kr. | 1,008,000 kr. |
| Gross margin | ~62% | ~68% | ~70% |

Assumptions: 2 agency partnerships. Tier mix shifts toward Sentinel. Local business association traction.

**Optimistic:**

| | Month 12 | Month 24 | Month 36 |
|---|---------|---------|---------|
| Active clients | 30 | 120 | 300 |
| MRR | 10,800 kr. | 48,000 kr. | 126,000 kr. |
| ARR | 129,600 kr. | 576,000 kr. | 1,512,000 kr. |
| Gross margin | ~64% | ~69% | ~72% |

Assumptions: 3+ agency partnerships. Post-CVR grant funding accelerates growth. EU pilot begins in Month 24.

### 14.2 Break-Even Analysis

| Metric | Value |
|--------|-------|
| Fixed monthly costs (infra + API + insurance + tool licensing) | ~2,800 kr. |
| Blended ARPC | ~350 kr. |
| Margin per client | ~205–245 kr. |
| **Break-even point** | **~11–12 paying clients** |

The trade-off is explicit: aggressive pricing requires ~12 clients to break even instead of 5–6 at premium pricing. But at 199 kr./mo, each conversion is significantly easier. The pipeline has identified 68 prime targets in Vejle alone — a 6× surplus over the break-even requirement.

Tool licensing costs (primarily WPScan commercial API for Sentinel/Guardian tiers) are amortised across the client base. As the client base grows, per-client licensing cost decreases.

### 14.3 Self-Sustainability

The business model is designed to be self-sustaining on subscription revenue alone. The founder has proof of financial capacity for the establishment phase as required by Startup Denmark.

The financial projections are based on subscription revenue only. They do not account for:
- **Remediation consultancy fees** — per-event revenue when clients choose Heimdall to execute fixes directly (no competitor offers this)
- **Grant funding** (NCC-DK, Digital Europe Programme, Industriens Fond) — non-dilutive growth capital, accessible post-CVR
- **Upsell revenue** from tier migration (Watchman → Sentinel → Guardian)
- **Annual Guardian discount** (599 kr./mo × 12 = cash flow advantage)

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

---

*This document was prepared in March 2026 as part of a Startup Denmark residence permit application. Financial projections are forward-looking estimates based on stated assumptions. All scanning activities described comply with Danish law as analyzed in the project's legal risk assessment — confirmation by qualified legal counsel is planned for the establishment phase.*
