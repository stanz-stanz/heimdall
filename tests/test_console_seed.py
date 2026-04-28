"""Tests for src.db.console_connection._seed_operator_zero — Stage A slice 2.

Stage A spec §2.2 / §2.3. The seed runs inside ``init_db_console()``
after the schema apply, gated by:

1. ``operators`` table is empty.
2. ``get_secret("console_password", "CONSOLE_PASSWORD")`` returns a
   non-empty value (Docker secret OR env-var fallback).
3. ``os.environ.get("CONSOLE_USER")`` returns a non-empty value.

If any precondition fails the seed is a silent no-op (one INFO line) —
``init_db_console()`` does not raise. Re-running on a non-empty DB does
not re-hash or overwrite, so changing ``CONSOLE_PASSWORD`` and
restarting is a documented no-op.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.core.secrets as core_secrets
import src.db.console_connection as cc
from src.api.auth.hashing import verify_password
from src.db.console_connection import (
    _seed_operator_zero,
    get_console_conn,
    init_db_console,
)


# ---------------------------------------------------------------------------
# Fixtures — keep every test isolated from the host's actual env / secrets
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_secrets(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point ``get_secret`` at an empty tmp dir and clear console env vars.

    Without this, a host with a real ``/run/secrets/console_password`` or
    a stray ``CONSOLE_PASSWORD`` in the shell environment would seed
    operator #0 in tests that expect the no-op branch.
    """
    secrets_dir = tmp_path / "run-secrets"  # type: ignore[operator]
    secrets_dir.mkdir()
    monkeypatch.setattr(core_secrets, "_SECRETS_DIR", secrets_dir)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    return secrets_dir


# ---------------------------------------------------------------------------
# Precondition #2: console_password must be non-empty
# ---------------------------------------------------------------------------


def test_seed_skips_when_console_password_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """No secret file, no env var → silent no-op, operators table empty."""
    monkeypatch.setenv("CONSOLE_USER", "federico")
    # CONSOLE_PASSWORD intentionally not set — neither file nor env.

    conn = init_db_console(tmp_path / "console.db")
    count = conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
    assert count == 0, "seed must be a no-op when console_password is missing"
    conn.close()


def test_seed_skips_when_console_password_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Empty secret file is treated identically to a missing one — no seed."""
    (isolated_secrets / "console_password").write_text("")
    monkeypatch.setenv("CONSOLE_USER", "federico")

    conn = init_db_console(tmp_path / "console.db")
    count = conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
    assert count == 0, "empty console_password must skip the seed"
    conn.close()


def test_seed_skips_when_console_password_env_only_but_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Empty env var (no secret file) is also a no-op."""
    monkeypatch.setenv("CONSOLE_USER", "federico")
    monkeypatch.setenv("CONSOLE_PASSWORD", "")

    conn = init_db_console(tmp_path / "console.db")
    assert conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0] == 0
    conn.close()


# ---------------------------------------------------------------------------
# Precondition #3: CONSOLE_USER must be non-empty
# ---------------------------------------------------------------------------


def test_seed_skips_when_console_user_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Even with a populated password, a missing CONSOLE_USER is a no-op."""
    (isolated_secrets / "console_password").write_text("devpassword")
    monkeypatch.delenv("CONSOLE_USER", raising=False)

    conn = init_db_console(tmp_path / "console.db")
    assert conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0] == 0
    conn.close()


def test_seed_skips_when_console_user_blank(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Whitespace-only CONSOLE_USER normalises to empty — no-op."""
    (isolated_secrets / "console_password").write_text("devpassword")
    monkeypatch.setenv("CONSOLE_USER", "   ")

    conn = init_db_console(tmp_path / "console.db")
    assert conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0] == 0
    conn.close()


# ---------------------------------------------------------------------------
# Happy path: all preconditions met → exactly one operator row
# ---------------------------------------------------------------------------


