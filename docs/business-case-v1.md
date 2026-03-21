# Heimdall

### An OpenClaw-Powered Cybersecurity Service for Small Businesses

**Business Case — Version 2.0 — March 21, 2026**

*Heimdall (Old Norse: "the one who illuminates the world") — the ever-vigilant guardian of the gods' stronghold, who never sleeps and sees all threats approaching from any direction.*

---

## 1. Executive Summary

Heimdall is a cybersecurity monitoring service for small businesses built on OpenClaw, an open-source autonomous AI agent framework, running on a Raspberry Pi 5. It continuously scans the external attack surface of a client's website, interprets findings in plain language, delivers them through messaging apps (Telegram, WhatsApp), and actively follows up on remediation — all without requiring the client to log into a dashboard or understand security terminology.

This document presents the market opportunity, defines the target customer, maps the competitive landscape with full transparency, identifies the specific differentiators, and outlines the business model.

**Important note on claims:** Throughout this document, statistical claims are attributed to their original sources. Where data is estimated or directional rather than verified, this is stated explicitly. The authors acknowledge that the cybersecurity market is dynamic and that competitive positioning may shift.

---

## 2. The Target Customer

### Who Heimdall Serves

Heimdall targets businesses that meet all three of the following criteria:

1. **They have a website that handles customer data or transactions** — an online shop, a booking system, a contact form collecting personal information, a restaurant with online reservations.

2. **They have no dedicated IT security staff or relationship with a managed security provider.** According to a 2026 survey by VikingCloud (cited in Digacore, 2026), approximately 20% of small businesses report having no security technology at all. The broader pattern — supported by data from the National Cyber Security Alliance (NCSA) and Techaisle — suggests that the majority of businesses under 50 employees lack formal security monitoring arrangements, though exact figures vary by region and industry.

3. **They are located in the EU (initially Denmark)**, where GDPR Article 32 creates a regulatory obligation to implement "appropriate technical and organisational measures" for data security, giving security monitoring a compliance dimension.

**In practical terms:** A bakery with an online ordering system. A physiotherapy clinic with a booking platform. A boutique hotel with a reservation engine. A craftsman with a WordPress portfolio and contact form. A small e-commerce brand running Shopify or WooCommerce.

### Who Heimdall Does NOT Serve

- Businesses that already have an MSSP or managed IT provider handling security
- Companies with internal IT/security teams (typically 50+ employees)
- Businesses seeking endpoint protection (laptops, servers, devices) — this is a different product category entirely (see Section 4)
- Organizations requiring compliance certification (SOC 2, PCI-DSS audit) — Heimdall generates evidence that supports compliance, but is not a certified auditor

---

## 3. The Market Context

### The Problem

Small businesses are increasingly targeted by cyberattacks, while their capacity to defend themselves has not kept pace:

