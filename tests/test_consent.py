"""Tests for the consent validator (Gate 2)."""

import json
from datetime import date

import pytest

from src.consent.validator import (
    ConsentCheckResult,
    check_consent,
    load_authorisation,
    validate_schema,
)


# ---------------------------------------------------------------------------
# Fixtures
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
        "consent_document": "consents/client-001-signed.pdf",
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


def _write_auth(tmp_path, client_id="client-001", **overrides):
    """Write an authorisation.json and return the base client_dir."""
    auth = _base_authorisation(client_id=client_id, **overrides)
    client_dir = tmp_path / client_id
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "authorisation.json").write_text(json.dumps(auth), encoding="utf-8")
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
        """Level 0 scan passes even when a consent file exists."""
        _write_auth(tmp_path)
        result = check_consent(tmp_path, "client-001", "test.dk", level_requested=0)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# check_consent — Level 1 (consent required)
# ---------------------------------------------------------------------------

class TestLevel1:
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

    def test_insufficient_level(self, tmp_path):
        _write_auth(tmp_path, level_authorised=0)
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "Authorised level 0 < requested level 1" in result.reason

    def test_invalid_expiry_format(self, tmp_path):
        _write_auth(tmp_path, consent_expiry="not-a-date")
        result = check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        )
        assert result.allowed is False
        assert "Invalid consent_expiry" in result.reason

    def test_reference_date_override(self, tmp_path):
        """Consent valid in 2026, but expired by 2028."""
        _write_auth(tmp_path, consent_expiry="2027-03-21")
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2026, 6, 1),
        ).allowed is True
        assert check_consent(
            tmp_path, "client-001", "test.dk",
            level_requested=1, reference_date=date(2028, 1, 1),
        ).allowed is False


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
        assert len(missing) >= 5  # many fields missing

    def test_missing_authorised_by_subfields(self):
        auth = _base_authorisation()
        auth["authorised_by"] = {"name": "Test"}  # missing role and email
        errors = validate_schema(auth)
        assert any("role" in e for e in errors)
        assert any("email" in e for e in errors)
