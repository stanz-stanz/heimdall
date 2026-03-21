# Heimdall — Project Briefing

**Context document for Claude Code sessions. Drop this in `docs/heimdall-briefing.md`.**
**Last updated: March 21, 2026**

---

## What Is Heimdall

Heimdall is a cybersecurity monitoring service for small businesses. It runs on OpenClaw (open-source AI agent framework) on a Raspberry Pi 5. It continuously scans the external attack surface of client websites, interprets findings in plain language via Claude API, and delivers them through Telegram conversations. Named after the Norse god who never sleeps and sees all threats approaching.

## The Owner

Federico, based in Vejle, Denmark. Building this alongside the Fjordleather brand. Technical background: Claude Code, React/TSX, self-hosted infrastructure, Raspberry Pi experience. Not a cybersecurity specialist — partnering with a network security specialist for domain expertise.

---

## Key Strategic Decisions Made

### Target Customer
- Small businesses (under 50 employees) with a website that handles customer data
- No existing IT security staff or MSSP relationship
- Initially Denmark, expanding to Nordics
- NOT businesses with CrowdStrike or similar endpoint security — Heimdall protects the website, not devices. Different product category entirely.

### Closest Competitor
**Intruder.io** (https://www.intruder.io) — $99/month, web dashboard, Slack alerts, 1000+ customers, GCHQ Cyber Accelerator alumni. Strong product. The space is NOT empty.

Other competitors: HostedScan, Detectify, Beagle Security, Astra Security, Sucuri.

### Three Differentiators
1. **Conversational delivery via Telegram/WhatsApp** — no dashboard, no portal. Findings arrive as plain-language messages in the app the business owner already uses.
2. **Persistent memory + active follow-up** — the agent remembers each client's tech stack, past findings, and remediation state. It nags about unresolved issues.
3. **Shadow AI infrastructure detection** — scanning for exposed OpenClaw instances, MCP servers, rogue AI agents. Niche today, growing fast. No SMB competitor does this yet.

### Pricing (Pilot: Tier 1 only)
- **Watchman: €29/month per domain** — weekly scan, plain-language Telegram findings, trend tracking
- Tier 2 (Sentinel, €79) and Tier 3 (Guardian, €199) exist in the business case but are NOT built for the pilot

### Go-to-Market
- **Lead generation via public CVR register** — scan all registered businesses in Vejle area, bucket by CMS/hosting, approach WordPress-on-shared-hosting businesses first
- **"First finding free" model** — show the business owner a real vulnerability on their site before asking for money
- **Physical letters** to pre-qualified leads with real, specific findings (GDPR compliant — publicly accessible websites)
- **Agency pitch via their exposure** — scan all sites built by a local agency, show them their clients are exposed, they become white-label partners
- **CVR industry codes** allow filtering for GDPR-sensitive sectors (clinics, law firms, accountants) for higher-value leads

---

## Architecture

### Hardware
- Raspberry Pi 5, 8GB RAM
- NVMe SSD via HAT (required for 24/7 reliability)
- Official 27W PSU
- Active cooler
- Tailscale VPN for remote access (no inbound ports)

### Scanning Tools (all run on ARM64 Pi 5)
- **Nuclei** — template-based vulnerability scanner (Go)
- **Nikto** — web server scanner (Perl)
- **Nmap** — port scanning (C)
- **SSLyze / testssl.sh** — TLS/SSL analysis
- **WPScan** — WordPress-specific (Ruby)
- **Subfinder** — subdomain enumeration (Go)
- **httpx** — HTTP probing + tech fingerprinting (Go)
- **webanalyze** — Wappalyzer Go port for batch CMS detection

### LLM Layer
- Claude API (Sonnet for scan interpretation)
- ~$50/month estimated at pilot scale
- Handles: finding interpretation, plain-language explanation, remediation guidance, report generation, conversational responses

### OpenClaw Role
- Gateway/orchestrator (LLM runs in cloud, not on Pi)
- Heartbeat engine for cron-scheduled scans
- Persistent memory per client
- Telegram bot integration
- Shell execution for scan tools

---

## Pilot Plan

### Budget: ~$1,000 (7,000 DKK)
- NVMe HAT + SSD: ~$45
- PSU + cooler (if needed): ~$25
- Claude API (3 months): ~$150
- Domain + landing page: ~$30
- Professional indemnity insurance: ~$500-700/year
- Contingency: ~$50-100

### Phase 0: Lead Generation Pipeline (BUILD FIRST, on laptop via Claude Code)
1. Obtain Vejle-area company list from CVR (https://datacvr.virk.dk)
2. Extract website URLs from register
3. Batch scan with `webanalyze` or `httpx` for CMS/hosting/tech detection
4. Auto-bucket results:
   - **Bucket A (HIGHEST):** Self-hosted WordPress on shared hosting
   - **Bucket B (HIGH):** Self-hosted other CMS (Joomla, Drupal, PrestaShop)
   - **Bucket C (LOWER):** Shopify / Squarespace / Wix (platform handles most security)
   - **Bucket D (SKIP):** No website / parked domain
   - **Bucket E (MEDIUM):** Custom-built / unidentifiable
5. Second dimension: filter by CVR industry code for GDPR-sensitive businesses
6. Generate per-site brief (3-4 lines: CMS, hosting, SSL status, plugins, risk level)
7. Output: CSV + per-site briefs = prospecting list + sales ammunition + pilot onboarding seed

### Phase 1: Week 1-2 — Build & Test
- Configure Pi with OpenClaw + all scanning tools
- Write core OpenClaw skill: scan orchestration → Claude interpretation → Telegram delivery
- Test on own domains (fjordleather.dk as first target)
- Human-in-the-loop: Federico reviews every message before it sends

### Phase 2: Week 2-3 — Recruit Pilot Clients
- 5 businesses from Bucket A leads
- Free first month
- "First finding free" approach using pre-scanned data
- Physical letter option for high-value leads

### Phase 3: Week 3-4 — Run & Learn
- First scan cycle across all 5 clients
- Manual review of every outgoing message
- Second scan cycle — test follow-up/memory model
- End-of-pilot conversation with each client: Did you read it? Did you understand? Did you act? Would you pay €29?

---

## Critical Open Questions

### Must Validate in Pilot
- Will non-technical business owners read and act on Telegram security messages?
- Can Claude consistently produce accurate, environment-specific remediation guidance? (Known risk: false specificity — plausible but wrong advice for the specific setup)
- Does the follow-up/nag model create value or annoyance?
- Will web agencies adopt white-label at proposed price points?

### Known Risks
- Claude may generate remediation instructions that sound precise but don't match the client's actual environment (e.g., "edit functions.php" when jQuery is loaded by a plugin)
- Mitigation: split messages into "what's wrong" (Claude does well) and "how to fix" (bounded to generic guidance + links to authoritative sources)
- Every message goes through Federico during pilot — human QA gate
- Disclaimer notice required on all findings

### The "Who Do I Send This To?" Problem
When client has no IT person, Heimdall handles it per scenario:
- **Has a web developer:** message designed to be forwarded directly
- **Self-manages WordPress:** step-by-step wp-admin instructions
- **Fully hosted (Shopify/Squarespace):** platform-specific settings or drafted support ticket
- **Nobody manages it:** draft hosting provider support ticket + curated freelancer referral list
- Every finding ends with a clear "who should fix this" line

---

## Documents Produced

1. **OpenClaw_RPi5_Autonomous_Profit_Research.md** — initial research on OpenClaw + Pi 5 profit scenarios (7 scenarios evaluated)
2. **Heimdall_Business_Case_v2.md** — full business case with competitive landscape, sourced statistics, glossary, risk analysis. Board-ready document.
3. **This briefing** — condensed context for Claude Code sessions

---

## What's Next

1. **Build the lead-gen pipeline in Claude Code** — CVR data → URL extraction → batch CMS detection → bucketing → per-site briefs
2. **Await feedback from network security specialist** on the business case
3. **Build the core OpenClaw scanning skill** on Pi 5
4. **Recruit 5 pilot clients** from the generated lead list
5. **Run the 4-week pilot**

---

*This document is a working artifact. Update it as decisions are made.*
