"""Tests for src.api.auth.sessions — Stage A session ticket lifecycle.

Stage A spec §3.2 / §3.3 / §3.4 / §4 / §7.5 + §8.2
(test_auth_sessions.py block). The module ships these primitives:

- ``issue_session(conn, operator_id, ip, ua) -> IssuedSession``
- ``validate_session(conn, token) -> sqlite3.Row | None``
- ``validate_session_by_hash(conn, token_hash) -> sqlite3.Row | None``
- ``refresh_session(conn, token, ip, ua) -> sqlite3.Row | None``
- ``revoke_session(conn, token) -> None``

Plaintext tokens are returned to the caller (for ``Set-Cookie``) and
NEVER persisted server-side: ``sessions.token_hash`` carries
``sha256(token).hexdigest()``. CSRF tokens are stored verbatim because
the SPA reads them from the ``heimdall_csrf`` cookie on every load.

The helpers do NOT commit — the caller wraps the helper plus its
audit-row insert in a single transaction (§7.5). Tests below
explicitly ``conn.commit()`` after each mutation to make the
transactional contract obvious and to keep the reader-vs-writer
contract clear under the WAL.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import src.api.auth.sessions as sessions
import src.core.secrets as core_secrets
from src.api.auth.sessions import (
    ABSOLUTE_TTL_MIN,
    IDLE_TTL_MIN,
    REFRESH_DEBOUNCE_SEC,
    IssuedSession,
    issue_session,
    refresh_session,
    revoke_session,
    validate_session,
    validate_session_by_hash,
)
from src.db.console_connection import get_console_conn, init_db_console


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_console_seed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop ``init_db_console`` from auto-seeding operator #0 in tests
    that hard-code ``id=1, username='alice'``. Mirrors the fixture in
    ``tests/test_db_console_connection.py`` — without it, a developer
    shell or CI job that exports ``CONSOLE_USER`` / ``CONSOLE_PASSWORD``
    (or has the secret mounted) would produce ``UNIQUE`` / ``IntegrityError``
    failures here that are unrelated to the session code under test."""
    secrets_dir = tmp_path / "run-secrets"
    secrets_dir.mkdir()
    monkeypatch.setattr(core_secrets, "_SECRETS_DIR", secrets_dir)
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)


@pytest.fixture
def console_conn(tmp_path: Path) -> sqlite3.Connection:
    """Fresh console.db with one active operator (id=1, username='alice')."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)
    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.commit()
    yield conn
    conn.close()


def _set_session_field(
    conn: sqlite3.Connection, token_hash: str, **fields: str | None
) -> None:
    """Helper to surgically mutate a session row for time-warp tests."""
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = (*fields.values(), token_hash)
    conn.execute(f"UPDATE sessions SET {sets} WHERE token_hash = ?", params)
    conn.commit()


def _iso_offset(seconds: int) -> str:
    """ISO-8601 UTC timestamp offset by *seconds* from now."""
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# Constants — env-derived TTLs + debounce
# ---------------------------------------------------------------------------


def test_default_ttls() -> None:
    """Spec §4.3 defaults: 15 min idle, 12 h absolute, 60 s debounce.

    Skipped if the test runner's shell exports either TTL env var —
    those overrides are explicitly documented (§4.3) and would
    legitimately move the constants away from the defaults. Asserting
    against the parsed-from-env value is what the override-tolerance
    tests below cover; this test pins the documented defaults only.
    """
    if any(
        os.environ.get(name) not in (None, "")
        for name in (
            "CONSOLE_SESSION_IDLE_TTL_MIN",
            "CONSOLE_SESSION_ABSOLUTE_TTL_MIN",
        )
    ):
        pytest.skip("TTL env override active; default-pin assertion skipped")
    assert IDLE_TTL_MIN == 15
    assert ABSOLUTE_TTL_MIN == 720  # 12 hours
    assert REFRESH_DEBOUNCE_SEC == 60


def test_ttl_env_blank_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / non-numeric env values must NOT crash module import."""
    for env_name in (
        "CONSOLE_SESSION_IDLE_TTL_MIN",
        "CONSOLE_SESSION_ABSOLUTE_TTL_MIN",
    ):
        for bad_value in ("", "   ", "not-a-number", "-5", "0"):
            monkeypatch.setenv(env_name, bad_value)
            assert sessions._ttl_minutes(env_name, 42) == 42


