# Heimdall Angel Investor Business Plan — Outline

**Status:** Designed, pending writing
**Output file:** `docs/heimdall-investor-plan.md`
**Agent ownership:** Grant & Funding Agent (`docs/agents/grant-funding/SKILL.md`)

---

## Context

Federico needs a comprehensive post-pilot business plan targeting angel investors. The document must make a realistic, transparent case for Heimdall's viability — covering the full rollout from pilot to public product, hardware scaling, marketing, risks, and financials. The audience is a skeptical angel investor who needs to be convinced, not sold to.

**Key constraints:**
- "Do not fabricate capabilities" — all budget figures must trace back to documented estimates in the briefing
- Unit economics included (user override of briefing line 395)
- Pricing: Watchman 499 / Sentinel 799 / Guardian 1,199 kr./mo (briefing line 394 correction)

---

## Document Structure (15 Sections)

### 1. Executive Summary (1 page)

- Hook: 40% of Danish SMBs lack adequate security (Styrelsen for Samfundssikkerhed). Government just allocated 211M kr. to fix it.
- The gap: every EASM tool delivers through dashboards for security teams. No one serves the restaurant owner.
- Business model: 499–1,199 kr./month subscription, "first finding free" acquisition at zero marginal cost.
- Current state: working pipeline (Python, 14 modules), 10-agent architecture, Valdí compliance system, legal research complete.
- The ask: 150,000–250,000 kr. for legal confirmation, pilot execution, first revenue, grant consortium.
- Timing: NCC-DK 5.5M kr. grant deadline April 15, 2026.

### 2. The Problem (1–1.5 pages)

- 40% statistic (sourced)
- GDPR Article 32 compliance obligation — SMBs are non-compliant by default
- NIS2 expanding scope
- Real-world scenario: restaurant with online booking system on outdated WordPress on shared hosting
- The dashboard gap: Qualys "interactive customizable widgets" vs. what a restaurant owner will actually use
- The "who do I send this to?" problem — findings without routing are useless

### 3. The Solution (1.5 pages)

- Conversational delivery via Telegram/WhatsApp — plain Danish, not jargon
- Persistent memory + escalating follow-up (1wk/2wk/3wk)
- Shadow AI/agent detection (21,000 exposed OpenClaw instances, no competitor does this)
- "First Finding Free" — Layer 1 scan produces real findings at zero cost
- Mock Telegram message example (from Message Composer SKILL.md)
- Tier logic: Watchman tells what, Sentinel tells how, Guardian tests and verifies

### 4. How It Works (1.5 pages)

- Pipeline flow: CVR → domain → robots.txt → Layer 1 scan → bucket → brief
- 10-agent chain architecture (diagram)
- Valdí two-gate compliance system with forensic logging + approval tokens
- Layer/Level framework explained simply
- The incident: Layer 2 code in Layer 1 pipeline → caught by human review → Valdí built as a result. Frame as strength: mature governance.

### 5. Market Opportunity (1.5 pages)

- TAM: ~200,000 Danish SMBs with websites × 650 kr./mo blended × 12 = ~1.56B kr./yr (theoretical max, clearly labeled)
- SAM: ~80,000 (apply 40% gap) × 650 × 12 = ~624M kr./yr
- SOM: 200 clients in 36 months = 1.56M kr./yr (conservative, honest)
- Regulatory tailwinds: 211M kr. govt allocation, SMV-CERT, NCC-DK grants (43M kr. 2026–2029), Industriens Fond, EU Digital Europe Programme
- Be transparent: SOM is conservative. The upside is if the model proves repeatable + grant funding accelerates.

### 6. Business Model & Unit Economics (2 pages)

- Pricing tiers: Watchman 499 / Sentinel 799 / Guardian 1,199 kr./mo
- Unit economics per client (monthly):
  - Revenue: ~650 kr. (blended)
  - Claude API: ~75 kr.
  - Infrastructure: ~15–30 kr. (at scale)
  - Insurance allocation: ~30–45 kr.
  - COGS: ~120–150 kr. → Gross margin: ~77–82%
