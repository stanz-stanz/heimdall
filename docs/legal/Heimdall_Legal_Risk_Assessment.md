# Heimdall — Legal Risk Assessment: Vulnerability Scanning Without Consent in Denmark

**Research Memo — March 21, 2026**
**Status: Preliminary research for review by legal counsel. This document does not constitute legal advice.**

---

## The Question

Is it legal in Denmark to scan a business's website for security vulnerabilities without the website owner's prior consent?

## The Short Answer

It depends on *what kind* of scanning. There is a legally meaningful distinction between passively reading information a website voluntarily serves to any visitor, and actively sending crafted requests to probe for vulnerabilities. The first is almost certainly permissible. The second is a gray zone that requires consent to be safe.

---

## The Relevant Law

### Straffeloven §263, stk. 1 (Danish Penal Code — Hacking Provision)

Full text (Danish):

> *"Med bøde eller fængsel indtil 1 år og 6 måneder straffes den, der uberettiget skaffer sig adgang til en andens datasystem eller data, som er bestemt til at bruges i et datasystem."*

English: A fine or imprisonment up to 18 months for anyone who **without authorization** (uberettiget) gains access to another person's data system or data intended for use in a data system.

Under aggravating circumstances (e.g., intent to access trade secrets, systematic offenses), the penalty increases to up to 6 years imprisonment under §263, stk. 3.

Source: https://danskelove.dk/straffeloven/263

### The Key Legal Term: "Uberettiget" (Without Authorization)

The entire question turns on this word. A detailed legal analysis from Aalborg University describes it as occupying "a very central role" in determining criminal liability, noting that authorization can derive from explicit consent, but also from what can "reasonably be expected" (en rimelighedstest) given the circumstances.

