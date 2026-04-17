"""End-to-end dry run for the Sentinel cert-change alert path.

Runs INSIDE the dev delivery container (shares the `client-data` Docker
volume, has `/run/secrets/*`, and talks to the internal Redis). Launched
by ``make dev-cert-dry-run`` which docker-cps the current host copy in
before exec.

Exercises:

    publisher : ct_monitor.poll_and_diff_client → client_cert_changes row
                                                + Redis client-cert-change event
    composer  : compose_cert_change(row_payload) → non-empty HTML
    subscriber: delivery runner _handle_cert_change → console:logs line

Does NOT send any Telegram message. The synthetic client's
``telegram_chat_id`` is NULL, so the runner hits its early-return at
``src/delivery/runner.py:358`` and emits a ``cert_change_no_chat_id``
INFO log — which flows through the ``redis_sink`` ``console:logs``
channel and is how we prove the subscriber fired.

Cleanup is unconditional on the ``DRYRUN-`` CVR prefix in a finally block.
Exits 0 on green, 1 on any failure.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import redis  # noqa: E402

from src.client_memory import ct_monitor  # noqa: E402
from src.composer.telegram import compose_cert_change  # noqa: E402
from src.core.secrets import get_secret  # noqa: E402
from src.db.migrate import _add_missing_columns  # noqa: E402

CONFIG_PATH = REPO / "config" / "ct_dry_run.json"
DB_PATH = os.environ.get("HEIMDALL_DRYRUN_DB", "/data/clients/clients.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return 1


def _assert_environment() -> None:
    if not Path(DB_PATH).exists():
        raise SystemExit(
            f"[FAIL] DB missing at {DB_PATH}. "
            "This script must run inside the dev delivery container via "
            "`make dev-cert-dry-run`."
        )
    if os.environ.get("HEIMDALL_SOURCE") != "delivery":
        # Not fatal — the env var is cosmetic — but a strong hint we're in the wrong place.
        print(
            f"[WARN] HEIMDALL_SOURCE={os.environ.get('HEIMDALL_SOURCE')!r}, "
            "expected 'delivery'. Script may not be running in the delivery container."
        )


def _assert_schema(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(client_cert_changes)")}
    expected = {
        "id", "cvr", "domain", "change_type", "details_json",
        "detected_at", "status", "delivered_at",
    }
    missing = expected - cols
    if missing:
        raise SystemExit(
            f"[FAIL] client_cert_changes missing columns {sorted(missing)}. "
            "Run `docker exec heimdall_dev-delivery-1 python -m src.db.migrate "
            f"--db-path {DB_PATH}`."
        )


def _cleanup(conn: sqlite3.Connection, prefix: str) -> dict[str, int]:
    counts = {}
    for table in (
        "client_cert_changes",
        "client_cert_snapshots",
        "client_domains",
        "clients",
    ):
        cur = conn.execute(f"DELETE FROM {table} WHERE cvr LIKE ?", (prefix + "%",))
        counts[table] = cur.rowcount
    conn.commit()
    return counts


def _insert_client(conn: sqlite3.Connection, cvr: str, cfg: dict) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO clients
            (cvr, company_name, plan, status, telegram_chat_id, contact_name,
             preferred_language, preferred_channel, gdpr_sensitive, gdpr_reasons,
             consent_granted, created_at, updated_at)
        VALUES (?, ?, 'sentinel', 'active', NULL, ?, ?, 'telegram', 0, '[]', 0, ?, ?)
        """,
        (
            cvr,
            cfg["synthetic_company_name"],
            cfg["synthetic_contact_name"],
            cfg["synthetic_preferred_language"],
            now,
            now,
        ),
    )


def _insert_domain(conn: sqlite3.Connection, cvr: str, domain: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO client_domains (cvr, domain, is_primary, added_at) "
        "VALUES (?, ?, 1, ?)",
        (cvr, domain, _now_iso()),
    )


def _seed_stale_snapshot(
    conn: sqlite3.Connection, cvr: str, domain: str, cfg: dict
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO client_cert_snapshots
            (cvr, domain, cert_sha256, common_name, issuer_name,
             dns_names_json, not_before, not_after, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cvr,
            domain,
            cfg["fake_prior_cert_sha256"],
            cfg["fake_prior_common_name"],
            cfg["fake_prior_issuer_name"],
            json.dumps(cfg["fake_prior_dns_names"]),
            cfg["fake_prior_not_before"],
            cfg["fake_prior_not_after"],
            now,
            now,
        ),
    )


