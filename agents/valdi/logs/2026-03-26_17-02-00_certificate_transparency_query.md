# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-26T17:02:00Z
- **Scan type:** Certificate Transparency log query via crt.sh API
- **Scan type ID:** certificate_transparency_query
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** a1b2c3d4-3333-4aaa-bbbb-crtsh00000001
- **Function hash:** sha256:6e5ff7917ce1d26f5a4957d2eb8e8a7dfb80724423a2d8aeb0ede837bd2afd0a
- **Triggered by:** Claude Code (new tool integration)

## Tools Invoked

- Python `requests` library (HTTP GET to crt.sh API)
- No external CLI tools

## URLs/Paths Requested

- `https://crt.sh/?q=%.{domain}&output=json` — queries the crt.sh Certificate Transparency log search API
- Requests go to crt.sh (a third-party public service), NOT to the target's infrastructure
- Rate-limited: 1-second delay between requests per CRT_SH_DELAY config

## robots.txt Handling

**N/A.** No HTTP requests are sent to the target's web server. crt.sh is a third-party public Certificate Transparency log aggregator operated by Sectigo. Querying it is equivalent to searching a public database — the target's robots.txt does not govern access to third-party services.

## Reasoning

Certificate Transparency (CT) is a public, append-only log of all SSL/TLS certificates issued by participating Certificate Authorities. crt.sh is a free public search interface for these logs. Querying it reveals which certificates have been issued for a domain — this is public data by design (CT exists specifically to make certificate issuance transparent).

This is explicitly allowed under SCANNING_RULES.md Level 0: "Subdomain enumeration via passive sources — certificate transparency logs, DNS datasets, search engine results. No direct queries to the target's infrastructure beyond DNS." and "Third-party public indexes — querying public databases or search engines for information about the target."

The function:
1. Iterates through domains, querying crt.sh API for each
2. Parses JSON response — extracts certificate common_name, issuer, not_before, not_after
3. Deduplicates by common_name
4. Returns dict of domain → [certificates]
5. Rate-limits requests (CRT_SH_DELAY between queries)
6. Gracefully handles API errors (returns empty dict for failed domains)
7. Does NOT send any requests to the target's infrastructure
8. Does NOT perform any Layer 2 or Layer 3 activity

All activity is within Layer 1 (querying a third-party public index).

## Violations

None.
