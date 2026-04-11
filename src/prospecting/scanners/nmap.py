"""Nmap port scanning and service detection (Level 1 — requires consent)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from loguru import logger

NMAP_TIMEOUT = 120  # seconds per domain
NMAP_TOP_PORTS = int(os.environ.get("NMAP_TOP_PORTS", "100"))

# Critical infrastructure ports outside nmap's top-100 that should never
# be internet-facing on SMB targets. Appended to --top-ports.
NMAP_SUPPLEMENT_PORTS = "2375,2376,3000,4443,5000,5601,6379,8888,9200,9300,10000,11211,27017"

# 4-tier severity mapping: port -> severity
_NMAP_PORT_SEVERITY: dict[int, str] = {
    # Critical — no-auth defaults, mass exploitation history
    445: "critical", 2375: "critical", 2376: "critical", 6379: "critical",
    9200: "critical", 9300: "critical", 11211: "critical", 27017: "critical",
    1433: "critical", 3306: "critical", 5432: "critical",
    # High — remote access, cleartext, admin panels
    3389: "high", 5900: "high", 5901: "high", 23: "high", 21: "high",
    135: "high", 139: "high", 1900: "high", 10000: "high",
    # Medium — dev/admin services
    8080: "medium", 8443: "medium", 8888: "medium", 9090: "medium",
    3000: "medium", 5000: "medium", 4443: "medium", 2222: "medium",
    5601: "medium",
    # Low — cleartext protocols with credential exposure
    110: "low", 143: "low",
    # Info — expected services (default for unlisted ports)
}

_NMAP_PORT_LABELS: dict[int, tuple[str, str]] = {
    # port: (service_label, risk_description)
    445: ("SMB/CIFS", "SMB file sharing is a primary target for ransomware (WannaCry, EternalBlue)."),
    2375: ("Docker API", "Unauthenticated Docker API access allows full container and host control."),
    2376: ("Docker API (TLS)", "Docker API with TLS may still allow unauthorized container control."),
    6379: ("Redis", "Redis has no authentication by default. Anyone can read, modify, or delete cached data."),
    9200: ("Elasticsearch", "Elasticsearch has no authentication by default (pre-8.0). Data can be read or deleted."),
    9300: ("Elasticsearch (transport)", "Elasticsearch transport port allows cluster-level access."),
    11211: ("Memcached", "Memcached has no authentication and can be used for DDoS amplification attacks."),
    27017: ("MongoDB", "MongoDB had no authentication by default before version 4.0. Data exfiltration risk."),
    1433: ("MS SQL Server", "Direct database access from the internet allows brute-force and data theft."),
    3306: ("MySQL", "Direct database access from the internet allows brute-force and data theft."),
    5432: ("PostgreSQL", "Direct database access from the internet allows brute-force and data theft."),
    3389: ("RDP", "Remote Desktop is a top target for brute-force attacks and credential stuffing."),
    5900: ("VNC", "VNC often has weak or no authentication, providing direct screen access."),
    5901: ("VNC", "VNC often has weak or no authentication, providing direct screen access."),
    23: ("Telnet", "Telnet transmits all data including credentials in cleartext."),
    21: ("FTP", "FTP transmits credentials in cleartext and may allow anonymous uploads."),
    135: ("RPC", "Windows RPC is used for lateral movement and information disclosure."),
    139: ("NetBIOS", "NetBIOS exposes internal network information and enables lateral movement."),
    1900: ("SSDP/UPnP", "SSDP can be used for DDoS reflection attacks and exposes internal services."),
    10000: ("Webmin", "Webmin is a web-based admin panel with a history of critical vulnerabilities."),
    8080: ("HTTP (alt)", "Non-standard HTTP port — often a development server or admin interface."),
    8443: ("HTTPS (alt)", "Non-standard HTTPS port — often a development server or admin interface."),
    8888: ("HTTP (alt)", "Non-standard HTTP port — often Jupyter Notebook or admin panel."),
    9090: ("HTTP (admin)", "Often Prometheus, Cockpit, or other admin UIs."),
    3000: ("HTTP (dev)", "Often Grafana, Node.js dev server, or similar development tools."),
    5000: ("HTTP (dev)", "Often Docker Registry or Flask development server."),
    4443: ("HTTPS (alt)", "Non-standard HTTPS port — often an admin interface."),
    2222: ("SSH (alt)", "Non-standard SSH port — indicates non-default server configuration."),
    5601: ("Kibana", "Kibana dashboard for Elasticsearch — may expose sensitive log data."),
    110: ("POP3", "POP3 transmits email credentials in cleartext. Use POP3S (port 995) instead."),
    143: ("IMAP", "IMAP transmits email credentials in cleartext. Use IMAPS (port 993) instead."),
}

_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def parse_nmap_xml(xml_output: str, domain: str) -> dict:
    """Parse nmap XML output for a single host into structured port data."""
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError as exc:
        logger.warning("nmap: XML parse error for {}: {}", domain, exc)
        return {"open_ports": [], "port_count": 0}

    open_ports: list[dict] = []

    for host in root.findall("host"):
        ports_elem = host.find("ports")
        if ports_elem is None:
            continue
        for port_elem in ports_elem.findall("port"):
            state_elem = port_elem.find("state")
            if state_elem is None or state_elem.get("state") != "open":
                continue

            service_elem = port_elem.find("service")
            open_ports.append({
                "port": int(port_elem.get("portid", "0")),
                "protocol": port_elem.get("protocol", "tcp"),
                "state": "open",
                "service": service_elem.get("name", "") if service_elem is not None else "",
                "product": service_elem.get("product", "") if service_elem is not None else "",
                "version": service_elem.get("version", "") if service_elem is not None else "",
            })

    return {"open_ports": open_ports, "port_count": len(open_ports)}


def nmap_ports_to_findings(open_ports: list[dict]) -> list[dict]:
    """Map open ports to severity-scored findings for the brief/interpreter."""
    findings: list[dict] = []
    for port_info in open_ports:
        port_num = port_info["port"]
        severity = _NMAP_PORT_SEVERITY.get(port_num, "info")

        label_info = _NMAP_PORT_LABELS.get(port_num)
        if label_info:
            label, risk = label_info
        else:
            svc = port_info.get("service") or "unknown"
            label = svc
            risk = f"Port {port_num} ({svc}) is open — verify this service is intentionally exposed."

        product = port_info.get("product", "")
        version = port_info.get("version", "")
        version_detail = f"{product} {version}".strip()
        version_str = f" ({version_detail})" if product else ""

        findings.append({
            "severity": severity,
            "description": f"Port {port_num} ({label}){version_str} is open and accessible from the internet",
            "risk": risk,
            "source": "nmap",
        })

    return findings


def run_nmap(domains: list[str]) -> dict[str, dict]:
    """Layer 2 / Level 1 — Port scanning and service detection via Nmap.

    Scans top-N TCP ports plus critical infrastructure supplement ports with
    service version detection. Requires written consent (Level 1) before
    execution.

    Returns ``{domain: {"open_ports": [...], "port_count": N}}``.
    """
    if not shutil.which("nmap"):
        logger.warning("nmap not found in PATH — skipping port scan")
        return {}

    results: dict[str, dict] = {}

    for domain in domains:
        if not _DOMAIN_RE.match(domain):
            logger.warning("nmap: invalid domain format {!r} — skipping", domain)
            continue

        try:
            proc = subprocess.run(
                [
                    "nmap",
                    "-sV",
                    "-Pn",
                    "-T3",
                    "--top-ports", str(NMAP_TOP_PORTS),
                    "-p", NMAP_SUPPLEMENT_PORTS,
                    "--open",
                    "--max-retries", "2",
                    "--host-timeout", "90",
                    "--defeat-rst-ratelimit",
                    "-oX", "-",
                    domain,
                ],
                capture_output=True,
                text=True,
                timeout=NMAP_TIMEOUT,
            )

            if proc.returncode != 0 and proc.stderr:
                logger.warning("nmap exited with code {} for {}: {}",
                               proc.returncode, domain, proc.stderr[:500])

            parsed = parse_nmap_xml(proc.stdout, domain)
            if parsed["port_count"] > 0:
                results[domain] = parsed

            logger.bind(context={
                "domain": domain,
                "open_ports": parsed["port_count"],
            }).info("nmap_complete")

        except subprocess.TimeoutExpired:
            logger.warning("nmap timed out after {}s for {}", NMAP_TIMEOUT, domain)
        except FileNotFoundError:
            logger.warning("nmap binary not found")
            return results

    logger.info("nmap: scanned {}/{} domains, {} with open ports",
                len(domains), len(domains), len(results))
    return results