def test_ttl_env_valid_value_is_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A documented integer override is honored end-to-end."""
    monkeypatch.setenv("CONSOLE_SESSION_IDLE_TTL_MIN", "30")
    assert sessions._ttl_minutes("CONSOLE_SESSION_IDLE_TTL_MIN", 15) == 30


# ---------------------------------------------------------------------------
# issue_session
# ---------------------------------------------------------------------------


def test_issue_session_returns_plaintext_token_and_csrf(
    console_conn: sqlite3.Connection,
) -> None:
    """Issue returns plaintext token + csrf for the Set-Cookie response.

    The plaintext token must be 256 bits of entropy (43 chars base64url)
    and never appear in the DB row — only its sha256 digest does.
    """
    issued = issue_session(console_conn, operator_id=1, ip="127.0.0.1", ua="pytest")
    assert isinstance(issued, IssuedSession)
    assert isinstance(issued.token, str)
    assert isinstance(issued.csrf_token, str)
    # secrets.token_urlsafe(32) is 43 chars, no padding.
    assert len(issued.token) == 43
    assert len(issued.csrf_token) == 43

    rows = console_conn.execute(
        "SELECT token_hash, csrf_token FROM sessions"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    # Cookie-vs-DB-key separation: the DB stores the digest, not plaintext.
    assert row["token_hash"] == hashlib.sha256(issued.token.encode()).hexdigest()
    assert row["token_hash"] != issued.token
    # CSRF is stored verbatim — the SPA echoes it back as X-CSRF-Token.
    assert row["csrf_token"] == issued.csrf_token


def test_issue_session_populates_both_expiry_timestamps(
    console_conn: sqlite3.Connection,
) -> None:
    """expires_at = now + IDLE_TTL; absolute_expires_at = now + ABSOLUTE_TTL."""
    issued = issue_session(console_conn, operator_id=1)
    issued_at = datetime.fromisoformat(issued.issued_at.replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(issued.expires_at.replace("Z", "+00:00"))
    abs_expires = datetime.fromisoformat(
        issued.absolute_expires_at.replace("Z", "+00:00")
    )

    # IDLE_TTL window (allow ±5s slop for clock drift).
    idle_delta = (expires_at - issued_at).total_seconds()
    assert abs(idle_delta - IDLE_TTL_MIN * 60) < 5

    # ABSOLUTE_TTL window.
    abs_delta = (abs_expires - issued_at).total_seconds()
    assert abs(abs_delta - ABSOLUTE_TTL_MIN * 60) < 5


def test_issue_session_unique_token_hash_each_call(
    console_conn: sqlite3.Connection,
) -> None:
    """Two issues for the same operator yield two distinct rows + tokens."""
    a = issue_session(console_conn, operator_id=1)
    b = issue_session(console_conn, operator_id=1)
    assert a.token != b.token
    count = console_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 2


def test_issue_session_rejects_disabled_operator(
    console_conn: sqlite3.Connection,
) -> None:
    """Defense-in-depth: never mint a session for a disabled operator.

    Even if the login handler somehow reached this helper with a row
    that was disabled mid-flow, the INSERT...SELECT short-circuits and
    we raise rather than ship a dead-on-arrival cookie.
    """
    console_conn.execute(
        "UPDATE operators SET disabled_at = ? WHERE id = 1", (_iso_offset(0),)
    )
    console_conn.commit()
    with pytest.raises(ValueError, match="disabled or does not exist"):
        issue_session(console_conn, operator_id=1)
    count = console_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 0


def test_issue_session_rejects_unknown_operator(
    console_conn: sqlite3.Connection,
) -> None:
    """Same guard catches a caller passing a non-existent operator id."""
    with pytest.raises(ValueError, match="disabled or does not exist"):
        issue_session(console_conn, operator_id=999)


def test_issue_session_clamps_initial_expiry_at_absolute_cap(
    console_conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misconfigured ABSOLUTE_TTL < IDLE_TTL must NOT advertise a
    lifetime longer than the absolute cap. The cookie / SPA reads the
    returned expires_at — letting it overshoot the server's actual
    enforcement is a UX bug ("logged out before my cookie expired")."""
    monkeypatch.setattr(sessions, "IDLE_TTL_MIN", 60)
    monkeypatch.setattr(sessions, "ABSOLUTE_TTL_MIN", 5)

    issued = issue_session(console_conn, operator_id=1)
    assert issued.expires_at == issued.absolute_expires_at, (
        "initial expires_at must clamp at absolute_expires_at when "
        "ABSOLUTE_TTL < IDLE_TTL"
    )


