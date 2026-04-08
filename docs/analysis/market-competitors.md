# Market Competitors — Pricing & Feature Reference

> Permanent reference for competitive positioning. Updated as new competitors are analysed.
> Pricing converted to Danish kroner (kr.) where applicable.

---

## Direct Competitors

### Intruder.io

- **Website:** https://www.intruder.io
- **Positioning:** Hybrid vulnerability scanning + EASM for lean security teams
- **Best for:** Non-experts who need "plain English" advice on what to fix
- **Pricing:** ~740 kr./month (plans start at roughly $99/month for five licenses)
- **Delivery:** Web dashboard + Slack/Jira integrations
- **Founded:** 2015, GCHQ Cyber Accelerator alumni, 1,000+ customers
- **Key features:** Risk trends, cyber hygiene scoring, audit-ready report generation, "Emerging Threat" scans (proactive checks when a new high-profile vulnerability is discovered globally)
- **SMB gap:** Dashboard requires security knowledge to interpret. No messaging-based delivery. Adding Telegram/WhatsApp would require rebuilding their entire communication layer — notification is not delivery. Claims "plain English" but still delivers via dashboard, not where the owner already is.

### Detectify

- **Website:** https://detectify.com
- **Positioning:** Payload-based scanning that finds vulnerabilities automated scanners often miss
- **Best for:** Online-heavy businesses (e-commerce, SaaS) needing deep application testing
- **Pricing:** ~610 kr./month (app scanning); ~2,050 kr./month (surface monitoring). Starts at approximately $430/month for 25 subdomains.
- **Delivery:** Web dashboard
- **Key features:** Application scanning, surface monitoring, crowdsourced security research that keeps the tool updated with the latest attacker techniques
- **SMB gap:** Enterprise-oriented pricing and complexity. No plain-language interpretation. No messaging delivery. A restaurant owner does not need "payload-based" deep application testing — they need to know their booking plugin is outdated.

### HostedScan

- **Website:** https://hostedscan.com
- **Pricing:** Free tier; paid from ~215 kr./month
- **Delivery:** Web dashboard + API
- **Key features:** Free tier with basic scanning, API access
- **SMB gap:** Dashboard requires the user to understand CVSS scores and technical output. If you can navigate dashboards and interpret findings, HostedScan is cheaper — but for the target SMB owner, the dashboard might as well not exist. Heimdall's Watchman tier (199 kr./month) undercuts their paid plan.

### Beagle Security

- **Website:** https://beaglesecurity.com
- **Pricing:** ~885 kr./month
- **Delivery:** Web dashboard
- **Key features:** Automated penetration testing, compliance reports
- **SMB gap:** Price and complexity. Dashboard-only delivery.

### Astra Security

- **Website:** https://www.getastra.com
- **Pricing:** Custom (~740–2,225 kr./month)
- **Delivery:** Web dashboard + manual pentest
- **Key features:** Automated scanning + manual penetration testing, WAF, compliance
- **SMB gap:** Enterprise pricing. Manual pentest component is overkill for SMBs.

### UpGuard BreachSight

- **Website:** https://www.upguard.com/product/breach-risk
- **Positioning:** Security scoring platform for your company and your vendors
- **Best for:** Small businesses that need to prove security posture to larger clients or insurance companies
- **Pricing:** Entry-level from ~22,300 kr./year ($3,000/year)
- **Delivery:** Web dashboard + security score reports
- **Key features:** Security scoring, vendor risk management, typosquatting detection (alerts if someone creates a fake version of your domain to phish your customers)
- **SMB gap:** $3,000/year is 15x Heimdall Watchman. Designed for businesses that already care about security posture (supply chain compliance) — not for the SMB owner who doesn't know they have a problem yet. Dashboard-based. No messaging delivery. No Danish localisation.

### TRaViS EASM

