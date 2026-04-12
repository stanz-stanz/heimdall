"""Unit tests for SAN extraction from crt.sh name_value field.

The old query_crt_sh_single only captured common_name. After the ct
rebuild it also parses name_value (newline-separated SANs) into a sans
list per cert. Subdomain merge in runner.py depends on this.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.prospecting.scanners.ct import query_crt_sh_single


def _mock_response(payload: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def test_san_extraction_multi_san_cert() -> None:
    payload = [
        {
            "common_name": "jellingkro.dk",
            "issuer_name": "Let's Encrypt",
            "not_before": "2026-01-01",
            "not_after": "2026-04-01",
            "name_value": "jellingkro.dk\nwww.jellingkro.dk\nadmin.jellingkro.dk",
        }
    ]
    with patch("src.prospecting.scanners.ct.requests.get", return_value=_mock_response(payload)), \
            patch("src.prospecting.scanners.ct.time.sleep"):
        domain, certs = query_crt_sh_single("jellingkro.dk")

    assert domain == "jellingkro.dk"
    assert len(certs) == 1
    sans = certs[0]["sans"]
    assert "jellingkro.dk" in sans
    assert "www.jellingkro.dk" in sans
    assert "admin.jellingkro.dk" in sans


def test_san_extraction_wildcard_stripped_in_lowercase() -> None:
    payload = [
        {
            "common_name": "example.dk",
            "issuer_name": "DigiCert",
            "not_before": "2026-01-01",
            "not_after": "2026-04-01",
            "name_value": "*.EXAMPLE.DK\nexample.dk",
        }
    ]
    with patch("src.prospecting.scanners.ct.requests.get", return_value=_mock_response(payload)), \
            patch("src.prospecting.scanners.ct.time.sleep"):
        _, certs = query_crt_sh_single("example.dk")
    assert certs[0]["sans"] == ["*.example.dk", "example.dk"]


def test_san_extraction_empty_name_value_still_returns_cert() -> None:
    payload = [
        {
            "common_name": "foo.dk",
            "issuer_name": "",
            "not_before": "",
            "not_after": "",
            "name_value": "",
        }
    ]
    with patch("src.prospecting.scanners.ct.requests.get", return_value=_mock_response(payload)), \
            patch("src.prospecting.scanners.ct.time.sleep"):
        _, certs = query_crt_sh_single("foo.dk")
    assert certs[0]["sans"] == []


def test_san_extraction_dedupes_common_name_across_certs() -> None:
    payload = [
        {"common_name": "foo.dk", "issuer_name": "A", "not_before": "", "not_after": "", "name_value": "foo.dk"},
        {"common_name": "foo.dk", "issuer_name": "B", "not_before": "", "not_after": "", "name_value": "foo.dk"},
    ]
    with patch("src.prospecting.scanners.ct.requests.get", return_value=_mock_response(payload)), \
            patch("src.prospecting.scanners.ct.time.sleep"):
        _, certs = query_crt_sh_single("foo.dk")
    assert len(certs) == 1  # dedupe by common_name