def main() -> int:
    _assert_environment()
    cfg = json.loads(CONFIG_PATH.read_text())

    cvr = cfg["synthetic_cvr"]
    domain = cfg["domain"]
    prefix = cfg["cvr_prefix"]
    wait_s = cfg["subscriber_wait_seconds"]

    api_key = get_secret("certspotter_api_key", "CERTSPOTTER_API_KEY")
    if not api_key:
        print("[WARN] no CertSpotter API key — using unauthenticated rate limit")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    added = _add_missing_columns(conn)
    if added:
        conn.commit()
        print(f"[MIGRATE] added columns: {added}")

    _assert_schema(conn)

    pre = _cleanup(conn, prefix)
    if sum(pre.values()) > 0:
        print(f"[PRE-CLEANUP] cleared stale rows: {pre}")

    print(f"[SETUP] client {cvr} + domain {domain} + stale snapshot")
    _insert_client(conn, cvr, cfg)
    _insert_domain(conn, cvr, domain)
    _seed_stale_snapshot(conn, cvr, domain, cfg)
    conn.commit()

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.ping()
    except redis.RedisError as exc:
        _cleanup(conn, prefix)
        conn.close()
        return _fail(f"redis unreachable at {REDIS_URL}: {exc}")

    pub = r.pubsub()
    pub.subscribe("client-cert-change", "console:logs")
    # Drain the subscribe-confirmation frames.
    for _ in range(2):
        pub.get_message(timeout=1.0)

    try:
        print(f"[POLL] CertSpotter → {domain}")
        summary = ct_monitor.poll_and_diff_client(
            cvr=cvr,
            primary_domain=domain,
            db_conn=conn,
            redis_conn=r,
            api_key=api_key,
            http_timeout_s=cfg["certspotter_timeout_seconds"],
        )
        print(
            f"    issuances={summary['issuances']} "
            f"new_snapshots={summary['new_snapshots']} changes={summary['changes']}"
        )
        if summary["issuances"] == 0:
            return _fail("CertSpotter returned 0 issuances — rate-limited or domain unknown")
        if summary["changes"] == 0:
            return _fail("ct_monitor emitted 0 changes — classifier did not fire")

        got_event: dict | None = None
        got_sub_log = False
        deadline = time.time() + wait_s
        while time.time() < deadline and (got_event is None or not got_sub_log):
            msg = pub.get_message(timeout=1.0)
            if not msg or msg["type"] != "message":
                continue
            if msg["channel"] == "client-cert-change" and got_event is None:
                try:
                    payload = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if payload.get("cvr") == cvr:
                    got_event = payload
                    print(
                        f"[PUB] redis event: change_id={payload['change_id']} "
                        f"type={payload['change_type']}"
                    )
            elif msg["channel"] == "console:logs" and not got_sub_log:
                try:
                    log = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if (
                    log.get("source") == "delivery"
                    and log.get("ctx", {}).get("cvr") == cvr
                ):
                    got_sub_log = True
                    print(
                        f"[SUB] delivery log: {log.get('message', '')} "
                        f"(ctx={log.get('ctx')})"
                    )

        if got_event is None:
            return _fail(f"no client-cert-change event received within {wait_s}s")
        if not got_sub_log:
            return _fail(
                f"no delivery-sourced console:log for cvr={cvr} within {wait_s}s — "
                "subscriber did not fire"
            )

        row = conn.execute(
            "SELECT change_type, details_json FROM client_cert_changes "
            "WHERE cvr = ? AND domain = ? ORDER BY id DESC LIMIT 1",
            (cvr, domain),
        ).fetchone()
        if not row:
            return _fail("client_cert_changes row missing after poll")
        payload = {
            "change_type": row["change_type"],
            "domain": domain,
            "details": json.loads(row["details_json"]),
        }
        messages = compose_cert_change(
            payload, lang="en", contact_name=cfg["synthetic_contact_name"]
        )
        if not messages or not any(messages):
            return _fail("compose_cert_change returned empty")
        preview = messages[0][:120].replace("\n", " ")
        total_len = sum(len(m) for m in messages)
        print(f"[COMPOSE] HTML len={total_len}, preview: {preview}…")

        print("[PASS] cert-change dry run green")
        return 0

    finally:
        try:
            pub.unsubscribe()
            pub.close()
        except Exception:
            pass
        try:
            counts = _cleanup(conn, prefix)
            print(f"[CLEANUP] deleted rows: {counts}")
        finally:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