Source: Aalborg University thesis — "Straffelovens §263, stk. 1 — En analyse af straffelovens værn mod hacking" (https://vbn.aau.dk/ws/files/305754822/Speciale_Straffelovens_263_stk._1.pdf)

### EU Directive 2013/40/EU (Attacks Against Information Systems)

Denmark transposed this directive into national law. Article 3 requires member states to criminalize "the access without right, to the whole or to any part of an information system ... committed by infringing a security measure." The Danish implementation maps primarily to §263.

Source: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013L0040

---

## The Authoritative Legal Commentary on This Specific Question

The ICLG Cybersecurity Laws and Regulations Report 2026 — Denmark chapter (authored by Danish legal practitioners) addresses unsolicited vulnerability scanning directly:

> *"Unsolicited penetration of an IT system (without permission from the owner) will — most likely — be considered a violation under section 263 of the Danish Penal Code."*

Source: https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark

The phrase **"most likely"** is significant. It indicates that even specialist practitioners consider the boundary unsettled.

---

## The Three Layers of Scanning Activity

Heimdall's operations span multiple types of scanning. Their legal risk profiles differ:

### Layer 1 — Passive Observation

**What it involves:** Reading HTTP response headers, HTML source code, meta generator tags, DNS records, SSL/TLS certificate details, and publicly referenced JavaScript/CSS files. This is the information any web browser receives when visiting a website. Technology fingerprinting tools (Wappalyzer, webanalyze, httpx) operate at this layer.

**Legal risk assessment:** Minimal. This data is voluntarily served by the website to any HTTP client. Search engines, web crawlers, and browser extensions perform identical operations at massive scale. The Aalborg University analysis suggests that where access to information can "reasonably be expected" — as with publicly served HTTP responses — the threshold for "uberettiget" is not met.

**Relevance to Heimdall:** This layer covers the lead generation pipeline (CMS detection, hosting identification, SSL status checks, technology fingerprinting). It also covers portions of the "first finding free" approach — identifying outdated CMS versions, expired SSL certificates, and exposed meta information.

### Layer 2 — Active Vulnerability Probing

**What it involves:** Sending crafted HTTP requests designed to detect specific vulnerabilities. Tools such as Nuclei (template-based vulnerability scanner), Nikto (web server scanner), and OWASP ZAP (dynamic application security testing) operate at this layer. These tools go beyond reading what the server voluntarily presents — they send requests specifically designed to test whether known vulnerabilities (CVEs) are exploitable.

**Legal risk assessment:** This is the gray zone. The ICLG commentary quoted above applies here. While these tools do not exploit vulnerabilities or extract data, they actively probe the system in ways the site owner did not invite. No Danish court ruling was found addressing this specific activity. However, the law is written broadly enough that a prosecutor could argue this constitutes gaining access to a data system without authorization.

**Supporting precedent from other jurisdictions:** A Finnish court convicted a 17-year-old for port scanning a bank. In the UK, the R v Cuthbert case (2005) resulted in conviction under the Computer Misuse Act for testing a charity website for a well-known vulnerability — even though no data was accessed or damaged, and the defendant's intent was benign.

Sources: Nmap legal guide (https://nmap.org/book/legal-issues.html), SCRIPTed journal analysis (https://script-ed.org/article/can-csirts-lawfully-scan-for-vulnerabilities/)

**Relevance to Heimdall:** This layer covers the core vulnerability scanning service — the weekly/daily scans that detect specific CVEs, misconfigurations, and exploitable weaknesses.

### Layer 3 — Exploitation / Penetration Testing

**What it involves:** Attempting to actually exploit a vulnerability — SQL injection, authentication bypass, privilege escalation.

**Legal risk assessment:** Clearly criminal without consent under §263. No ambiguity.

**Relevance to Heimdall:** Heimdall does not perform exploitation. This layer is outside scope.

---

## What We Could Not Find

The following would strengthen the legal analysis but were not identified in this research:

- A Danish court ruling specifically addressing external vulnerability scanning (as distinct from hacking or penetration testing)
- Danish regulatory guidance explicitly permitting or prohibiting good-faith external vulnerability scanning
- A Danish safe harbor provision for security research (comparable to the US DOJ's 2022 CFAA policy or the Dutch coordinated vulnerability disclosure framework)
- Guidance from Datatilsynet (Danish Data Protection Authority) or the Danish Centre for Cyber Security on this specific topic

---

## Practical Implications for Heimdall

### The lead generation pipeline can proceed.

Technology fingerprinting (Layer 1) reads publicly served information. This is functionally identical to visiting a website in a browser. The risk here is de minimis.

### The vulnerability scanning service requires written consent.

Active vulnerability probing (Layer 2) should only be performed after the site owner has provided explicit, documented authorization. This is not merely a best practice — it is the line between operating a security service and risking prosecution under §263.

### This aligns with the existing business model.

The proposed Heimdall service model already assumes client onboarding before active scanning begins. The "first finding free" approach relies on Layer 1 data (outdated CMS versions, SSL status, exposed technologies) — not on active vulnerability probes. The full Nuclei/Nikto scan runs only after the client subscribes and authorizes the service. The consent requirement does not break the business model; it confirms it.

### The white-label agency model needs attention.

When a web agency authorizes Heimdall to scan their clients' websites, the legal question is whether the agency has the authority to grant that consent on behalf of their clients. This depends on the agency's contractual relationship with each client. This specific point requires legal counsel review.

---

## Recommended Next Steps

1. **Engage a Danish IT/cybersecurity lawyer** to confirm the Layer 1 / Layer 2 distinction and its treatment under §263. Firms with relevant specialization include Plesner, Kromann Reumert, and Bech-Bruun.

2. **Have counsel draft or review a scanning authorization template** — a simple document the client signs before active scanning begins, granting explicit permission for Heimdall to perform external vulnerability scanning against specified domains.

3. **Obtain legal guidance on agency delegation** — whether a web agency can authorize scanning of their clients' sites under their existing service agreements, or whether each end client must consent independently.

4. **Monitor legislative developments.** The NIS2 Directive (implemented in Denmark via the Danish NIS Act, effective July 1, 2025) and ongoing EU cybersecurity regulatory evolution may clarify the status of authorized external scanning services.

---

## Addendum — Compliance Controls Implemented (March 22, 2026)

Since this assessment was written, the following technical and procedural controls have been implemented to enforce the Layer 1 / Layer 2 boundary:

### Valdí — Legal Compliance Agent

A programmatic compliance agent ("Valdí") now validates all scanning code before execution. Valdí operates at two gates:

- **Gate 1 (scan-type validation):** Every scanning function is reviewed against a documented set of rules (`SCANNING_RULES.md`) before it can execute. Valdí classifies the function's activities by Layer, confirms they do not exceed what the target's consent Level permits, and issues an approval token. If the function violates any rule, it is blocked with a structured explanation. Each review — approval or rejection — produces a timestamped forensic log with the full function source, reasoning, and rule citations.

- **Gate 2 (per-target authorisation):** Before each scan batch, Valdí confirms that the scan type has a valid approval token and that each target's consent level permits the scan's Layer. Targets without written consent are restricted to Layer 1.

Valdí's forensic logs are retained as evidence of due diligence. Rejection logs are preserved alongside approval logs — they demonstrate that the system catches and blocks non-compliant scanning code.

### robots.txt Compliance

A blanket rule has been adopted: if a target's `robots.txt` denies automated access, Heimdall skips the target entirely, regardless of Layer or consent Level. This goes beyond what §263 requires, but reduces friction and demonstrates respect for site operators' expressed preferences.

### Relevance to Counsel Consultation

These controls are documented in three project files that should accompany this memo when presented to legal counsel:

| Document | Contents |
|----------|----------|
| `SCANNING_RULES.md` | Authoritative rules for what is allowed/forbidden at each Layer and Level |
| `docs/agents/legal-compliance/SKILL.md` | Valdí's full specification — gates, forensic log format, approval tokens, consent registry |
| `docs/legal/Valdi_Implementation_Actions.md` | Implementation checklist for the compliance system |

### Additional Questions for Counsel (Arising from Implementation)

5. Does the existence of a programmatic compliance layer (Valdí) with timestamped forensic logs reduce liability if an agent-generated scanning function inadvertently crosses the Layer 1 / Layer 2 boundary?
6. What audit trail documentation would a Danish court or prosecutor expect to see to demonstrate due diligence in automated external scanning?

---

## Sources

| Source | URL |
|--------|-----|
| Straffeloven §263 (full text) | https://danskelove.dk/straffeloven/263 |
| ICLG Cybersecurity Report 2026 — Denmark | https://iclg.com/practice-areas/cybersecurity-laws-and-regulations/denmark |
| Aalborg University thesis on §263 stk. 1 | https://vbn.aau.dk/ws/files/305754822/Speciale_Straffelovens_263_stk._1.pdf |
| EU Directive 2013/40/EU | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013L0040 |
| Lexology — Cybersecurity in Denmark | https://www.lexology.com/library/detail.aspx?g=a2b86bca-08e1-479d-9a9a-46535babecd9 |
| SCRIPTed — Can CSIRTs Lawfully Scan? | https://script-ed.org/article/can-csirts-lawfully-scan-for-vulnerabilities/ |
| Nmap — Legal Issues | https://nmap.org/book/legal-issues.html |
| Cybernews — Port Scanning Legality | https://cybernews.com/editorial/port-scanning-legality-explained/ |
| Danish Police — Crimes Against Digital Devices | https://politi.dk/en/report-a-crime/crimes-against-digital-devices |

---

*This document presents legal research, not legal advice. All conclusions are preliminary and subject to confirmation by qualified Danish legal counsel. The author is not a lawyer.*
