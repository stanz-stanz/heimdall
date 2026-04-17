"""End-to-end dry run for the Finding Interpreter (M33 operational verification).

Runs INSIDE the dev delivery container (shares the ``client-data`` Docker
volume, has ``/run/secrets/*`` mounted, and talks to the internal Redis).
Launched by ``make dev-interpret-dry-run`` which docker-cps the current
host copy of this script and its config into the container before exec.

Exercises three layers of the live interpretation path:

    seed      : clients + client_domains + brief_snapshots rows for a
                synthetic Watchman client under CVR prefix DRYRUN-INT-
    publish   : redis PUBLISH client-scan-complete {domain, job_id, cvr}
    observe   : subscribe to console:logs, wait for the delivery runner
                to emit the deterministic log lines that prove it walked
                the _handle_scan_complete path

Modes
-----
``--mode=observe`` (default, free):
    Synthetic client has ``telegram_chat_id = NULL``. The delivery runner
    early-returns at ``src/delivery/runner.py`` after emitting the
    ``no_chat_id_for_client`` log. **The interpreter is NOT called in
    this mode** — the pre-interpreter early-return makes observe safe to
    run without any Claude API spend. We assert on the deterministic log
    pair (``processing_scan_event`` then ``no_chat_id_for_client``).

``--mode=send-to-operator`` (real API call, ~$0.02):
    Overrides ``telegram_chat_id`` on the synthetic client with
    ``TELEGRAM_OPERATOR_CHAT_ID`` so the runner proceeds through
    ``interpret_brief`` (live Claude API), ``compose_telegram``, and
    ``send_with_logging``. Asserts on the ``delivery_log`` row that
    ``send_with_logging`` writes. Useful for visual inspection of the
    real Telegram message. Cleanup still wipes every DRYRUN-INT-* row.

Cost guard
----------
Refuses to run under CI (``CI=true`` or ``GITHUB_ACTIONS=true``) unless
``HEIMDALL_ALLOW_PAID_DRYRUN=1`` is set in the same env, even for the
observe mode. The blanket guard is belt-and-braces: if someone changes
``--mode`` semantics later, CI still won't burn API budget silently.

Cleanup
-------
Pre-run: every invocation (both modes) wipes the ``DRYRUN-INT-`` prefix
before seeding, so reruns start clean regardless of what the previous
run left behind. No ALL-scope wipes.

Post-run (finally):
- observe mode wipes the prefix again.
- send-to-operator mode SKIPS the wipe. The Telegram message still has
  live Approve/Reject buttons whose callbacks look up ``delivery_log``
  by id, and a cleanup-then-click would hit the approval handler's
  "Delivery {id} not found" error path. Synthetic rows linger until
  the operator clicks (approval handler updates ``delivery_log.status``
  to ``delivered`` or ``rejected``) or until the next invocation's
  pre-run cleanup fires.

Exits 0 on green, 1 on any failure.
"""

from __future__ import annotations

import argparse
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

from src.core.secrets import get_secret  # noqa: E402
from src.db.migrate import _add_missing_columns  # noqa: E402

