# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:00:00Z
- **Scan type:** SSL certificate check via TLS handshake
- **Scan type ID:** ssl_certificate_check
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 9446c250-37c3-4f36-bc82-e2be64ee9381
- **Function hash:** sha256:92913351a212ed6abcb6d9a8a9614c1205140f15cd2bfbf267abb06f4e6c30b8
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def _check_ssl(domain: str) -> dict:
    """Check SSL certificate details for a domain."""
    result = {"valid": False, "issuer": "", "expiry": "", "days_remaining": -1}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as sock:
            sock.settimeout(REQUEST_TIMEOUT)
            sock.connect((domain, 443))
            cert = sock.getpeercert()

        not_after = cert.get("notAfter", "")
        if not_after:
            expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            result["expiry"] = expiry_dt.strftime("%Y-%m-%d")
            result["days_remaining"] = (expiry_dt - datetime.now(timezone.utc)).days
            result["valid"] = result["days_remaining"] > 0

        issuer = dict(x[0] for x in cert.get("issuer", []))
        result["issuer"] = issuer.get("organizationName", issuer.get("commonName", ""))

    except Exception as e:
        log.debug("SSL check failed for %s: %s", domain, e)

    return result
```

**File:** `pipeline/scanner.py` (lines 41-64)

## Tools Invoked

- Python `ssl` stdlib module (standard TLS handshake)
- Python `socket` stdlib module (TCP connection)

No external scanning tools invoked.

## URLs/Paths Requested

- TCP connection to `{domain}:443` for TLS handshake — no HTTP path requested

## robots.txt Handling

**N/A.** This function performs a standard TLS handshake (protocol-level negotiation), not an HTTP request. robots.txt governs HTTP user agents and crawling behaviour; it does not apply to TLS certificate retrieval. Every browser performs this same handshake on every HTTPS connection.

## Reasoning

This function performs a standard TLS handshake to port 443 — the same operation every web browser performs when visiting an HTTPS site. It reads the SSL certificate presented by the server (expiry date, issuer, validity). This is explicitly allowed under SCANNING_RULES.md Level 0: "SSL/TLS certificate data — certificate chain, expiry date, issuer, SANs, protocol versions. Obtained via standard TLS handshake."

The function:
1. Does NOT send any HTTP requests
2. Does NOT probe any paths
3. Does NOT use any external scanning tools
4. Does NOT attempt to identify vulnerabilities — only reads the publicly presented certificate
5. Does NOT perform any Layer 2 or Layer 3 activity

All activity is within Layer 1 (passive observation of publicly served data). The function's actual behaviour matches its declared Level 0 requirements.

**Note:** This is a private helper function (`_` prefix). It must only be invoked through the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level.

## Violations

None.