- Acquisition economics: Layer 1 scan = near-zero cost. Agency partnerships = 1 relationship → 10–35 clients.
- Churn: 30–40% Y1, 20–25% Y2+ (honest — mitigated by persistent memory, compliance value, agency relationships)
- Break-even: ~5–6 paying clients

### 7. Go-to-Market Strategy (1.5 pages)

- Constraint as advantage: Danish marketing law (Markedsføringsloven) prohibits cold email → forces high-trust in-person model
- Phase 1 (Month 1–3): Vejle pilot, 5 clients, in-person "first finding free"
- Phase 2 (Month 3–6): Agency partnerships — "I scanned 35 of your client sites. 22 have issues. Your name is on the footer."
- Phase 3 (Month 6–12): Local business associations (Erhvervsforeninger), referrals, speaking events
- Phase 4 (Month 12–24): Geographic expansion — Aarhus, Odense, Aalborg
- Phase 5 (Month 24–36+): EU expansion — GDPR framework translates directly, messaging delivery is language-agnostic

### 8. Competitive Landscape (1.5 pages)

- Comparison table: Heimdall vs Intruder.io vs Detectify vs HostedScan vs Sucuri
- Counter: "Why can't Intruder just add Telegram?" → Delivery isn't a feature, it's the architecture. Rebuilding for non-technical users means rebuilding the product.
- Counter: "HostedScan is free" → True. If the owner can use a dashboard, HostedScan wins. Most cannot.
- Persistent memory as switching cost
- Shadow AI detection as first-mover position
- Enterprise players (CrowdStrike, Qualys) moving upmarket, not down

### 9. Infrastructure & Scaling Plan (1 page)

| Stage | Clients | Infra | Monthly Cost |
|-------|---------|-------|-------------|
| Phase 0 (now) | 0 | Laptop | 0 kr. |
| Pilot | 5–10 | Pi 5 + Tailscale | 175–560 kr. |
| Early prod | 10–50 | VPS + Docker | 350–700 kr. |
| Scale | 50–200 | Multi-container VPS | 700–2,100 kr. |
| Growth | 200+ | Multi-node cloud | 2,100–7,000 kr. |

- Same OpenClaw skill architecture at every tier
- Cost per client decreases: 112 kr. (5 clients) → 14 kr. (50) → 35 kr. (200+)
- Pi is pilot-only. Client-facing language: "dedicated secure infrastructure"

### 10. Risk Analysis & Mitigations (2 pages)

Seven risks, each with probability, impact, mitigation:
1. LLM hallucination — tools produce findings, LLM only interprets; human-in-the-loop for pilot; confidence scoring
2. Legal gray zone (§263) — Valdí system, forensic logs, legal counsel engagement funded as milestone
3. Solo founder — network security partner, Claude Code as force multiplier, knowledge encoded in SKILL.md files
4. Customer churn — persistent memory as switching cost, agency partnerships, compliance value
5. Competitive response — delivery model requires full product rebuild, not a feature; local relationships as moat
6. Danish market size — Denmark-first = GDPR-first; framework translates to EU; 200 clients is viable domestically
7. Shadow AI detection commoditization — one of three differentiators, not the only one

### 11. Regulatory & Legal Framework (1 page)

- §263 analysis: Layer 1 minimal risk, Layer 2 gray zone → consent model
- GDPR Art. 32 as compliance driver for clients
- Markedsføringsloven as outreach constraint → reframed as advantage
- Valdí as demonstrable due diligence
- Open questions for counsel (documented, engagement is funded milestone)

### 12. Team & Execution Capability (1 page)

