"""Tests for Nmap port scanning and finding severity mapping."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from src.prospecting.scanner import (
    _nmap_ports_to_findings,
    _parse_nmap_xml,
    _run_nmap,
)

# ---------------------------------------------------------------------------
# XML fixtures
# ---------------------------------------------------------------------------

NMAP_XML_MULTI_PORT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun>
  <host>
    <address addr="93.184.216.34" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="open" reason="syn-ack"/>
        <service name="http" product="nginx" version="1.24.0"/>
      </port>
      <port protocol="tcp" portid="443">
        <state state="open" reason="syn-ack"/>
        <service name="https" product="nginx" version="1.24.0"/>
      </port>
      <port protocol="tcp" portid="3306">
        <state state="open" reason="syn-ack"/>
        <service name="mysql" product="MySQL" version="8.0.35"/>
      </port>
    </ports>
  </host>
</nmaprun>"""

NMAP_XML_NO_OPEN = """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun>
  <host>
    <address addr="93.184.216.34" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="filtered" reason="no-response"/>
      </port>
    </ports>
  </host>
</nmaprun>"""

NMAP_XML_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun>
  <host>
    <address addr="93.184.216.34" addrtype="ipv4"/>
  </host>
</nmaprun>"""

NMAP_XML_PARTIAL_SERVICE = """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun>
  <host>
    <address addr="93.184.216.34" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="8080">
        <state state="open" reason="syn-ack"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


# ---------------------------------------------------------------------------
# XML parsing tests
# ---------------------------------------------------------------------------

class TestParseNmapXml:
    """Unit tests for nmap XML output parsing."""

    def test_multi_port(self):
        result = _parse_nmap_xml(NMAP_XML_MULTI_PORT, "example.dk")
        assert result["port_count"] == 3
        assert result["open_ports"][0]["port"] == 80
        assert result["open_ports"][0]["service"] == "http"
        assert result["open_ports"][0]["product"] == "nginx"
        assert result["open_ports"][0]["version"] == "1.24.0"
        assert result["open_ports"][2]["port"] == 3306
        assert result["open_ports"][2]["product"] == "MySQL"

    def test_no_open_ports(self):
        result = _parse_nmap_xml(NMAP_XML_NO_OPEN, "example.dk")
        assert result["port_count"] == 0
        assert result["open_ports"] == []

    def test_empty_host(self):
        result = _parse_nmap_xml(NMAP_XML_EMPTY, "example.dk")
        assert result["port_count"] == 0
        assert result["open_ports"] == []

    def test_malformed_xml(self):
        result = _parse_nmap_xml("not xml at all", "example.dk")
        assert result["port_count"] == 0
        assert result["open_ports"] == []

    def test_partial_service_attributes(self):
        result = _parse_nmap_xml(NMAP_XML_PARTIAL_SERVICE, "example.dk")
        assert result["port_count"] == 1
        assert result["open_ports"][0]["port"] == 8080
        assert result["open_ports"][0]["service"] == ""
        assert result["open_ports"][0]["product"] == ""


# ---------------------------------------------------------------------------
# Port-to-findings severity mapping tests
# ---------------------------------------------------------------------------

