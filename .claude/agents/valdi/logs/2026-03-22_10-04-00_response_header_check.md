# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:04:00Z
- **Scan type:** Security-relevant HTTP response header check
- **Scan type ID:** response_header_check
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 60ecae45-0147-4fa4-a3d8-82e149f01291
- **Function hash:** sha256:3c588da7ab51fd46f4d899289f396c5e014c2c7616aae572a4c96d2e212b5049
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def _get_response_headers(domain: str) -> dict:
    """Fetch security-relevant response headers."""
    headers = {
        "x_frame_options": False,
        "content_security_policy": False,
        "strict_transport_security": False,
        "x_content_type_options": False,
    }
    try:
        resp = requests.head(
            f"https://{domain}",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        h = {k.lower(): v for k, v in resp.headers.items()}
        headers["x_frame_options"] = "x-frame-options" in h
        headers["content_security_policy"] = "content-security-policy" in h
        headers["strict_transport_security"] = "strict-transport-security" in h
        headers["x_content_type_options"] = "x-content-type-options" in h
    except requests.RequestException:
        pass
    return headers
```

**File:** `pipeline/scanner.py` (lines 210-232)

## Tools Invoked

- Python `requests` library (HTTP HEAD)

No external CLI scanning tools invoked.

## URLs/Paths Requested

- `https://{domain}/` (homepage, HEAD request) — permitted: publicly served page

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) designed to be called from the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level.

**Condition:** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance.

## Reasoning

This function sends a HEAD request to the homepage — a lighter version of a GET request that retrieves only response headers without the page body. It then checks for the presence of four standard security headers (X-Frame-Options, Content-Security-Policy, Strict-Transport-Security, X-Content-Type-Options). These headers are voluntarily sent by the server to every visitor.

SCANNING_RULES.md Level 0 explicitly allows: "HTTP response headers from the site's public pages (homepage, publicly linked pages). Includes Server, X-Powered-By, Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, etc."

The function:
1. Only requests the homepage (`/`) — a publicly served page
2. Uses HEAD method — even lighter than a normal browser GET request
3. Only reads which standard headers are present (boolean check)
4. Does NOT probe hidden paths, admin panels, or API endpoints
5. Does NOT send crafted requests or vulnerability probes

All activity is within Layer 1. No Layer 2 or Layer 3 activity present.

## Violations

None.
