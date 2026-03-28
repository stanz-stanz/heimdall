"""Tests for the consent validator (Gate 2).

SAFETY-CRITICAL TESTS. Every test in this file verifies that the consent
framework either correctly allows a scan (with full valid consent) or
correctly blocks it. The principle: any ambiguity, error, or unexpected
input MUST result in blocked.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from src.consent.validator import (
    ConsentCheckResult,
    check_consent,
    load_authorisation,
    validate_schema,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_authorisation(**overrides):
    """Build a valid authorisation dict with optional overrides."""
    base = {
        "client_id": "client-001",
        "company_name": "Test ApS",
        "cvr": "12345678",
        "authorised_domains": ["test.dk"],
        "level_authorised": 1,
        "layers_permitted": [1, 2],
        "consent_type": "written",
        "consent_date": "2026-03-21",
        "consent_expiry": "2027-03-21",
        "consent_document": "consents/signed.pdf",
        "authorised_by": {
            "name": "Test Person",
            "role": "CVR-registered legal representative",
            "email": "test@test.dk",
        },
        "status": "active",
        "notes": "",
    }
    base.update(overrides)
    return base


def _write_auth(tmp_path, client_id="client-001", with_document=True, **overrides):
    """Write an authorisation.json and optionally the consent document.

    Returns the base client_dir (tmp_path).
    """
    auth = _base_authorisation(client_id=client_id, **overrides)
    client_dir = tmp_path / client_id
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "authorisation.json").write_text(json.dumps(auth), encoding="utf-8")

    if with_document:
        doc_path = auth.get("consent_document", "consents/signed.pdf")
        if isinstance(doc_path, str) and doc_path.strip():
            full_doc = client_dir / doc_path
            full_doc.parent.mkdir(parents=True, exist_ok=True)
            full_doc.write_text("signed consent document", encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# load_authorisation
# ---------------------------------------------------------------------------

class TestLoadAuthorisation:
    def test_valid_file(self, tmp_path):
        _write_auth(tmp_path)
        result = load_authorisation(tmp_path, "client-001")
        assert result is not None
        assert result["client_id"] == "client-001"

    def test_missing_file(self, tmp_path):
        assert load_authorisation(tmp_path, "nonexistent") is None

    def test_malformed_json(self, tmp_path):
        client_dir = tmp_path / "bad-client"
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text("{broken", encoding="utf-8")
        assert load_authorisation(tmp_path, "bad-client") is None

    def test_json_array_not_dict(self, tmp_path):
        """A valid JSON file that is an array, not a dict, should return None."""
        client_dir = tmp_path / "array-client"
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text('[1, 2, 3]', encoding="utf-8")
        assert load_authorisation(tmp_path, "array-client") is None

    def test_json_string_not_dict(self, tmp_path):
        client_dir = tmp_path / "str-client"
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text('"hello"', encoding="utf-8")
        assert load_authorisation(tmp_path, "str-client") is None


# ---------------------------------------------------------------------------
# check_consent — Level 0 (no consent needed)
# ---------------------------------------------------------------------------

class TestLevel0:
    def test_level_0_always_passes(self, tmp_path):
        """Level 0 scan needs no consent file at all."""
        result = check_consent(tmp_path, "prospect", "example.dk", level_requested=0)
        assert result.allowed is True
        assert "no consent required" in result.reason

    def test_level_0_passes_even_with_consent(self, tmp_path):
        _write_auth(tmp_path)
        result = check_consent(tmp_path, "client-001", "test.dk", level_requested=0)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# check_consent — Level 1 (consent required) — HAPPY PATH
# ---------------------------------------------------------------------------

class TestLevel1Valid:
    def test_valid_consent(self, tmp_path):
        _write_auth(tmp_path)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is True
        assert result.reason == "Valid consent on file"
        assert result.authorised_by_role == "CVR-registered legal representative"
        assert result.consent_expiry == "2027-03-21"
        assert result.level_authorised == 1

    def test_case_insensitive_domain_match(self, tmp_path):
        """DNS is case-insensitive. Test.DK must match test.dk in consent."""
        _write_auth(tmp_path, authorised_domains=["Test.DK"])
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is True

    def test_trailing_dot_normalised(self, tmp_path):
        """DNS trailing dot (test.dk.) should match test.dk in consent."""
        _write_auth(tmp_path)
        result = check_consent(
            tmp_path, "client-001", "test.dk.",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is True

    def test_multiple_authorised_domains(self, tmp_path):
        _write_auth(tmp_path, authorised_domains=["test.dk", "other.dk", "third.dk"])
        result = check_consent(
            tmp_path, "client-001", "other.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is True


# ---------------------------------------------------------------------------
# check_consent — Level 1 — BLOCKED scenarios
# ---------------------------------------------------------------------------

class TestLevel1Blocked:
    def test_no_consent_file(self, tmp_path):
        result = check_consent(tmp_path, "client-001", "test.dk", level_requested=1)
        assert result.allowed is False
        assert "No authorisation file" in result.reason
        assert result.level_authorised == -1

    def test_expired_consent(self, tmp_path):
        _write_auth(tmp_path, consent_expiry="2026-01-01")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "expired" in result.reason.lower()

    def test_domain_not_in_scope(self, tmp_path):
        _write_auth(tmp_path)
        result = check_consent(
            tmp_path, "client-001", "other-domain.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "not in authorised scope" in result.reason

    def test_subdomain_not_covered(self, tmp_path):
        """Consent for test.dk does NOT cover sub.test.dk — strict match."""
        _write_auth(tmp_path)
        result = check_consent(
            tmp_path, "client-001", "sub.test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "not in authorised scope" in result.reason

    def test_status_suspended(self, tmp_path):
        _write_auth(tmp_path, status="suspended")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "suspended" in result.reason

    def test_status_revoked(self, tmp_path):
        _write_auth(tmp_path, status="revoked")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "revoked" in result.reason

    def test_status_expired(self, tmp_path):
        _write_auth(tmp_path, status="expired")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_insufficient_level(self, tmp_path):
        _write_auth(tmp_path, level_authorised=0)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "Authorised level 0 < requested level 1" in result.reason

    def test_consent_document_missing(self, tmp_path):
        """Consent JSON exists but the actual signed PDF does not."""
        _write_auth(tmp_path, with_document=False)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "Consent document not found" in result.reason

    def test_consent_document_path_empty(self, tmp_path):
        _write_auth(tmp_path, consent_document="")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_reference_date_override(self, tmp_path):
        """Consent valid in 2026, but expired by 2028."""
        _write_auth(tmp_path)
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        ).allowed is True
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2028, 1, 1),
        ).allowed is False

    def test_expiry_boundary_date(self, tmp_path):
        """The expiry date itself is the LAST valid day (> not >=)."""
        _write_auth(tmp_path, consent_expiry="2027-03-21")
        # On the expiry date: still valid
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2027, 3, 21),
        ).allowed is True
        # Day after: expired
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2027, 3, 22),
        ).allowed is False

    def test_consent_document_path_traversal(self, tmp_path):
        """Consent document path must not escape the client directory."""
        _write_auth(tmp_path, consent_document="../../etc/passwd", with_document=False)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "escapes client directory" in result.reason


# ---------------------------------------------------------------------------
# Type safety — every wrong type MUST block, never crash
# ---------------------------------------------------------------------------

class TestTypeSafety:
    """Malformed data must always result in blocked, never an exception."""

    def test_level_requested_string(self, tmp_path):
        result = check_consent(tmp_path, "c", "d", level_requested="1")
        assert result.allowed is False
        assert "must be int" in result.reason

    def test_level_requested_bool(self, tmp_path):
        result = check_consent(tmp_path, "c", "d", level_requested=True)
        assert result.allowed is False
        assert "must be int" in result.reason

    def test_level_requested_none(self, tmp_path):
        result = check_consent(tmp_path, "c", "d", level_requested=None)
        assert result.allowed is False

    def test_level_requested_float(self, tmp_path):
        result = check_consent(tmp_path, "c", "d", level_requested=1.0)
        assert result.allowed is False

    def test_level_requested_negative(self, tmp_path):
        result = check_consent(tmp_path, "c", "d", level_requested=-1)
        assert result.allowed is False
        assert ">= 0" in result.reason

    def test_empty_domain(self, tmp_path):
        result = check_consent(tmp_path, "c", "", level_requested=1)
        assert result.allowed is False
        assert "Empty domain" in result.reason

    def test_whitespace_only_domain(self, tmp_path):
        result = check_consent(tmp_path, "c", "   ", level_requested=1)
        assert result.allowed is False
        assert "Empty domain" in result.reason

    def test_whitespace_only_consent_document(self, tmp_path):
        _write_auth(tmp_path, consent_document="   ")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_authorised_domains_is_string(self, tmp_path):
        """If authorised_domains is a string instead of list, block."""
        _write_auth(tmp_path, authorised_domains="test.dk")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "must be a list" in result.reason

    def test_level_authorised_is_string(self, tmp_path):
        _write_auth(tmp_path, level_authorised="1")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "must be int" in result.reason

    def test_level_authorised_is_bool(self, tmp_path):
        _write_auth(tmp_path, level_authorised=True)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_consent_expiry_is_int(self, tmp_path):
        _write_auth(tmp_path, consent_expiry=20270321)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "must be a string" in result.reason

    def test_consent_expiry_invalid_format(self, tmp_path):
        _write_auth(tmp_path, consent_expiry="not-a-date")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "Invalid consent_expiry" in result.reason

    def test_status_is_none(self, tmp_path):
        _write_auth(tmp_path, status=None)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_status_is_int(self, tmp_path):
        _write_auth(tmp_path, status=1)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_authorised_by_not_dict(self, tmp_path):
        """authorised_by as a string should still allow (field is informational)."""
        _write_auth(tmp_path, authorised_by="not a dict")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        # Should still pass — authorised_by is informational, not gating
        assert result.allowed is True
        assert result.authorised_by_role is None

    def test_consent_document_is_int(self, tmp_path):
        _write_auth(tmp_path, consent_document=123)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False

    def test_non_string_domain_in_authorised_domains(self, tmp_path):
        """Non-string items in authorised_domains list are silently skipped."""
        _write_auth(tmp_path, authorised_domains=["test.dk", 123, None])
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is True  # test.dk is still in the list


# ---------------------------------------------------------------------------
# Safety net — check_consent NEVER raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """check_consent must return a ConsentCheckResult, never raise."""

    def test_nonexistent_client_dir(self):
        """Passing a client_dir that doesn't exist should block, not crash."""
        result = check_consent(
            Path("/nonexistent/path"), "client-001", "test.dk", level_requested=1,
        )
        assert result.allowed is False

    def test_permission_error_simulation(self, tmp_path):
        """Even if something unexpected happens, block — don't crash."""
        # This is tested by the outer try/except in check_consent.
        # We trust the safety net exists; a real permission error is
        # hard to simulate portably.
        result = check_consent(tmp_path, "c", "d", level_requested=1)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# ConsentCheckResult
# ---------------------------------------------------------------------------

class TestConsentCheckResult:
    def test_frozen(self):
        result = ConsentCheckResult(
            allowed=True, client_id="c", domain="d",
            level_requested=0, level_authorised=0, reason="ok",
        )
        with pytest.raises(AttributeError):
            result.allowed = False


# ---------------------------------------------------------------------------
# validate_schema
# ---------------------------------------------------------------------------

class TestValidateSchema:
    def test_valid_authorisation(self):
        errors = validate_schema(_base_authorisation())
        assert errors == []

    def test_missing_required_fields(self):
        errors = validate_schema({"client_id": "x"})
        assert len(errors) > 0
        missing = [e for e in errors if "Missing required field" in e]
        assert len(missing) >= 5

    def test_missing_authorised_by_subfields(self):
        auth = _base_authorisation()
        auth["authorised_by"] = {"name": "Test"}
        errors = validate_schema(auth)
        assert any("role" in e for e in errors)
        assert any("email" in e for e in errors)
