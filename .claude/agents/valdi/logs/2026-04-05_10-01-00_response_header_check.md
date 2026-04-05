# Valdi Scan-Type Validation

- **Timestamp:** 2026-04-05T10:01:00Z
- **Scan type:** Security-relevant HTTP response header check (re-validation)
- **Scan type ID:** response_header_check
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 60ecae45-0147-4fa4-a3d8-82e149f01291 (retained — same scan type, code-only change)
- **Function hash:** sha256:ce079b27dac4aeb91eceb2c522aa7432829496cb6cfa6d5946cc88662391e4d8
- **Previous hash:** sha256:da1541bd1c72627be49f28f12f13b3f69de27876e94ba4eec5ae026a1c7d192c
- **Triggered by:** Federico (manual re-validation request due to hash invalidation)

## Reason for Re-Validation

Function source code was modified, invalidating the previous approval hash. The approval token `60ecae45-0147-4fa4-a3d8-82e149f01291` (issued 2026-03-22) was invalidated by hash mismatch. A full Gate 1 review is required before the scan type can execute again.

## Function Reviewed

```python
def _get_response_headers(domain: str) -> dict:
    """Fetch security-relevant response headers."""
    headers = {
        "x_frame_options": False,
        "content_security_policy": False,
        "strict_transport_security": False,
        "x_content_type_options": False,
        "permissions_policy": False,
        "referrer_policy": False,
        "server_value": "",
        "x_powered_by": "",
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
        headers["permissions_policy"] = "permissions-policy" in h
        headers["referrer_policy"] = "referrer-policy" in h
        headers["server_value"] = h.get("server", "")
        headers["x_powered_by"] = h.get("x-powered-by", "")
    except requests.RequestException:
        pass
    return headers
```

**File:** `src/prospecting/scanner.py` (lines 373-403)

## Changes Since Last Approval

Four new fields extracted from the existing `resp.headers` dictionary:

```python
headers["permissions_policy"] = "permissions-policy" in h
headers["referrer_policy"] = "referrer-policy" in h
headers["server_value"] = h.get("server", "")
headers["x_powered_by"] = h.get("x-powered-by", "")
```

- `permissions_policy`: boolean check for Permissions-Policy header presence
- `referrer_policy`: boolean check for Referrer-Policy header presence
- `server_value`: string value of the Server header (e.g., "Apache/2.4.41")
- `x_powered_by`: string value of the X-Powered-By header (e.g., "PHP/7.4")

All four read from the same `resp.headers` dict populated by the single `requests.head()` call that was already approved. No new HTTP request. No new outbound connection.

The result dict was expanded with corresponding new keys in its initializer.

## Tools Invoked

- Python `requests` library (HTTP HEAD — unchanged)

No external CLI scanning tools invoked. No new tools added.

## URLs/Paths Requested

- `https://{domain}/` (homepage, HEAD request) — permitted: publicly served page (unchanged)

No new URLs or paths requested. The additions read from the already-received response object.

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) designed to be called from the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level.

**Condition:** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance.

## Reasoning

The original function was approved on 2026-03-22 because it sends a single HEAD request to the homepage and reads security-relevant response headers. The additions do not change this analysis.

The four new fields all read from `resp.headers` — the same response object that was already being inspected. No additional HTTP request is made. The function still sends exactly one HEAD request to `https://{domain}/`.

SCANNING_RULES.md explicitly allows (under "Without Consent -- What Is Allowed"):

> "HTTP response headers from the site's public pages (homepage, publicly linked pages). Includes **Server, X-Powered-By**, Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, **etc.**"

All four new headers are explicitly covered:
- **Server** and **X-Powered-By** are named by name in the allowance text
- **Permissions-Policy** and **Referrer-Policy** are standard security headers sent voluntarily by the server to every visitor, covered by the "etc." in the allowance and by the general principle that reading response headers from public pages is Layer 1

The Decision Test: "Does this request go to a URL that a normal person would reach by clicking links on the public website?" — The request goes to `https://{domain}/`, the homepage. Yes, this is a URL a normal person would visit. The additions do not change the URL — they only read additional headers from the same response.

**Verdict: APPROVED.** The modifications extract additional header values from an already-received HTTP response. No new network activity. No change in Layer classification. The function remains Layer 1, Level 0.

## Violations

None.
