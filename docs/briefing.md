# Heimdall — Project Briefing v3

**Master context document for Claude Code sessions. Drop this in `docs/briefing.md`.**
**Replaces v2. Last updated: March 22, 2026.**

---

## What Is Heimdall

Heimdall is an External Attack Surface Management (EASM) service for small and medium businesses. It uses a Claude API agent (Anthropic SDK with tool use and agentic loops) to continuously monitor the public-facing digital surface of client websites — discovering assets, detecting vulnerabilities, interpreting findings in plain language, and delivering them through Telegram. Named after the Norse god who never sleeps and sees all threats approaching.

### What Is EASM

External Attack Surface Management is the continuous discovery, monitoring, evaluation, prioritization, and remediation of an organization's internet-facing assets and attack vectors. These include domain names, SSL certificates, web servers, APIs, CMS platforms, plugins, open ports, cloud services, and any other asset reachable from the public internet. EASM looks at the organization from the outside — exactly as an attacker would.¹ ² ³

Unlike endpoint security (which protects devices inside the network), EASM protects the perimeter that faces the internet. A business needs both, but most SMBs have neither.

---

## The Owner

Federico, based in Vejle, Denmark. Technical background: Claude Code, React/TSX, self-hosted infrastructure, Raspberry Pi experience. Building this alongside the Fjordleather brand. Partnering with a network security specialist for domain expertise.

---

## Danish State Policy Context — Critical for Sales Pitch and Grant Applications

### National Cybersecurity Strategy 2026–2029

In January 2026, the Danish government signed a cross-party agreement: "Aftale om strategi for cyber- og informationssikkerhed 2026-2029." Backed by nearly every party in the Folketing.⁴

Key allocations:
- **211 million kr. for 2026–2029**, plus 33 million kr./year from 2030 onwards
- **275 million kr. annually from 2025** for NIS2 implementation
- Funded from the national reserve for societal security (Finansloven 2026)

Key initiatives relevant to Heimdall:
- **SMV-CERT**: A new Computer Emergency Response Team specifically for SMBs, built as a public-private partnership. Will provide early warnings, practical prevention tools, and incident response help.⁵
- **Styrket Cyberhotline** (33 37 00 37): Enhanced citizen/business advisory line for digital security
- **Coordinated effort against digital fraud**
- **National cyber exercises** across public and private sectors

Minister Torsten Schack Pedersen: "Et vigtigt element i strategien er, at vi styrker cybersikkerhed for danskerne og de små og mellemstore virksomheder, så vi får alle med ombord."⁴

### The 40% Problem

According to Styrelsen for Samfundssikkerhed (Danish Agency for Civil Protection), **40% of Danish SMBs do not have a security level matching the severity of the threats they face.** DI's Lars Sandahl called the new SMV-CERT "en gamechanger for samfundets samlede beskyttelse."⁵

### Industriens Fond — Cybersecurity Program

Industriens Fond (Danish Industry Foundation) runs a dedicated Cybersikkerhedsprogram for SMBs. Vision: "Danske virksomheder er førende i at udvikle og anvende ansvarlige og sikre digitale løsninger." Provides tools, case studies, and collaboration with Erhvervsstyrelsen. Also runs D-mærket — Denmark's certification mark for IT security and responsible data use.⁶

### NCC-DK Grant Pool — OPEN NOW

The Nationale Koordinationscenter for Cybersikkerhed (NCC-DK) opened a **5.5 million kr. grant pool** on February 26, 2026 for innovative cybersecurity solutions. Deadline: **April 15, 2026**. Total NCC-DK budget 2026–2029: **43 million kr.** in grants.⁷

Requirements: minimum 2 consortium partners, at least 1 private company. Example projects they cite include "an AI-based tool that uses pattern recognition to simulate attacker behavior."

**This is directly relevant to Heimdall.** A consortium application (Heimdall + a university or established security firm) developing an AI-powered EASM service for Danish SMBs fits their stated criteria. **Note:** NCC-DK grants require a CVR. This opportunity becomes accessible after Startup Denmark approval and company registration. See decision log entry 2026-03-25.

