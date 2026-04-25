"""Tests for src.db.signup — magic-link signup token lifecycle."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from src.db.connection import init_db
from src.db.signup import (
    DEFAULT_TTL_MINUTES,
    consume_signup_token,
    create_signup_token,
    expire_stale_tokens,
    get_signup_token,
)


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


class TestCreateSignupToken:
    def test_returns_token_with_expected_fields(self, db):
        result = create_signup_token(db, cvr="12345678", email="owner@example.dk")

        assert set(result.keys()) == {
            "token",
            "cvr",
            "email",
            "source",
            "expires_at",
            "consumed_at",
            "created_at",
        }
        assert result["cvr"] == "12345678"
        assert result["email"] == "owner@example.dk"
        assert result["source"] == "email_reply"
        assert result["consumed_at"] is None
        assert len(result["token"]) >= 32

    def test_tokens_are_unique(self, db):
        a = create_signup_token(db, cvr="12345678")
        b = create_signup_token(db, cvr="12345678")
        assert a["token"] != b["token"]

    def test_expires_at_reflects_ttl(self, db):
        result = create_signup_token(db, cvr="12345678", ttl_minutes=60)
        expires = datetime.strptime(result["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        now = datetime.now(UTC)
        # Must be between 59 and 60 minutes away (allow a little clock skew).
        delta = (expires - now).total_seconds()
        assert 59 * 60 - 5 <= delta <= 60 * 60 + 5

    def test_default_ttl_is_30_minutes(self, db):
        assert DEFAULT_TTL_MINUTES == 30
        result = create_signup_token(db, cvr="12345678")
        expires = datetime.strptime(result["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        delta = (expires - datetime.now(UTC)).total_seconds()
        assert 29 * 60 - 5 <= delta <= 30 * 60 + 5

    def test_source_validation(self, db):
        with pytest.raises(ValueError, match="Invalid source"):
            create_signup_token(db, cvr="12345678", source="landing_page")

    def test_accepts_operator_manual_source(self, db):
        result = create_signup_token(db, cvr="12345678", source="operator_manual")
        assert result["source"] == "operator_manual"

    def test_email_is_optional(self, db):
        result = create_signup_token(db, cvr="12345678")
        assert result["email"] is None


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------


class TestConsumeSignupToken:
    def test_consume_returns_payload(self, db):
        # Note: email is intentionally nulled on consumption for GDPR
        # Art 5(1)(e) compliance — see test_consume_nulls_email_for_gdpr
        # below. The returned dict reflects the post-consumption state.
        issued = create_signup_token(db, cvr="12345678", email="owner@example.dk")
        consumed = consume_signup_token(db, issued["token"])
        assert consumed is not None
        assert consumed["cvr"] == "12345678"
        assert consumed["email"] is None
        assert consumed["consumed_at"] is not None

    def test_double_consume_returns_none(self, db):
        issued = create_signup_token(db, cvr="12345678")
        first = consume_signup_token(db, issued["token"])
        second = consume_signup_token(db, issued["token"])
        assert first is not None
        assert second is None

    def test_consume_unknown_token_returns_none(self, db):
        result = consume_signup_token(db, "not-a-real-token")
        assert result is None

    def test_consume_expired_token_returns_none(self, db):
        # Create with 1-minute TTL, then forcibly back-date via direct UPDATE.
        issued = create_signup_token(db, cvr="12345678", ttl_minutes=1)
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        db.execute(
            "UPDATE signup_tokens SET expires_at = ? WHERE token = ?",
            (past, issued["token"]),
        )
        db.commit()

        assert consume_signup_token(db, issued["token"]) is None

    def test_consume_marks_consumed_at(self, db):
        # _now() truncates to whole-second precision, so compare at that
        # resolution — not against a sub-second wall-clock snapshot.
        issued = create_signup_token(db, cvr="12345678")
        before = datetime.now(UTC).replace(microsecond=0)
        time.sleep(0.01)

        consume_signup_token(db, issued["token"])
        row = get_signup_token(db, issued["token"])

        assert row is not None
        assert row["consumed_at"] is not None
        consumed_at = datetime.strptime(row["consumed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        assert consumed_at >= before

    def test_consume_nulls_email_for_gdpr(self, db):
        """GDPR Art 5(1)(e): the reply-from email is only needed during
        the handshake; after consumption the duplicate on the token row
        is no longer justified. CVR + source + consumed_at remain.
        """
        issued = create_signup_token(
            db, cvr="12345678", email="owner@example.dk"
        )
        consumed = consume_signup_token(db, issued["token"])
        assert consumed is not None
        assert consumed["email"] is None

        row = get_signup_token(db, issued["token"])
        assert row["email"] is None
        assert row["cvr"] == "12345678"
        assert row["source"] == "email_reply"
        assert row["consumed_at"] is not None


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestExpireStaleTokens:
    def test_deletes_expired_unconsumed(self, db):
        issued = create_signup_token(db, cvr="12345678")
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        db.execute(
            "UPDATE signup_tokens SET expires_at = ? WHERE token = ?",
            (past, issued["token"]),
        )
        db.commit()

        deleted = expire_stale_tokens(db)

        assert deleted == 1
        assert get_signup_token(db, issued["token"]) is None

    def test_preserves_consumed_tokens(self, db):
        issued = create_signup_token(db, cvr="12345678")
        consume_signup_token(db, issued["token"])
        # Back-date expiry so it would match the cleanup predicate if not for
        # consumed_at.
        past = (datetime.now(UTC) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        db.execute(
            "UPDATE signup_tokens SET expires_at = ? WHERE token = ?",
            (past, issued["token"]),
        )
        db.commit()

        expire_stale_tokens(db)

        # Consumed token must still exist as audit evidence.
        assert get_signup_token(db, issued["token"]) is not None

    def test_preserves_active_unconsumed(self, db):
        active = create_signup_token(db, cvr="12345678")
        deleted = expire_stale_tokens(db)
        assert deleted == 0
        assert get_signup_token(db, active["token"]) is not None

    def test_returns_zero_when_no_stale(self, db):
        create_signup_token(db, cvr="12345678")
        assert expire_stale_tokens(db) == 0