class TestNmapPortsToFindings:
    """Tests for severity classification of open ports."""

    def test_critical_port_redis(self):
        ports = [{"port": 6379, "protocol": "tcp", "state": "open",
                  "service": "redis", "product": "Redis", "version": "7.0"}]
        findings = _nmap_ports_to_findings(ports)
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        assert "Redis" in findings[0]["description"]
        assert findings[0]["source"] == "nmap"

    def test_critical_port_mysql(self):
        ports = [{"port": 3306, "protocol": "tcp", "state": "open",
                  "service": "mysql", "product": "MySQL", "version": "8.0"}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "critical"

    def test_high_port_rdp(self):
        ports = [{"port": 3389, "protocol": "tcp", "state": "open",
                  "service": "ms-wbt-server", "product": "", "version": ""}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "high"
        assert "RDP" in findings[0]["description"]

    def test_high_port_telnet(self):
        ports = [{"port": 23, "protocol": "tcp", "state": "open",
                  "service": "telnet", "product": "", "version": ""}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "high"

    def test_medium_port_alt_http(self):
        ports = [{"port": 8080, "protocol": "tcp", "state": "open",
                  "service": "http-proxy", "product": "", "version": ""}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "medium"

    def test_info_port_https(self):
        ports = [{"port": 443, "protocol": "tcp", "state": "open",
                  "service": "https", "product": "nginx", "version": "1.24"}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "info"

    def test_unknown_port_defaults_to_info(self):
        ports = [{"port": 12345, "protocol": "tcp", "state": "open",
                  "service": "unknown", "product": "", "version": ""}]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "info"

    def test_mixed_ports(self):
        ports = [
            {"port": 80, "protocol": "tcp", "state": "open",
             "service": "http", "product": "", "version": ""},
            {"port": 6379, "protocol": "tcp", "state": "open",
             "service": "redis", "product": "", "version": ""},
            {"port": 3389, "protocol": "tcp", "state": "open",
             "service": "ms-wbt-server", "product": "", "version": ""},
        ]
        findings = _nmap_ports_to_findings(ports)
        assert findings[0]["severity"] == "info"      # port 80
        assert findings[1]["severity"] == "critical"   # port 6379
        assert findings[2]["severity"] == "high"       # port 3389

    def test_empty_list(self):
        findings = _nmap_ports_to_findings([])
        assert findings == []

    def test_finding_has_risk_field(self):
        ports = [{"port": 445, "protocol": "tcp", "state": "open",
                  "service": "microsoft-ds", "product": "", "version": ""}]
        findings = _nmap_ports_to_findings(ports)
        assert "risk" in findings[0]
        assert len(findings[0]["risk"]) > 0

    def test_finding_includes_product_version(self):
        ports = [{"port": 80, "protocol": "tcp", "state": "open",
                  "service": "http", "product": "Apache", "version": "2.4.57"}]
        findings = _nmap_ports_to_findings(ports)
        assert "Apache 2.4.57" in findings[0]["description"]


# ---------------------------------------------------------------------------
# _run_nmap subprocess tests
# ---------------------------------------------------------------------------

class TestRunNmap:
    """Tests for the _run_nmap scan function."""

    @patch("src.prospecting.scanner.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        result = _run_nmap(["example.dk"])
        assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap")
    @patch("src.prospecting.scanner.subprocess.run",
           side_effect=subprocess.TimeoutExpired("nmap", 120))
    def test_timeout(self, mock_run, mock_which):
        result = _run_nmap(["example.dk"])
        assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_success(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            stdout=NMAP_XML_MULTI_PORT,
            stderr="",
            returncode=0,
        )
        result = _run_nmap(["example.dk"])
        assert "example.dk" in result
        assert result["example.dk"]["port_count"] == 3
        assert result["example.dk"]["open_ports"][0]["port"] == 80

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_nonzero_exit(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            stdout=NMAP_XML_MULTI_PORT,
            stderr="Warning: some hosts down",
            returncode=1,
        )
        result = _run_nmap(["example.dk"])
        # Should still parse output despite non-zero exit
        assert "example.dk" in result

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_no_open_ports_excluded(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            stdout=NMAP_XML_NO_OPEN,
            stderr="",
            returncode=0,
        )
        result = _run_nmap(["example.dk"])
        # Domain excluded when no open ports found
        assert "example.dk" not in result

    def test_invalid_domain_skipped(self):
        with patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap"):
            result = _run_nmap(["not a valid domain!"])
            assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/bin/nmap")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_multiple_domains(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            stdout=NMAP_XML_MULTI_PORT,
            stderr="",
            returncode=0,
        )
        result = _run_nmap(["a.dk", "b.dk"])
        # Each call returns same fixture but keyed by first host in XML
        # The function loops per-domain, so each gets its own subprocess call
        assert mock_run.call_count == 2
