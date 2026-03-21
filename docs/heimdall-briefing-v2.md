# Heimdall — Project Briefing v2

**Master context document for Claude Code sessions. Drop this in `docs/heimdall-briefing.md`.**
**Replaces v1. Last updated: March 21, 2026.**

---

## What Is Heimdall

Heimdall is an External Attack Surface Management (EASM) service for small and medium businesses. It runs on OpenClaw (open-source AI agent framework) and continuously monitors the public-facing digital surface of client websites — discovering assets, detecting vulnerabilities, interpreting findings in plain language, and delivering them through messaging apps (Telegram, WhatsApp). Named after the Norse god who never sleeps and sees all threats approaching.

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

**This is directly relevant to Heimdall.** A consortium application (Heimdall + a university or established security firm) developing an AI-powered EASM service for Danish SMBs fits their stated criteria.

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

**Layer 2 — Active vulnerability probing (gray zone):** Tools like Nuclei and Nikto send crafted requests to test for specific CVEs. This goes beyond passive observation. No Danish court ruling was found specifically addressing this activity, but the law is broad enough that a prosecutor could argue it triggers §263.

**Layer 3 — Exploitation (clearly criminal without consent):** Actually exploiting a vulnerability. Outside Heimdall's scope entirely.

### Practical Implication

The lead generation pipeline (Layer 1) can proceed — it reads publicly served information. The vulnerability scanning service (Layer 2) requires **written consent** before activation. This aligns with the business model: the free prospecting scan uses Layer 1 data; the paid service activates Layer 2 only after onboarding and authorization.

### Open Legal Questions for Counsel
1. Confirm the Layer 1/Layer 2 boundary under §263
2. Draft/review a scanning authorization template
3. Clarify whether a web agency can authorize scanning of their clients' sites, or whether each end client must consent independently
4. Recommended firms: Plesner, Kromann Reumert, Bech-Bruun (all have IT law / cybersecurity practices)

Full legal research memo: see `Heimdall_Legal_Risk_Assessment.md`

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
- OpenClaw as gateway/orchestrator
- Tailscale VPN (no inbound ports)
- Claude API (Sonnet) for finding interpretation
- Telegram Bot for client delivery

### Production Migration Path (Post-Pilot)

- VPS or cloud instance (Hetzner, DigitalOcean, or similar)
- Docker containerization for reproducibility
- Separation of scanning infrastructure from client communication
- Potential multi-node architecture as client volume grows
- Same OpenClaw skill architecture, different substrate

### Scanning Tools

| Tool | Function | Source |
|------|----------|--------|
| Nuclei | Template-based vulnerability scanner | https://github.com/projectdiscovery/nuclei |
| Nikto | Web server vulnerability scanner | https://github.com/sullo/nikto |
| Nmap | Port scanning, service detection | https://github.com/nmap/nmap |
| SSLyze | TLS/SSL configuration analysis | https://github.com/nabla-c0d3/sslyze |
| testssl.sh | SSL/TLS testing | https://github.com/drwetter/testssl.sh |
| WPScan | WordPress-specific scanner | https://github.com/wpscanteam/wpscan |
| Subfinder | Subdomain enumeration | https://github.com/projectdiscovery/subfinder |
| httpx | HTTP probing + tech fingerprinting | https://github.com/projectdiscovery/httpx |
| webanalyze | Batch CMS detection (Wappalyzer port) | https://github.com/rverton/webanalyze |

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

CrowdStrike Falcon Surface, Trend Micro Cyber Risk Exposure Management, Censys Attack Surface Management, Qualys EASM. All enterprise-priced, enterprise-designed. Relevant as context for what EASM means at scale, but not competitors at the SMB/kr. 215/month tier.

### Three Differentiators

1. **Conversational delivery via messaging apps** — findings arrive as a Telegram/WhatsApp conversation, not a dashboard. The restaurant owner reads a message; they never log into a portal.

2. **Persistent memory + active remediation follow-up** — the agent tracks each client's tech stack, past findings, and remediation state. It follows up on unresolved issues with escalating urgency.

3. **Shadow AI / agent infrastructure detection** — scanning for exposed OpenClaw instances, MCP servers, rogue AI agents. No SMB-focused competitor does this as of March 2026.¹⁵ ¹⁶ ¹⁷

---

## Service Tiers and Pricing

| Tier | Price | Key Features |
|------|-------|-------------|
| Watchman | 215 kr./month | Weekly scan, plain-language Telegram findings, trend tracking, on-demand rescan |
| Sentinel | 590 kr./month | Daily scan, uptime monitoring, SSL tracking, DNS change detection, proactive CVE matching, vendor email drafts |
| Guardian | 1.480 kr./month | Authenticated scanning, OWASP ZAP DAST, shadow AI detection, quarterly PDF report, remediation verification |

