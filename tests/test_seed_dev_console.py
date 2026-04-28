"""Tests for scripts/dev/seed_dev_console.py.

Validates the DRYRUN-CONSOLE seed end-to-end against the real V1 + V6
read functions in src.db.console_views:

- V1 (list_trial_expiring) returns exactly 15 rows in days_remaining ASC.
- 3 V1-shadow CVRs are present in clients but absent from V1.
- V6 (list_retention_queue_pending_due) returns exactly 12 rows with the
  3 expected action types (6 purge / 5 anonymise / 1 purge_bookkeeping).
- 5 future purge_bookkeeping rows from Sentinel cancellations are present
  in retention_jobs but absent from V6 (the D5=B negative fixtures).
- Re-seed is idempotent (counts unchanged).
- --clean leaves zero DRYRUN-CONSOLE-% rows in any of the four tables.
- DRYRUN- prefix guards still exist in trial_expiry.py + retention runner.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.dev.seed_dev_console import (
    CVR_PREFIX,
    SeedError,
    allocate_roles,
    run_seed,
)
from src.db.console_views import (
    list_retention_queue_pending_due,
    list_trial_expiring,
)

_FIXTURE_BUCKETS = {
    "wordpress": ["wp1.test", "wp2.test", "wp3.test", "wp4.test", "wp5.test"],
    "drupal": ["dr1.test", "dr2.test", "dr3.test", "dr4.test", "dr5.test"],
    "joomla": ["jo1.test", "jo2.test", "jo3.test", "jo4.test", "jo5.test"],
    "squarespace": ["sq1.test", "sq2.test", "sq3.test", "sq4.test", "sq5.test"],
    "wix": ["wx1.test", "wx2.test", "wx3.test", "wx4.test", "wx5.test"],
    "shopify": ["sh1.test", "sh2.test", "sh3.test", "sh4.test", "sh5.test"],
}

_SEED_NOW = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
_SEED_NOW_ISO = _SEED_NOW.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_dataset(tmp_path: Path) -> Path:
    path = tmp_path / "dev_dataset.json"
    path.write_text(
        json.dumps({"campaign": "test-fixture", "buckets": _FIXTURE_BUCKETS}),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "clients.db"


@pytest.fixture
def open_conn(db_path: Path):
    def _open() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    return _open


def _seed(
    dataset: Path,
    db: Path,
    *,
    clean_only: bool = False,
    check_only: bool = False,
):
    return run_seed(
        dataset_path=dataset,
        db_path=db,
        now=_SEED_NOW,
        clean_only=clean_only,
        check_only=check_only,
    )


# ---------------------------------------------------------------------------
# Role allocation
# ---------------------------------------------------------------------------


def test_allocate_roles_slices_30_domains_in_insertion_order():
    roles = allocate_roles(_FIXTURE_BUCKETS)
    assert roles.v1_active == [
        "wp1.test", "wp2.test", "wp3.test", "wp4.test", "wp5.test",
        "dr1.test", "dr2.test", "dr3.test", "dr4.test", "dr5.test",
        "jo1.test", "jo2.test", "jo3.test", "jo4.test", "jo5.test",
    ]
    assert roles.v1_shadow == ["sq1.test", "sq2.test", "sq3.test"]
    assert roles.v6_watchman_purge == [
        "sq4.test", "sq5.test", "wx1.test", "wx2.test", "wx3.test", "wx4.test",
    ]
    assert roles.v6_sentinel_anonymise == [
        "wx5.test", "sh1.test", "sh2.test", "sh3.test", "sh4.test",
    ]
    assert roles.v6_forced_bookkeeping == ["sh5.test"]


def test_allocate_roles_rejects_wrong_total():
    bad = {"a": ["x.test"]}
    with pytest.raises(SeedError, match="Expected exactly 30"):
        allocate_roles(bad)


# ---------------------------------------------------------------------------
# V1 view shape
# ---------------------------------------------------------------------------


def test_v1_returns_15_rows_in_days_remaining_asc(
    fixture_dataset, db_path, open_conn
):
    report = _seed(fixture_dataset, db_path)
    assert report.v1_active == 15
    assert report.v1_shadow == 3

    conn = open_conn()
    try:
        rows = list_trial_expiring(conn, window_days=7, now=_SEED_NOW_ISO)
    finally:
        conn.close()

    assert len(rows) == 15
    days = [r["days_remaining"] for r in rows]
    assert days == sorted(days), "V1 must order by trial_expires_at ASC"
    # Under synthetic time (query.now == seed.anchor) the floor in
    # CAST(julianday(...) - julianday(now) AS INTEGER) lands exactly on
    # the seeded offset, so display range == seed range. Real-time
    # clock skew shifts this to [0, 6]; the live-API assertion lives in
    # scripts/dev/verify_dev_console_seed.py.
    assert min(days) == 1, "smallest seeded offset is 1d (no day-0 by design)"
    assert max(days) == 7, "upper edge (7d) must be present"


def test_v1_excludes_shadow_cvrs_via_intent_event_filter(
    fixture_dataset, db_path, open_conn
):
    _seed(fixture_dataset, db_path)

    conn = open_conn()
    try:
        v1_cvrs = {r["cvr"] for r in list_trial_expiring(conn, window_days=7, now=_SEED_NOW_ISO)}
        for shadow_idx in (16, 17, 18):
            shadow_cvr = f"{CVR_PREFIX}{shadow_idx:03d}"
            client_row = conn.execute(
                "SELECT cvr, status FROM clients WHERE cvr = ?", (shadow_cvr,)
            ).fetchone()
            assert client_row is not None, f"{shadow_cvr} missing from clients"
            assert client_row["status"] == "watchman_active", (
                f"{shadow_cvr} status not watchman_active — would fail V1 by status, "
                "not by intent-event filter; the test wouldn't prove anything"
            )
            assert shadow_cvr not in v1_cvrs, (
                f"{shadow_cvr} appears in V1 — the SENTINEL_CONVERSION_INTENT_EVENTS "
                "filter is broken or the seeder didn't write the disqualifying event"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# V6 view shape
# ---------------------------------------------------------------------------


def test_v6_returns_12_rows_with_three_action_types(
    fixture_dataset, db_path, open_conn
):
    report = _seed(fixture_dataset, db_path)
    assert report.v6_due == 12
    assert report.v6_future_bookkeeping == 5

    conn = open_conn()
    try:
        rows = list_retention_queue_pending_due(conn, now=_SEED_NOW_ISO)
    finally:
        conn.close()

    assert len(rows) == 12
    scheduled = [r["scheduled_for"] for r in rows]
    assert scheduled == sorted(scheduled), "V6 must order by scheduled_for ASC"

    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    assert by_action == {"purge": 6, "anonymise": 5, "purge_bookkeeping": 1}


def test_v6_excludes_future_purge_bookkeeping_rows(
    fixture_dataset, db_path, open_conn
):
    _seed(fixture_dataset, db_path)

    conn = open_conn()
    try:
        all_bookkeeping = conn.execute(
            "SELECT id, scheduled_for, status FROM retention_jobs "
            "WHERE action = 'purge_bookkeeping'"
        ).fetchall()
        assert len(all_bookkeeping) == 6, (
            "expected 1 forced + 5 future purge_bookkeeping rows = 6 total"
        )
        future = [r for r in all_bookkeeping if r["scheduled_for"] > _SEED_NOW_ISO]
        assert len(future) == 5
        assert all(r["status"] == "pending" for r in future), (
            "future rows must remain pending — they're just not due yet"
        )

        v6_ids = {
            r["id"] for r in list_retention_queue_pending_due(conn, now=_SEED_NOW_ISO)
        }
        future_ids = {r["id"] for r in future}
        assert future_ids.isdisjoint(v6_ids), (
            "future purge_bookkeeping rows leaked into V6 — scheduled_for filter broken"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Idempotency + clean
# ---------------------------------------------------------------------------


def test_re_seed_is_idempotent(fixture_dataset, db_path, open_conn):
    first = _seed(fixture_dataset, db_path)
    second = _seed(fixture_dataset, db_path)

    assert first.total_clients == second.total_clients == 30
    assert first.total_jobs == second.total_jobs == 17
    assert second.deleted == 30, "second pass must wipe the first 30 CVRs"

    conn = open_conn()
    try:
        client_count = conn.execute(
            "SELECT COUNT(*) FROM clients WHERE cvr LIKE ?", (CVR_PREFIX + "%",)
        ).fetchone()[0]
        job_count = conn.execute(
            "SELECT COUNT(*) FROM retention_jobs WHERE cvr LIKE ?",
            (CVR_PREFIX + "%",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert client_count == 30
    assert job_count == 17


def test_clean_removes_all_dryrun_console_rows(
    fixture_dataset, db_path, open_conn
):
    _seed(fixture_dataset, db_path)
    cleaned = _seed(fixture_dataset, db_path, clean_only=True)
    assert cleaned.deleted == 30

    conn = open_conn()
    try:
        for table in ("clients", "client_domains", "conversion_events", "retention_jobs"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE cvr LIKE ?",
                (CVR_PREFIX + "%",),
            ).fetchone()[0]
            assert count == 0, (
                f"{table} still has DRYRUN-CONSOLE-% rows after --clean"
            )
    finally:
        conn.close()


def test_clean_does_not_require_dataset(tmp_path: Path, db_path, open_conn):
    """--clean must wipe even if the dataset file is missing or invalid.

    Codex review item #5: ``make dev-seed-console-clean`` should never
    fail because ``config/dev_dataset.json`` is missing in the container —
    cleanup needs only the CVR prefix, not the role allocation.
    """
    missing_dataset = tmp_path / "does_not_exist.json"
    assert not missing_dataset.exists()

    # Run --clean against an empty DB (init_db creates schema). It must
    # succeed even though the dataset path is invalid.
    report = run_seed(
        dataset_path=missing_dataset,
        db_path=db_path,
        now=_SEED_NOW,
        clean_only=True,
    )
    assert report.mode == "clean"
    assert report.deleted == 0  # nothing was there to wipe


# ---------------------------------------------------------------------------
# Prefix guards: regression tripwires for seed safety
# ---------------------------------------------------------------------------


def test_dryrun_prefix_guard_remains_in_trial_expiry():
    """Seed safety: trial_expiry sweep must skip DRYRUN-* CVRs.

    If this fails, V1 active CVRs from this seed will be silently flipped
    to watchman_expired by the next sweep run. Asserts both the constant
    AND the live ``cvr.startswith(...)`` call site so an orphaned constant
    that's no longer consulted still trips the test.
    """
    text = Path("src/client_memory/trial_expiry.py").read_text(encoding="utf-8")
    assert '_DRYRUN_CVR_PREFIX = "DRYRUN-"' in text, (
        "_DRYRUN_CVR_PREFIX constant removed or renamed in trial_expiry.py"
    )
    assert "cvr.startswith(_DRYRUN_CVR_PREFIX)" in text, (
        "trial_expiry.py no longer skips DRYRUN-* CVRs via "
        "cvr.startswith(_DRYRUN_CVR_PREFIX) — V1 seed rows would get auto-expired"
    )


def test_dryrun_prefix_guard_remains_in_retention_runner():
    """Seed safety: retention runner must skip DRYRUN-* CVRs.

    If this fails, V6 retention jobs from this seed will be silently
    executed against fake clients on the next runner tick. Asserts both
    the constant AND the live ``cvr.startswith(...)`` call site.
    """
    text = Path("src/retention/runner.py").read_text(encoding="utf-8")
    assert 'DRYRUN_CVR_PREFIX = "DRYRUN-"' in text, (
        "DRYRUN_CVR_PREFIX constant removed or renamed in retention/runner.py"
    )
    assert "cvr.startswith(DRYRUN_CVR_PREFIX)" in text, (
        "retention/runner.py no longer skips DRYRUN-* CVRs via "
        "cvr.startswith(DRYRUN_CVR_PREFIX) — V6 seed jobs would get executed"
    )