### EU-Level: SECURE Project + Digital Europe Programme

The SECURE project launched financial support on January 28, 2026 for SMBs achieving cybersecurity compliance. 18-month mentorship program; participants must conduct minimum 10 penetration tests for external end-users including SMBs.⁸

The Digital Europe Programme has multiple open calls for cybersecurity solutions, including grants of up to €60,000 per SME for field-testing cybersecurity technologies.⁸

### Impact on Sales Pitch

The consent conversation with a prospect becomes: "The Danish government just allocated 211 million kroner because businesses like yours are the ones getting attacked. 40% of Danish SMBs don't have adequate protection. Heimdall is the simplest way to close that gap — and depending on how we structure this, government subsidies may cover the cost."

---

## Legal Framework — Scanning Without Consent

### The Law

**Straffeloven §263, stk. 1** criminalizes gaining unauthorized access ("uberettiget adgang") to another person's data system. Penalty: fine or up to 18 months imprisonment. Up to 6 years under aggravating circumstances.⁹

The ICLG Cybersecurity Report 2026 (Denmark chapter) states: "Unsolicited penetration of an IT system (without permission from the owner) will — most likely — be considered a violation under section 263 of the Danish Penal Code."¹⁰

### The Three Layers

**Layer 1 — Passive observation (minimal risk):** Reading HTTP headers, HTML source, meta tags, DNS records, SSL certificates. This is information the server voluntarily sends to any visitor. Technology fingerprinting tools (Wappalyzer, webanalyze, httpx) operate here. Search engines and browsers do this at massive scale.

**Layer 2 — Active vulnerability probing (gray zone):** Tools like Nuclei send crafted requests to test for specific CVEs. This goes beyond passive observation. No Danish court ruling was found specifically addressing this activity, but the law is broad enough that a prosecutor could argue it triggers §263. Note: WPVulnerability API lookups are Layer 1 (public database queries, no requests sent to target).

**Layer 3 — Exploitation (clearly criminal without consent):** Actually exploiting a vulnerability. Outside Heimdall's scope entirely.

### Practical Implication

The lead generation pipeline (Layer 1) can proceed — it reads publicly served information. The vulnerability scanning service (Layer 2) requires **written consent** before activation. This aligns with the business model: the free prospecting scan uses Layer 1 data; the paid service activates Layer 2 only after onboarding and authorization.

### Outreach Constraints — Danish Marketing Practices Act

Markedsføringsloven prohibits unsolicited electronic marketing 
(email, SMS, automated messages) without prior consent. Cold 
calling requires checking the Robinson List. 

Heimdall's outreach model for the pilot is therefore non-electronic: 
in-person visits to local businesses, local business networking, 
and the agency partnership channel. The prospecting pipeline 
produces scan data and per-site briefs that feed into these 
conversations — it does not automate any client contact.

This constraint should be confirmed with legal counsel alongside 
the §263 review.

### Open Legal Questions for Counsel
1. Confirm the Layer 1/Layer 2 boundary under §263
2. Draft/review a scanning authorization template
3. Clarify whether a web agency can authorize scanning of their clients' sites, or whether each end client must consent independently
4. Recommended firms: Plesner, Kromann Reumert, Bech-Bruun (all have IT law / cybersecurity practices)

Full legal research memo: see `docs/Heimdall_Legal_Risk_Assessment.md`

### Compliance Controls — Valdí

Heimdall uses a programmatic compliance agent ("Valdí") that validates all scanning code against `SCANNING_RULES.md` before execution. Every validation produces a timestamped forensic log. See `.claude/agents/valdi/SKILL.md` for the full specification. See `SCANNING_RULES.md` (project root) for the authoritative rules on what is permitted at each Layer and Level.

### Digital Twin System

Heimdall extends Layer 1 findings with Layer 2 context through a digital twin system: replicas of prospect websites built from Layer 1 scan data, running entirely on Heimdall's own infrastructure. Scanning a system you own is not a §263 violation, so the twin enables vulnerability testing (Nuclei) without requiring client consent. Additionally, WPVulnerability API lookups provide CVSS-scored plugin/core CVEs as Layer 1 database queries (no requests to target). Findings carry `provenance: "twin-derived"` markers to distinguish them from direct scan results. See `SCANNING_RULES.md` for the full digital twin framework and constraints.

