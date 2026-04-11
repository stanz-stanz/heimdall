"""Tests for the CT collector: database layer, extraction, local query, backfill."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.ct_collector.db import (
    cleanup_old_entries,
    get_db_stats,
    init_db,
    insert_certificate,
    insert_certificates_batch,
    open_readonly,
    query_certificates,
)
from src.ct_collector.main import _extract_cert_data, _is_dk_domain

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return a path to a temporary database file."""
    return str(tmp_path / "test_ct.db")


@pytest.fixture
def db_conn(db_path):
    """Return an initialised database connection."""
    conn = init_db(db_path)
    yield conn
    conn.close()


def _make_cert(
    cn="example.dk",
    issuer="Let's Encrypt",
    not_before="2026-01-01T00:00:00",
    not_after="2027-01-01T00:00:00",
    san_domains=None,
    seen_at=None,
):
    """Helper to build a certificate dict."""
    return {
        "common_name": cn,
        "issuer_name": issuer,
        "not_before": not_before,
        "not_after": not_after,
        "san_domains": san_domains or [cn],
        "seen_at": seen_at or datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# TestDb
# ---------------------------------------------------------------------------


class TestDb:
    """Database layer tests."""

    def test_init_db_creates_schema(self, db_path):
        conn = init_db(db_path)
        # Verify table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='certificates'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_init_db_wal_mode(self, db_path):
        conn = init_db(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_insert_certificate(self, db_conn):
        inserted = insert_certificate(
            db_conn,
            common_name="test.dk",
            issuer_name="LE",
            not_before="2026-01-01",
            not_after="2027-01-01",
            san_domains=["test.dk", "www.test.dk"],
            seen_at=datetime.now(UTC).isoformat(),
        )
        assert inserted is True

    def test_insert_duplicate_ignored(self, db_conn):
        kwargs = dict(
            common_name="dup.dk",
            issuer_name="LE",
            not_before="2026-01-01",
            not_after="2027-01-01",
            san_domains=["dup.dk"],
            seen_at=datetime.now(UTC).isoformat(),
        )
        assert insert_certificate(db_conn, **kwargs) is True
        assert insert_certificate(db_conn, **kwargs) is False

    def test_batch_insert(self, db_conn):
        certs = [_make_cert(cn=f"batch{i}.dk") for i in range(5)]
        count = insert_certificates_batch(db_conn, certs)
        assert count == 5

    def test_batch_insert_duplicates(self, db_conn):
        certs = [_make_cert(cn="same.dk")] * 3
        count = insert_certificates_batch(db_conn, certs)
        # Only first should insert, rest are duplicates
        assert count >= 1

    def test_query_exact_domain(self, db_conn):
        insert_certificate(
            db_conn, "exact.dk", "LE", "2026-01-01", "2027-01-01",
            ["exact.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "exact.dk", include_expired=True)
        assert len(results) == 1
        assert results[0]["common_name"] == "exact.dk"

    def test_query_wildcard_cn(self, db_conn):
        insert_certificate(
            db_conn, "*.wild.dk", "LE", "2026-01-01", "2027-01-01",
            ["*.wild.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "wild.dk", include_expired=True)
        assert len(results) == 1
        assert results[0]["common_name"] == "*.wild.dk"

    def test_query_by_san(self, db_conn):
        insert_certificate(
            db_conn, "other-cn.dk", "LE", "2026-01-01", "2027-01-01",
            ["san-target.dk", "other-cn.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "san-target.dk", include_expired=True)
        assert len(results) == 1

    def test_exclude_expired(self, db_conn):
        # Insert an expired cert
        insert_certificate(
            db_conn, "expired.dk", "LE", "2020-01-01", "2021-01-01",
            ["expired.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "expired.dk", include_expired=False)
        assert len(results) == 0

    def test_include_expired(self, db_conn):
        insert_certificate(
            db_conn, "expired2.dk", "LE", "2020-01-01", "2021-01-01",
            ["expired2.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "expired2.dk", include_expired=True)
        assert len(results) == 1

    def test_cleanup(self, db_conn):
        old_seen = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        insert_certificate(
            db_conn, "old.dk", "LE", "2020-01-01", "2021-01-01",
            ["old.dk"], old_seen,
        )
        deleted = cleanup_old_entries(db_conn, days=90)
        assert deleted == 1

    def test_readonly_cannot_write(self, db_path):
        conn = init_db(db_path)
        conn.close()

        ro_conn = open_readonly(db_path)
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute(
                "INSERT INTO certificates (common_name, seen_at) VALUES (?, ?)",
                ("fail.dk", "2026-01-01"),
            )
        ro_conn.close()

    def test_get_db_stats(self, db_conn):
        insert_certificate(
            db_conn, "stats.dk", "LE", "2026-01-01", "2027-01-01",
            ["stats.dk"], datetime.now(UTC).isoformat(),
        )
        stats = get_db_stats(db_conn)
        assert stats["total_rows"] == 1
        assert stats["oldest_entry"] is not None
        assert stats["newest_entry"] is not None
        assert stats["db_size_bytes"] > 0

    def test_get_db_stats_empty(self, db_conn):
        stats = get_db_stats(db_conn)
        assert stats["total_rows"] == 0

    def test_query_returns_expected_keys(self, db_conn):
        insert_certificate(
            db_conn, "keys.dk", "LE", "2026-01-01", "2027-01-01",
            ["keys.dk"], datetime.now(UTC).isoformat(),
        )
        results = query_certificates(db_conn, "keys.dk", include_expired=True)
        assert len(results) == 1
        cert = results[0]
        assert set(cert.keys()) == {"common_name", "issuer_name", "not_before", "not_after"}


# ---------------------------------------------------------------------------
# TestExtractCertData
# ---------------------------------------------------------------------------


class TestExtractCertData:
    """CertStream message extraction tests."""

    def _make_message(self, domains, cn=None, msg_type="certificate_update"):
        """Build a minimal CertStream-like message."""
        if cn is None:
            cn = domains[0] if domains else ""
        return {
            "message_type": msg_type,
            "data": {
                "leaf_cert": {
                    "subject": {"CN": cn},
                    "all_domains": domains,
                    "issuer": {"O": "Test CA", "CN": "Test CA"},
                    "not_before": "2026-01-01T00:00:00",
                    "not_after": "2027-01-01T00:00:00",
                },
            },
        }

    def test_dk_cert_extracted(self):
        msg = self._make_message(["example.dk", "www.example.dk"])
        result = _extract_cert_data(msg)
        assert result is not None
        assert result["common_name"] == "example.dk"
        assert "example.dk" in result["san_domains"]

    def test_non_dk_filtered(self):
        msg = self._make_message(["example.com", "www.example.com"])
        result = _extract_cert_data(msg)
        assert result is None

    def test_dk_in_san_only(self):
        msg = self._make_message(
            ["example.com", "example.dk"],
            cn="example.com",
        )
        result = _extract_cert_data(msg)
        assert result is not None
        assert "example.dk" in result["san_domains"]

    def test_non_cert_update_ignored(self):
        msg = self._make_message(["example.dk"], msg_type="heartbeat")
        result = _extract_cert_data(msg)
        assert result is None


# ---------------------------------------------------------------------------
# TestIsDkDomain
# ---------------------------------------------------------------------------


class TestIsDkDomain:
    """Domain suffix filter tests."""

    def test_exact_dk(self):
        assert _is_dk_domain("example.dk") is True

    def test_subdomain_dk(self):
        assert _is_dk_domain("sub.example.dk") is True

    def test_not_dk(self):
        assert _is_dk_domain("example.com") is False

    def test_dk_in_middle(self):
        assert _is_dk_domain("dk.example.com") is False

    def test_empty_string(self):
        assert _is_dk_domain("") is False

    def test_trailing_dot(self):
        assert _is_dk_domain("example.dk.") is True


# ---------------------------------------------------------------------------
# TestQueryLocalCt
# ---------------------------------------------------------------------------


class TestQueryLocalCt:
    """Tests for _query_local_ct in scan_job.py."""

    def test_returns_tuple_format(self, db_path):
        """_query_local_ct returns (domain, certs_list)."""
        conn = init_db(db_path)
        insert_certificate(
            conn, "local.dk", "LE", "2026-01-01", "2027-01-01",
            ["local.dk"], datetime.now(UTC).isoformat(),
        )
        conn.close()

        import src.worker.scan_job as mod
        from src.worker.scan_job import _query_local_ct

        original = mod._CT_DB_PATH
        try:
            mod._CT_DB_PATH = db_path
            result = _query_local_ct("local.dk")
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert result[0] == "local.dk"
            assert isinstance(result[1], list)
            assert len(result[1]) >= 1
            # Verify cert dict keys match crt.sh format
            cert = result[1][0]
            assert "common_name" in cert
            assert "issuer_name" in cert
            assert "not_before" in cert
            assert "not_after" in cert
        finally:
            mod._CT_DB_PATH = original

    def test_missing_db_returns_empty(self):
        """Missing DB file returns (domain, [])."""
        import src.worker.scan_job as mod
        from src.worker.scan_job import _query_local_ct

        original = mod._CT_DB_PATH
        try:
            mod._CT_DB_PATH = "/nonexistent/path/ct.db"
            result = _query_local_ct("test.dk")
            assert result == ("test.dk", [])
        finally:
            mod._CT_DB_PATH = original

    def test_integration_with_scan_job_unpacking(self, db_path):
        """Verify the tuple format works with scan_job.py's unpacking logic (lines 191-199)."""
        conn = init_db(db_path)
        insert_certificate(
            conn, "*.unpack.dk", "LE", "2026-01-01", "2027-01-01",
            ["unpack.dk", "*.unpack.dk"], datetime.now(UTC).isoformat(),
        )
        conn.close()

        import src.worker.scan_job as mod
        from src.worker.scan_job import _query_local_ct

        original = mod._CT_DB_PATH
        try:
            mod._CT_DB_PATH = db_path
            crtsh_raw = _query_local_ct("unpack.dk")

            # Simulate the unpacking logic from scan_job.py lines 191-199
            ct_certificates = []
            if isinstance(crtsh_raw, (list, tuple)):
                if len(crtsh_raw) == 2 and isinstance(crtsh_raw[0], str):
                    ct_certificates = crtsh_raw[1] if isinstance(crtsh_raw[1], list) else []
                else:
                    ct_certificates = list(crtsh_raw)
            assert len(ct_certificates) >= 1
            assert ct_certificates[0]["common_name"] == "*.unpack.dk"
        finally:
            mod._CT_DB_PATH = original


# ---------------------------------------------------------------------------
# TestBackfill
# ---------------------------------------------------------------------------


class TestBackfill:
    """Backfill module tests."""

    def test_inserts_from_crtsh_response(self, db_path, tmp_path):
        """Mock crt.sh response is properly inserted."""
        from src.ct_collector.backfill import _backfill_chunk

        conn = init_db(db_path)
        progress_file = str(tmp_path / "progress.json")
        progress = {"completed_patterns": [], "total_inserted": 0, "last_updated": None}

        mock_response = [
            {"common_name": "a.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2027-01-01"},
            {"common_name": "b.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2027-01-01"},
        ]

        with patch("src.ct_collector.backfill._fetch_crtsh_page", return_value=mock_response):
            inserted = _backfill_chunk(conn, "%.dk", progress, progress_file)

        assert inserted == 2
        assert "%.dk" in progress["completed_patterns"]
        conn.close()

    def test_handles_rate_limit(self, db_path, tmp_path):
        """Backfill retries on request failure."""
        import requests

        from src.ct_collector.backfill import _backfill_chunk

        conn = init_db(db_path)
        progress_file = str(tmp_path / "progress.json")
        progress = {"completed_patterns": [], "total_inserted": 0, "last_updated": None}

        # Fail twice, succeed on third attempt
        call_count = 0

        def _side_effect(pattern, timeout=60):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.ConnectionError("rate limited")
            return [{"common_name": "retry.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2027-01-01"}]

        with patch("src.ct_collector.backfill._fetch_crtsh_page", side_effect=_side_effect), \
             patch("src.ct_collector.backfill.time.sleep"):
            inserted = _backfill_chunk(conn, "%.dk", progress, progress_file)

        assert inserted == 1
        assert call_count == 3
        conn.close()

    def test_resume(self, db_path, tmp_path):
        """Backfill skips already-completed patterns."""
        from src.ct_collector.backfill import _save_progress, backfill

        progress_file = str(tmp_path / "progress.json")

        # Pre-populate progress with all patterns completed
        patterns = ["%.dk"] + [f"%.{c}.dk" for c in "abcdefghijklmnopqrstuvwxyz0123456789"]
        progress = {
            "completed_patterns": patterns,
            "total_inserted": 100,
            "started_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
        }
        _save_progress(progress, progress_file)

        with patch("src.ct_collector.backfill._fetch_crtsh_page") as mock_fetch:
            backfill(db_path=db_path, progress_file=progress_file)
            mock_fetch.assert_not_called()

    def test_idempotent(self, db_path, tmp_path):
        """Running backfill twice with same data produces same result."""
        from src.ct_collector.backfill import _backfill_chunk

        conn = init_db(db_path)
        progress_file = str(tmp_path / "progress.json")

        mock_response = [
            {"common_name": "idem.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2027-01-01"},
        ]

        with patch("src.ct_collector.backfill._fetch_crtsh_page", return_value=mock_response):
            progress1 = {"completed_patterns": [], "total_inserted": 0, "last_updated": None}
            inserted1 = _backfill_chunk(conn, "%.dk", progress1, progress_file)

            progress2 = {"completed_patterns": [], "total_inserted": 0, "last_updated": None}
            inserted2 = _backfill_chunk(conn, "%.dk", progress2, progress_file)

        assert inserted1 == 1
        assert inserted2 == 0  # duplicate ignored

        # Only 1 row in DB
        count = conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
        assert count == 1
        conn.close()
