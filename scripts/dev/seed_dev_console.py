"""Seed DRYRUN-CONSOLE rows for V1 (trial-expiring) + V6 (retention-queue).

Purpose
-------
The operator console renders V1 (Watchman trials about to expire, with no
Sentinel-conversion intent) and V6 (retention jobs the cron is about to claim)
as the first two non-Onboarded tabs of the Clients view. In DEV both lists
are empty out of the box because the natural funnel hasn't run. This script
fabricates a deterministic 30-CVR dataset that exercises both views end to
end, including filter-correctness negative fixtures.

Domain → role allocation (insertion order over ``config/dev_dataset.json``):

    1..15   V1 active                 — 15 watchman_active rows, days_remaining
                                        spread across [0, 7] with edge coverage.
    16..18  V1 shadow                 — 3 rows that would qualify for V1 except
                                        a single SENTINEL_CONVERSION_INTENT_EVENTS
                                        row exists per CVR. Must NOT appear in V1.
    19..24  V6 Watchman purge         — 6 churned Watchman, one due 'purge' job
                                        each, scheduled_for spread 5min..12h ago.
    25..29  V6 Sentinel anonymise     — 5 churned Sentinel. schedule_churn_retention
                                        emits both an 'anonymise' job (due, 1d..21d
                                        ago) and a 'purge_bookkeeping' job (anchor
                                        + 5 years, future negative fixture for V6).
    30      V6 forced bookkeeping     — 1 standalone 'purge_bookkeeping' with
                                        scheduled_for hand-forced 30 days ago,
                                        notes-tagged as synthetic.

Result: 30 clients, 17 retention_jobs (12 due in V6 + 5 future negative
fixtures), 33 conversion_events (30 'signup' + 3 disqualifying intent events).

Idempotency: wipe-and-rebuild keyed on ``cvr LIKE 'DRYRUN-CONSOLE-%'``. The
prefix is a hard constant — the wipe refuses to run if it ever changes,
so the deletion blast radius can never silently widen.

Safety: the production retention runner and trial-expiry sweep both skip
``DRYRUN-`` CVRs, so the seed survives across cron ticks without being
auto-acted on. See ``src/retention/runner.DRYRUN_CVR_PREFIX`` and
``src/client_memory/trial_expiry._DRYRUN_CVR_PREFIX``.

Usage
-----
Inside the dev delivery container::

    python -m scripts.dev.seed_dev_console               # full seed
    python -m scripts.dev.seed_dev_console --check       # plan only, no writes
    python -m scripts.dev.seed_dev_console --clean       # wipe DRYRUN-CONSOLE-% only
    python -m scripts.dev.seed_dev_console --db-path /tmp/test.db --now 2026-04-27T12:00:00Z

Via Makefile::

    make dev-seed-console
    make dev-seed-console-clean
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Bootstrap project root onto sys.path so ``from src.*`` resolves when this
# script is invoked as ``python scripts/dev/seed_dev_console.py`` (the form
# used by the Makefile + ``docker exec``). The ``-m`` form does not need
# this, but mirrors of the sibling dev scripts keep it for parity.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from loguru import logger  # noqa: E402

from src.db.clients import add_domain, create_client  # noqa: E402
from src.db.connection import init_db  # noqa: E402
from src.db.conversion import record_conversion_event  # noqa: E402
from src.db.retention import schedule_churn_retention, schedule_retention_job  # noqa: E402

# ---------------------------------------------------------------------------
# Constants — locked plan values
# ---------------------------------------------------------------------------

# CVR prefix is a hard constant. The wipe asserts on this exact string
# before running any DELETE so a future rename can never widen the blast
# radius (e.g. accidentally to bare 'DRYRUN-' which would also match
# DRYRUN-VERIFY-SIGNUP and DRYRUN-BROWSER tokens used elsewhere).
CVR_PREFIX = "DRYRUN-CONSOLE-"

_DEFAULT_DATASET = _REPO_ROOT / "config" / "dev_dataset.json"
# In-container default. The host fallback is ``data/clients/clients.db``;
# the container's named-volume mount lives at ``/data/clients/clients.db``.
_DEFAULT_DB_PATH = Path("/data/clients/clients.db")

# V1 active: trial_expires_at offsets (days) from anchor. 15 values, edge
# coverage at 0 and 7 + duplicates so sort-stability is exercised.
_V1_DAYS_REMAINING: list[int] = [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7]

# V1 shadow: the disqualifying conversion event written per shadow CVR.
# Each is a member of SENTINEL_CONVERSION_INTENT_EVENTS, so each shadow row
# must be filtered out of V1 by the NOT EXISTS clause.
_V1_SHADOW_INTENT_EVENTS: list[str] = ["cta_click", "consent_signed", "payment_intent"]

# V1 shadow trial spread inside the 7-day window (mirrors the qualifying
# rows; the ONLY thing keeping these out of V1 is the intent event).
_V1_SHADOW_DAYS_REMAINING: list[int] = [3, 5, 7]

# V6 Watchman purge: 6 anchors in the recent past. ``schedule_churn_retention(
# plan='watchman')`` schedules a single 'purge' at anchor; we want the row
# to render at the top of V6 (least overdue) so we use the recent-past slots.
_V6_WATCHMAN_PURGE_ANCHOR_OFFSETS_SECONDS: list[int] = [
    -5 * 60,      # 5 minutes ago
    -10 * 60,     # 10 minutes ago
    -1 * 3600,    # 1 hour ago
    -2 * 3600,
    -6 * 3600,
    -12 * 3600,
]

# V6 Sentinel anonymise: 5 anchors so anchor + 30 days lands at -1d, -2d,
# -7d, -14d, -21d (all due). The matching purge_bookkeeping at anchor + 5y
# stays clearly future (the negative fixture for V6).
_V6_SENTINEL_ANCHOR_OFFSETS_DAYS: list[int] = [-31, -32, -37, -44, -51]

# V6 forced bookkeeping: a standalone purge_bookkeeping with hand-forced
# scheduled_for. Picked at -30d so it sorts deeper than every Sentinel
# anonymise (the deepest sentinel is at -21d) — distinct stamp, no clash.
_V6_FORCED_BOOKKEEPING_OFFSET_DAYS: int = -30

# Domain bucket totals must equal 30; the role slicer enforces it.
_TOTAL_DOMAINS_EXPECTED = 30


class SeedError(RuntimeError):
    """Raised when the seed cannot produce a consistent dataset."""


@dataclass
class SeedRoles:
    v1_active: list[str]
    v1_shadow: list[str]
    v6_watchman_purge: list[str]
    v6_sentinel_anonymise: list[str]
    v6_forced_bookkeeping: list[str]


@dataclass
class SeedReport:
    db_path: Path
    mode: str  # "write" | "check" | "clean"
    v1_active: int = 0
    v1_shadow: int = 0
    v6_watchman_purge: int = 0
    v6_sentinel_anonymise: int = 0
    v6_forced_bookkeeping: int = 0
    v6_future_bookkeeping: int = 0
    deleted: int = 0

    @property
    def v6_due(self) -> int:
        return (
            self.v6_watchman_purge
            + self.v6_sentinel_anonymise
            + self.v6_forced_bookkeeping
        )

    @property
    def total_clients(self) -> int:
        return (
            self.v1_active
            + self.v1_shadow
            + self.v6_watchman_purge
            + self.v6_sentinel_anonymise
            + self.v6_forced_bookkeeping
        )

    @property
    def total_jobs(self) -> int:
        return self.v6_due + self.v6_future_bookkeeping

    def summary(self) -> str:
        return (
            f"mode={self.mode} db={self.db_path} "
            f"V1_active={self.v1_active} V1_shadow={self.v1_shadow} "
            f"V6_due={self.v6_due} V6_future={self.v6_future_bookkeeping} "
            f"clients={self.total_clients} jobs={self.total_jobs} "
            f"deleted={self.deleted}"
        )


# ---------------------------------------------------------------------------
# Dataset loading + role allocation
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> dict:
    if not path.is_file():
        raise SeedError(f"Dataset file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "buckets" not in data:
        raise SeedError(f"Dataset must have a 'buckets' object: {path}")
    return data


def allocate_roles(buckets: dict[str, list[str]]) -> SeedRoles:
    """Flatten the 30 fixture domains in dict-insertion order and slice."""
    flat: list[str] = []
    for _bucket_name, domains in buckets.items():
        flat.extend(domains)
    if len(flat) != _TOTAL_DOMAINS_EXPECTED:
        raise SeedError(
            f"Expected exactly {_TOTAL_DOMAINS_EXPECTED} domains across buckets, "
            f"got {len(flat)}. The seed plan assumes the canonical 30-domain "
            "dev fixture (5 worst per hosting bucket × 6 buckets)."
        )
    return SeedRoles(
        v1_active=flat[0:15],
        v1_shadow=flat[15:18],
        v6_watchman_purge=flat[18:24],
        v6_sentinel_anonymise=flat[24:29],
        v6_forced_bookkeeping=flat[29:30],
    )


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Format as ISO-8601 UTC matching ``src.db.connection._now``."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_now(value: str | None) -> datetime:
    """Accept ``--now`` arg or default to current UTC. Returns aware UTC dt."""
    if value is None:
        return datetime.now(UTC)
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------


def wipe_dryrun_console(conn: sqlite3.Connection) -> int:
    """Delete every row keyed by ``cvr LIKE 'DRYRUN-CONSOLE-%'``.

    Hard guard: refuses to run if ``CVR_PREFIX`` has been changed away from
    the exact literal ``DRYRUN-CONSOLE-``. The seed must never run a
    broader DELETE — bare ``DRYRUN-%`` would also match
    ``DRYRUN-VERIFY-SIGNUP`` and ``DRYRUN-BROWSER`` tokens used by other
    dev scripts.

    Returns the number of clients rows deleted (proxy for total seeded
    CVRs cleared).
    """
    if CVR_PREFIX != "DRYRUN-CONSOLE-":
        raise SeedError(
            f"CVR_PREFIX changed to {CVR_PREFIX!r} — refusing to wipe. "
            "Audit every DELETE in this file before relaxing this guard."
        )
    pattern = CVR_PREFIX + "%"
    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM retention_jobs WHERE cvr LIKE ?", (pattern,))
        conn.execute("DELETE FROM conversion_events WHERE cvr LIKE ?", (pattern,))
        conn.execute("DELETE FROM client_domains WHERE cvr LIKE ?", (pattern,))
        cur = conn.execute("DELETE FROM clients WHERE cvr LIKE ?", (pattern,))
        deleted = cur.rowcount or 0
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return deleted


# ---------------------------------------------------------------------------
# Synthetic value helpers (D9: fake-but-shaped-like-real)
# ---------------------------------------------------------------------------


def _cvr_for(idx: int) -> str:
    return f"{CVR_PREFIX}{idx:03d}"


def _telegram_chat_id(idx: int) -> str:
    return f"DRYRUN-CHAT-{idx:03d}"


def _contact_email(idx: int) -> str:
    return f"noreply+dryrun-{idx:03d}@digitalvagt.dk"


def _company_name(domain: str) -> str:
    return f"DRYRUN-CONSOLE: {domain}"


# ---------------------------------------------------------------------------
# Seeders
# ---------------------------------------------------------------------------


def seed_v1_active(
    conn: sqlite3.Connection, domains: list[str], anchor: datetime
) -> int:
    """15 watchman_active rows. trial_expires spread 0..7 days from anchor."""
    if len(domains) != 15:
        raise SeedError(f"V1 active expects 15 domains, got {len(domains)}")
    inserted = 0
    for offset, domain in enumerate(domains):
        idx = offset + 1
        cvr = _cvr_for(idx)
        days_remaining = _V1_DAYS_REMAINING[offset]
        trial_expires = anchor + timedelta(days=days_remaining)
        trial_started = trial_expires - timedelta(days=30)
        signup_source = "operator_manual" if idx % 5 == 0 else "email_reply"
        create_client(
            conn,
            cvr=cvr,
            company_name=_company_name(domain),
            plan="watchman",
            status="watchman_active",
            telegram_chat_id=_telegram_chat_id(idx),
            contact_email=_contact_email(idx),
            signup_source=signup_source,
            trial_started_at=_iso(trial_started),
            trial_expires_at=_iso(trial_expires),
            consent_granted=0,
            data_retention_mode="standard",
        )
        add_domain(conn, cvr, domain, is_primary=1)
        record_conversion_event(
            conn,
            cvr,
            "signup",
            source="signup_form",
            occurred_at=_iso(trial_started),
        )
        inserted += 1
    return inserted


def seed_v1_shadow(
    conn: sqlite3.Connection, domains: list[str], anchor: datetime
) -> int:
    """3 rows that look like V1 candidates but carry a disqualifying intent event.

    Each shadow row gets a 'signup' event (so the funnel is realistic) plus
    one of cta_click / consent_signed / payment_intent — all members of
    ``SENTINEL_CONVERSION_INTENT_EVENTS``. The V1 query's ``NOT EXISTS``
    clause must filter them out.
    """
    if len(domains) != 3:
        raise SeedError(f"V1 shadow expects 3 domains, got {len(domains)}")
    if len(_V1_SHADOW_INTENT_EVENTS) != 3 or len(_V1_SHADOW_DAYS_REMAINING) != 3:
        raise SeedError("V1 shadow tables must be length 3")
    inserted = 0
    for offset, (domain, intent_event, days_remaining) in enumerate(
        zip(domains, _V1_SHADOW_INTENT_EVENTS, _V1_SHADOW_DAYS_REMAINING, strict=True)
    ):
        idx = 16 + offset
        cvr = _cvr_for(idx)
        trial_expires = anchor + timedelta(days=days_remaining)
        trial_started = trial_expires - timedelta(days=30)
        create_client(
            conn,
            cvr=cvr,
            company_name=_company_name(domain),
            plan="watchman",
            status="watchman_active",
            telegram_chat_id=_telegram_chat_id(idx),
            contact_email=_contact_email(idx),
            signup_source="email_reply",
            trial_started_at=_iso(trial_started),
            trial_expires_at=_iso(trial_expires),
            consent_granted=0,
            data_retention_mode="standard",
        )
        add_domain(conn, cvr, domain, is_primary=1)
        record_conversion_event(
            conn,
            cvr,
            "signup",
            source="signup_form",
            occurred_at=_iso(trial_started),
        )
        record_conversion_event(
            conn,
            cvr,
            intent_event,
            source="dryrun_console_seed",
            occurred_at=_iso(anchor - timedelta(hours=1)),
        )
        inserted += 1
    return inserted


def seed_v6_watchman_purge(
    conn: sqlite3.Connection, domains: list[str], anchor: datetime
) -> int:
    """6 churned Watchman CVRs each with one due 'purge' job.

    ``schedule_churn_retention(plan='watchman')`` schedules a single
    ``purge`` row at the anchor and flips ``data_retention_mode`` to
    ``purge_scheduled``. The seed creates the client with
    ``status='churned'`` upfront — there's no point materialising the
    realistic ``watchman_active → churned`` transition for a fixture.
    """
    if len(domains) != 6:
        raise SeedError(f"V6 Watchman expects 6 domains, got {len(domains)}")
    if len(_V6_WATCHMAN_PURGE_ANCHOR_OFFSETS_SECONDS) != 6:
        raise SeedError("V6 Watchman offset table must be length 6")
    inserted = 0
    for offset, (domain, anchor_offset_seconds) in enumerate(
        zip(domains, _V6_WATCHMAN_PURGE_ANCHOR_OFFSETS_SECONDS, strict=True)
    ):
        idx = 19 + offset
        cvr = _cvr_for(idx)
        purge_anchor = anchor + timedelta(seconds=anchor_offset_seconds)
        # Realistic timeline: trial_started 60d before purge anchor,
        # trial_expires 30d before. Not surfaced by V6 but kept coherent.
        trial_started = purge_anchor - timedelta(days=60)
        trial_expires = purge_anchor - timedelta(days=30)
        create_client(
            conn,
            cvr=cvr,
            company_name=_company_name(domain),
            plan="watchman",
            status="churned",
            telegram_chat_id=_telegram_chat_id(idx),
            contact_email=_contact_email(idx),
            signup_source="email_reply",
            trial_started_at=_iso(trial_started),
            trial_expires_at=_iso(trial_expires),
            consent_granted=0,
            data_retention_mode="standard",
        )
        add_domain(conn, cvr, domain, is_primary=1)
        # schedule_churn_retention sets data_retention_mode='purge_scheduled',
        # stamps churn_purge_at + churn_requested_at + churn_reason, and
        # writes the single 'purge' retention_job row.
        schedule_churn_retention(
            conn,
            cvr,
            "watchman",
            anchor_at=_iso(purge_anchor),
            churn_reason="dryrun-console fixture: watchman non-converter",
        )
        inserted += 1
    return inserted


def seed_v6_sentinel_anonymise(
    conn: sqlite3.Connection, domains: list[str], anchor: datetime
) -> int:
    """5 churned Sentinel CVRs.

    For each, ``schedule_churn_retention(plan='sentinel', anchor_at=<past>)``
    emits TWO retention jobs: an ``anonymise`` at anchor + 30d (due, since
    every anchor is ≥ 31d in the past) and a ``purge_bookkeeping`` at
    anchor + 5y (future negative fixture — must NOT appear in V6).

    Returns a (due_count, future_count) tuple via the mutating side
    effect; for the report we count due rows here and infer future_count
    as equal to due_count (1-to-1 from the helper).
    """
    if len(domains) != 5:
        raise SeedError(f"V6 Sentinel expects 5 domains, got {len(domains)}")
    if len(_V6_SENTINEL_ANCHOR_OFFSETS_DAYS) != 5:
        raise SeedError("V6 Sentinel anchor table must be length 5")
    inserted = 0
    for offset, (domain, anchor_offset_days) in enumerate(
        zip(domains, _V6_SENTINEL_ANCHOR_OFFSETS_DAYS, strict=True)
    ):
        idx = 25 + offset
        cvr = _cvr_for(idx)
        churn_anchor = anchor + timedelta(days=anchor_offset_days)
        # Realistic Sentinel timeline: 90d trial → upgrade → ran → cancelled.
        trial_started = churn_anchor - timedelta(days=120)
        trial_expires = churn_anchor - timedelta(days=90)
        create_client(
            conn,
            cvr=cvr,
            company_name=_company_name(domain),
            plan="sentinel",
            status="churned",
            telegram_chat_id=_telegram_chat_id(idx),
            contact_email=_contact_email(idx),
            signup_source="email_reply",
            trial_started_at=_iso(trial_started),
            trial_expires_at=_iso(trial_expires),
            consent_granted=1,
            data_retention_mode="standard",
        )
        add_domain(conn, cvr, domain, is_primary=1)
        schedule_churn_retention(
            conn,
            cvr,
            "sentinel",
            anchor_at=_iso(churn_anchor),
            churn_reason="dryrun-console fixture: sentinel cancelled",
        )
        inserted += 1
    return inserted


def seed_v6_forced_bookkeeping(
    conn: sqlite3.Connection, domains: list[str], anchor: datetime
) -> int:
    """1 standalone ``purge_bookkeeping`` row with hand-forced past scheduled_for.

    Real Bogføringsloven 5y horizon would put the natural row 5 years out.
    Forced into the past here so the action badge renders in V6 today,
    note-tagged so any operator reading the row sees why.
    """
    if len(domains) != 1:
        raise SeedError(f"V6 forced expects 1 domain, got {len(domains)}")
    domain = domains[0]
    cvr = _cvr_for(30)
    scheduled_at = anchor + timedelta(days=_V6_FORCED_BOOKKEEPING_OFFSET_DAYS)
    trial_started = anchor - timedelta(days=120)
    trial_expires = anchor - timedelta(days=90)
    create_client(
        conn,
        cvr=cvr,
        company_name=_company_name(domain),
        plan="sentinel",
        status="churned",
        telegram_chat_id=_telegram_chat_id(30),
        contact_email=_contact_email(30),
        signup_source="email_reply",
        trial_started_at=_iso(trial_started),
        trial_expires_at=_iso(trial_expires),
        consent_granted=1,
        data_retention_mode="purge_scheduled",
        churn_reason="dryrun-console fixture: sentinel long-cancelled",
        churn_requested_at=_iso(scheduled_at),
        churn_purge_at=_iso(scheduled_at),
    )
    add_domain(conn, cvr, domain, is_primary=1)
    schedule_retention_job(
        conn,
        cvr,
        "purge_bookkeeping",
        _iso(scheduled_at),
        notes=(
            "synthetic — anchor backdated for UI visibility. "
            "Real Bogføringsloven 5y horizon would put this 5 years out; "
            "forced into the past here so V6 renders the action badge."
        ),
    )
    return 1


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_seed(
    *,
    dataset_path: Path = _DEFAULT_DATASET,
    db_path: Path = _DEFAULT_DB_PATH,
    now: datetime | None = None,
    check_only: bool = False,
    clean_only: bool = False,
) -> SeedReport:
    """Run the seed.

    Args:
        dataset_path: Path to the JSON dataset.
        db_path: SQLite DB path. Defaults to the in-container named-volume
            mount; override for tests.
        now: Override the seed anchor time. Defaults to current UTC.
        check_only: Validate dataset + role allocation, no DB writes.
        clean_only: Wipe DRYRUN-CONSOLE-% rows and exit; no re-seed.

    Returns:
        ``SeedReport`` describing the outcome.
    """
    if check_only and clean_only:
        raise SeedError("--check and --clean are mutually exclusive")

    mode = "check" if check_only else ("clean" if clean_only else "write")
    report = SeedReport(db_path=db_path, mode=mode)

    # --clean only needs the prefix-keyed wipe; the dataset is irrelevant.
    # Loading it before the early exit would make ``make dev-seed-console-clean``
    # fail when ``config/dev_dataset.json`` is missing or invalid in the
    # container — Codex review item #5.
    if clean_only:
        conn = init_db(str(db_path))
        try:
            report.deleted = wipe_dryrun_console(conn)
        finally:
            conn.close()
        return report

    dataset = load_dataset(dataset_path)
    roles = allocate_roles(dataset["buckets"])

    if check_only:
        # No DB connection at all in check mode.
        report.v1_active = len(roles.v1_active)
        report.v1_shadow = len(roles.v1_shadow)
        report.v6_watchman_purge = len(roles.v6_watchman_purge)
        report.v6_sentinel_anonymise = len(roles.v6_sentinel_anonymise)
        report.v6_forced_bookkeeping = len(roles.v6_forced_bookkeeping)
        report.v6_future_bookkeeping = len(roles.v6_sentinel_anonymise)
        return report

    anchor = now or datetime.now(UTC)
    conn = init_db(str(db_path))
    try:
        report.deleted = wipe_dryrun_console(conn)

        report.v1_active = seed_v1_active(conn, roles.v1_active, anchor)
        report.v1_shadow = seed_v1_shadow(conn, roles.v1_shadow, anchor)
        report.v6_watchman_purge = seed_v6_watchman_purge(
            conn, roles.v6_watchman_purge, anchor
        )
        report.v6_sentinel_anonymise = seed_v6_sentinel_anonymise(
            conn, roles.v6_sentinel_anonymise, anchor
        )
        report.v6_forced_bookkeeping = seed_v6_forced_bookkeeping(
            conn, roles.v6_forced_bookkeeping, anchor
        )
        # Sentinel anonymise CVRs each emit one anchor+5y purge_bookkeeping
        # row alongside their anonymise — that's the future negative fixture.
        report.v6_future_bookkeeping = report.v6_sentinel_anonymise
    finally:
        conn.close()

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_dev_console",
        description=(
            "Seed DRYRUN-CONSOLE-% rows for V1 (trial-expiring) + V6 "
            "(retention-queue) operator console verification."
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_DEFAULT_DATASET,
        help="Path to the dev dataset JSON (default: config/dev_dataset.json).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="Path to the clients SQLite DB (default: /data/clients/clients.db).",
    )
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help=(
            "Override the seed anchor time (ISO-8601 UTC, e.g. "
            "2026-04-27T12:00:00Z). Defaults to current UTC."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Validate dataset and print planned counts. No DB writes.",
    )
    group.add_argument(
        "--clean",
        action="store_true",
        help="Wipe DRYRUN-CONSOLE-%% rows and exit; no re-seed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run_seed(
            dataset_path=args.dataset,
            db_path=args.db_path,
            now=_parse_now(args.now),
            check_only=args.check,
            clean_only=args.clean,
        )
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    logger.info("dev_console_seed {}", report.summary())
    if report.mode == "check":
        print(
            f"check: V1_active={report.v1_active} V1_shadow={report.v1_shadow} "
            f"V6_due={report.v6_due} V6_future={report.v6_future_bookkeeping} "
            f"clients={report.total_clients} jobs={report.total_jobs}"
        )
    elif report.mode == "clean":
        print(f"cleaned: deleted={report.deleted} clients (DRYRUN-CONSOLE-%)")
    else:
        print(
            f"seeded: V1_active={report.v1_active} V1_shadow={report.v1_shadow} "
            f"V6_due={report.v6_due} V6_future={report.v6_future_bookkeeping} "
            f"clients={report.total_clients} jobs={report.total_jobs} "
            f"deleted_first={report.deleted}"
        )
    return 0


if __name__ == "__main__":
    os.chdir(_REPO_ROOT)
    raise SystemExit(main())