---

## Target Customer

### Who Heimdall Serves

Businesses meeting these criteria:
1. They have a website handling customer data or transactions — an online booking system, a web shop, a contact form collecting personal information
2. They lack the internal resources or expertise to monitor their own external attack surface
3. They are located in the EU (initially Denmark), where GDPR Article 32 creates a regulatory obligation for "appropriate technical and organisational measures"¹¹

**In practical terms:** A restaurant with an online booking system. A physiotherapy clinic with a patient portal. A boutique hotel with a reservation engine. A small e-commerce brand running WooCommerce. An accounting firm with a client portal.

### Who Heimdall Also Serves (revised from v1)

- **Businesses with existing endpoint security (e.g., CrowdStrike Falcon Go)** — endpoint security protects devices; Heimdall protects the website. These are complementary, not overlapping. A business running CrowdStrike on its laptops still has an unmonitored external attack surface.
- **Companies with small internal IT teams** — an IT generalist managing printers, passwords, and onboarding rarely has time for continuous external vulnerability monitoring. Heimdall fills that specific gap.

### Who Heimdall Does NOT Serve

- Businesses with a managed IT/security provider (MSSP) already handling external surface monitoring
- Organizations requiring compliance certification (Heimdall generates evidence, not certificates)

---

## Infrastructure — Pilot vs. Production

### Important Framing Note

**The Raspberry Pi 5 is the pilot infrastructure, not the production architecture.** The pilot uses a Pi 5 because it's available, cheap to operate, and sufficient for 5 clients. The production infrastructure will migrate to cloud or dedicated server hosting as the client base grows.

When writing client-facing materials, **do not mention the Raspberry Pi.** The architecture description for external audiences should reference:
- "Dedicated secure infrastructure with encrypted communications"
- "Always-on monitoring with Tailscale VPN and zero inbound ports"
- "Cloud-based AI interpretation layer (Anthropic Claude API)"

The Pi is an implementation detail for the pilot, not a selling point. Clients care about uptime, security, and results — not what hardware runs the scans.

### Pilot Infrastructure (Internal Knowledge Only)

- Raspberry Pi 5, 8 GB RAM, NVMe SSD via HAT
- Official 27W PSU, active cooler
- Raspberry Pi OS Lite (64-bit, minimal attack surface)
- Claude API agent (Anthropic SDK, Sonnet) for finding interpretation and delivery orchestration
- python-telegram-bot for two-way client communication
- Tailscale VPN (no inbound ports)

### Production Migration Path (Post-Pilot)

- VPS or cloud instance (Hetzner, DigitalOcean, or similar)
- Docker containerization for reproducibility
- Separation of scanning infrastructure from client communication
- Potential multi-node architecture as client volume grows
- Same agent architecture (Claude API + tools), different substrate

### Digital Twin Container (Testing Infrastructure)

The digital twin runs as a Docker Compose service under profile `["twin"]`, exposing ports 9080 (HTTP) and 9443 (HTTPS with self-signed TLS cert). Resource budget: 256 MB RAM. The twin container reconstructs a target's CMS environment from Layer 1 scan data (detected CMS version, plugins, theme) and serves it locally for Layer 2 scanning. This is testing infrastructure — it does not serve client traffic and is not part of the production scanning pipeline. Implementation: `tools/twin/`, Docker support in `infra/docker/Dockerfile.twin`, pipeline integration via `src/worker/twin_scan.py`.

### Scanning Tools