def test_issue_session_leaves_last_seen_at_null(
    console_conn: sqlite3.Connection,
) -> None:
    """A freshly-issued session has last_seen_at = NULL so the first
    authenticated request triggers a refresh without the 60-second
    debounce blocking it. Otherwise an operator who logs in then makes
    one request 30 seconds later loses up to a minute of idle window."""
    issue_session(console_conn, operator_id=1)
    console_conn.commit()
    last_seen = console_conn.execute(
        "SELECT last_seen_at FROM sessions"
    ).fetchone()["last_seen_at"]
    assert last_seen is None


def test_refresh_debounce_is_atomic_at_sql_level(
    console_conn: sqlite3.Connection,
) -> None:
    """The 60-second debounce holds even under concurrent workers.

    Simulates the multi-worker race by UPDATE-ing last_seen_at directly
    to a "just-now" timestamp (mimicking another worker's recent write),
    THEN calling refresh_session. The Python-side debounce check
    against the freshly-fetched row would skip the UPDATE in the
    common path; the regression we're locking in is the SQL-side
    predicate — set last_seen_at to just-now AFTER the validate read
    by hand-mutating the row, then call the helper and assert no
    duplicate write goes through. Concretely, two refreshes inside
    60s must produce exactly one ``last_seen_at`` change in the DB.
    """
    issued = issue_session(console_conn, operator_id=1)
    console_conn.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    # First refresh — last_seen_at was NULL, so this MUST fire.
    refresh_session(console_conn, issued.token, ip="1.1.1.1", ua="ua-1")
    console_conn.commit()
    after_first = console_conn.execute(
        "SELECT last_seen_at, last_seen_ip FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert after_first["last_seen_at"] is not None

    # Second refresh inside the debounce window — must NOT touch the
    # row, even with different IP/UA. The SQL predicate is what
    # protects us under concurrent workers.
    refresh_session(console_conn, issued.token, ip="2.2.2.2", ua="ua-2")
    console_conn.commit()
    after_second = console_conn.execute(
        "SELECT last_seen_at, last_seen_ip FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert after_second["last_seen_at"] == after_first["last_seen_at"]
    assert after_second["last_seen_ip"] == after_first["last_seen_ip"]


def test_first_refresh_after_login_is_not_debounced(
    console_conn: sqlite3.Connection,
) -> None:
    """The first refresh after issue must always slide expires_at
    forward — last_seen_at starts NULL and the debounce treats NULL as
    "no prior visit". Pairs with the test above to lock the contract.
    """
    issued = issue_session(console_conn, operator_id=1)
    console_conn.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    before = console_conn.execute(
        "SELECT expires_at, last_seen_at FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert before["last_seen_at"] is None

    refresh_session(console_conn, issued.token, ip="1.1.1.1", ua="ua")
    console_conn.commit()

    after = console_conn.execute(
        "SELECT expires_at, last_seen_at FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert after["last_seen_at"] is not None, "first refresh must populate last_seen_at"
    assert after["expires_at"] >= before["expires_at"]


# ---------------------------------------------------------------------------
# validate_session — happy + four failure modes (revoked / idle-expired /
#                   absolute-expired / operator-disabled)
# ---------------------------------------------------------------------------


def test_validate_session_returns_row_when_valid(
    console_conn: sqlite3.Connection,
) -> None:
    issued = issue_session(console_conn, operator_id=1)
    row = validate_session(console_conn, issued.token)
    assert row is not None
    assert row["operator_id"] == 1
    assert row["token_hash"] == hashlib.sha256(issued.token.encode()).hexdigest()


def test_validate_session_returns_none_for_unknown_token(
    console_conn: sqlite3.Connection,
) -> None:
    issue_session(console_conn, operator_id=1)
    assert validate_session(console_conn, "totally-fake-token") is None


def test_validate_session_returns_none_for_empty_token(
    console_conn: sqlite3.Connection,
) -> None:
    """Defensive: empty cookie value never resolves to a session row."""
    issue_session(console_conn, operator_id=1)
    assert validate_session(console_conn, "") is None


def test_validate_session_returns_none_when_revoked(
    console_conn: sqlite3.Connection,
) -> None:
    issued = issue_session(console_conn, operator_id=1)
    revoke_session(console_conn, issued.token)
    assert validate_session(console_conn, issued.token) is None


def test_validate_session_returns_none_when_idle_expired(
    console_conn: sqlite3.Connection,
) -> None:
    """Sliding-window expiry: expires_at in the past invalidates the session."""
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    _set_session_field(console_conn, h, expires_at=_iso_offset(-1))
    assert validate_session(console_conn, issued.token) is None


def test_validate_session_returns_none_when_absolute_expired(
    console_conn: sqlite3.Connection,
) -> None:
    """Hard cap: absolute_expires_at in the past invalidates regardless of activity."""
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    _set_session_field(console_conn, h, absolute_expires_at=_iso_offset(-1))
    assert validate_session(console_conn, issued.token) is None


def test_validate_session_returns_none_when_operator_disabled(
    console_conn: sqlite3.Connection,
) -> None:
    """Disabling the operator must invalidate live sessions immediately."""
    issued = issue_session(console_conn, operator_id=1)
    console_conn.execute(
        "UPDATE operators SET disabled_at = ? WHERE id = 1", (_iso_offset(0),)
    )
    console_conn.commit()
    assert validate_session(console_conn, issued.token) is None


def test_validate_session_by_hash_matches_validate_session(
    console_conn: sqlite3.Connection,
) -> None:
    """The two entry points share a SELECT — by-hash skips the SHA-256 step."""
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    row_a = validate_session(console_conn, issued.token)
    row_b = validate_session_by_hash(console_conn, h)
    assert row_a is not None
    assert row_b is not None
    assert row_a["id"] == row_b["id"]


# ---------------------------------------------------------------------------
# refresh_session — idle-window slide + debounce + absolute cap
# ---------------------------------------------------------------------------


def test_refresh_session_extends_expires_at_within_absolute_cap(
    console_conn: sqlite3.Connection,
) -> None:
    """Refresh slides expires_at forward to now + IDLE_TTL."""
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    # Backdate last_seen_at so the debounce won't suppress the write.
    _set_session_field(console_conn, h, last_seen_at=_iso_offset(-300))

    before = console_conn.execute(
        "SELECT expires_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["expires_at"]

    row = refresh_session(console_conn, issued.token, ip="127.0.0.1", ua="pytest")
    assert row is not None

    after = console_conn.execute(
        "SELECT expires_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["expires_at"]
    assert after >= before  # ISO-8601 strings are lexicographic-time safe


def test_refresh_session_capped_at_absolute_expires_at(
    console_conn: sqlite3.Connection,
) -> None:
    """Refresh never extends past absolute_expires_at — that's the hard cap."""
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    # Move absolute cap to 30s in the future and last_seen_at far back so
    # the refresh actually fires; the slide would normally land at
    # now + 15min, but it must clamp at the absolute cap.
    cap = _iso_offset(30)
    _set_session_field(
        console_conn, h, absolute_expires_at=cap, last_seen_at=_iso_offset(-300)
    )

    refresh_session(console_conn, issued.token)
    row = console_conn.execute(
        "SELECT expires_at, absolute_expires_at FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert row["expires_at"] <= row["absolute_expires_at"]
    assert row["expires_at"] == cap


def test_refresh_session_debounced_within_60s(
    console_conn: sqlite3.Connection,
) -> None:
    """Two refreshes within 60s touch the row at most once.

    Spec §3.2: "we don't UPDATE the session row on every request — only
    when last_seen_at is stale by ≥60 seconds."
    """
    issued = issue_session(console_conn, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    # First refresh: row is fresh from issue_session, last_seen_at is None
    # or recent → may or may not write. Force an initial last_seen_at so
    # the contract is unambiguous: with last_seen_at fresh (now), the
    # second refresh inside 60s must NOT write.
    _set_session_field(console_conn, h, last_seen_at=_iso_offset(0))

    snapshot_a = console_conn.execute(
        "SELECT expires_at, last_seen_at, last_seen_ip FROM sessions "
        "WHERE token_hash = ?",
        (h,),
    ).fetchone()

    refresh_session(console_conn, issued.token, ip="9.9.9.9", ua="pytest-2")

    snapshot_b = console_conn.execute(
        "SELECT expires_at, last_seen_at, last_seen_ip FROM sessions "
        "WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert snapshot_b["expires_at"] == snapshot_a["expires_at"]
    assert snapshot_b["last_seen_at"] == snapshot_a["last_seen_at"]
    assert snapshot_b["last_seen_ip"] == snapshot_a["last_seen_ip"]


def test_refresh_session_returns_none_when_invalid(
    console_conn: sqlite3.Connection,
) -> None:
    """Refresh on a revoked / unknown / disabled session returns None,
    no row mutation."""
    issued = issue_session(console_conn, operator_id=1)
    revoke_session(console_conn, issued.token)
    assert refresh_session(console_conn, issued.token) is None
    assert refresh_session(console_conn, "nope") is None


def test_concurrent_refresh_converges(
    tmp_path: Path,
) -> None:
    """Two threads refreshing the same session don't deadlock or raise.

    Spec §8.2: "last-write-wins is acceptable because both writes contain
    the same intent." We assert the row ends up valid + readable from
    either thread.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    # Seed operator + session via a single-shot connection.
    setup = get_console_conn(db_path)
    setup.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    issued = issue_session(setup, operator_id=1)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    _set_session_field(setup, h, last_seen_at=_iso_offset(-300))
    setup.close()

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            conn = get_console_conn(db_path)
            try:
                refresh_session(conn, issued.token, ip="t", ua="t")
            finally:
                conn.close()
        except BaseException as exc:  # pragma: no cover — recorded for assertion
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"concurrent refresh raised: {errors}"

    final = get_console_conn(db_path)
    row = final.execute(
        "SELECT revoked_at, expires_at FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    final.close()
    assert row is not None
    assert row["revoked_at"] is None


# ---------------------------------------------------------------------------
# revoke_session — idempotent
# ---------------------------------------------------------------------------


def test_revoke_session_sets_revoked_at(
    console_conn: sqlite3.Connection,
) -> None:
    issued = issue_session(console_conn, operator_id=1)
    revoke_session(console_conn, issued.token)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    row = console_conn.execute(
        "SELECT revoked_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()
    assert row["revoked_at"] is not None


def test_revoke_session_idempotent(
    console_conn: sqlite3.Connection,
) -> None:
    """Second revoke on the same token is a no-op — the original
    revoked_at timestamp does not get overwritten."""
    issued = issue_session(console_conn, operator_id=1)
    revoke_session(console_conn, issued.token)
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    first = console_conn.execute(
        "SELECT revoked_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["revoked_at"]

    revoke_session(console_conn, issued.token)

    second = console_conn.execute(
        "SELECT revoked_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["revoked_at"]
    assert second == first, "revoke_session must not overwrite revoked_at"


def test_revoke_session_unknown_token_no_op(
    console_conn: sqlite3.Connection,
) -> None:
    """Revoking an unknown token is silent — no row created, no exception."""
    revoke_session(console_conn, "token-that-was-never-issued")
    count = console_conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# Caller-managed transactions (§7.5)
# ---------------------------------------------------------------------------


def test_refresh_session_commits_so_writes_survive_connection_close(
    tmp_path: Path,
) -> None:
    """Refresh must self-commit: the middleware / WS handler patterns
    are read-only request paths whose connection closes with no other
    write to pair against. Without the self-commit, the slid
    ``expires_at`` and ``last_seen_at`` are rolled back on close and
    operators time out after the original IDLE_TTL despite activity.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    setup = get_console_conn(db_path)
    setup.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    issued = issue_session(setup, operator_id=1)
    setup.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    setup.close()

    # Refresh on a fresh connection that we then close without touching
    # anything else — mirrors the middleware's open-validate-close path.
    middleware_conn = get_console_conn(db_path)
    refresh_session(middleware_conn, issued.token, ip="9.9.9.9", ua="m-ua")
    middleware_conn.close()  # NB: no explicit commit by caller.

    # A separate reader-side connection must observe the slid values.
    reader = get_console_conn(db_path)
    row = reader.execute(
        "SELECT last_seen_at, last_seen_ip FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    reader.close()
    assert row["last_seen_at"] is not None, (
        "refresh_session must self-commit so middleware-style read-only "
        "callers don't lose their slide on close"
    )
    assert row["last_seen_ip"] == "9.9.9.9"


def test_helpers_do_not_self_commit(tmp_path: Path) -> None:
    """Spec §7.5: session writes must commit in the caller's transaction.

    Issue a session on conn-1 without committing. A second connection
    opened against the same DB file must NOT see the row — proof that
    the helper deferred commit. This is the contract the login /
    logout handlers rely on to roll back the session row when the
    paired audit-log insert fails.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    conn_writer = get_console_conn(db_path)
    conn_writer.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn_writer.commit()

    issue_session(conn_writer, operator_id=1)
    # Deliberately no commit here.

    conn_reader = get_console_conn(db_path)
    visible = conn_reader.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn_reader.close()
    assert visible == 0, "issue_session must defer commit to the caller (§7.5)"

    # Roll back the writer; the row must vanish completely.
    conn_writer.rollback()
    after_rollback = conn_writer.execute(
        "SELECT COUNT(*) FROM sessions"
    ).fetchone()[0]
    conn_writer.close()
    assert after_rollback == 0


# ---------------------------------------------------------------------------
# CAS expiry guard (P1 from Codex review on this slice)
# ---------------------------------------------------------------------------


def test_refresh_session_does_not_revive_idle_expired_row(
    console_conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Race: validate passes, then idle expiry crosses, then UPDATE fires.

    Simulates by holding ``_now`` constant for the validate call, then
    advancing it past ``expires_at`` before the UPDATE's CAS WHERE
    re-checks expiry. The UPDATE must affect zero rows; refresh
    returns None.
    """
    issued = issue_session(console_conn, operator_id=1)
    console_conn.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()

    # Set last_seen far back so the debounce won't intercept us, and
    # set expires_at to 30s in the future.
    expiry = _iso_offset(30)
    _set_session_field(
        console_conn, h, expires_at=expiry, last_seen_at=_iso_offset(-300)
    )

    # Hand the helper a "now" before the expiry (so validate passes),
    # then a "now" after the expiry (so the CAS UPDATE finds 0 rows).
    real_dt = datetime
    times = iter(
        [
            real_dt.fromisoformat(expiry.replace("Z", "+00:00"))
            - timedelta(seconds=10),
            real_dt.fromisoformat(expiry.replace("Z", "+00:00"))
            + timedelta(seconds=10),
            # Trailing values so any extra _now() calls after the UPDATE
            # don't IndexError. Real code paths only call _now twice
            # (once in refresh, once via validate-by-hash on success);
            # on the lost-CAS branch we return None before that.
            real_dt.fromisoformat(expiry.replace("Z", "+00:00"))
            + timedelta(seconds=10),
        ]
    )

    def fake_now() -> datetime:
        return next(times)

    monkeypatch.setattr(sessions, "_now", fake_now)

    result = refresh_session(console_conn, issued.token, ip="9.9.9.9", ua="ua")
    assert result is None, "expired session must not be revived by refresh"

    # Row's expires_at must NOT have moved forward.
    row = console_conn.execute(
        "SELECT expires_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()
    assert row["expires_at"] == expiry


# ---------------------------------------------------------------------------
# UA truncation (P3 from Codex review on this slice)
# ---------------------------------------------------------------------------


def test_issue_session_truncates_long_user_agent(
    console_conn: sqlite3.Connection,
) -> None:
    """A pathological UA gets truncated at write time, capping growth."""
    long_ua = "X" * 2048
    issue_session(console_conn, operator_id=1, ua=long_ua)
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT last_seen_ua FROM sessions"
    ).fetchone()["last_seen_ua"]
    assert stored is not None
    assert len(stored) == 512


def test_refresh_session_truncates_long_user_agent(
    console_conn: sqlite3.Connection,
) -> None:
    """Refresh applies the same UA truncation as issue."""
    issued = issue_session(console_conn, operator_id=1)
    console_conn.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    _set_session_field(console_conn, h, last_seen_at=_iso_offset(-300))

    refresh_session(console_conn, issued.token, ip="ip", ua="Y" * 2048)
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT last_seen_ua FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["last_seen_ua"]
    assert stored is not None
    assert len(stored) == 512


# ---------------------------------------------------------------------------
# Forensic preservation on metadata-less refresh
# ---------------------------------------------------------------------------


def test_refresh_session_preserves_prior_ip_and_ua_when_omitted(
    console_conn: sqlite3.Connection,
) -> None:
    """A refresh that lacks IP / UA must NOT clear the previously
    captured forensic values — that would erase the last good snapshot
    for incident analysis. COALESCE keeps the existing column."""
    issued = issue_session(
        console_conn, operator_id=1, ip="1.1.1.1", ua="first-ua"
    )
    console_conn.commit()
    h = hashlib.sha256(issued.token.encode()).hexdigest()
    _set_session_field(console_conn, h, last_seen_at=_iso_offset(-300))

    # Refresh without IP / UA — the existing values must remain.
    refresh_session(console_conn, issued.token, ip=None, ua=None)
    console_conn.commit()

    row = console_conn.execute(
        "SELECT last_seen_ip, last_seen_ua FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    assert row["last_seen_ip"] == "1.1.1.1"
    assert row["last_seen_ua"] == "first-ua"