- Federico: Vejle-based, technical (Claude Code, React, self-hosted infra), built entire codebase in days
- Network security partner: domain expertise, credibility
- Claude Code as force multiplier: 10 agent specs, 14 Python modules, legal research, compliance system — one developer
- Advisory targets: university (AAU/SDU/DTU) for grant consortium, legal counsel, Industriens Fond

### 13. Financial Projections (2 pages)

Three scenarios:

**Conservative (10 → 50 → 100 clients):**

| | M12 | M24 | M36 |
|---|---|---|---|
| Clients | 10 | 50 | 100 |
| MRR | 6,500 | 32,500 | 65,000 |
| ARR | 78,000 | 390,000 | 780,000 |
| Gross margin | ~73% | ~81% | ~83% |

**Moderate (20 → 80 → 200):** ARR at M36 = 1,560,000 kr.

**Optimistic (30 → 120 → 300):** ARR at M36 = 2,340,000 kr. (assumes 2+ agency partnerships + grant)

Break-even: ~5–6 clients. Pilot budget (12,000 kr.) covers 3–4 months pre-revenue.

### 14. The Ask (1 page)

Amount: 150,000–250,000 kr. (deliberately modest)

| Use | Amount |
|-----|--------|
| Legal counsel (§263 + consent template) | 15,000–25,000 kr. |
| Insurance (year 1) | 5,500 kr. |
| Pilot hardware | 2,500 kr. |
| Claude API (6 months) | 4,500 kr. |
| Domain + marketing materials | 3,000 kr. |
| Founder runway (3–6 months part-time) | 60,000–120,000 kr. |
| VPS migration | 10,000 kr. |
| Grant consortium costs | 20,000 kr. |
| Contingency | 20,000–40,000 kr. |

Milestones funded:
- M1–2: Legal confirmation + authorization template
- M2: Pilot launch (5 clients, Vejle)
- M3: Pilot validation data
- M3–4: First paying clients
- Before April 15: NCC-DK grant application
- M4–6: First agency partnership
- M6: Break-even (10 clients)
- M12: 20 paying clients

### 15. Why Now? (1 page)

Five converging forces:
1. Government spending starts 2026 (211M kr.)
2. NCC-DK grant deadline April 15 (5.5M kr. pool)
3. NIS2 compliance pressure mounting
4. Shadow AI attack surface exploding (21,000 exposed instances)
5. Dashboard delivery gap still open — no one has built messaging-first EASM

### References

Numbered superscript citations throughout → references section at end, sourced from `docs/heimdall-briefing.md` (lines 401–431) plus market data.

---

## Content Rules

- All pricing in kr. (Danish kroner)
- Recurring example: "restaurant with online booking system"
- No phrases like "stated honestly," "full transparency," "to be honest"
- Scanning tool references include GitHub repository links
- Pi details included (investor doc) but clearly marked pilot-only
- Incident framed as governance strength, not failure
- Self-contained document — include data, don't just reference the briefing
- Tone: realistic and transparent, not pitch-deck hype

## Source Files

| File | Use |
|------|-----|
| `docs/heimdall-briefing.md` | All business data, pricing, stats, references |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Legal framework content |
| `docs/agents/grant-funding/SKILL.md` | Agent boundaries |
| `docs/reference/incidents/incident-2026-03-22-layer2-violation.md` | Incident framing |
| `SCANNING_RULES.md` | Layer/Level definitions (reference, don't restate) |

## Anticipated Investor Objections (Pre-Countered in Document)

1. "This is just a Telegram bot wrapper" → Architecture argument
2. "Danish market is tiny" → Denmark-first = GDPR-first; EU expansion path
3. "Solo founder risk" → Network partner + Claude Code as force multiplier
4. "LLM hallucination" → Tools produce findings, LLM only interprets
5. "Why can't Intruder add Telegram?" → Delivery model requires full rebuild
6. "HostedScan is free" → If the owner can use a dashboard, HostedScan wins. Most cannot.
7. "Shadow AI is a fad" → One of three differentiators, not the only one
