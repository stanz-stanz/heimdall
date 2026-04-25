"""End-to-end verification for the SvelteKit signup-site slice 1.

Runs INSIDE the dev `scheduler` container (which has read-write
`client-data:/data/clients` and can reach the api on the internal
docker network at `http://api:8000`). Launched by ``make signup-verify``
which docker-cps the current host copy in before exec.

Replaces the slice-1 plan's Task-20 ad-hoc one-liners (per
``feedback_build_reusable_verify_scripts``).

Four checks:

  1. Issue a fresh signup token via :func:`src.db.signup.create_signup_token`.
  2. POST ``/signup/validate`` to the api container with that token + a
     valid dev ``Origin``. Assert ``200`` + ``ok=True`` +
     ``bot_username == "HeimdallSecurityDEVbot"``.
  3. Re-query ``signup_tokens`` row directly. Assert ``consumed_at IS NULL``
     and ``email`` unchanged — proves the validate endpoint is read-only.
  4. POST the same endpoint with an obviously-bad token. Assert ``200`` +
     ``{"ok": False, "reason": "invalid"}``.

Cleanup deletes the test CVR row + any signup_tokens for it in a finally
block. Token prefix is ``DRYRUN-`` so any orphaned rows are easy to spot.

Exits 0 on green, 1 on any failure.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import requests  # noqa: E402

from src.db.signup import create_signup_token  # noqa: E402

DB_PATH = os.environ.get(
    "HEIMDALL_VERIFY_DB", "/data/clients/clients.db"
)
API_BASE = os.environ.get("HEIMDALL_VERIFY_API_BASE", "http://api:8000")
ORIGIN = os.environ.get("HEIMDALL_VERIFY_ORIGIN", "http://localhost:5173")
EXPECTED_BOT = os.environ.get(
    "HEIMDALL_VERIFY_BOT_USERNAME", "HeimdallSecurityDEVbot"
)

VERIFY_CVR = "DRYRUN-VERIFY-SIGNUP"
VERIFY_EMAIL = "verify-signup@example.invalid"


class VerifyError(RuntimeError):
    """Raised when a signup-slice-1 verification check fails."""


def _pass(msg: str) -> None:
    print(f"[PASS] {msg}")


def _fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return 1


def _assert_environment() -> None:
    if not Path(DB_PATH).exists():
        raise VerifyError(
            f"clients.db not found at {DB_PATH} — run inside the scheduler "
            "container, or set HEIMDALL_VERIFY_DB"
        )


def _seed_client(conn: sqlite3.Connection) -> None:
    """Insert (or upsert) a synthetic client row for the verify CVR."""
    conn.execute(
        """
        INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at)
        VALUES (?, ?, 'prospect', 'watchman', datetime('now'), datetime('now'))
        ON CONFLICT(cvr) DO UPDATE SET
          updated_at = datetime('now')
        """,
        (VERIFY_CVR, "Verify Signup Slice 1"),
    )
    conn.commit()


def _cleanup(conn: sqlite3.Connection) -> None:
    """Remove the synthetic CVR + any tokens issued during this run."""
    conn.execute("DELETE FROM signup_tokens WHERE cvr = ?", (VERIFY_CVR,))
    conn.execute("DELETE FROM clients WHERE cvr = ?", (VERIFY_CVR,))
    conn.commit()


def _issue_token(conn: sqlite3.Connection) -> str:
    result = create_signup_token(conn, cvr=VERIFY_CVR, email=VERIFY_EMAIL)
    return result["token"]


def _post_validate(token: str) -> requests.Response:
    return requests.post(
        f"{API_BASE}/signup/validate",
        json={"token": token},
        headers={"Origin": ORIGIN},
        timeout=10,
    )


def _check_valid_token_succeeds(token: str) -> None:
    resp = _post_validate(token)
    if resp.status_code != 200:
        raise VerifyError(
            f"valid-token POST returned {resp.status_code}, body={resp.text!r}"
        )
    body = resp.json()
    if body.get("ok") is not True:
        raise VerifyError(f"valid-token body has ok != True: {body!r}")
    if body.get("bot_username") != EXPECTED_BOT:
        raise VerifyError(
            f"bot_username mismatch: got {body.get('bot_username')!r}, "
            f"expected {EXPECTED_BOT!r} (set HEIMDALL_VERIFY_BOT_USERNAME if "
            "you're running against a different bot)"
        )
    _pass(
        f"POST /signup/validate (valid token) → 200 ok=True "
        f"bot_username={EXPECTED_BOT!r}"
    )


def _check_token_state_unchanged(
    conn: sqlite3.Connection, token: str
) -> None:
    row = conn.execute(
        "SELECT consumed_at, email FROM signup_tokens WHERE token = ?",
        (token,),
    ).fetchone()
    if row is None:
        raise VerifyError(
            f"signup_tokens row vanished for token {token[:8]}…"
        )
    consumed_at, email = row
    if consumed_at is not None:
        raise VerifyError(
            f"validate mutated token: consumed_at={consumed_at!r} (must be NULL)"
        )
    if email != VERIFY_EMAIL:
        raise VerifyError(
            f"validate mutated token: email={email!r} (must be {VERIFY_EMAIL!r})"
        )
    _pass(
        "signup_tokens row unchanged after validate (consumed_at NULL, email preserved)"
    )


def _check_invalid_token_returns_invalid() -> None:
    resp = _post_validate("DRYRUN-VERIFY-INVALID-TOKEN-XYZ")
    if resp.status_code != 200:
        raise VerifyError(
            f"invalid-token POST returned {resp.status_code}, body={resp.text!r}"
        )
    body = resp.json()
    if body != {"ok": False, "reason": "invalid"}:
        raise VerifyError(f"invalid-token body wrong: {body!r}")
    _pass(
        "POST /signup/validate (unknown token) → 200 ok=False reason='invalid'"
    )


def _run_checks(conn: sqlite3.Connection) -> None:
    _seed_client(conn)
    _pass(f"seeded synthetic client for CVR={VERIFY_CVR!r}")

    token = _issue_token(conn)
    _pass(f"issued signup token (length={len(token)})")

    _check_valid_token_succeeds(token)
    _check_token_state_unchanged(conn, token)
    _check_invalid_token_returns_invalid()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the SvelteKit signup-site slice-1 backend "
        "contract against the running dev stack."
    )
    parser.add_argument(
        "--keep-test-data",
        action="store_true",
        help="Leave the synthetic CVR + tokens in clients.db after the run "
        "(useful for poking at the DB manually). Default: cleanup runs.",
    )
    args = parser.parse_args()

    try:
        _assert_environment()
    except VerifyError as exc:
        return _fail(str(exc))

    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        try:
            _run_checks(conn)
        except VerifyError as exc:
            _fail(str(exc))
            return 1
        except requests.RequestException as exc:
            _fail(
                f"network error talking to {API_BASE}: {exc!r}. "
                f"Is `make dev-up` green?"
            )
            return 1
    finally:
        if args.keep_test_data:
            print(
                "[INFO] --keep-test-data set; not cleaning up "
                f"CVR={VERIFY_CVR!r}",
                file=sys.stderr,
            )
        else:
            _cleanup(conn)
        conn.close()

    print("[PASS] all four checks (signup-slice-1 backend contract green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
