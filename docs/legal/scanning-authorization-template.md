# Scanning Authorization Template — Heimdall EASM

**Status:** DRAFT — awaiting review by Danish IT/cybersecurity lawyer
**Prepared:** 2026-04-01
**For meeting:** Week of 2026-04-14 (see legal briefing Q6, Q12)

This template is a starting point for legal counsel to refine. It addresses the elements required by Straffeloven SS263 (scope, identity, duration, explicit authorization), GDPR Article 28 (data processing), and the Heimdall consent validation system. The lawyer should verify that the form and language satisfy Danish evidentiary requirements.

---

### AUTHORIZED SECURITY SCANNING AGREEMENT

**Agreement number:** ___________________

---

#### 1. PARTIES

**Service Provider (Data Processor):**

| | |
|---|---|
| Company name | Heimdall |
| CVR number | [To be inserted after SIRI approval and company registration] |
| Address | [Address] |
| Contact person | Federico Alvarez |
| Email | [Email] |

**Client (Data Controller):**

| | |
|---|---|
| Company name | _____________________ |
| CVR number | _____________________ |
| Address | _____________________ |
| Contact person (name) | _____________________ |
| Position/role | _____________________ |
| Email | _____________________ |

---

#### 2. BACKGROUND AND PURPOSE

This agreement establishes the terms under which Heimdall will perform external security scanning of the Client's web infrastructure. The scanning is intended to identify security vulnerabilities, misconfigurations, and outdated software in the Client's publicly accessible digital assets.

This authorization explicitly removes the element of "uberettiget" (without authorization) under Straffeloven SS263, stk. 1, in that the Client hereby grants Heimdall authorized access to perform the scanning activities described below within the agreed scope.

---

#### 3. AUTHORIZED DOMAINS

Heimdall is authorized exclusively to scan the following domains and subdomains. Domains not listed here are NOT covered by this authorization.

| # | Domain |
|---|--------|
| 1 | _____________________ |
| 2 | _____________________ |
| 3 | _____________________ |
| 4 | _____________________ |
| 5 | _____________________ |

Additional domains may be added via a written addendum signed by both parties.

Note: Authorization for a domain (e.g., `company.dk`) does NOT automatically cover subdomains (e.g., `shop.company.dk`). Each subdomain must be listed explicitly.

---

#### 4. SCANNING SCOPE

The Client authorizes the following scanning layers (check one):

- [ ] **Layer 1 (Passive observation):** Reading publicly available information — HTTP headers, HTML source code, DNS lookups, SSL/TLS certificate data, technology fingerprints. Equivalent to what a normal browser receives when visiting the website.

- [ ] **Layer 1 + Layer 2 (Active scanning):** Everything in Layer 1, plus: template-based vulnerability scanning (Nuclei), port scanning (Nmap), CMS detection (CMSeek), and other active probes within the agreed scope. These tools send targeted requests beyond what a normal visitor would generate. WordPress plugin and core CVE enrichment is performed via lookups against the public WPVulnerability API — no requests are sent to the Client's systems for this enrichment.

**Layer 3 (Exploitation) is ALWAYS excluded.** Heimdall will never exploit discovered vulnerabilities, regardless of this agreement's scope.

---

#### 5. WHAT HEIMDALL WILL DO

Within the agreed scope, Heimdall will:

- Perform external security scanning of the authorized domains using open source tools
- Identify known vulnerabilities (CVEs), outdated software, missing security headers, and misconfigurations
- Generate security reports with findings and recommendations in Danish
- Store scan results securely and encrypted
- Respect robots.txt rules — if an authorized domain's robots.txt denies automated access, Heimdall will halt scanning of that domain and inform the Client
- Rate-limit all scanning to avoid impacting server performance

---

#### 6. WHAT HEIMDALL WILL NOT DO

Under no circumstances will Heimdall:

- Exploit discovered vulnerabilities (no SQL injection, no authentication bypass, no privilege escalation)
- Perform denial-of-service attacks or overload servers
- Attempt to log in, test credentials, or perform brute force attacks
- Extract, modify, or delete data from the Client's systems
- Scan domains not listed in Section 3
- Perform scanning beyond the selected layer in Section 4
- Share scan results with third parties without the Client's written consent

---

#### 7. DURATION

This agreement takes effect on: _____________________ (date)

This agreement expires on: _____________________ (date)

OR:

- [ ] This agreement remains valid until revoked in writing by either party (see Section 11).

Upon expiry, a new agreement must be signed before scanning can resume.

---

#### 8. DATA HANDLING AND GDPR

##### 8.1 Roles

Under this agreement, the Client acts as **data controller** and Heimdall acts as **data processor** pursuant to GDPR Article 28.

##### 8.2 Data collected

Heimdall collects and processes the following types of technical data:

- HTTP headers and server information
- CMS and software versions
- SSL/TLS certificate details
- DNS configuration
- Identified vulnerabilities and misconfigurations
- Technology fingerprints (plugins, frameworks, tools)

Personal data (e.g., email addresses in WHOIS records, names in SSL certificates) may be incidentally present in collected data.

##### 8.3 Purpose

Data is processed solely for the purpose of delivering security assessments and reports to the Client.

##### 8.4 Retention

Scan data is retained for a maximum of _____ months after this agreement's termination. After this period, all data is deleted.

OR:

- [ ] Data is deleted within 30 days of agreement termination.

##### 8.5 Security measures

Heimdall implements appropriate technical and organizational measures pursuant to GDPR Article 32, including:

- Encryption of stored scan results
- Access controls on scan data
- Audit trails for all scanning activities (Valdí forensic log files)
- Secure deletion upon agreement termination

##### 8.6 Sub-processors

Heimdall does not use sub-processors for the processing of Client scan data unless the Client provides written consent.

##### 8.7 Data Processing Agreement (DPA)

The parties may attach a separate Data Processing Agreement (DPA) in accordance with GDPR Article 28(3) as an addendum to this agreement.

- [ ] Separate DPA attached as Annex A.

---

#### 9. LEGAL REFERENCE

This authorization is specifically intended to satisfy the requirements of **Straffeloven SS263, stk. 1**, which criminalizes unauthorized access to another person's data system. By signing this agreement, the Client confirms that Heimdall's scanning activities within the agreed scope are authorized and therefore do NOT constitute unauthorized access.

The Client confirms that:

- The Client is the owner of, or authorized representative for, the domains listed in Section 3
- The Client has the right to authorize external security scanning of these domains
- This authorization is given voluntarily and with full knowledge of the nature and scope of the scanning

---

#### 10. LIMITATION OF LIABILITY

Heimdall endeavors to perform scans carefully and professionally, but does not guarantee:

- That all vulnerabilities will be identified
- That there will be no false positives in reports
- That scanning will not cause any unforeseen impact on server performance

Heimdall is not liable for damages caused by third-party exploitation of vulnerabilities identified in reports, provided that reports are delivered securely and exclusively to the Client.

---

#### 11. TERMINATION AND REVOCATION

The Client may revoke this authorization at any time by written notice to Heimdall (email is sufficient). Upon revocation:

- Heimdall will halt all scanning activities within 24 hours
- Ongoing scans will be interrupted immediately
- Client scan data will be deleted in accordance with Section 8.4
- The revocation will be confirmed in writing by Heimdall

---

#### 12. SIGNATURES

**For the Client:**

| | |
|---|---|
| Name | _____________________ |
| Position | _____________________ |
| Date | _____________________ |
| Signature | _____________________ |

**For Heimdall:**

| | |
|---|---|
| Name | Federico Alvarez |
| Position | Founder |
| Date | _____________________ |
| Signature | _____________________ |

---

#### 13. ANNEXES

- [ ] Annex A: Data Processing Agreement (DPA)
- [ ] Annex B: Technical description of scanning tools

---

## Notes for Legal Counsel

This template should be reviewed for:

1. **SS263 compliance** — Does the authorization language adequately establish "berettiget adgang" (authorized access)? Is the scope definition (domains, layers, duration) sufficient to withstand a challenge?

2. **Who can sign** — The template does not currently restrict who on the client side can sign. Legal briefing Q9 asks whether the CVR-registered legal representative is required, or whether any person with administrative control over the domain suffices, and also covers the agency delegation case. The signer's role is currently recorded as informational only in the technical system. Counsel should advise on whether role validation is needed.

3. **Subdomain scope** — The template requires explicit listing of each subdomain (no wildcards). Legal briefing Q11 asks whether `*.company.dk` would be legally sufficient. The conservative default (explicit listing) is implemented in the consent validation system.

4. **Electronic consent** — Legal briefing Q12 asks whether click-to-accept with audit logging carries the same weight as a wet-ink signature. The template assumes physical or digital signature. Counsel should advise on acceptable electronic alternatives.

5. **DPA sufficiency** — Section 8 includes GDPR Article 28 provisions inline. Counsel should advise whether a separate, standalone DPA is required or whether the inline provisions are sufficient for Heimdall's processing activities.

6. **Agency delegation** — If a web agency signs on behalf of their clients, does this template need modification? Legal briefing Q9 covers agency delegation as part of the consent-authority question. If delegation is valid, the template may need a clause for agency authorization with evidence of delegated authority from the end client.

7. **robots.txt contradiction** — Section 5 states Heimdall will respect robots.txt even with consent. This means a client could sign a scanning authorization, but if their robots.txt denies automated access, Heimdall will not scan and will notify the client. Counsel should confirm this approach is appropriate.