| Tool | Function | Layer | Source |
|------|----------|-------|--------|
| httpx | HTTP probing + tech fingerprinting | 1 | https://github.com/projectdiscovery/httpx |
| webanalyze | Batch CMS detection (Wappalyzer port) | 1 | https://github.com/rverton/webanalyze |
| subfinder | Subdomain enumeration (passive sources) | 1 | https://github.com/projectdiscovery/subfinder |
| dnsx | DNS resolution and enrichment | 1 | https://github.com/projectdiscovery/dnsx |
| CertStream | Certificate Transparency log monitoring | 1 | https://github.com/CaliDog/certstream-python |
| GrayHatWarfare | Exposed cloud storage index search | 1 | https://grayhatwarfare.com |
| Nuclei | Template-based vulnerability scanner | 2 | https://github.com/projectdiscovery/nuclei |
| WPVulnerability API | WordPress plugin/core CVE lookups (free, CVSS-scored) | 1 | https://www.wpvulnerability.net/ |
| WordPress.org API | Plugin latest version checks (outdated plugin detection) | 1 | https://api.wordpress.org/plugins/info/1.0/ |
| WordPress REST API | Plugin enumeration via namespace discovery (when site advertises /wp-json/) | 1 | Built-in WordPress feature |
| CMSeek | CMS deep fingerprinting | 2 | https://github.com/Tuhinshubhra/CMSeeK |
| Nikto | Web server vulnerability scanner | 2 | https://github.com/sullo/nikto |
| Nmap | Port scanning, service detection | 2 | https://github.com/nmap/nmap |

### What the Infrastructure Cannot Do

| Limitation | Mitigation |
|-----------|------------|
| Internal network scanning | Scope limited to external surface (the attack surface that matters for web properties) |
| Authenticated app testing | Premium tier only, with explicit written authorization |
| Real-time WAF/IDS | Recommend complementary WAF (Cloudflare, Sucuri); monitor their status |
| Compliance certification | Generate evidence; refer to certified auditors |
| Server patching | Step-by-step instructions; vendor escalation email drafts |

---

## Competitive Landscape

### The Dashboard Gap (Visual Concept for Business Case)

Every competitor delivers findings through a web dashboard. The business case should include a screenshot or mockup illustrating a typical vulnerability scanner dashboard (e.g., Qualys VMDR, Intruder.io) alongside a Heimdall Telegram conversation — showing the contrast between a complex, technical interface and a plain-language message.

Qualys dashboards feature "interactive, customizable widgets," "drill-down to details on events," and "QQL queries."¹² Intruder shows "risk trends, cyber hygiene scoring, and audit-ready report generation."¹³ These are powerful for security professionals. They are impenetrable for a restaurant owner.

### Direct Competitors

| Competitor | Starting Price | Interface | URL |
|-----------|---------------|-----------|-----|
| Intruder.io | ~740 kr./month | Web dashboard + Slack/Jira | https://www.intruder.io |
| HostedScan | Free tier; paid from ~215 kr./month | Web dashboard + API | https://hostedscan.com |
| Detectify | ~610 kr./month (app); ~2.050 kr./month (surface) | Web dashboard | https://detectify.com |
| Beagle Security | ~885 kr./month | Web dashboard | https://beaglesecurity.com |
| Astra Security | Custom (~740–2.225 kr./month) | Dashboard + manual pentest | https://www.getastra.com |
| Sucuri (GoDaddy) | ~1.480 kr./year | Dashboard + WAF | https://sucuri.net |
| Censys | Enterprise pricing | Platform + API | https://censys.com |

Closest competitor: **Intruder.io**. Founded 2015, GCHQ Cyber Accelerator alumni, 1,000+ customers.¹⁴

### Enterprise EASM Players (For Context — Not Direct Competitors)

CrowdStrike Falcon Surface, Trend Micro Cyber Risk Exposure Management, Censys Attack Surface Management, Qualys EASM. All enterprise-priced, enterprise-designed. Relevant as context for what EASM means at scale, but not competitors at the SMB tier.

### Three Differentiators

1. **Conversational delivery via messaging apps** — findings arrive as a Telegram/WhatsApp conversation, not a dashboard. The restaurant owner reads a message; they never log into a portal.

2. **Persistent memory + active remediation follow-up** — the agent tracks each client's tech stack, past findings, and remediation state. It follows up on unresolved issues with escalating urgency.