- **Website:** https://travisasm.com
- **Positioning:** "Silent guardian" EASM — markets itself as cost-effective protection for SMEs
- **Best for:** Security practitioners (SOC analysts, CISOs, pentesters, MSSPs) monitoring for leaked credentials and dark web threats
- **Pricing:** $2,999/year (~22,500 kr.) Hunter plan; $4,999/year (~37,400 kr.) Researcher plan; Enterprise custom
- **Billing model:** Annual, scan-count limited (100–200 on-demand scans/year). Not continuous monitoring.
- **Delivery:** Web dashboard (raw security data — CVE IDs, asset lists, credential dumps)
- **Key features:** Subdomain discovery, CVE detection, exposed API key detection, compromised credential / infostealer detection, dark web monitoring, JavaScript SAST, custom Nuclei templates (Researcher+), Google Dorks, AI code fixes (Enterprise only)
- **Target market reality:** Despite "SME" marketing copy, pricing and feature language targets security practitioners and MSSPs. The buyer already understands EASM.
- **MSSP angle:** Actively courts MSSPs as a channel — indirect competitive threat if an MSSP resells managed service to Danish SMBs using TRaViS as backend
- **SMB gap:** Cheapest plan is 113x Heimdall Watchman. Dashboard requires security literacy. No plain-language interpretation. No messaging delivery. No Danish localisation. No European presence. A barbershop owner would never encounter this product.

### Sucuri (GoDaddy)

- **Website:** https://sucuri.net
- **Pricing:** ~1,480 kr./year
- **Delivery:** Web dashboard + WAF
- **Key features:** Website firewall, malware cleanup, security monitoring
- **SMB gap:** Bundled with WAF (different product category). Dashboard still requires interpretation. Also available as a WordPress plugin (secondary competitor — requires technical owner to understand what the plugin shows).

---

## Mid-Market EASM

### Attaxion

- **Website:** https://attaxion.com
- **Origin:** Delaware, USA (startup registration). Founded ~2023.
- **Tagline:** "Agentless Exposure Management with #1 Asset Coverage"
- **Pricing:**

| Plan | Monthly | Annual | Assets |
|------|---------|--------|--------|
| Starter | ~903 kr./month | ~9,030 kr./year | Up to 40 |
| Plus | ~2,443 kr./month | ~24,430 kr./year | Up to 120 |
| Business | ~6,643 kr./month | ~66,430 kr./year | Up to 360 |
| Enterprise | Custom | Custom | Custom |

