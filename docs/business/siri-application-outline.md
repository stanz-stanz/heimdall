# Heimdall — Startup Denmark (SIRI) Application Outline

**Status:** Designed, pending writing
**Output file:** `docs/business/heimdall-siri-application.md`
**Agent ownership:** Grant & Funding Agent (`.claude/agents/grant-funding/SKILL.md`)

---

## Context

Federico Alvarez needs a Startup Denmark residence permit to establish Heimdall ApS in Denmark. He is Argentinian, currently in Denmark on a Fast-Track scheme (Senior SAP Engineer at LEGO), and wants to leave salaried employment to run a cybersecurity startup.

The Startup Denmark program is administered by the Danish Business Authority and SIRI (Styrelsen for International Rekruttering og Integration). An independent expert panel evaluates applications on four criteria, scoring each 1–5. **Minimum average score of 3.5 required for approval.**

**Format constraints:**
- Pitch deck: **10 pages maximum** (Word/PDF) or 15 pages (PowerPoint/images)
- Video pitch: **5 minutes maximum**, English, mandatory (separate deliverable)
- Application fee: DKK 3,060
- Proof of financial capacity: DKK 153,240–356,904 depending on family size

**Key constraints:**
- "Do not fabricate capabilities" — all budget figures must trace back to documented estimates in the briefing
- Unit economics included to demonstrate self-sustainability
- Pricing: Watchman 199 / Sentinel 399 / Guardian 799 kr./mo (annual: Watchman 169 / Sentinel 339 / Guardian 669 kr./mo). All prices excl. moms.
- No CVR required at application — CVR registration happens after approval

---

## SIRI Scoring Criteria (map every section to at least one)

| # | Criterion | What the Panel Evaluates |
|---|-----------|------------------------|
| C1 | **Innovation** | Novel product, service, process, or technology. Patents or proprietary methods. New market creation. |
| C2 | **Market Potential** | Market size, competition, positioning, commercial viability, revenue model. |
| C3 | **Scalability** | Growth potential, job creation in Denmark, expansion path, sustainable long-term growth. |
| C4 | **Team Competencies** | Skills, experience, entrepreneurial track record, execution capability. |

---

## Document Structure (14 Sections)

### 1. Executive Summary (1 page) — C1, C2, C3, C4

- Hook: 40% of Danish SMBs lack adequate security (Styrelsen for Samfundssikkerhed). Government allocated 211M kr. to fix it.
- The gap: every EASM tool delivers through dashboards for security teams. No one serves the restaurant owner.
- The innovation: messaging-first EASM with AI-powered interpretation — a fundamentally new delivery model.
- Business model: 199–799 kr./month subscription, "first finding free" acquisition at zero marginal cost. Watchman cheaper than every competitor's entry tier.
- Current state: working pipeline (Python, 14 modules), 10-agent architecture, Valdí compliance system, legal research complete.
- Self-sustainability: break-even at ~10 clients. Founder has financial capacity for the establishment phase.
- Why Denmark: regulatory alignment, grant ecosystem (post-CVR), GDPR-first strategy, existing local presence.
- This application is for a Startup Denmark residence permit to establish Heimdall ApS.

### 2. The Problem (1–1.5 pages) — C2

- 40% statistic (sourced)
- GDPR Article 32 compliance obligation — SMBs are non-compliant by default
- NIS2 expanding scope
- Real-world scenario: restaurant with online booking system on outdated WordPress on shared hosting
- The dashboard gap: Qualys "interactive customizable widgets" vs. what a restaurant owner will actually use
- The "who do I send this to?" problem — findings without routing are useless

### 3. The Solution (1.5 pages) — C1, C2

- Conversational delivery via Telegram/WhatsApp — plain language (Danish for Denmark pilot), not jargon
- Persistent memory + escalating follow-up (1wk/2wk/3wk)
- "First Finding Free" — Layer 1 scan produces real findings at zero cost
- Mock Telegram message example (from Message Composer SKILL.md)
- Tier differentiation: Watchman tells what's wrong, Sentinel adds how to fix it (written report), Guardian adds priority scanning cadence + dedicated support
- Frame as: "This delivery model represents a fundamentally new approach — no existing product operates this way"

### 4. How It Works (1 page) — C1

- Pipeline flow: CVR → domain → robots.txt → Layer 1 scan → bucket → brief
- 10-agent chain architecture (diagram)
- Valdí two-gate compliance system with forensic logging + approval tokens
- Layer/Level framework explained simply
- The incident: Layer 2 code in Layer 1 pipeline → caught by human review → Valdí built as a result. Frame as governance maturity.

### 5. Innovation (1 page) — C1 **[NEW]**

Directly addresses SIRI Criterion 1. Synthesize from existing sections:

- **Messaging-first EASM delivery:** No competitor delivers findings through messaging apps to non-technical users. The entire product architecture is built around conversational delivery — not a notification bolted onto a dashboard.
- **Persistent memory architecture:** Longitudinal client knowledge as a product feature — the agent remembers what it told the client, what changed, and what was fixed.
- **Programmatic legal compliance (Valdí):** Novel approach to automated scanning governance with two-gate validation, forensic logging, and approval tokens.
- **AI-powered interpretation chain:** Open-source tools produce findings; Claude API interprets them in plain language for non-technical users. The LLM never decides what is vulnerable — it explains what the tools found.
- Frame: "These are not incremental improvements to existing products. They represent a fundamentally different approach to delivering cybersecurity to non-technical users."