CONFIG_PATH = REPO / "config" / "interpret_dry_run.json"
DB_PATH = os.environ.get("HEIMDALL_DRYRUN_DB", "/data/clients/clients.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return 1


def _assert_environment() -> None:
    if not Path(DB_PATH).exists():
        raise SystemExit(
            f"[FAIL] DB missing at {DB_PATH}. "
            "This script must run inside the dev delivery container via "
            "`make dev-interpret-dry-run`."
        )
    if os.environ.get("HEIMDALL_SOURCE") != "delivery":
        # Not fatal — cosmetic — but a strong hint we're in the wrong place.
        print(
            f"[WARN] HEIMDALL_SOURCE={os.environ.get('HEIMDALL_SOURCE')!r}, "
            "expected 'delivery'. Script may not be running in the delivery container."
        )


def _assert_schema(conn: sqlite3.Connection) -> None:
    """Confirm brief_snapshots has the columns save_brief_snapshot writes.

    We only assert on the columns our seed touches directly plus the
    handful the delivery runner reads (domain, brief_json). PRAGMA
    pulls the live set so drift shows up here, not in a silent INSERT.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(brief_snapshots)")}
    required = {
        "id", "domain", "scan_date", "bucket", "cms",
        "finding_count", "critical_count", "high_count",
        "company_name", "cvr", "brief_json", "created_at",
    }
    missing = required - cols
    if missing:
        raise SystemExit(
            f"[FAIL] brief_snapshots missing columns {sorted(missing)}. "
            "Run the delivery container migrate step: "
            f"`docker exec heimdall_dev-delivery-1 python -m src.db.migrate --db-path {DB_PATH}`."
        )


def _cleanup(conn: sqlite3.Connection, prefix: str) -> dict[str, int]:
    """Delete every row tied to the DRYRUN-INT- prefix.

    brief_snapshots is unique-indexed on (domain, scan_date) — we delete
    by cvr since the seed sets cvr to the synthetic prefix. delivery_log
    rows written by send_with_logging in send-to-operator mode must also
    be purged so successive reruns start clean.
    """
    counts = {}
    for table in ("brief_snapshots", "delivery_log", "client_domains", "clients"):
        cur = conn.execute(f"DELETE FROM {table} WHERE cvr LIKE ?", (prefix + "%",))
        counts[table] = cur.rowcount
    conn.commit()
    return counts


def _insert_client(
    conn: sqlite3.Connection, cvr: str, cfg: dict, chat_id: str | None
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT OR REPLACE INTO clients
            (cvr, company_name, plan, status, telegram_chat_id, contact_name,
             preferred_language, preferred_channel, gdpr_sensitive, gdpr_reasons,
             consent_granted, created_at, updated_at)
        VALUES (?, ?, ?, 'active', ?, ?, ?, 'telegram', 1,
                '["synthetic GDPR flag for dry run"]', 0, ?, ?)
        """,
        (
            cvr,
            cfg["synthetic_company_name"],
            cfg["synthetic_plan"],
            chat_id,
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


def _seed_brief(
    conn: sqlite3.Connection, cvr: str, domain: str, cfg: dict
) -> dict:
    """Write a brief_snapshots row with 3 findings.

    Findings shape matches brief_generator output (severity/description/risk
    plus optional provenance). The pre-filter in _handle_scan_complete
    accepts critical|high only, so we need at least one high-severity row
    to reach the interpreter in send-to-operator mode. We also include a
    medium finding so the pre-filter has work to do.
    """
    scan_date = _today()
    brief = {
        "domain": domain,
        "cvr": cvr,
        "company_name": cfg["synthetic_company_name"],
        "scan_date": scan_date,
        "bucket": "A",
        "gdpr_sensitive": True,
        "gdpr_reasons": ["synthetic GDPR flag for dry run"],
        "industry": cfg["industry"],
        "technology": {
            "cms": "WordPress",
            "hosting": "Synthetic Host",
            "ssl": {
                "valid": True,
                "issuer": "Synthetic CA",
                "expiry": "2027-01-01",
                "days_remaining": 365,
                "tls_version": "TLS 1.3",
            },
            "server": "nginx",
            "detected_plugins": ["synthetic-plugin"],
            "plugin_versions": {"synthetic-plugin": "1.0.0"},
            "detected_themes": [],
            "headers": {
                "x_frame_options": False,
                "content_security_policy": False,
                "strict_transport_security": False,
                "x_content_type_options": False,
                "permissions_policy": False,
                "referrer_policy": False,
                "server_value": "nginx",
                "x_powered_by": "",
            },
        },
        "tech_stack": ["nginx"],
        "plugin_versions": {"synthetic-plugin": "1.0.0"},
        "subdomains": {"count": 0, "list": []},
        "dns": {"a": [], "aaaa": [], "cname": [], "mx": [], "ns": [], "txt": []},
        "cloud_exposure": [],
        "agency": {"meta_author": "", "footer_credit": ""},
        "findings": [
            {
                "severity": "high",
                "description": (
                    "Synthetic confirmed high — booking form accepts input without CSRF token"
                ),
                "risk": (
                    "A third party could trick a logged-in admin into submitting form "
                    "changes without their knowledge."
                ),
                "provenance": "confirmed",
            },
            {
                "severity": "medium",
                "description": (
                    "Synthetic potential medium — outdated plugin version (GDPR-adjacent)"
                ),
                "risk": (
                    "Running an old plugin version may expose customer personal data "
                    "stored in the booking form."
                ),
                "provenance": "unconfirmed",
            },
            {
                "severity": "high",
                "description": (
                    "Synthetic confirmed high — customer records exposed via "
                    "unauthenticated endpoint"
                ),
                "risk": "Personal contact details are reachable without login.",
                "provenance": "confirmed",
            },
        ],
    }

    tech = brief["technology"]
    ssl = tech["ssl"]
    findings = brief["findings"]
    critical = sum(1 for f in findings if f["severity"] == "critical")
    high = sum(1 for f in findings if f["severity"] == "high")
    medium = sum(1 for f in findings if f["severity"] == "medium")

    conn.execute(
        "INSERT OR REPLACE INTO brief_snapshots ("
        "domain, scan_date, bucket, cms, hosting, server, "
        "finding_count, critical_count, high_count, medium_count, "
        "low_count, info_count, plugin_count, theme_count, subdomain_count, "
        "has_twin_scan, twin_finding_count, "
        "ssl_valid, ssl_issuer, ssl_days_remaining, "
        "company_name, cvr, brief_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            domain, scan_date, brief["bucket"],
            tech["cms"], tech["hosting"], tech["server"],
            len(findings), critical, high, medium, 0, 0,
            len(tech["detected_plugins"]), 0, 0,
            0, 0,
            1 if ssl["valid"] else 0, ssl["issuer"], ssl["days_remaining"],
            brief["company_name"], cvr, json.dumps(brief), _now_iso(),
        ),
    )
    return brief


def _resolve_mode_chat_id(mode: str) -> tuple[str | None, bool]:
    """Return (chat_id_for_client_row, expect_interpret_call).

    observe -> (None, False): runner early-returns, no Claude call.
    send-to-operator -> (<operator_chat_id>, True): runner interprets + sends.
    """
    if mode == "observe":
        return None, False

    operator_chat_id = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID", "").strip()
    if not operator_chat_id:
        raise SystemExit(
            "[FAIL] --mode=send-to-operator requires TELEGRAM_OPERATOR_CHAT_ID "
            "in the delivery container env. Set it in infra/compose/.env.dev."
        )
    return operator_chat_id, True


def _cost_guard(mode: str) -> int | None:
    """Refuse CI runs without an explicit opt-in. Returns exit code or None."""
    in_ci = (
        os.environ.get("CI") == "true"
        or os.environ.get("GITHUB_ACTIONS") == "true"
    )
    if in_ci and os.environ.get("HEIMDALL_ALLOW_PAID_DRYRUN") != "1":
        print(
            "[REFUSE] running in CI but HEIMDALL_ALLOW_PAID_DRYRUN != 1. "
            "send-to-operator mode makes a real Claude API call (~$0.02/run); "
            "observe mode is free but still guarded belt-and-braces. "
            "Set HEIMDALL_ALLOW_PAID_DRYRUN=1 to override.",
            file=sys.stderr,
        )
        return 1
    if mode == "send-to-operator":
        # Confirm the Claude key is present before we seed any rows.
        api_key = get_secret("claude_api_key", "CLAUDE_API_KEY")
        if not api_key:
            print(
                "[FAIL] send-to-operator mode requires claude_api_key "
                "secret or CLAUDE_API_KEY env var. Neither is set.",
                file=sys.stderr,
            )
            return 1
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry run the delivery runner's interpretation path.",
    )
    parser.add_argument(
        "--mode",
        choices=("observe", "send-to-operator"),
        default="observe",
        help=(
            "observe (default): client has NULL chat_id, runner early-returns "
            "before Claude. send-to-operator: overrides chat_id with "
            "TELEGRAM_OPERATOR_CHAT_ID, drives real Claude + Telegram."
        ),
    )
    args = parser.parse_args()

    # Cost guard — before any DB/Redis I/O so there's no partial state.
    gated = _cost_guard(args.mode)
    if gated is not None:
        return gated

    _assert_environment()
    cfg = json.loads(CONFIG_PATH.read_text())

    cvr = cfg["synthetic_cvr"]
    domain = cfg["domain"]
    prefix = cfg["cvr_prefix"]
    wait_s = cfg["subscriber_wait_seconds"]

    chat_id, expect_interpret = _resolve_mode_chat_id(args.mode)
    print(
        f"[SETUP] mode={args.mode} domain={domain} cvr={cvr} "
        f"chat_id={'<operator>' if chat_id else 'NULL'}"
    )

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

    _insert_client(conn, cvr, cfg, chat_id)
    _insert_domain(conn, cvr, domain)
    brief = _seed_brief(conn, cvr, domain, cfg)
    conn.commit()
    high_count = sum(1 for f in brief["findings"] if f["severity"] == "high")
    print(
        f"[SETUP] seeded client + domain + brief "
        f"(findings={len(brief['findings'])}, high={high_count})"
    )

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.ping()
    except redis.RedisError as exc:
        _cleanup(conn, prefix)
        conn.close()
        return _fail(f"redis unreachable at {REDIS_URL}: {exc}")

    pub = r.pubsub()
    pub.subscribe("console:logs")
    # Drain the subscribe-confirmation frame.
    pub.get_message(timeout=1.0)

    try:
        event = {
            "domain": domain,
            "cvr": cvr,
            "job_id": f"dryrun-int-{int(time.time())}",
        }
        r.publish("client-scan-complete", json.dumps(event))
        print(f"[PUB] client-scan-complete {event}")

        saw_processing = False
        saw_early_return = False
        saw_empty_comp_warn = False
        saw_interp_exception = False
        delivery_log_row: sqlite3.Row | None = None
        deadline = time.time() + wait_s

        # Target signals differ by mode.
        #   observe: processing_scan_event AND no_chat_id_for_client
        #   send-to-operator: processing_scan_event AND a delivery_log row
        #                     for this cvr (written by send_with_logging)
        while time.time() < deadline:
            # Mode-specific satisfaction check first.
            if expect_interpret:
                row = conn.execute(
                    "SELECT id, status, message_type, channel, created_at "
                    "FROM delivery_log WHERE cvr = ? ORDER BY id DESC LIMIT 1",
                    (cvr,),
                ).fetchone()
                if row is not None:
                    delivery_log_row = row
                    break
            elif saw_processing and saw_early_return:
                break

            msg = pub.get_message(timeout=1.0)
            if not msg or msg["type"] != "message":
                continue
            try:
                log = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if log.get("source") != "delivery":
                continue
            ctx = log.get("ctx") or {}
            if ctx.get("domain") != domain and ctx.get("cvr") != cvr:
                continue
            message = log.get("message", "")
            if message == "processing_scan_event":
                saw_processing = True
                print(f"[SUB] processing_scan_event domain={domain}")
            elif message == "no_chat_id_for_client":
                saw_early_return = True
                print(f"[SUB] no_chat_id_for_client domain={domain} cvr={cvr}")
            elif message == "empty_composition":
                saw_empty_comp_warn = True
                print(f"[SUB] empty_composition domain={domain}")
            elif message.startswith("interpretation_failed"):
                saw_interp_exception = True
                print(f"[SUB] interpretation_failed domain={domain}: {log.get('exc', '')[:200]}")

        # Adjudicate.
        if not saw_processing:
            return _fail(
                f"no processing_scan_event log for {domain} within {wait_s}s — "
                "delivery runner did not receive the client-scan-complete event"
            )

        if expect_interpret:
            if saw_interp_exception:
                return _fail(
                    "interpret_brief raised — Claude API call failed. Check "
                    "claude_api_key secret and network."
                )
            if saw_empty_comp_warn:
                return _fail("composer produced empty messages — interpreter output invalid")
            if delivery_log_row is None:
                return _fail(
                    f"no delivery_log row for cvr={cvr} within {wait_s}s — "
                    "send_with_logging did not complete"
                )
            print(
                f"[PASS] delivery_log id={delivery_log_row['id']} "
                f"status={delivery_log_row['status']} "
                f"channel={delivery_log_row['channel']} "
                f"message_type={delivery_log_row['message_type']}"
            )
            print("[PASS] interpret dry run (send-to-operator) green — Claude + Telegram exercised")
            return 0

        if not saw_early_return:
            return _fail(
                f"no no_chat_id_for_client log for cvr={cvr} within {wait_s}s — "
                "runner walked past the early-return unexpectedly"
            )
        print(
            "[PASS] interpret dry run (observe) green — "
            "scan-complete -> runner early-return proven"
        )
        return 0

    finally:
        try:
            pub.unsubscribe()
            pub.close()
        except Exception:
            pass
        try:
            if args.mode == "send-to-operator":
                # Leave the synthetic rows in place so the Telegram
                # message's Approve/Reject buttons still resolve — the
                # approval handler looks up delivery_log by id, and a
                # cleanup-then-click would hit "Delivery {id} not found".
                # The next invocation (either mode) pre-cleans the prefix.
                print(
                    "[NO-CLEANUP] send-to-operator: synthetic DRYRUN-INT-* "
                    "rows left intact so Approve/Reject callbacks resolve. "
                    "Run `make dev-interpret-dry-run` again (either mode) "
                    "to pre-clean them."
                )
            else:
                counts = _cleanup(conn, prefix)
                print(f"[CLEANUP] deleted rows: {counts}")
        finally:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
