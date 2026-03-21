# CLAUDE.md

MANDATORY: Before performing any task, identify which agent(s) from docs/agents/ are relevant. Read the corresponding SKILL.md file(s) BEFORE writing any code or taking any action.

## Before Every Task
1. Identify which agent(s) this task falls under (see docs/agents/README.md)
2. Read the relevant SKILL.md file(s)
3. Check if Legal Compliance gate applies
4. Confirm you are operating within that agent's boundaries

---

## What This Repository Is

Heimdall is an External Attack Surface Management (EASM) service for small businesses. It runs on OpenClaw (open-source AI agent framework), continuously monitors the public-facing digital surface of client websites, interprets findings via Claude API, and delivers plain-language results through Telegram — no client dashboard.

This repository is in the **pre-code planning phase**. Context lives in `docs/`.

---

## Key Documents

| File | Contents |
|------|----------|
| `docs/heimdall-briefing-v2.md` | **Primary context doc — read this first.** Architecture, pilot plan, go-to-market, Danish policy context, corrections to apply to business case. Single source of truth. |
| `docs/business-case-v2.docx` | Business case v2. Reference only. |
| `docs/Heimdall_Legal_Risk_Assessment.md` | Danish legal analysis of scanning under Straffeloven §263. Read before touching any scanning functionality. |
| `docs/OpenClaw_RPi5_Autonomous_Profit_Research.md` | Original autonomous profit scenario research — background context. |

---

## Architecture

### Stack

- **OpenClaw** — runs on the Pi as gateway/orchestrator. Handles: Heartbeat engine (cron scheduling), Telegram bot, persistent memory per client, shell execution for scan tools. LLM inference does NOT run on the Pi.
- **Claude API (Sonnet)** — cloud-side. Handles: finding interpretation, plain-language explanation, remediation guidance, report generation, conversational responses.
- **Telegram Bot** — client-facing delivery channel. No dashboard, no portal.

### Scanning Tools (all on ARM64)

Nuclei, Nikto, Nmap, SSLyze, testssl.sh, WPScan, Subfinder, httpx, webanalyze — see briefing v2 for GitHub links.

### Pilot vs. Production

**Pilot:** Raspberry Pi 5, 8GB RAM, NVMe SSD, Raspberry Pi OS Lite, Tailscale VPN (zero inbound ports).

**Production path:** VPS/cloud (Hetzner/DigitalOcean), Docker containerization, same OpenClaw skill architecture on a different substrate.

**Do not mention Raspberry Pi in any client-facing content.** External audiences see: "Dedicated secure infrastructure with encrypted communications" / "Cloud-based AI interpretation layer." The Pi is a pilot implementation detail.

---

## Service Tiers (Pricing in Danish Kroner)

| Tier | Price | Pilot Status |
|------|-------|-------------|
| Watchman | 215 kr./month | **Only tier built for the pilot** |
| Sentinel | 590 kr./month | Not built yet |
| Guardian | 1.480 kr./month | Not built yet |

---

## Build Priority: Phase 0 — Lead Generation Pipeline

**Build this first, on the laptop.** No dependency on the Pi or OpenClaw.

Goal: CVR register data → website URLs → CMS/tech detection → bucketed prospecting list + per-site briefs.

Steps:
1. Obtain Vejle-area company list from CVR (`https://datacvr.virk.dk`)
2. Extract website URLs
3. Batch scan with `webanalyze` or `httpx` for CMS/hosting/tech detection (Layer 1 — passive, legally safe)
4. Bucket results: A (WordPress on shared hosting) > B (other self-hosted CMS) > E (custom/unidentifiable) > C (Shopify/Squarespace/Wix) > D (no website — skip)
5. Second dimension: filter by CVR branchekoder for GDPR-sensitive sectors (healthcare, legal, accounting, dental, real estate)
6. Generate per-site brief: CMS, hosting, SSL status, detected plugins, risk profile
7. Output: bucketed CSV + per-site briefs

---

## Legal Constraints — Non-Negotiable

**Layer 1 (passive):** Reading HTTP headers, HTML source, meta tags, DNS records, SSL certs. Safe — this is what any browser does. Legal for lead generation.

**Layer 2 (active probing):** Nuclei, Nikto, Nmap sending crafted requests. Requires **written client authorization** before running against any target. The Danish Penal Code (§263) is broad enough to cover unauthorized active probing.

**Layer 3 (exploitation):** Out of scope entirely — clearly criminal without consent.

The business model is already structured correctly: the "first finding free" prospecting uses only Layer 1 data; paid scanning activates Layer 2 only after onboarding and signed authorization.

---

## Content and Copywriting Rules

When generating any written output for this project:

- **Pricing always in kr. (Danish kroner)**, not euros
- **Recurring example:** "restaurant with online booking system" — not "bakery owner"
- **No Raspberry Pi in client-facing text** — use abstract infrastructure language
- **No phrases like** "stated honestly," "full transparency," "to be honest" — confidence is implicit
- **Citations:** numbered superscripts → References section at end (not inline "Source: ..." format)
- **Target customer includes** businesses with endpoint security (CrowdStrike etc.) — endpoint security and EASM are complementary, not overlapping
- **All scanning tool references** should include GitHub repository links

---

## Danish Policy Context (Sales and Grant Applications)

- Danish cybersecurity strategy 2026–2029: **211M kr. allocated**, cross-party agreement, includes SMV-CERT (new CERT specifically for SMBs)
- **40% of Danish SMBs** lack adequate security (Styrelsen for Samfundssikkerhed)
- **NCC-DK grant pool:** 5.5M kr. open now, deadline April 15, 2026. Minimum 2 consortium partners (1 private company). Fits Heimdall directly.
- Sales framing: "The Danish government just allocated 211 million kroner because businesses like yours are the ones getting attacked."

Full reference list with numbered sources is in `docs/heimdall-briefing-v2.md`.

---

## Generating the Business Case v2.0

When asked to produce the final Heimdall Business Case — apply all corrections listed in the "Instructions for Claude Code" section of `docs/heimdall-briefing-v2.md`. Key changes from v1: add EASM definition, remove Pi from client-facing sections, revise target customer scope, switch to superscript citations, add Danish cybersecurity policy section, add legal framework section, use kr. pricing, use numbered references from the briefing.

MANDATORY: Before performing any task, identify which agent(s) from docs/agents/ are relevant. Read the corresponding SKILL.md file(s) BEFORE writing any code or taking any action.