def test_seed_inserts_operator_zero_when_preconditions_met(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """All three preconditions met → exactly one operator row with the
    spec-mandated normalisation, role, and a verifiable Argon2id hash."""
    (isolated_secrets / "console_password").write_text("devpassword")
    monkeypatch.setenv("CONSOLE_USER", "  Federico  ")  # surrounding ws + casing

    conn = init_db_console(tmp_path / "console.db")
    rows = conn.execute(
        "SELECT username, display_name, role_hint, password_hash, "
        "       disabled_at, last_login_at, created_at, updated_at "
        "FROM operators"
    ).fetchall()
    assert len(rows) == 1, "exactly one operator row expected"
    row = rows[0]

    # §2.2 normalisation: trim then lowercase for username, trim only
    # (case preserved) for display_name.
    assert row["username"] == "federico"
    assert row["display_name"] == "Federico"
    assert row["role_hint"] == "owner"
    assert row["disabled_at"] is None
    assert row["last_login_at"] is None
    assert row["created_at"] == row["updated_at"]
    # ISO-8601 UTC, e.g. 2026-04-28T13:01:41Z — sanity-check the format.
    assert row["created_at"].endswith("Z")

    # The hash must be a verifiable Argon2id PHC string for the seeded password.
    assert row["password_hash"].startswith("$argon2id$")
    assert verify_password(row["password_hash"], "devpassword") is True
    assert verify_password(row["password_hash"], "wrongpassword") is False

    conn.close()


# ---------------------------------------------------------------------------
# Idempotency: re-run with new password leaves row unchanged
# ---------------------------------------------------------------------------


def test_seed_idempotent_when_operators_already_seeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Restarting with a new CONSOLE_PASSWORD must NOT re-hash or overwrite.

    Spec §2.3: rotating the operator-zero password is an explicit
    Stage A.5 path (admin UI) or a runbook step (lever 9.2). The seed
    has no permission to silently invalidate live sessions.
    """
    db_path = tmp_path / "console.db"

    # First boot: seed with one password.
    (isolated_secrets / "console_password").write_text("first-password")
    monkeypatch.setenv("CONSOLE_USER", "Federico")
    init_db_console(db_path).close()

    # Capture the hash post-seed.
    snap = get_console_conn(db_path)
    first_hash = snap.execute(
        "SELECT password_hash FROM operators WHERE username='federico'"
    ).fetchone()["password_hash"]
    first_count = snap.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
    snap.close()

    # Second boot: same DB, different password. Must be a no-op.
    (isolated_secrets / "console_password").write_text("rotated-password")
    init_db_console(db_path).close()

    snap = get_console_conn(db_path)
    after = snap.execute(
        "SELECT password_hash, COUNT(*) OVER () AS n FROM operators"
    ).fetchall()
    snap.close()

    assert len(after) == first_count == 1
    assert after[0]["password_hash"] == first_hash, "password hash must not be rehashed"
    # The original password still verifies; the rotated one does not.
    assert verify_password(first_hash, "first-password") is True
    assert verify_password(first_hash, "rotated-password") is False


# ---------------------------------------------------------------------------
# init_db_console invokes the seed (wiring contract)
# ---------------------------------------------------------------------------


def test_init_db_console_invokes_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """``init_db_console`` must call ``_seed_operator_zero`` after schema apply.

    Lock the wiring contract: the seed isn't a separate caller's job.
    Implementation can refactor freely as long as the seed fires.
    """
    (isolated_secrets / "console_password").write_text("devpassword")
    monkeypatch.setenv("CONSOLE_USER", "federico")

    calls: list[None] = []
    real_seed = cc._seed_operator_zero

    def spy(conn):  # type: ignore[no-untyped-def]
        calls.append(None)
        return real_seed(conn)

    monkeypatch.setattr(cc, "_seed_operator_zero", spy)

    init_db_console(tmp_path / "console.db").close()
    assert len(calls) == 1, "init_db_console must call _seed_operator_zero exactly once"


# ---------------------------------------------------------------------------
# Direct unit test of the helper (no init_db_console wrapper)
# ---------------------------------------------------------------------------


def test_seed_helper_skips_on_already_populated_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_secrets: Path,
) -> None:
    """Calling _seed_operator_zero directly on a non-empty table is a no-op,
    even if env + secret are populated. Defends against any future refactor
    that calls the helper outside init_db_console."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()  # seed branch will be skipped — no env yet

    conn = get_console_conn(db_path)
    conn.execute(
        "INSERT INTO operators "
        "(username, display_name, password_hash, role_hint, created_at, updated_at) "
        "VALUES ('preexisting', 'Preexisting', 'placeholder', 'operator', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.commit()

    # Now populate env + secret. The helper must still skip because the
    # table has a row.
    (isolated_secrets / "console_password").write_text("devpassword")
    monkeypatch.setenv("CONSOLE_USER", "federico")

    _seed_operator_zero(conn)
    rows = conn.execute(
        "SELECT username FROM operators ORDER BY username"
    ).fetchall()
    assert [r["username"] for r in rows] == ["preexisting"], (
        "seed must not insert when table is non-empty"
    )
    conn.close()
