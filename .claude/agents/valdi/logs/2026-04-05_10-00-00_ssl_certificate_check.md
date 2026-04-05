# Valdi Scan-Type Validation

- **Timestamp:** 2026-04-05T10:00:00Z
- **Scan type:** SSL certificate check via TLS handshake (re-validation)
- **Scan type ID:** ssl_certificate_check
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 9446c250-37c3-4f36-bc82-e2be64ee9381 (retained — same scan type, code-only change)
- **Function hash:** sha256:e7d48a879161d827ecaf73b9ca31ee03bfacb1266fa3e994c4726eb92dee1b54
- **Previous hash:** sha256:e83c524bc9670743dec22bd800ee69ac08d1538dd44ff9a687ce9064bf8800bc
- **Triggered by:** Federico (manual re-validation request due to hash invalidation)

## Reason for Re-Validation

Function source code was modified, invalidating the previous approval hash. The approval token `9446c250-37c3-4f36-bc82-e2be64ee9381` (issued 2026-03-22) was invalidated by hash mismatch. A full Gate 1 review is required before the scan type can execute again.

## Function Reviewed

```python
def _check_ssl(domain: str) -> dict:
    """Check SSL certificate details for a domain."""
    result = {
        "valid": False, "issuer": "", "expiry": "", "days_remaining": -1,
        "tls_version": "", "tls_cipher": "", "tls_bits": 0,
    }
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as sock:
            sock.settimeout(REQUEST_TIMEOUT)
            sock.connect((domain, 443))

            result["tls_version"] = sock.version() or ""
            cipher_info = sock.cipher()
            if cipher_info:
                result["tls_cipher"] = cipher_info[0]
                result["tls_bits"] = cipher_info[2]

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
        logger.debug("SSL check failed for {}: {}", domain, e)

    return result
```

**File:** `src/prospecting/scanner.py` (lines 73-106)

## Changes Since Last Approval

Three new lines added after `sock.connect()`, before the existing `sock.getpeercert()` call:

```python
result["tls_version"] = sock.version() or ""
cipher_info = sock.cipher()
if cipher_info:
    result["tls_cipher"] = cipher_info[0]
    result["tls_bits"] = cipher_info[2]
```

These call `ssl.SSLSocket.version()` and `ssl.SSLSocket.cipher()` — Python stdlib accessor methods that read metadata from the already-negotiated TLS session. No new network connection. No new outbound request. No additional data sent to the target.

The result dict was also expanded with three new keys: `tls_version` (str), `tls_cipher` (str), `tls_bits` (int).

## Tools Invoked

- Python `ssl` stdlib module (standard TLS handshake — unchanged)
- Python `socket` stdlib module (TCP connection — unchanged)

No external scanning tools invoked. No new tools added.

## URLs/Paths Requested

- TCP connection to `{domain}:443` for TLS handshake — no HTTP path requested (unchanged)

No new network requests. The additions read from the already-open socket object.

## robots.txt Handling

**N/A.** This function performs a standard TLS handshake (protocol-level negotiation), not an HTTP request. robots.txt governs HTTP user agents and crawling behaviour; it does not apply to TLS certificate retrieval. Every browser performs this same handshake on every HTTPS connection.

The function is a private helper (`_` prefix) called from the `scan_domains` orchestrator, which enforces robots.txt compliance at the domain level before any per-domain functions execute.

## Reasoning

The original function was approved on 2026-03-22 because it performs a standard TLS handshake — the same operation every browser performs on every HTTPS visit. The additions do not change this analysis.

`sock.version()` returns the TLS protocol version (e.g., "TLSv1.3") negotiated during the handshake that already happened. `sock.cipher()` returns the cipher suite negotiated during the same handshake. Both are accessor methods on the `ssl.SSLSocket` object — they read local state from the already-completed handshake. They do not send any additional data to the server.

SCANNING_RULES.md explicitly allows (under "Without Consent -- What Is Allowed"):

> "SSL/TLS certificate data — certificate chain, expiry date, issuer, SANs, **protocol versions**. Obtained via standard TLS handshake."

The term "protocol versions" directly covers `sock.version()`. Cipher suite information is part of the same TLS handshake negotiation and falls under the same allowance — it is metadata the server presents to every connecting client.

The Decision Test: "Does this request go to a URL that a normal person would reach by clicking links on the public website?" — No URL is requested at all. This is a protocol-level handshake, not an HTTP request. Every browser connection negotiates TLS version and cipher suite. This is Layer 1 (passive) activity.

**Verdict: APPROVED.** The modifications extract additional metadata from an already-open TLS socket. No new network activity. No change in Layer classification. The function remains Layer 1, Level 0.

## Violations

None.
