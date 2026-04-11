"""TLS/SSL certificate check."""

from __future__ import annotations

import socket
import ssl
from datetime import UTC, datetime

from loguru import logger

from src.core.config import REQUEST_TIMEOUT


def check_ssl(domain: str) -> dict:
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
            expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
            result["expiry"] = expiry_dt.strftime("%Y-%m-%d")
            result["days_remaining"] = (expiry_dt - datetime.now(UTC)).days
            result["valid"] = result["days_remaining"] > 0

        issuer = dict(x[0] for x in cert.get("issuer", []))
        result["issuer"] = issuer.get("organizationName", issuer.get("commonName", ""))

    except Exception as e:
        logger.debug("SSL check failed for {}: {}", domain, e)

    return result
