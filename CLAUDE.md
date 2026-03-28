<!-- CLAUDE.md v2.6 — Last updated: 2026-03-24 -->

# CLAUDE.md

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

## Before Every Task
1. Identify which agent(s) this task falls under (see `.claude/agents/README.md`)
2. Read the relevant SKILL.md file(s)
3. If the task involves scanning, target selection, or client data — read `.claude/agents/valdi/SKILL.md` and `SCANNING_RULES.md` (project root), and verify compliance gates before proceeding
4. Confirm you are operating within that agent's boundaries

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses. It runs on OpenClaw, interprets findings via Claude API, and delivers plain-language results through Telegram. No client dashboard.

This repository is in **Phase 0 — Lead Generation Pipeline**, building on the laptop via Claude Code. OpenClaw and Pi infrastructure come later.

---

## Document Hierarchy

When documents conflict, this is the precedence order:

| Priority | Document | Role |
|----------|----------|------|
| 1 | `SCANNING_RULES.md` (project root) | Authoritative source for what scanning actions are allowed or forbidden at each level. All other documents defer to it on scanning legality. |
| 2 | `.claude/agents/valdi/SKILL.md` (Valdí) | Enforces SCANNING_RULES.md. Defines the validation workflow, forensic logging, approval tokens, and consent registry. |
| 3 | This file (`CLAUDE.md`) | Orchestration and general project rules. Points to the above documents for scanning constraints — does not restate them. |
| 4 | `docs/briefing.md` | Business context, strategy, architecture. Single source of truth for non-scanning project details. |

If this file says something about scanning that contradicts `SCANNING_RULES.md`, follow `SCANNING_RULES.md`.

---

## Terminology

This project uses two distinct terms for scanning classification. Do not conflate them.

**Layer** describes the *type of activity*:
- **Layer 1 (Passive):** Reading publicly served information (HTTP headers, HTML source, DNS, SSL certs, tech fingerprinting). What a normal browser visit would produce.
- **Layer 2 (Active probing):** Sending crafted requests to test for specific vulnerabilities, probing paths not linked from public pages, port scanning.
- **Layer 3 (Exploitation):** Exploiting discovered vulnerabilities. Always blocked.

**Level** describes the *consent state* of a target:
- **Level 0:** No written consent. Only Layer 1 activities are permitted.
- **Level 1:** Written consent on file. Layer 1 and Layer 2 activities are permitted within the scope of the agreement.

The rule: a scan's Layer must not exceed what the target's Level permits.

The complete definition of what is allowed and forbidden at each Layer/Level is in `SCANNING_RULES.md`. Do not rely on summaries elsewhere — read the source document.

---

## Key Documents

| File | Contents |
|------|----------|
| `docs/briefing.md` | **Primary context doc — read this first.** Architecture, pilot plan, go-to-market, legal framework, Danish policy context. Single source of truth for all business and technical details. |
| `SCANNING_RULES.md` | **Authoritative scanning constraint document.** What is allowed and forbidden at each Layer/Level. Read before writing or modifying any scanning code. |
| `.claude/agents/valdi/SKILL.md` | **Valdí — Legal Compliance Agent.** Enforces SCANNING_RULES.md. Validates scan types, manages consent registry, produces forensic logs. |
| `docs/legal/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis of scanning under Straffeloven §263. |
| `docs/legal/compliance-checklist.md` | Compliance checklist for scanning operations. |
| `.claude/agents/README.md` | Agent system overview, chain architecture, handoff protocols. |
| `docs/reference/incidents/` | Post-incident reports. Read before building any scanning functionality. |
| `docs/business/heimdall-siri-application.md` | **Startup Denmark (SIRI) application.** Business plan targeting the SIRI expert panel's four scoring criteria (Innovation, Market Potential, Scalability, Team). |
| `docs/business/siri-application-outline.md` | Outline and structure reference for the SIRI application. |
| `docs/decisions/log.md` | Decision log for project-level choices. |
| `docs/architecture/pi5-docker-architecture.md` | Pi5 Docker stack design: containers, queues, caching, resource budget, measured throughput. |
| `src/api/` | Results API + Mobile Console — FastAPI service serving scan results, pub/sub listener, console PWA (monitor dashboard + demo mode with live twin scanning) |
| `src/api/console.py` | Console API router — operator monitor, demo replay, live twin demo endpoints |
| `src/consent/validator.py` | Consent validator — Gate 2 enforcement, fail-closed on all error paths |
| `src/interpreter/` | Finding Interpreter — LLM-powered scan interpretation (Claude API / Ollama abstraction) |
| `src/composer/telegram.py` | Message Composer — Telegram formatting with 4096-char auto-splitting |
| `docs/digital-twin-use-cases.md` | Digital twin architecture, use cases, legal foundation |
| `config/synthetic_targets.json` | Config: synthetic target registry for twin consent bypass |

---

## Scanning Workflow

All scanning code must pass through Valdí before execution. The workflow is:

1. **Write or modify** a scanning function
2. **Submit to Valdí** (Gate 1) for scan-type validation against `SCANNING_RULES.md`
3. **If rejected:** Valdí logs the rejection with full reasoning. Rewrite the function. No execution.
4. **If approved:** Valdí logs the approval, generates an approval token, registers the scan type
5. **Federico reviews** Valdí's log entry and gives final go-ahead
6. **Execute** the scan, referencing the approval token

Before a scan batch runs, Valdí performs a lightweight Gate 2 check: confirming the approval token is valid and the target's consent level permits the scan type's layer.

**No scanning code executes without a valid Valdí approval token.** This applies to new code and to all existing code (which must be backfilled through Valdí before further use).

---

## Build Priority: Sprint 3 — Level 1 Pipeline

**Sprint 2 complete (Docker on Pi5). Sprint 3 in progress — consent management, interpretation pipeline, Level 1 scan types. Digital twin system shipped (Layer 2 without consent). Mobile console PWA shipped (operator monitor + live twin demo).**

Goal: consent-gated scanning for paying clients, AI-interpreted findings in Danish, Telegram delivery.

The pipeline runs as a Docker Compose stack on Pi5 with a two-phase architecture: subfinder batch enrichment (3 parallel batches) → per-domain core scans (with warm cache). Local CertStream CT database replaces remote crt.sh API. See `docs/architecture/pi5-docker-architecture.md` for full details.

### Input

Federico manually extracts a company list from CVR (`https://datacvr.virk.dk`) and saves it as `data/input/CVR-extract.xlsx`. The pipeline does **not** scrape or access datacvr.virk.dk.