### 6. Market Opportunity (1 page) — C2

- TAM/SAM/SOM calculations (same data)
- Regulatory tailwinds table (211M kr. government allocation, NCC-DK 43M kr. budget as market signal, NIS2, EU programmes)
- Reframe: Danish/EU grant ecosystem as non-dilutive growth capital accessible post-CVR
- Expansion path: Denmark → EU (GDPR framework translates, messaging delivery is language-agnostic)
- SOM is conservative; upside depends on agency partnerships and post-CVR grant funding

### 7. Business Model & Unit Economics (1 page) — C2

- Pricing tiers: Watchman 199 / Sentinel 399 / Guardian 799 kr./mo (annual: 169 / 339 / 669)
- Unit economics per client (monthly): revenue ~305 kr. blended, COGS ~95–125, gross margin ~59–69%
- Acquisition economics: Layer 1 scan = near-zero cost; agency partnerships = high leverage
- Break-even: ~13–14 paying clients
- Frame: "199 kr./mo eliminates price as an objection. Volume compensates for margin."

### 8. Go-to-Market Strategy (1 page) — C2, C3

- Constraint as advantage: Markedsføringsloven prohibits cold email → forces high-trust in-person model
- Five phases (Vejle pilot → agency partnerships → local networks → geographic expansion → EU)
- At each phase, note job creation implications

### 9. Scalability & Job Creation in Denmark (1 page) — C3 **[NEW]**

Directly addresses SIRI Criterion 3.

- Infrastructure scaling stages table (abstracted — no Pi details in client-facing language)
- **Job creation timeline:**

| Timeline | Headcount | Roles | Location |
|----------|-----------|-------|----------|
| Year 1 (establishment) | 1 (founder) | Development, sales, operations | Vejle |
| Year 1–2 | 2–3 | Part-time operations hire, network security partner formalized | Vejle |
| Year 2–3 | 4–6 | Client success manager, junior developer, sales/BD | Vejle/Aarhus |
| Year 3+ | 6–10 | Security analysts, EU expansion team | Denmark |

- Danish economic contribution: tax revenue, supporting SMB resilience, grant funding staying in Denmark
- Scalability argument: same architecture at every scale; Denmark-first then EU; messaging delivery language-agnostic

### 10. Competitive Landscape (1 page) — C2

- Comparison table: Heimdall vs Intruder.io vs Detectify vs HostedScan vs Sucuri
- Counter: "Why can't Intruder just add Telegram?" → Architecture argument
- Counter: "HostedScan is free" → Dashboard vs. messaging for non-technical users
- Four durable differentiators: messaging-first, digital twin, persistent memory, tiered fix guidance (Sentinel/Guardian written reports)

### 11. Regulatory & Legal Framework (0.5 pages) — C2

- §263 analysis: Layer 1 minimal risk, Layer 2 gray zone → consent model
- GDPR Art. 32 as compliance driver for clients
- Markedsføringsloven as outreach constraint → reframed as advantage
- Valdí as demonstrable due diligence
- Open questions for legal counsel (engagement planned post-establishment)

### 12. Why Denmark (1 page) — C1, C2, C3, C4 **[NEW]**

Mandatory for Startup Denmark. Explains why Denmark is the right place to build this business:

- **Regulatory alignment:** Denmark's 211M kr. cybersecurity investment creates the market. Government policy explicitly targets SMBs. Heimdall serves this policy-created demand.
- **Grant ecosystem (post-CVR):** Denmark's cybersecurity grant landscape (NCC-DK 43M kr. 2026–2029, Digital Europe Programme up to €60K/SME, Industriens Fond, EU SECURE Project) becomes accessible once Heimdall has a CVR via Startup Denmark approval.
- **GDPR-first strategy:** Building in Denmark means building for the strictest data protection regime. The compliance framework translates to all 27 EU member states.
- **SMB density:** 200,000+ Danish SMBs with websites. High digital adoption + high regulatory requirements = ideal first market.
- **Danish marketing law as moat:** Markedsføringsloven forces high-trust local acquisition. This rewards physical presence in Denmark and creates a barrier to remote-first competitors.
- **Founder's existing presence:** Already in Vejle since 2019, embedded in Danish business environment, tested the pipeline against 203 local domains.
- **Talent and partnerships:** Danish universities (AAU, SDU, DTU) as research and consortium partners. Strong tech ecosystem.

### 13. Team & Execution Capability (1.5 pages) — C4

Directly addresses SIRI Criterion 4.

