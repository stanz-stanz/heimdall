<!-- CLAUDE.md v2.1 — Last updated: 2026-03-21 -->

# CLAUDE.md

MANDATORY: Before performing any task, determine which agent(s) from `docs/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.

## Before Every Task
1. Identify which agent(s) this task falls under (see `docs/agents/README.md`)
2. Read the relevant SKILL.md file(s)
3. If the task involves scanning, target selection, or client data — read `docs/agents/legal-compliance/SKILL.md` and verify compliance gates before proceeding
4. Confirm you are operating within that agent's boundaries

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses. It runs on OpenClaw, interprets findings via Claude API, and delivers plain-language results through Telegram. No client dashboard.

This repository is in the **pre-code planning phase**. All project context lives in `docs/`.

---

## Key Documents

| File | Contents |
|------|----------|
| `docs/heimdall-briefing-v2.md` | **Primary context doc — read this first.** Architecture, pilot plan, go-to-market, legal framework, Danish policy context. Single source of truth for all business and technical details. |
| `docs/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis of scanning under Straffeloven §263. Read before touching any scanning functionality. |
| `docs/agents/README.md` | Agent system overview, chain architecture, handoff protocols. |

---

## Build Priority: Phase 0 — Lead Generation Pipeline

**Build this first, on the laptop.** No dependency on the Pi or OpenClaw.

Goal: CVR register data → website URLs → CMS/tech detection → bucketed prospecting list + per-site briefs.

Steps:
1. Obtain Vejle-area company list from CVR (`https://datacvr.virk.dk`)
2. Extract website URLs
3. Batch scan with `webanalyze` or `httpx` for CMS/hosting/tech detection (Layer 1 only)
4. Bucket results: A > B > E > C > D (see `docs/agents/prospecting/SKILL.md` for full bucketing logic)
5. Filter by CVR branchekoder for GDPR-sensitive sectors
6. Generate per-site briefs
7. Output: bucketed CSV + per-site JSON briefs

---

## Do Not

- Do not create scanning functionality without reading `docs/agents/network-security/SKILL.md` and `docs/agents/legal-compliance/SKILL.md` first
- Do not run Layer 2 scanning tools against any target without verified written authorisation
- Do not write client-facing text that mentions Raspberry Pi, specific hardware, or internal infrastructure details — use abstract language ("dedicated secure infrastructure," "cloud-based AI interpretation layer")
- Do not store API keys, tokens, or secrets in any committed file
- Do not modify files in `docs/agents/` without explicit instruction — these are agent definitions, not working documents
- Do not duplicate business data (pricing, statistics, policy figures) that already exists in `docs/heimdall-briefing-v2.md` — reference the briefing instead

---

## Content and Copywriting Rules

When generating any written output for this project:

- **Pricing always in kr. (Danish kroner)**, not euros
- **Recurring example:** "restaurant with online booking system" — not "bakery owner"
- **No phrases like** "stated honestly," "full transparency," "to be honest" — confidence is implicit
- **Citations:** numbered superscripts → References section at end (not inline "Source: ..." format)
- **All scanning tool references** must include GitHub repository links
- **For policy data, statistics, and pricing details** — pull from `docs/heimdall-briefing-v2.md`, do not rely on memory

---

MANDATORY: Before performing any task, determine which agent(s) from `docs/agents/` own this task. Read their SKILL.md. Do not proceed without confirming you are operating within that agent's stated boundaries and responsibilities.
