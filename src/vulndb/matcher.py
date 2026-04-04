"""Version matching and finding generation from cached WPVulnerability data."""

from __future__ import annotations

import re

CVSS_SEVERITY = {
    "c": "critical",
    "h": "high",
    "m": "medium",
    "l": "low",
}


def is_vulnerable(installed_version: str | None, vuln: dict) -> bool:
    """Check if installed_version falls within the vuln's affected range.

    Uses packaging.version.Version for PEP 440-compatible comparison.
    Returns False if version cannot be parsed (conservative: assume safe).
    Returns True if vuln is marked unfixed (no patch exists).
    """
    from packaging.version import InvalidVersion, Version

    if not installed_version:
        # Unknown version — only flag unfixed vulns and high/critical severity
        if vuln.get("unfixed") == "1":
            return True
        severity = vuln.get("cvss_severity", "")
        return severity in ("c", "h")

    # Unfixed vulns have no patch — all versions in range are affected
    if vuln.get("unfixed") == "1":
        # If there's a min_version constraint, check it; otherwise all versions affected
        min_ver = vuln.get("min_version")
        min_op = vuln.get("min_operator")
        if not min_ver or not min_op:
            return True
        try:
            v = Version(installed_version)
            mnv = Version(min_ver)
            if min_op == "gte" and not (v >= mnv):
                return False
            if min_op == "gt" and not (v > mnv):
                return False
        except InvalidVersion:
            return False
        return True

    try:
        v = Version(installed_version)
    except InvalidVersion:
        return False

    max_ver = vuln.get("max_version")
    max_op = vuln.get("max_operator")
    if max_ver and max_op:
        try:
            mv = Version(max_ver)
        except InvalidVersion:
            return False
        if max_op == "lt" and not (v < mv):
            return False
        if max_op == "lte" and not (v <= mv):
            return False
        if max_op == "eq" and not (v == mv):
            return False

    min_ver = vuln.get("min_version")
    min_op = vuln.get("min_operator")
    if min_ver and min_op:
        try:
            mnv = Version(min_ver)
        except InvalidVersion:
            return False
        if min_op == "gte" and not (v >= mnv):
            return False
        if min_op == "gt" and not (v > mnv):
            return False

    return True


def extract_primary_cve(vuln: dict) -> str:
    """Extract the first CVE ID from sources, or '' if none."""
    for source in vuln.get("sources", []):
        src_id = source.get("id", "")
        if re.match(r"^CVE-\d{4}-\d+$", src_id):
            return src_id
    return ""


def map_severity(vuln: dict) -> str:
    """Map CVSS severity code to finding severity string.

    Falls back to 'medium' if no CVSS data available.
    """
    severity_code = vuln.get("cvss_severity", "")
    return CVSS_SEVERITY.get(severity_code, "medium")


def _source_description(vuln: dict) -> str:
    """Get the best human-readable description from sources."""
    for source in vuln.get("sources", []):
        name = source.get("name", "")
        if name and not re.match(r"^CVE-\d{4}-\d+$", name):
            return name
    return vuln.get("name", "")


def build_findings(
    slug: str,
    installed_version: str | None,
    vulns: list[dict],
    provenance: str = "unconfirmed",
) -> list[dict]:
    """Generate finding dicts from vulnerabilities affecting the installed version.

    Each finding matches the downstream format consumed by scan_job.py
    and twin_scan.py.
    """
    findings = []
    confidence = "high-inference" if installed_version else "medium-inference"

    for vuln in vulns:
        if not is_vulnerable(installed_version, vuln):
            continue

        cve = extract_primary_cve(vuln)
        severity = map_severity(vuln)
        vuln_name = vuln.get("name", "Unknown vulnerability")
        desc_parts = [vuln_name]
        if cve:
            desc_parts.append(f"({cve})")
        description = " ".join(desc_parts)

        source_desc = _source_description(vuln)
        risk = f"{cve}: {source_desc}" if cve else source_desc

        finding = {
            "severity": severity,
            "description": description,
            "risk": risk,
        }
        if provenance:
            finding["provenance"] = provenance
            finding["provenance_detail"] = {
                "source_layer": 1,
                "twin_scan_tool": "wpvulnerability",
                "template_id": cve or vuln.get("uuid", ""),
                "confidence": confidence,
            }

        findings.append(finding)

    return findings