### Unit Economics (Estimates)

| Tier | Price | Est. API Cost | Est. Compute | Est. Gross Margin |
|------|-------|--------------|-------------|------------------|
| Watchman | 215 kr. | ~22 kr. | ~1.5 kr. | ~89% |
| Sentinel | 590 kr. | ~74 kr. | ~3.7 kr. | ~87% |
| Guardian | 1.480 kr. | ~186 kr. | ~7.5 kr. | ~87% |

API cost estimates based on current Claude API pricing. Actual costs vary with usage.

---

## Lead Generation Pipeline (BUILD IN CLAUDE CODE)

### Phase 0: Prospecting Engine

1. Obtain Vejle-area company list from CVR (https://datacvr.virk.dk — public data)
2. Extract website URLs from register entries
3. Batch scan with `webanalyze` or `httpx` for CMS/hosting/tech detection (Layer 1 — passive, legally safe)
4. Auto-bucket results:
   - **Bucket A (HIGHEST):** Self-hosted WordPress on shared hosting
   - **Bucket B (HIGH):** Other self-hosted CMS (Joomla, Drupal, PrestaShop)
   - **Bucket C (LOWER):** Shopify / Squarespace / Wix (platform handles most infrastructure security)
   - **Bucket D (SKIP):** No website / parked domain
   - **Bucket E (MEDIUM):** Custom-built / unidentifiable
5. Second dimension: filter by CVR branchekoder for GDPR-sensitive industries (healthcare, legal, accounting, real estate, dental)
6. Generate per-site brief: CMS, hosting provider, SSL status, detected plugins, risk profile
7. Output: bucketed CSV + per-site briefs

### The "First Finding Free" Sales Motion

The prospecting scan (Layer 1) costs nothing to run and produces real findings: outdated CMS versions, expiring SSL certificates, exposed admin panels, detectable technology stack. This data powers a free-sample sales motion — show the prospect a real finding on their actual website before asking for money.

### Agency Pitch (Bonus)

Scan all sites built by a specific local agency (identifiable from footer credits, meta author tags, common templates). Approach the agency with: "I scanned 35 of your client sites. 22 have at least one issue. Your name is on the footer." The agency becomes a white-label partner.

---

## Pilot Plan

### Budget: ~7.000 kr. ($1,000)

| Item | Est. Cost |
|------|----------|
| NVMe HAT + 256GB SSD | ~335 kr. |
| PSU + cooler (if needed) | ~185 kr. |
| Claude API (3 months) | ~1.115 kr. |
| Domain + landing page | ~225 kr. |
| Professional indemnity insurance | ~3.700–5.200 kr./year |
| Contingency | ~375–740 kr. |

### Timeline

**Week 1:** Build lead-gen pipeline in Claude Code. Configure Pi with OpenClaw + scanning tools. Write core scanning skill. Test on own domains.

**Week 2–3:** Run prospecting scan across Vejle businesses. Recruit 5 pilot clients from Bucket A. Free first month. Get written scanning authorization.

**Week 3–4:** Run scan cycles. Human-in-the-loop (Federico reviews every message). Refine prompt templates. Document what Claude gets right and wrong.

**Week 4:** Second scan cycle. Test follow-up/memory model. End-of-pilot conversations: Did you read it? Did you understand? Did you act? Would you pay 215 kr./month?

### What the Pilot Validates

1. Will a non-technical business owner read and act on a Telegram security message?
2. Is the LLM interpretation accurate enough? (Known risk: false specificity — plausible advice wrong for the specific environment. Mitigate: split "what's wrong" from "how to fix"; bound remediation to generic guidance + authoritative links)
3. Does the follow-up model create value or annoyance?

### The "Who Do I Send This To?" Problem

| Client Scenario | Heimdall's Response |
|----------------|-------------------|
| Has a web developer | Message designed to be forwarded directly |
| Self-manages WordPress | Step-by-step wp-admin instructions |
| Fully hosted (Shopify/Squarespace) | Platform-specific settings or drafted support ticket |
| Nobody manages it | Draft hosting provider support ticket + curated freelancer referral list |

Every finding ends with a clear "who should fix this" line.

---

## Documents Produced

1. **Heimdall_Business_Case_v2.md** — board-ready document (to be regenerated from this briefing in Claude Code with all corrections applied)
2. **Heimdall_Legal_Risk_Assessment.md** — legal research memo on §263 and scanning consent
3. **OpenClaw_RPi5_Autonomous_Profit_Research.md** — original research on autonomous profit scenarios
4. **This briefing** — master context for Claude Code

---

## Instructions for Claude Code: Generating the Final Business Case

When asked to produce the final Heimdall Business Case v2.0:

### Corrections from v1 to Apply
- Add EASM definition/context in the introduction
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
