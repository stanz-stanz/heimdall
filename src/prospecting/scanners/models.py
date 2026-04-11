"""Data models for scanner results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScanResult:
    domain: str = ""
    cms: str = ""
    server: str = ""
    hosting: str = ""
    ssl_valid: bool = False
    ssl_issuer: str = ""
    ssl_expiry: str = ""
    ssl_days_remaining: int = -1
    detected_plugins: list[str] = field(default_factory=list)
    plugin_versions: dict[str, str] = field(default_factory=dict)
    detected_themes: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    tech_stack: list[str] = field(default_factory=list)
    meta_author: str = ""
    footer_credit: str = ""
    raw_httpx: dict = field(default_factory=dict)
    subdomains: list[str] = field(default_factory=list)
    dns_records: dict = field(default_factory=dict)
    ct_certificates: list[dict] = field(default_factory=list)
    tls_version: str = ""
    tls_cipher: str = ""
    tls_bits: int = 0
    exposed_cloud_storage: list[dict] = field(default_factory=list)