- **Federico Alvarez — Founder:**
  - ~20 years enterprise software engineering (SAP ecosystem)
  - Currently Senior SAP Engineer at LEGO (Fast-Track scheme, since 2023)
  - Prior: JYSK, LEGO (via Hays), Medtronic (via IBM), Deloitte — across Denmark, USA, Mexico, Barbados, Colombia, Argentina
  - Led team of ~30 SAP CRM consultants at Grupo Bancolombia (via Deloitte), managing 170+ developments
  - Technical: Python, REST APIs, cloud platforms (SAP BTP, Cloud Foundry), CI/CD, test automation, data pipelines (Databricks)
  - Built Heimdall's entire codebase: 14-module Python pipeline, 10 agent specifications, Valdí compliance system, legal risk assessment, 203-domain test run
  - Entrepreneurial: Fjordleather brand (leather goods — separate business)
  - Education: Computer Systems Analyst
  - Languages: Spanish (native), English (professional)
  - In Denmark since 2019 (7 years by application date), based in Vejle

- **What has already been built** ("This is not a slide deck"):
  - 14-module Python pipeline for lead generation
  - 10 agent specifications with documented boundaries and handoff protocols
  - Valdí legal compliance system with two-gate validation and forensic logging
  - Complete legal risk assessment of Danish scanning law under §263
  - Post-incident report and remediation for a compliance boundary violation
  - Prospecting pipeline tested against 203 live Vejle-area domains

- **Network security partner:** Domain expertise, technical credibility, operational support
- **Claude Code as force multiplier:** Solo developer with AI tooling operates at output level of a small team
- **Post-establishment advisory:** University partners (consortium), legal counsel, Industriens Fond alignment

### 14. Financial Projections & Self-Sustainability (1.5 pages) — C2, C3

- Three scenarios: Conservative (10→50→100), Moderate (20→80→200), Optimistic (30→120→300)
- Break-even analysis: 5–6 clients covers operating costs
- **Self-sustainability statement:** Business reaches break-even at 5–6 clients. Founder has proof of financial capacity for establishment phase (DKK amount per SIRI requirements).
- **Post-CVR funding path:** Denmark's grant ecosystem (Digital Europe Programme, Industriens Fond, and others) becomes accessible with a CVR. These are non-dilutive growth capital — the business does not depend on them to survive.
- Projections demonstrate the business can sustain itself and grow on subscription revenue alone.

### References

Numbered superscript citations throughout → references section at end, sourced from `docs/briefing.md` (lines 401–431) plus market data. Add Startup Denmark programme reference.

---

## Content Rules

- All pricing in kr. (Danish kroner)
- Recurring example: "restaurant with online booking system"
- No phrases like "stated honestly," "full transparency," "to be honest"
- Scanning tool references include GitHub repository links
- No Pi/hardware details in client-facing language — use "dedicated secure infrastructure"
- Incident framed as governance maturity, not failure
- Self-contained document — include data, don't just reference the briefing
- Tone: realistic, confident, and specific — not pitch-deck hype
- Every section explicitly maps to at least one SIRI criterion
- No investor-addressing language ("an investor should...", "the question for an investor is...")
- 10-page target for PDF output — be concise

## Source Files

| File | Use |
|------|-----|
| `docs/briefing.md` | All business data, pricing, stats, references |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Legal framework content |
| `.claude/agents/grant-funding/SKILL.md` | Agent boundaries |
| `docs/reference/incidents/incident-2026-03-22-layer2-violation.md` | Incident framing |
| `SCANNING_RULES.md` | Layer/Level definitions (reference, don't restate) |
| Federico's resume (`canonical.yaml`) | Team section biographical data |

## Anticipated Panel Questions (Pre-Addressed in Document)

1. "What is innovative about this?" → Innovation section: messaging-first delivery, digital twin, persistent memory, Valdí, AI interpretation chain
2. "Can this scale beyond Denmark?" → Scalability section: GDPR framework translates, messaging is language-agnostic, Denmark-first is strategic
3. "Why must this be built in Denmark?" → Why Denmark section: regulatory alignment, grant ecosystem, GDPR-first, existing presence, local market
4. "How will this create jobs in Denmark?" → Scalability section: hiring timeline from 1 to 10 employees over 3 years
5. "What is your competitive advantage?" → Competitive Landscape + Innovation: three durable differentiators, no competitor serves non-technical SMBs via messaging
6. "Can you sustain yourself financially?" → Financial Projections: break-even at 5–6 clients, proof of financial capacity, post-CVR grant access
7. "Why are you the right person to build this?" → Team section: 20 years engineering, team leadership, 7 years in Denmark, working prototype already built

## Video Pitch Outline (separate deliverable)

Structure for the mandatory 5-minute video:

- **0:00–0:30** — Hook: the 40% problem, the dashboard gap
- **0:30–1:30** — The product: demo or walkthrough of a Telegram finding message
- **1:30–2:30** — Innovation: messaging-first, digital twin, persistent memory, Valdí
- **2:30–3:30** — Market & Scalability: Denmark first, EU expansion, job creation timeline
- **3:30–4:15** — Why Denmark: regulatory alignment, grant ecosystem, local market
- **4:15–4:45** — Team: Federico's background, what is already built, execution proof
- **4:45–5:00** — Close: summary of four criteria, vision

*Video script is a separate deliverable — not part of this document.*