3. **Shadow AI / agent infrastructure detection** — scanning for exposed OpenClaw instances, MCP servers, rogue AI agents. No SMB-focused competitor does this as of March 2026.¹⁵ ¹⁶ ¹⁷

---

## Service Tiers and Pricing (all prices excl. moms)

### Watchman — 199 kr./month

*We find problems on your website, explain them in plain language, and tell you what needs fixing.*

Weekly scan. Findings delivered straight to Telegram. We track what's changed since last time and follow up on anything unresolved.

### Sentinel — 399 kr./month

*We watch your website every day. If something changes or a new threat hits your setup, you'll know the same day — with step-by-step instructions and a message ready to forward to whoever handles it.*

Everything in Watchman, plus: daily scans, uptime monitoring, SSL and DNS change alerts, new vulnerability matching for your specific tech stack, drafted emails to your developer or hosting provider.

### Guardian — 799 kr./month (annual: 599 kr./month)

*We actively test your defences, confirm that fixes worked, and give you a report you can show your accountant or insurer.*

Everything in Sentinel, plus: active vulnerability testing (with your written permission), detection of exposed AI tools and agent infrastructure, remediation verification, quarterly security report.

### Tier Logic

The tiers are structured around how much Heimdall takes off the client's plate:

- **Watchman** tells you *what* is wrong.
- **Sentinel** tells you *how* to fix it and writes the message for you.
- **Guardian** *tests* your defences, *verifies* fixes, and *documents* your security posture.

The "Who Do I Send This To?" problem (see Pilot Plan) is resolved differently at each tier. Watchman identifies the category of person responsible (your developer, your hosting provider). Sentinel provides the specific steps and a ready-to-forward message. Guardian verifies the fix was applied.

### Remediation Service (Optional, All Tiers)

Available as an optional add-on across all tiers. When the client has no developer, no IT contact, and no ability to follow the fixing guide — Heimdall executes the fix directly. Billed hourly, separately from the subscription. Totally optional: the client can always follow the guide themselves or forward the drafted message to their own resources.

**Reference pricing (indicative — subject to adjustment during pilot):** Minimum charge (first hour) 599 kr., each additional hour 399 kr./hr. Positioned between a general web developer (~325 kr./hr) and a cybersecurity specialist (~500 kr./hr). Most common SMB fixes resolve within one hour.

No competitor (Intruder.io, HostedScan, Detectify, etc.) offers hands-on remediation. They all stop at advisory. This closes the last-mile gap between "you have a vulnerability" and "it is fixed."

### Pricing Summary

| Tier | Price | Scan Frequency | Remediation Guidance | Active Testing |
|------|-------|---------------|---------------------|---------------|
| Watchman | 199 kr./month | Weekly | What to fix | No |
| Sentinel | 399 kr./month | Daily | How to fix it + draft message | No |
| Guardian | 799 kr./month (annual: 599) | Daily | How to fix it + verification | Yes (with consent) |
| Remediation (add-on) | 599 kr. first hr, 399 kr./hr after* | On demand | Heimdall executes the fix | N/A |

*Reference pricing — subject to adjustment during pilot. All prices excl. moms (Danish VAT).

---

## Lead Generation Pipeline (BUILD IN CLAUDE CODE)

### Phase 0: Prospecting Engine