### Pipeline Steps

1. Read CVR Excel export
2. Apply pre-scan filters from `config/filters.json` (industry_code, contactable) — see `.claude/agents/prospecting/SKILL.md` for filter config
3. Derive website domains from company email addresses
4. Resolve domains (check website exists + robots.txt compliance)
5. Layer 1 scanning with Valdí-approved scan types (webanalyze, httpx, subfinder, dnsx, crt.sh, GrayHatWarfare)
6. Bucket results: A > B > E > C > D (see `.claude/agents/prospecting/SKILL.md` for full bucketing logic)
7. Apply post-scan filters from `filters.json` (bucket)
8. Evidence-based GDPR sensitivity determination (from scan results + industry code)
9. Agency detection (footer credits, meta author tags)
10. Generate per-site briefs
11. WordPress domains: enrich with twin-derived Layer 2 findings (Nuclei, WPScan against local digital twin — no consent required). See `SCANNING_RULES.md` for twin framework.
12. Output: `prospects-list.csv` + per-site JSON briefs + agency briefs

### Supporting Data Files

| File | Purpose |
|------|---------|
| `data/input/CVR-extract.xlsx` | Input: manually extracted CVR company list |
| `config/filters.json` | Optional: configurable pipeline filters |
| `config/industry_codes.json` | Static: industry code → English name mapping |
| `data/output/prospects-list.csv` | Output: bucketed prospect list (only companies with live websites) |
| `data/output/briefs/{domain}.json` | Output: per-site technology briefs |
| `config/interpreter.json` | Config: LLM backend, model, tone, language settings |
| `config/consent_schema.json` | Config: consent authorisation JSON schema |
| `config/synthetic_targets.json` | Config: synthetic target registry for twin consent bypass |
| `tools/twin/slug_map.json` | Static: plugin/theme slug → version mapping for twin reconstruction |

---

## Do Not

- Do not write or run scanning code without a valid Valdí approval token — see Scanning Workflow above
- Do not scan, probe, or make any automated requests to a domain whose `robots.txt` denies automated access — hard skip, log the reason, and move on. This applies to ALL layers including Layer 1. No exceptions.
- Do not restate scanning rules from `SCANNING_RULES.md` in other documents — reference the source document instead
- Do not write client-facing text that mentions Raspberry Pi, specific hardware, or internal infrastructure details — use abstract language ("dedicated secure infrastructure," "cloud-based AI interpretation layer")
- Do not store API keys, tokens, or secrets in any committed file
- Do not modify files in `.claude/agents/` without explicit instruction — these are agent definitions, not working documents
- Do not duplicate business data (pricing, statistics, policy figures) that already exists in `docs/briefing.md` — reference the briefing instead
- Do not modify code without running `git pull` first
- Do not commit directly to `main` — create a feature branch and merge via pull request
- Do not create large monolithic commits — commit logically grouped changes separately with descriptive messages

---

## Content and Copywriting Rules

When generating any written output for this project:

- **Pricing always in kr. (Danish kroner)**, not euros
- **Recurring example:** "restaurant with online booking system" — not "bakery owner"
- **No phrases like** "stated honestly," "full transparency," "to be honest" — confidence is implicit
- **Citations:** numbered superscripts → References section at end (not inline "Source: ..." format)
- **All scanning tool references** must include GitHub repository links
- **For policy data, statistics, and pricing details** — pull from `docs/briefing.md`, do not rely on memory

---

MANDATORY: Before performing any task, determine which agent(s) from `.claude/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.
