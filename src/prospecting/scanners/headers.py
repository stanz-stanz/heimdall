"""HTTP response header extraction."""

from __future__ import annotations

import requests

from src.core.config import REQUEST_TIMEOUT, USER_AGENT


def get_response_headers(domain: str) -> dict:
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
