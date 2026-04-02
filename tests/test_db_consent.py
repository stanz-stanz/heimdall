"""Tests for src.db.consent — consent record CRUD."""

from __future__ import annotations

import json

import pytest

from src.db.connection import init_db
from src.db.consent import (
    check_consent_status,
    create_consent_record,
    get_active_consent,
    revoke_consent,
)


@pytest.fixture()
def db(tmp_path):
    """Initialised client database connection."""
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_consent(db, cvr="12345678", consent_expiry="2027-12-31", **kwargs):
    """Create a consent record with sensible defaults for testing."""
    return create_consent_record(
        db,
        cvr=cvr,
        authorised_domains=kwargs.pop("authorised_domains", ["example.dk", "shop.example.dk"]),
        consent_date=kwargs.pop("consent_date", "2026-04-01"),
        consent_expiry=consent_expiry,
        consent_document=kwargs.pop("consent_document", "docs/consent/12345678-signed.pdf"),
        authorised_by_name=kwargs.pop("authorised_by_name", "Peter Nielsen"),
        authorised_by_role=kwargs.pop("authorised_by_role", "Owner"),
        authorised_by_email=kwargs.pop("authorised_by_email", "peter@example.dk"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_consent_record(db):
    """Create a consent record and verify all fields."""
    row = _create_test_consent(db)

    assert row["cvr"] == "12345678"
    assert row["consent_type"] == "written"
    assert row["consent_date"] == "2026-04-01"
    assert row["consent_expiry"] == "2027-12-31"
    assert row["consent_document"] == "docs/consent/12345678-signed.pdf"
    assert row["authorised_by_name"] == "Peter Nielsen"
    assert row["authorised_by_role"] == "Owner"
    assert row["authorised_by_email"] == "peter@example.dk"
    assert row["status"] == "active"
    assert row["created_at"] is not None
    assert row["updated_at"] is not None

    # authorised_domains stored as JSON array
    domains = json.loads(row["authorised_domains"])
    assert domains == ["example.dk", "shop.example.dk"]


def test_get_active_consent(db):
    """Create active consent and verify it is returned."""
    _create_test_consent(db)

    consent = get_active_consent(db, "12345678")
    assert consent is not None
    assert consent["cvr"] == "12345678"
    assert consent["status"] == "active"

    # Non-existent CVR returns None
    assert get_active_consent(db, "99999999") is None


def test_check_consent_status_active(db):
    """Returns True when active, non-expired consent exists."""
    _create_test_consent(db)
    assert check_consent_status(db, "12345678") is True


def test_check_consent_status_expired(db):
    """Returns False when consent has a past expiry date."""
    _create_test_consent(db, consent_expiry="2020-01-01")
    assert check_consent_status(db, "12345678") is False


def test_revoke_consent(db):
    """Revoke consent, verify status='revoked' and updated_at changed."""
    row = _create_test_consent(db)
    consent_id = row["id"]
    original_updated = row["updated_at"]

    revoke_consent(db, consent_id)

    updated = db.execute(
        "SELECT * FROM consent_records WHERE id = ?", (consent_id,)
    ).fetchone()

    assert updated["status"] == "revoked"
    assert updated["updated_at"] >= original_updated


def test_check_consent_status_revoked(db):
    """Returns False after consent is revoked."""
    row = _create_test_consent(db)
    assert check_consent_status(db, "12345678") is True

    revoke_consent(db, row["id"])
    assert check_consent_status(db, "12345678") is False
