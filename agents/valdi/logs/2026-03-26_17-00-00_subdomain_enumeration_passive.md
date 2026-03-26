# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-26T17:00:00Z
- **Scan type:** Subdomain enumeration via passive sources (CT logs, DNS datasets)
- **Scan type ID:** subdomain_enumeration_passive
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** a1b2c3d4-1111-4aaa-bbbb-subfinder00001
- **Function hash:** sha256:c77968b13596d827a0fec931b455c607a71b7b6dbfa8b486ca0e3858385244a8
- **Triggered by:** Claude Code (new tool integration)

## Tools Invoked

- `subfinder` CLI (ProjectDiscovery, MIT license)
- CLI flags: `-dL <domains.txt> -json -silent -all`

## URLs/Paths Requested

- No HTTP requests to target infrastructure
- subfinder queries third-party passive sources: Certificate Transparency logs, DNS datasets, search engine caches, passive DNS databases
- Standard DNS resolution for discovered subdomains

## robots.txt Handling

**N/A.** subfinder does not make HTTP requests to the target's web server. It queries third-party data sources (CT logs, DNS datasets) that have already indexed the target's publicly available DNS and certificate records. robots.txt governs HTTP crawling behaviour on the target's server — it does not apply to querying external databases about the target.

## Reasoning

subfinder discovers subdomains by querying passive data sources — Certificate Transparency logs (via crt.sh, Censys, etc.), passive DNS databases, and search engine caches. It does NOT send any requests to the target's infrastructure beyond standard DNS A/AAAA record lookups to confirm resolution.

This is explicitly allowed under SCANNING_RULES.md Level 0: "Subdomain enumeration via passive sources — certificate transparency logs, DNS datasets, search engine results. No direct queries to the target's infrastructure beyond DNS." subfinder is also listed in the Level 0 Allowed Tools table.

The function:
1. Writes domain list to temp file, runs subfinder as subprocess
2. Parses JSON output — each line contains a discovered subdomain and its source
3. Groups results by parent domain
4. Returns dict of domain → [subdomains]
5. Gracefully skips if subfinder is not installed (returns empty dict)
6. Does NOT probe any paths on the target
7. Does NOT send crafted requests
8. Does NOT perform any Layer 2 or Layer 3 activity

All activity is within Layer 1 (passive observation via third-party data sources).

## Violations

None.