- **61% of small businesses experienced a data breach in the past year** — Source: VikingCloud 2026 SMB Cybersecurity Statistics, cited in Digacore (https://digacore.com/blog/managed-cybersecurity-services-smb-2026/)
- **60% of small businesses that suffer a cyberattack close within six months** — Source: National Cyber Security Alliance (NCSA), cited in Astra Security (https://www.getastra.com/blog/dast/vulnerability-scanning-for-smbs/)
- **75% of SMB owners rank cyberattacks, breaches, and ransomware as the top threat to operations** — Source: VikingCloud 2026, cited in Digacore (ibid.)
- **The average breach cost for businesses under 500 employees reached $3.31 million in 2025** — Source: IBM Cost of a Data Breach Report, cited in Digacore (ibid.)
- **Cyberattacks targeting SMBs are increasing by approximately 40% year-over-year** — Source: Gurkha Technology analysis of 2026 threat data (https://gurkhatech.com/cybersecurity-solutions-smb-2026/)

### The Gap — Stated Honestly

The gap is **not** that no one offers external website vulnerability scanning to small businesses. That market exists and has established players (see Section 5).

The gap is that **existing solutions are designed for technical users who engage with dashboards**, while the vast majority of small business owners — who face the greatest risk — do not have the skills, time, or inclination to interpret a vulnerability dashboard. They need findings delivered in the language they already understand, through the channels they already use, with active follow-up rather than passive reporting.

Additionally, a new category of threat — **exposed AI agent infrastructure** (OpenClaw instances, MCP servers, shadow AI deployments) — represents an attack surface that, as of March 2026, is not covered by any SMB-focused scanning product we have identified.

---

## 4. What Heimdall Is — and What It Is Not

### The Distinction Between Endpoint Security and External Surface Monitoring

These are two separate product categories that serve different purposes:

| Dimension | Endpoint Security (e.g., CrowdStrike, Bitdefender) | External Surface Monitoring (Heimdall) |
|-----------|-----------------------------------------------------|----------------------------------------|
| **Protects** | Devices: laptops, servers, phones | The website and its public-facing infrastructure |
| **How** | Software agent installed on each device | External scanning — no installation required |
| **What it sees** | Processes, files, behaviors on the machine | What the internet sees: open ports, SSL config, CMS vulnerabilities, exposed services |
| **Threat model** | Malware, ransomware, insider threats | Web vulnerabilities, outdated software, misconfigurations, data exposure |
| **Who buys it** | Businesses with IT staff or an MSP relationship | Any business with a website and a domain name |
| **Minimum cost** | ~$60/device/year (CrowdStrike Falcon Go, https://www.crowdstrike.com/en-us/pricing/) | €29/month per domain (Heimdall Tier 1) |
| **Requires from client** | Installation, management, endpoint access | Nothing — just the domain name |

**Heimdall does not compete with CrowdStrike, Bitdefender, or Sophos.** These products protect the devices inside a business. Heimdall protects the website facing the internet. A business could (and ideally should) use both.

---

## 5. Competitive Landscape — Full Transparency

### Direct Competitors

The following companies offer external website/infrastructure vulnerability scanning to SMBs. This is the space Heimdall enters.

| Competitor | Starting Price | Interface | Target User | URL |
|-----------|---------------|-----------|-------------|-----|
| **Intruder.io** | $99/month (Essential) | Web dashboard + Slack/Jira alerts | Lean security teams, developers | https://www.intruder.io |
| **HostedScan** | Free (3 scans/month); paid plans from ~$29/month | Web dashboard + API | MSPs reselling to SMBs | https://hostedscan.com |
| **Detectify** | €82/month (app scanning); €275/month (surface monitoring) | Web dashboard | Security teams, developers | https://detectify.com |
| **Beagle Security** | $119/month | Web dashboard | SMBs, MSPs | https://beaglesecurity.com |
| **Astra Security** | Custom pricing (typically $99–$299/month) | Web dashboard + manual pentesting | SMBs seeking compliance | https://www.getastra.com |
| **Sucuri** (GoDaddy) | $199/year | Web dashboard + WAF | WordPress/CMS site owners | https://sucuri.net |
| **Qualys Community Edition** | Free (limited) | Web dashboard | Technical users | https://www.qualys.com |

### The Closest Competitor: Intruder.io

Intruder is the most direct competitor. Founded in 2015, originally part of the GCHQ Cyber Accelerator in the UK, with over 1,000 customers in government and enterprise (source: Bugcrowd, https://www.bugcrowd.com/glossary/intruder-vulnerability-scanner/). They offer:

- Continuous external vulnerability scanning
- Emerging threat alerts (proactive scans when new CVEs are published)
- Smart prioritization with remediation advice
- Integrations with Slack, Jira, Microsoft Teams, AWS, Azure, Google Cloud
- Over 140,000 infrastructure checks and 75+ application security checks

**Honest assessment:** Intruder is a strong, mature product. Any claim that "nobody does this" would be false.

### Where Competitors Overlap With Heimdall

All competitors listed above, and Heimdall, share the same core function: **external vulnerability scanning of web-facing infrastructure.** The underlying scanning technology (Nmap, OpenVAS/Greenbone, ZAP, Nuclei, SSLyze) is largely commoditized — many of these tools are open source and available to anyone.

---

## 6. Heimdall's Three Differentiators

Given that the scanning itself is commodity, Heimdall's value proposition rests on three specific differences. We state each one honestly, including its limitations.

### Differentiator 1: Conversational Delivery via Messaging Apps

**What it means:** Every competitor delivers findings through a web dashboard that the client must log into. Some send notification pings to Slack or email, but these link back to the dashboard for detail. Heimdall delivers the full finding — explanation, risk assessment, remediation steps — as a conversation in WhatsApp, Telegram, or Signal. No dashboard. No login. No portal.

**Why it matters:** The target customer (a bakery owner, a clinic receptionist, a boutique hotel manager) will not log into Intruder's dashboard. They will read a WhatsApp message. The interface determines whether findings are acted upon.

**Limitation:** This advantage is structural only for non-technical buyers. Technical users (developers, IT staff) may prefer dashboards with filtering, sorting, and export capabilities. Heimdall is intentionally not designed for them.

### Differentiator 2: Persistent Memory and Active Remediation Follow-Up

**What it means:** Existing scanners find a vulnerability, report it, and if nobody acts, it reappears as an open finding on the next scan. Heimdall's OpenClaw agent maintains persistent memory of each client's technology stack, hosting provider, previous findings, and remediation history. It actively follows up:

*"It's been 14 days since I flagged the outdated jQuery library on your checkout page. This vulnerability allows attackers to inject scripts that could steal customer payment data. Here's the fix again: [specific steps for your WooCommerce setup]. Your SSL certificate also expires in 11 days — want me to draft an email to SiteGround requesting renewal?"*

The agent adapts its communication based on the client's history — escalating urgency for recurring issues, reducing noise for resolved ones.

**Why it matters:** The bottleneck in SMB security is not detection — it is comprehension and action. Tools like Intruder already find the vulnerabilities. What many small businesses lack is someone who translates findings into plain language, explains the business impact, provides specific fix instructions, and checks whether the fix was applied.

**Limitation:** This is a software capability of OpenClaw's persistent memory architecture, not a proprietary technology. Any competitor could build a similar follow-up system. The barrier is architectural — bolting persistent conversational memory onto a SaaS dashboard is a significant re-architecture, not a feature toggle.

### Differentiator 3: Shadow AI and Agent Infrastructure Detection

**What it means:** Heimdall scans for a category of exposure that, as of March 2026, we have not identified in any competing SMB product: exposed AI agent infrastructure. This includes:

- Open OpenClaw instances on TCP port 18789 (the default gateway port)
- Unauthenticated MCP (Model Context Protocol) servers
- Characteristic AI agent signatures in HTTP responses
- Exposed AI chatbot backends leaking credentials or configuration data

**Why it matters:** OpenClaw's own security crisis demonstrates the scale of the problem:

- **135,000+ publicly exposed OpenClaw instances** were identified across 82 countries by SecurityScorecard's STRIKE team — Source: SecurityScorecard, cited in pbxscience.com (https://pbxscience.com/openclaw-2026s-first-major-ai-agent-security-crisis-explained/)
- **15,000+ instances were vulnerable to remote code execution** — Source: SecurityScorecard STRIKE Team (ibid.)
- **820+ malicious skills** were found in ClawHub (the OpenClaw skill marketplace), up from 341 just weeks earlier — Source: Koi Security / Bitdefender, cited in cyberdesserts.com (https://blog.cyberdesserts.com/openclaw-malicious-skills-security/)
- **48% of cybersecurity professionals identify agentic AI as the top attack vector for 2026** — Source: Dark Reading readership poll, cited in Kiteworks (https://www.kiteworks.com/cybersecurity-risk-management/agentic-ai-attack-surface-enterprise-security-2026/)
- **Only 14.4% of deployed AI agents went live with full security and IT approval** — Source: Gravitee State of AI Agent Security 2026 (https://beam.ai/agentic-insights/ai-agent-security-in-2026-the-risks-most-enterprises-still-ignore)

Enterprise vendors (Microsoft Defender, Trend Micro, AGAT Software's Pragatix) are beginning to address agentic AI security, but at enterprise price points and complexity. No SMB-focused scanner we have identified includes shadow AI detection in its scan templates.

**Limitation:** This is a niche differentiator today. Its value increases as AI agent adoption grows in workplaces, but it is not yet a primary purchasing driver for most small businesses.

---

## 7. Architecture: What the Raspberry Pi 5 Can and Cannot Do

### The Setup

The Raspberry Pi 5 (8 GB RAM, NVMe SSD recommended) runs OpenClaw as a **gateway**. The LLM reasoning (finding interpretation, report generation, conversational responses) happens via cloud API (Anthropic Claude or equivalent). The Pi handles orchestration, cron scheduling (via OpenClaw's Heartbeat engine), tool execution, and persistent memory.

This is a proven architecture: the Raspberry Pi Foundation published an official guide on running OpenClaw on Pi 5 in February 2026 (https://www.raspberrypi.com/news/turn-your-raspberry-pi-into-an-ai-agent-with-openclaw/), and multiple community implementations exist on GitHub (e.g., https://github.com/MasteraSnackin/Autonomous-AI-Agent-on-Raspberry-Pi-5).

**Operating costs:** ~5W power consumption (~€1/month electricity) + LLM API tokens (~€20–50/month depending on usage).

### What Runs on the Pi

| Tool | Function | Runs on ARM64 Pi 5? |
|------|----------|---------------------|
| Nuclei | Template-based vulnerability scanner (Go binary) | Yes |
| Nikto | Web server vulnerability scanner (Perl) | Yes |
| Nmap | Port scanning, service detection | Yes |
| SSLyze / testssl.sh | TLS/SSL configuration analysis | Yes |
| WPScan | WordPress-specific scanner (Ruby) | Yes |
| Subfinder | Subdomain enumeration (Go) | Yes |
| httpx | HTTP probing and technology fingerprinting (Go) | Yes |
| curl + custom scripts | Header analysis, cookie security, CORS checks | Yes |

### What the Pi Cannot Do

| Limitation | Reason | Mitigation |
|-----------|--------|------------|
| Internal network scanning | Pi has no access to client's LAN | Scope limited to external surface (which is the internet-facing attack surface) |
| Authenticated application testing | Requires client credentials; liability risk | Offered only in premium tier with explicit written authorization |
| Real-time WAF/IDS | Pi lacks network positioning and bandwidth | Recommend complementary WAF services (Cloudflare, Sucuri); monitor their status |
| Compliance certification | Not a licensed auditor | Generate evidence supporting compliance; refer to certified auditors for certification |
| Server patching | No SSH access to client infrastructure | Generate step-by-step instructions; draft vendor escalation emails |

---

## 8. Service Tiers and Pricing

### Tier 1 — "Watchman" — €29/month per domain

- Weekly automated external scan (Nuclei + Nikto + SSLyze + header analysis)
- Findings delivered as plain-language messages via Telegram or WhatsApp
- Each finding includes: what's wrong, why it matters to the business, how to fix it, severity rating
- Monthly trend summary
- On-demand re-scan after fixes are applied

### Tier 2 — "Sentinel" — €79/month per domain

Everything in Tier 1, plus:

- Daily scanning
- Continuous uptime monitoring (HTTP probe every 5 minutes)
- SSL certificate expiry tracking (30/14/7-day warnings)
- DNS change detection
- Subdomain discovery (forgotten staging servers, exposed dev environments)
- Technology fingerprinting (alerts when the site's stack changes)
- Proactive CVE matching against stored tech profile
- Vendor escalation email drafts

### Tier 3 — "Guardian" — €199/month per domain

Everything in Tier 2, plus:

- Authenticated scanning (with explicit client authorization)
- API endpoint discovery and testing
- Full OWASP ZAP DAST scans
- Browser automation checks for visual defacement, injected scripts
- Shadow AI infrastructure detection
- Quarterly PDF security report (suitable for insurance applications, board presentations, GDPR compliance evidence)
- Remediation verification loop (automated re-scan after fixes)

### Unit Economics

| Tier | Price | Estimated API cost/client/month | Compute cost/client/month | Estimated gross margin |
|------|-------|------|------|--------|
| Watchman (€29) | €29 | ~€3 | ~€0.20 | ~89% |
| Sentinel (€79) | €79 | ~€10 | ~€0.50 | ~87% |
| Guardian (€199) | €199 | ~€25 | ~€1.00 | ~87% |

*Note: API cost estimates are based on current Claude API pricing for typical scan interpretation workloads. Actual costs will vary with usage patterns and model selection.*

A single Raspberry Pi 5 is estimated to handle 50–100 clients, depending on scan frequency and complexity. This estimate is based on the Pi's role as a gateway (not running inference) and the asynchronous nature of scan scheduling.

---

## 9. Go-to-Market: Denmark First

### Why Denmark

- **GDPR enforcement is active:** Denmark's Datatilsynet (Data Protection Authority) has been increasingly active in enforcement actions, including against SMBs.
- **Market size:** Denmark has approximately 350,000 active businesses (source: Statistics Denmark / Danmarks Statistik), the majority of which are small enterprises.
- **Local presence advantage:** Cybersecurity is a trust business. Local language, local understanding of the business environment, and physical proximity matter.
- **Nordic scaling path:** Denmark, Sweden, Norway, and Finland share GDPR as a common regulatory framework and similar business cultures, enabling geographic expansion with minimal product adaptation.

### Distribution Channel: Web Agencies

The primary distribution strategy is **white-label through web development agencies**. The agency that built the bakery's website becomes the channel partner that bundles Heimdall into their ongoing maintenance package.

The agency charges the client €50–80/month for "website care" (hosting + updates + security monitoring), of which €29 goes to Heimdall. The agency earns recurring revenue from a service they don't have to build or maintain. The client gets security monitoring bundled into a relationship they already trust.

This is the distribution advantage: Intruder.io sells directly to the technical buyer through their website. Heimdall sells through the agency that already has the bakery owner's trust and phone number.

---

## 10. Risk Analysis and Counter-Cases

### Risk 1: "Intruder.io or HostedScan could add a conversational interface"

**Assessment:** Technically possible. Architecturally difficult. Adding persistent memory and conversational delivery to a SaaS dashboard platform requires significant re-engineering of the product's core interaction model. Both companies are optimized for dashboard-first, notification-second delivery. However, this risk is real on a 12–24 month horizon.

**Mitigation:** Build the client base and agency channel relationships quickly. Switching costs increase with every month of accumulated client history in Heimdall's persistent memory.

### Risk 2: "The scanning technology is commodity — anyone can do this"

**Assessment:** Correct. Nuclei, Nmap, ZAP, and SSLyze are open-source and free. The scanning is not the product. The interpretation, contextual memory, conversational delivery, and remediation follow-up are the product.

**Mitigation:** This is a service business wrapped in agent technology, not a technology product. The moat is the client relationship and accumulated context, not the scan engine.

### Risk 3: "Legal liability if Heimdall misses a vulnerability"

**Assessment:** Real and must be addressed from day one.

**Mitigation:** Terms of service explicitly frame Heimdall as a monitoring and advisory service, not a guarantee of security. This is standard framing across the industry — Intruder, Astra, and every MSSP use equivalent disclaimers. Professional indemnity insurance (standard for IT consultancies in Denmark, estimated at €500–1,000/year) provides additional protection.

### Risk 4: "The Pi itself gets compromised"

**Assessment:** Using OpenClaw — a framework that had 512 vulnerabilities identified in its first security audit (source: Kaspersky, January 2026, cited in Institutional Investor at https://www.institutionalinvestor.com/article/openclaw-ai-agent-institutional-investors-need-understand-shouldnt-touch) — to protect others is an irony that must be addressed.

**Mitigation:**
- Pi binds to 127.0.0.1 only; accessible exclusively via Tailscale VPN (no inbound ports)
- No client credentials stored (except Tier 3 authenticated scans, under separate isolation)
- Scan tools operate in sandboxed environments
- Pi runs Raspberry Pi OS Lite (minimal attack surface, no desktop)
- Automated security updates via unattended-upgrades
- Pi is treated as disposable: if compromised, wipe and rebuild from documented configuration in under 30 minutes

### Risk 5: "Small businesses won't pay €29/month for security"

**Assessment:** Valid concern. Many small businesses view security as an expense with no visible return — until an incident occurs.

**Mitigation:** The agency white-label channel addresses this directly. The bakery owner doesn't buy "security monitoring" — they buy "website care" from their web developer, which happens to include security. The purchasing psychology is different when security is bundled into a trusted existing relationship rather than sold as a standalone product.

---

## 11. What We Know, and What We Don't

### What We Know With Confidence

- The external vulnerability scanning market for SMBs exists and has funded competitors
- OpenClaw runs reliably on Raspberry Pi 5 as documented by the Raspberry Pi Foundation and community implementations
- The open-source scanning tools (Nuclei, Nmap, ZAP, etc.) run on ARM64 and are well-maintained
- No competitor we have identified delivers findings as persistent, contextual conversations through messaging apps
- No SMB-focused scanner we have identified includes shadow AI / agent infrastructure detection
- The GDPR compliance dimension creates a regulatory driver in the EU market

### What We Believe but Cannot Yet Prove

- That non-technical business owners will engage with security findings delivered via messaging app at higher rates than via dashboard (this hypothesis must be validated with pilot clients)
- That web agencies will adopt a white-label model at the proposed price points (this requires channel partner conversations)
- That the persistent memory / follow-up model materially improves remediation rates (this requires measurement over multiple scan cycles)
- That shadow AI detection will become a significant purchasing driver within 12 months (this depends on the pace of AI agent adoption in workplaces)

### What We Accept as Risks

- A well-funded competitor could build a similar conversational interface
- OpenClaw's own security track record creates a credibility challenge that must be actively managed
- API costs may change as LLM providers adjust pricing
- The Danish SMB market may be smaller in practice than the 350,000-business headline figure suggests, once filters are applied

---

## 12. Glossary

| Acronym | Full Term | Explanation |
|---------|-----------|-------------|
| **API** | Application Programming Interface | A set of rules that allows software programs to communicate with each other |
| **ARM64** | Advanced RISC Machine 64-bit | The processor architecture used by the Raspberry Pi 5 |
| **CMS** | Content Management System | Software for building websites (e.g., WordPress, Shopify) |
| **CORS** | Cross-Origin Resource Sharing | A browser security mechanism controlling which websites can access resources |
| **CVE** | Common Vulnerabilities and Exposures | A unique identifier for a publicly known cybersecurity vulnerability |
| **CVSS** | Common Vulnerability Scoring System | A standardized severity rating for vulnerabilities (0–10 scale) |
| **DAST** | Dynamic Application Security Testing | Testing a running website/app for vulnerabilities by interacting with it |
| **DNS** | Domain Name System | The internet's address book, translating domain names to IP addresses |
| **EDR** | Endpoint Detection and Response | Security software that monitors and responds to threats on devices |
| **EU** | European Union | Political and economic union of 27 European member states |
| **GDPR** | General Data Protection Regulation | EU regulation governing the processing of personal data (effective 2018) |
| **HTTP/HTTPS** | Hypertext Transfer Protocol (Secure) | The protocol used to transfer web pages; HTTPS adds encryption |
| **IDS** | Intrusion Detection System | A system that monitors network traffic for suspicious activity |
| **LLM** | Large Language Model | An AI system trained on large amounts of text (e.g., Claude, GPT) |
| **MCP** | Model Context Protocol | A protocol connecting AI agents to tools, data sources, and APIs |
| **MDR** | Managed Detection and Response | An outsourced security service providing monitoring and incident response |
| **MSP** | Managed Service Provider | A company that remotely manages a client's IT infrastructure |
| **MSSP** | Managed Security Service Provider | An MSP specializing in cybersecurity services |
| **NCSA** | National Cyber Security Alliance | A US-based nonprofit promoting cybersecurity awareness |
| **NVD** | National Vulnerability Database | A US government repository of vulnerability data |
| **NVMe** | Non-Volatile Memory Express | A fast storage interface; used with SSDs connected to the Pi 5 |
| **OWASP** | Open Worldwide Application Security Project | A nonprofit producing security standards and tools (e.g., OWASP Top 10) |
| **PCI-DSS** | Payment Card Industry Data Security Standard | Security standards for organizations handling credit card data |
| **RCE** | Remote Code Execution | A vulnerability allowing an attacker to run commands on a remote system |
| **SaaS** | Software as a Service | Software delivered via the internet on a subscription basis |
| **SMB** | Small and Medium-Sized Business | Generally businesses with fewer than 250 employees (EU definition) |
| **SOC 2** | System and Organization Controls 2 | A framework for managing customer data security and privacy |
| **SQL** | Structured Query Language | A language used to interact with databases |
| **SSL/TLS** | Secure Sockets Layer / Transport Layer Security | Encryption protocols securing internet communications |
| **SSRF** | Server-Side Request Forgery | An attack where a server is tricked into making requests to unintended targets |
| **TCP** | Transmission Control Protocol | A core internet protocol for reliable data transmission |
| **VPN** | Virtual Private Network | An encrypted connection providing secure remote access to a network |
| **WAF** | Web Application Firewall | A security layer filtering and monitoring HTTP traffic to web applications |
| **XDR** | Extended Detection and Response | Security platform integrating data from multiple security layers |
| **XSS** | Cross-Site Scripting | An attack injecting malicious scripts into web pages viewed by others |
| **ZAP** | Zed Attack Proxy | An open-source web application security scanner (now maintained by Checkmarx) |

---

## 13. Document Sources

All external sources referenced in this document:

- Astra Security — SMB Vulnerability Scanning: https://www.getastra.com/blog/dast/vulnerability-scanning-for-smbs/
- Beam.ai — AI Agent Security 2026: https://beam.ai/agentic-insights/ai-agent-security-in-2026-the-risks-most-enterprises-still-ignore
- Beagle Security: https://beaglesecurity.com
- Bugcrowd — Intruder Scanner Profile: https://www.bugcrowd.com/glossary/intruder-vulnerability-scanner/
- CrowdStrike Pricing: https://www.crowdstrike.com/en-us/pricing/
- Cyberdesserts — OpenClaw Security Risks: https://blog.cyberdesserts.com/openclaw-malicious-skills-security/
- Detectify: https://detectify.com
- Digacore — Managed Cybersecurity for SMBs 2026: https://digacore.com/blog/managed-cybersecurity-services-smb-2026/
- Gurkha Technology — SMB Cybersecurity Solutions 2026: https://gurkhatech.com/cybersecurity-solutions-smb-2026/
- HostedScan: https://hostedscan.com
- Institutional Investor — OpenClaw Analysis: https://www.institutionalinvestor.com/article/openclaw-ai-agent-institutional-investors-need-understand-shouldnt-touch
- Intruder.io: https://www.intruder.io
- Kiteworks — Agentic AI Attack Surface: https://www.kiteworks.com/cybersecurity-risk-management/agentic-ai-attack-surface-enterprise-security-2026/
- OpenClaw Documentation — Raspberry Pi Setup: https://docs.openclaw.ai/platforms/raspberry-pi
- OpenClaw Wikipedia: https://en.wikipedia.org/wiki/OpenClaw
- pbxscience — OpenClaw Security Crisis Explained: https://pbxscience.com/openclaw-2026s-first-major-ai-agent-security-crisis-explained/
- Qualys SMB Solutions: https://www.qualys.com/subscriptions/smb
- Raspberry Pi Foundation — OpenClaw on Pi: https://www.raspberrypi.com/news/turn-your-raspberry-pi-into-an-ai-agent-with-openclaw/
- Sucuri (GoDaddy): https://sucuri.net
- Techaisle — SMB Security Predictions 2026: https://techaisle.com/blog/670-beyond-the-breach-techaisle-top-10-smb-mid-market-security-predictions-for-2026

---

*Document prepared March 21, 2026. This is a strategic business case, not a financial prospectus. All projections are estimates based on publicly available data and reasonable assumptions. The authors welcome scrutiny and correction.*