- **Billing model:** Per-asset (domains, subdomains, IPs count; ports/emails/certs are free). 30-day free trial.
- **Delivery:** SaaS dashboard (app.attaxion.com) + email alerts + Slack + Jira + REST API. No messaging-based delivery.
- **Target market:** Mid-market security teams ("lean security teams"), not SMBs. Language targets security analysts and IT directors.
- **Products:**
  - **Attaxion Core** — main EASM platform (discovery, assessment, remediation, monitoring)
  - **Black Box Scanner** — DAST (SQLi, XSS, SSRF, insecure headers, OWASP Top 10)
  - **Asset Finder** — free tool at assetfinder.attaxion.com (lead generation, like Heimdall's "first finding free")
- **Scanning capabilities:**
  - Passive + active subdomain discovery (DNS, CT logs, WHOIS, reverse DNS)
  - Cloud provider scanning (AWS, Azure, GCP, DigitalOcean)
  - Port scanning with service detection
  - Web crawling + screenshot capture
  - CVE + CWE + EUVD + CISA KEV + EPSS vulnerability scoring
  - AI-powered prioritisation
  - NetFlow-based agentless traffic monitoring (genuinely novel — flow metadata from internet nodes, no agents)
  - Domain brand impersonation monitoring (typosquatting, every 5 minutes, 365-day lookback) — Business/Enterprise only
- **MSP/MSSP program:** Multi-tenant partner architecture, per-asset billing per customer
- **SMB gap:** Cheapest plan (903 kr./month) is 4.5x Heimdall Watchman. Requires security staff to operate dashboard. Self-service tool, not a managed service. No Danish localisation.
- **What they have that Heimdall doesn't:**
  - NetFlow-based traffic monitoring
  - Domain brand impersonation / typosquatting detection
  - EUVD database integration (alongside CVE/CWE)
  - EPSS (Exploit Prediction Scoring System) scoring
  - Cloud asset discovery (AWS/Azure/GCP)
  - Black box DAST scanner
  - Screenshot capture of discovered services
  - MSP/MSSP multi-tenant partner program
- **What Heimdall has that they don't:**
  - Messaging-native delivery (Telegram)
  - AI interpretation in plain language for non-technical owners
  - Danish-first localisation
  - Managed service (zero setup for client)
  - SMB-accessible pricing (199–399 kr./month)
  - Deep WordPress-specific detection (plugin versions, REST API namespaces, CSS signatures)
  - Digital twin approach for safe Layer 2 testing
  - Prospect discovery from CVR data (clients don't provide assets — Heimdall finds them)

---

## Enterprise EASM (Not Direct Competitors)

These validate the EASM category exists but serve enterprises, not SMBs. They are all moving upmarket, not down.

### Outpost24

- **Origin:** Swedish, Danish subsidiary (CVR 35517936)
- **Pricing:** 40,000–100,000 kr./year
- **Delivery:** Enterprise platform
- **Relevance:** Validates SMB pricing gap for SIRI application. A carpenter in Vejle will not pay enterprise EASM prices.

### Qualys

- **Website:** https://www.qualys.com
- **Pricing:** Enterprise (unstated publicly)
- **Delivery:** Platform with "interactive, customisable widgets," "drill-down to details on events," and "QQL queries"
- **Relevance:** Exemplar of dashboard complexity that is impenetrable for non-technical users.

### CrowdStrike (Falcon Surface)

- **Website:** https://www.crowdstrike.com
- **Pricing:** Enterprise (unstated publicly)
- **Delivery:** Platform
- **Relevance:** Endpoint security (Falcon Go) is complementary to Heimdall — endpoint protects devices, Heimdall protects the website. Not overlapping.

### Censys ASM

- **Website:** https://censys.com
- **Pricing:** Enterprise (unstated publicly)
- **Delivery:** Platform + API
- **Relevance:** Enterprise EASM category validation only.

### Trend Micro (Cyber Risk Exposure Management)

- **Website:** https://www.trendmicro.com
- **Pricing:** Enterprise (unstated publicly)
- **Delivery:** Platform
- **Relevance:** Enterprise EASM category validation only.

---

## Tool / Benchmark References (Not Competitors)

### HackerTarget

- **Pricing:** Free tier; $10/month paid
- **Relevance:** Detection quality benchmark. Their free WordPress scan detected 9 plugins with versions when Heimdall detected 6 (gap since addressed). Manual OSINT assessment priced at ~$2,000 — Heimdall automates this at SMB prices. Rejected as a data source (adds dependency, couples pipeline to third-party uptime).

### WPScan (Automattic)

- **Relevance:** Former tool dependency (replaced by free WPVulnerability API). Cost elimination cited in SIRI financial projections.

### Wordfence / Patchstack

- **Relevance:** WordPress security plugins (secondary competitors in the "DIY security" category — require technical owner to interpret). Also used as upstream data sources via WPVulnerability API and RSS CVE feeds.

---

## Heimdall Positioning Summary

| | Heimdall (Watchman) | Heimdall (Sentinel) | Cheapest direct | Cheapest mid-market |
|---|---|---|---|---|
| **Price** | 199 kr./month | 399 kr./month | ~215 kr./month (HostedScan) | ~903 kr./month (Attaxion) |
| **Delivery** | Telegram (plain Danish) | Telegram (plain Danish + fix instructions) | Web dashboard | Web dashboard + Slack/Jira |
| **Interpretation** | AI, non-technical language | AI, non-technical language | Raw CVSS | CVSS + EPSS + AI prioritisation |
| **Setup** | Zero — no dashboard login | Zero | Account + dashboard | Account + asset configuration |
| **Target** | SMB owners (no security staff) | SMB owners (no security staff) | Small teams with some security knowledge | Lean security teams |

### Sentinel vs. Top 3 Equivalent Competitors

Equivalence criteria: external attack surface scanning + vulnerability reporting as core service. Excludes WAFs (Sucuri), pentest services (Astra, Beagle), vendor risk platforms (UpGuard), deep DAST (Detectify), and enterprise EASM.

| Capability | **Heimdall Sentinel** | **Intruder.io** | **HostedScan** | **Attaxion Starter** |
|---|---|---|---|---|
| **Price** | 399 kr./month | ~740 kr./month | ~215 kr./month | ~903 kr./month |
| **Price vs. Sentinel** | — | 1.9x | 0.5x | 2.3x |
| **Target user** | SMB owner (no security staff) | Lean security team | Small team with some security knowledge | Security analyst / IT director |
| **Delivery channel** | Telegram message | Web dashboard + Slack/Jira | Web dashboard + API | Web dashboard + Slack/Jira + email |
| **Finding interpretation** | AI plain-language + fix instructions | "Plain English" in dashboard | Raw CVSS scores | CVSS + EPSS + AI prioritisation |
| **Setup required** | Zero (managed service) | Account + dashboard config | Account + dashboard config | Account + asset configuration |
| **Language** | Danish-first (per-client language) | English only | English only | English only |
| **Subdomain discovery** | Yes (subfinder, DNS, CT logs) | Yes | Limited | Yes (DNS, CT, WHOIS, reverse DNS) |
| **Port scanning** | Yes (Nmap top-100 + 13 critical) | Yes | Yes (OpenVAS, Nmap) | Yes |
| **HTTP header analysis** | Yes (security headers, TLS, server) | Yes | Yes | Yes |
| **WordPress-specific detection** | Deep (plugin versions, REST API, CSS signatures, outdated checks) | Generic CMS detection | Generic | Generic CMS detection |
| **CVE enrichment** | WPVulnerability API + CISA KEV + RSS feeds | Yes (CVE database) | Yes (NVD) | CVE + CWE + EUVD + CISA KEV + EPSS |
| **Emerging threat scans** | RSS CVE watch (Wordfence, CISA, Bleeping Computer) | Yes (proactive on new global vulns) | No | No |
| **Digital twin** | Yes (Layer 1 — scans local replica, not live target) | No | No | No |
| **Cloud asset discovery** | No | Yes (AWS, Azure, GCP) | No | Yes (AWS, Azure, GCP, DO) |
| **Typosquatting detection** | No | No | No | Yes (Business+ only) |
| **Traffic monitoring** | No | No | No | Yes (NetFlow-based) |
| **DAST / app scanning** | No | Limited | No | Yes (Black Box Scanner) |
| **Compliance reports** | No | Yes (audit-ready) | No | No |
| **API access** | No (managed service) | Yes | Yes | Yes |
| **GDPR-aware content** | Yes (per-finding, Danish law) | No | No | No |
| **Prospect discovery** | Yes (CVR → domain → scan) | No (client provides assets) | No (client provides assets) | Free Asset Finder tool |

**Where Sentinel wins:** Price (cheapest after HostedScan, but with interpretation). Only product that delivers interpreted findings via messaging to a non-technical owner in their language. Zero-setup managed service. Deep WordPress pipeline. Digital twin for CVE detection against a local replica (Layer 1, no live target interaction).

**Where Sentinel loses:** No cloud asset discovery, no compliance reports, no API, no typosquatting detection, no DAST. Narrower scanning depth than Attaxion.

**HostedScan price note:** HostedScan is cheaper but delivers raw CVSS scores via dashboard. The 184 kr./month delta buys AI interpretation, fix instructions, messaging delivery, and zero setup — the entire value proposition.

### Durable Differentiators

1. **Messaging-native delivery** — Telegram today, WhatsApp/SMS later. No dashboard to learn.
2. **AI interpretation in plain language** — Findings explained for business owners, not security engineers.
3. **Price floor** — Below or at parity with cheapest paid competitor, with fundamentally different delivery.
4. **Danish-first** — Localised for Danish SMBs, culturally adapted communication (Janteloven-aware, craftsperson tone).

---

*Last updated: 2026-04-08*