**Input:** Federico manually extracts a Vejle-area company list from CVR (https://datacvr.virk.dk — public data) and saves it as `data/input/CVR-extract.xlsx`. The pipeline does not scrape or access datacvr.virk.dk.

**Pipeline steps:**

1. Read CVR Excel export
2. Apply pre-scan filters from `config/filters.json` (industry_code, contactable)
3. Derive website domains from company email addresses (discard free webmail)
4. Resolve domains (check website exists + robots.txt compliance)
5. Layer 1 scanning with Valdí-approved scan types (`webanalyze`, `httpx`) + WordPress-specific passive detection (plugin `?ver=` version extraction, REST API namespace enumeration, meta generator tags, CSS class signatures) — all scan types must pass Valdí Gate 1 review before execution
6. Auto-bucket results:
   - **Bucket A (HIGHEST):** Self-hosted WordPress on shared hosting
   - **Bucket B (HIGH):** Other self-hosted CMS (Joomla, Drupal, PrestaShop)
   - **Bucket C (LOWER):** Shopify / Squarespace / Wix (platform handles most infrastructure security)
   - **Bucket D (SKIP):** No website / parked domain
   - **Bucket E (MEDIUM):** Custom-built / unidentifiable
7. Apply post-scan filters from `filters.json` (bucket)
8. Flag GDPR-sensitive industries via CVR branchekoder (healthcare, legal, accounting, real estate, dental)
9. Detect web agencies via footer credits and meta author tags
10. Generate per-site brief: CMS, hosting provider, SSL status, detected plugins, risk profile
11. WordPress domains: check installed plugin versions against wordpress.org latest (flag outdated), enrich with twin-derived Layer 2 findings (Nuclei against local digital twin replica) + WPVulnerability API lookups for plugin/core CVEs (no consent required)
12. Output: `prospects-list.csv` + per-site JSON briefs + agency briefs

**Output notes:**
- Only companies with a live website appear in the output CSV
- Industry names are translated to English via `config/industry_codes.json` (static lookup by industry code)
- `contactable` field (boolean) replaces the Danish Reklamebeskyttet flag (inverted: ad-protected = not contactable)
- `tech_stack` is in per-site briefs only, not in the CSV

**Filter configuration:** see `.claude/agents/prospecting/SKILL.md` for the `filters.json` format

### The "First Finding Free" Sales Motion

The prospecting scan (Layer 1) costs nothing to run and produces real findings: outdated CMS versions, expiring SSL certificates, missing security headers, detectable technology stack. The digital twin system takes this further — by reconstructing the prospect's CMS environment locally, Heimdall can surface CVE-level vulnerability findings (with `provenance: "twin-derived"` markers) in the initial outreach, without requiring consent. This data powers a free-sample sales motion — show the prospect a real, specific finding on their actual website before asking for money.

The mobile console PWA (`/static/index.html`) provides a theatrical demo mode for in-person sales meetings: the operator selects a pre-scanned prospect, and the console animates a 30-second scan replay with real findings. A "Live Twin" mode can run real Nuclei scans against a digital twin in real-time, streaming findings to the screen as they are discovered.

### Agency Pitch (Bonus)

Scan all sites built by a specific local agency (identifiable from footer credits, meta author tags, common templates). Approach the agency with: "I scanned 35 of your client sites. 22 have at least one issue. Your name is on the footer." The agency becomes a white-label partner.

---

## Pilot Plan

### Budget: ~12.000 kr.

| Item | Est. Cost |
|------|----------|
Hardware (Raspberry Pi 5 8gb NVMe HAT + 256 GB SSD)  |~2.000 kr.
Power supply and cooling    |~250 kr.
Claude API usage (3 months)    |~1.500 kr.
Domain and landing page    |~500 kr./year
Professional indemnity insurance    |~3.700–5.500 kr./year
Contingency    |~800–1.500 kr.


### Timeline

**Week 1:** Build lead-gen pipeline in Claude Code on laptop. Implement Valdí compliance gates. Test scanning functions on own domains. Pi setup comes after pipeline is validated.

**Week 2–3:** Run prospecting scan across Vejle businesses. Recruit 5 pilot clients from Bucket A. Free first month. Get written scanning authorization.

**Week 3–4:** Run scan cycles. Human-in-the-loop (Federico reviews every message). Refine prompt templates. Document what Claude gets right and wrong.

**Week 4:** Second scan cycle. Test follow-up/memory model. End-of-pilot conversations: Did you read it? Did you understand? Did you act? Would you pay for this?

### What the Pilot Validates

1. Will a non-technical business owner read and act on a Telegram security message?
2. Is the LLM interpretation accurate enough? (Known risk: false specificity — plausible advice wrong for the specific environment. Mitigate: split "what's wrong" from "how to fix"; bound remediation to generic guidance + authoritative links)
3. Does the follow-up model create value or annoyance?

### The "Who Do I Send This To?" Problem

| Client Scenario | Watchman | Sentinel / Guardian |
|----------------|----------|-------------------|
| Has a web developer | Identifies the issue and who should handle it | Message designed to be forwarded directly to the developer |
| Self-manages WordPress | Identifies the issue and that it's a wp-admin task | Step-by-step wp-admin instructions |
| Fully hosted (Shopify/Squarespace) | Identifies the issue and the platform | Platform-specific settings or drafted support ticket |
| Nobody manages it | Identifies the issue and suggests contacting hosting provider | Draft hosting provider support ticket + option to use Heimdall's remediation service (per-event, excl. moms) |

Every finding ends with a clear "who should fix this" line. Sentinel and Guardian add the "how" — specific steps and ready-to-send messages.

---

## Documents Produced

1. **heimdall-siri-application.md** — Startup Denmark (SIRI) application document, targeting the expert panel's four scoring criteria (Innovation, Market Potential, Scalability, Team)
2. **Heimdall_Legal_Risk_Assessment.md** — legal research memo on §263 and scanning consent (with Valdí addendum)
3. **OpenClaw_RPi5_Autonomous_Profit_Research.md** — original research on autonomous profit scenarios (historical — OpenClaw removed from Heimdall architecture 2026-03-29)
4. **SCANNING_RULES.md** — authoritative constraint document for all scanning code (project root)
5. **.claude/agents/valdi/SKILL.md** — Valdí legal compliance agent specification
6. **docs/legal/Valdi_Implementation_Actions.md** — implementation checklist for the compliance system
7. **This briefing** — master context for Claude Code

---

## Instructions for Claude Code: Generating the SIRI Application

When asked to produce or update the Heimdall Startup Denmark (SIRI) application (`docs/business/heimdall-siri-application.md`):

### Corrections from v1/v2 to Apply
- Add EASM definition/context in the introduction ✓ (done in v2)
- Do NOT mention Raspberry Pi in client-facing sections. Infrastructure section should describe the architecture abstractly. Keep Pi details in an internal appendix only.
- Target customer DOES include businesses with endpoint security (CrowdStrike etc.) and businesses with small IT teams. Does NOT include businesses with an MSSP already handling external monitoring.
- Replace all "Sources: ..." inline citations with superscript reference numbers pointing to a References section at the end
- Include a visual concept/mockup showing a vulnerability dashboard vs. a Heimdall Telegram message (the "gap" illustration)
- Do not use phrases like "stated honestly," "full transparency," "to be honest" — confidence is implicit
- All tool references should include links to their GitHub/source repositories
- All pricing in kr. (Danish kroner), not euros
- Replace "bakery owner" with "restaurant with online booking" as the recurring example
- Incorporate the Danish cybersecurity strategy (211M kr., SMV-CERT, NCC-DK grants, 40% statistic) as a major section
- Incorporate the legal framework summary (§263, consent requirement, Layer 1/2/3 distinction)
- Incorporate GDPR Article 32 as a compliance driver¹¹
- Add the EASM reference sources (CrowdStrike, Trend Micro, Censys, NCSC UK, Vectra) to the references
- Use aggressive pricing tiers: Watchman 199 kr., Sentinel 399 kr., Guardian 799 kr. (annual: 599 kr.) ✓ (updated in SIRI application)
- Include unit economics in the SIRI application to demonstrate self-sustainability (break-even, gross margins)
- Remove "exposed admin panels" from Layer 1 findings — admin panel detection is Layer 2 ✓ (done in v3)
- Reference Valdí compliance controls in legal and scanning sections ✓ (done in v3)
- Tier descriptions must use client-facing language, no tool names (no "OWASP ZAP DAST", no "Nuclei")

### References (for numbered superscripts in the document)

1. CrowdStrike — What Is EASM: https://www.crowdstrike.com/en-us/cybersecurity-101/exposure-management/external-attack-surface-management-easm/
2. Trend Micro — What Is EASM: https://www.trendmicro.com/en/what-is/attack-surface/external-attack-surface-management.html
3. Censys — Attack Surface Management: https://censys.com/solutions/attack-surface-management/
4. Danish Government — Cybersecurity Strategy 2026–2029: https://mssb.dk/nyheder/nyhedsarkiv/2026/januar/aftale-ny-strategi-for-cyber-og-informationssikkerhed/
5. DI Digital — SMV-CERT proposal: https://www.danskindustri.dk/brancher/di-digital/nyhedsarkiv/nyheder/2025/12/di-vil-samle-krafterne-mod-cyberangreb-ny-enhed-skal-styrke-beskyttelsen-af-sma-og-mellemstore-virksomheder/
6. Industriens Fond — Cybersikkerhedsprogram: https://industriensfond.dk/vores-fokusomrader/cybersikkerhed/
7. NCC-DK — 5.5M kr. grant pool: https://samsik.dk/artikler/2026/02/ny-pulje-55-mio-kr-til-innovative-loesninger-paa-cybertruslen/
8. EU Funding Portal — Cybersecurity grants: https://eufundingportal.eu/cybersecurity/
9. Straffeloven §263: https://danskelove.dk/straffeloven/263
10. ICLG Cybersecurity Report 2026 — Denmark: https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark
11. Vectra — GDPR Compliance Guide: https://www.vectra.ai/topics/gdpr-compliance
12. Qualys — Dashboard documentation: https://blog.qualys.com/product-tech/2020/02/04/actionable-searching-and-data-download-with-vulnerability-management-dashboards
13. Intruder.io — Vulnerability scanning tools: https://www.intruder.io/blog/the-top-vulnerability-scanning-tools
14. Bugcrowd — Intruder scanner profile: https://www.bugcrowd.com/glossary/intruder-vulnerability-scanner/
15. SecurityScorecard STRIKE Team — OpenClaw exposure: cited via https://pbxscience.com/openclaw-2026s-first-major-ai-agent-security-crisis-explained/
16. Koi Security / Bitdefender — ClawHub malicious skills: cited via https://blog.cyberdesserts.com/openclaw-malicious-skills-security/
17. Gravitee — State of AI Agent Security 2026: cited via https://beam.ai/agentic-insights/ai-agent-security-in-2026-the-risks-most-enterprises-still-ignore
18. NCSC UK — EASM Buyers Guide: https://www.ncsc.gov.uk/guidance/external-attack-surface-management-buyers-guide
19. VikingCloud 2026 SMB Statistics: cited via https://digacore.com/blog/managed-cybersecurity-services-smb-2026/
20. NCSA — SMB breach survival: cited via https://www.getastra.com/blog/dast/vulnerability-scanning-for-smbs/
21. Gurkha Technology — SMB attack trends: https://gurkhatech.com/cybersecurity-solutions-smb-2026/
22. Aalborg University — Straffelovens §263 analysis: https://vbn.aau.dk/ws/files/305754822/Speciale_Straffelovens_263_stk._1.pdf
23. EU Directive 2013/40/EU: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013L0040
24. OpenClaw Documentation — Raspberry Pi setup: https://docs.openclaw.ai/platforms/raspberry-pi
25. Raspberry Pi Foundation — OpenClaw on Pi: https://www.raspberrypi.com/news/turn-your-raspberry-pi-into-an-ai-agent-with-openclaw/
26. Kaspersky — OpenClaw security audit (512 vulnerabilities): cited via https://www.institutionalinvestor.com/article/openclaw-ai-agent-institutional-investors-need-understand-shouldnt-touch
27. Dark Reading — 48% agentic AI attack vector poll: cited via https://www.kiteworks.com/cybersecurity-risk-management/agentic-ai-attack-surface-enterprise-security-2026/
28. Danish CVR Register: https://datacvr.virk.dk
29. Styrelsen for Samfundssikkerhed (SAMSIK): https://samsik.dk
30. Strategy agreement full text (PDF): https://mssb.dk/media/5jdlnv41/aftaletekst.pdf

---

*This document is a working artifact. It is the single source of truth for the Heimdall project. Update it as decisions are made.*
