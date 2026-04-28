"""End-to-end verification for the DRYRUN-CONSOLE seed.

Hits the live operator-console API endpoints on the dev stack and asserts
the locked seed shape:

- V1 ``/console/clients/trial-expiring?window_days=7`` returns 15 rows,
  ordered by ``days_remaining`` ASC, with min=0 and max=7.
- V6 ``/console/clients/retention-queue`` returns 12 rows, ordered by
  ``scheduled_for`` ASC, with action mix {purge:6, anonymise:5,
  purge_bookkeeping:1}.

With ``--post-clean``: asserts both endpoints return an empty list
(invariant after ``make dev-seed-console-clean``).

Reads dev console credentials from ``infra/compose/.env.dev`` (CONSOLE_USER)
and ``infra/compose/secrets.dev/console_password`` (the file-backed secret
materialised by ``make dev-secrets``).

Usage (Mac host, dev stack up)::

    python -m scripts.dev.verify_dev_console_seed
    python -m scripts.dev.verify_dev_console_seed --post-clean
    python -m scripts.dev.verify_dev_console_seed --base http://localhost:8001

Exit code: 0 if every assertion passed, 1 otherwise. Per-check ``PASS:`` /
``FAIL:`` lines on stdout, single-line ``summary:`` at the end.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "http://localhost:8001"
ENV_DEV = REPO / "infra" / "compose" / ".env.dev"
SECRETS_DIR = REPO / "infra" / "compose" / "secrets.dev"
PASSWORD_FILE = SECRETS_DIR / "console_password"

# Locked seed expectations — mirror the plan Federico approved 2026-04-27.
#
# V1 displayed days_remaining is CAST(julianday(trial_expires_at) -
# julianday(now) AS INTEGER), which floors the float. Both timestamps
# are formatted with second precision (``Z``-suffixed ISO), so:
#
#   - seed and query in the same wall-second → display == seed offset,
#     range observed = [1, 7];
#   - query in a later second → display == seed offset - 1,
#     range observed = [0, 6].
#
# Either is correct for a seed list of [1..7] inclusive. We assert
# count + sort + 7 distinct values + tight bounds [0, 7], rather than
# a fixed exact range, because the timing depends on how fast the
# Make target runs. The unit-test suite (synthetic time) asserts the
# exact [1, 7] range for the same seed.
EXPECTED_V1_ROWS = 15
EXPECTED_V1_DISTINCT_DAYS = 7
EXPECTED_V1_DAYS_BOUND_LOW = 0
EXPECTED_V1_DAYS_BOUND_HIGH = 7
EXPECTED_V6_ROWS = 12
EXPECTED_V6_ACTION_MIX = {"purge": 6, "anonymise": 5, "purge_bookkeeping": 1}


class VerifyFail(RuntimeError):
    """Raised for environment / setup problems before any assertion runs."""


# ---------------------------------------------------------------------------
# Credentials + HTTP
# ---------------------------------------------------------------------------


def _read_env_dev() -> dict[str, str]:
    if not ENV_DEV.is_file():
        raise VerifyFail(
            f"{ENV_DEV} not found. Run `make dev-up` to materialise the dev env."
        )
    out: dict[str, str] = {}
    with open(ENV_DEV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            out[key.strip()] = value
    return out


def _read_password() -> str:
    if not PASSWORD_FILE.is_file():
        raise VerifyFail(
            f"{PASSWORD_FILE} not found. Run `make dev-secrets` to materialise "
            "infra/compose/secrets.dev/console_password from .env.dev."
        )
    password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    if not password:
        raise VerifyFail(
            f"{PASSWORD_FILE} is empty. An empty password would surface as "
            "a misleading 401 from the API. Re-run `make dev-secrets` after "
            "fixing CONSOLE_PASSWORD in infra/compose/.env.dev."
        )
    return password


def _credentials() -> tuple[str, str]:
    env = _read_env_dev()
    user = env.get("CONSOLE_USER", "")
    if not user:
        raise VerifyFail("CONSOLE_USER is missing or empty in infra/compose/.env.dev")
    return user, _read_password()


def _get(base: str, path: str, user: str, password: str) -> object:
    url = base.rstrip("/") + path
    auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise VerifyFail(f"GET {path} returned HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        raise VerifyFail(f"GET {path} failed: {exc.reason}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        snippet = body[:200].replace("\n", " ")
        raise VerifyFail(f"GET {path} returned non-JSON ({exc.msg}): {snippet}")


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _check(label: str, ok: bool, detail: str = "") -> bool:
    prefix = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"{prefix}: {label}{suffix}")
    return ok


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def verify_seeded(base: str) -> int:
    user, password = _credentials()
    fails = 0

    v1 = _get(base, "/console/clients/trial-expiring?window_days=7", user, password)
    if not isinstance(v1, list):
        _check("V1 returns a JSON list", False, f"got {type(v1).__name__}: {v1}")
        return 1
    fails += not _check(
        f"V1 row count == {EXPECTED_V1_ROWS}",
        len(v1) == EXPECTED_V1_ROWS,
        f"got {len(v1)}",
    )
    if v1:
        bad_rows = [
            i for i, r in enumerate(v1)
            if not isinstance(r, dict) or not isinstance(r.get("days_remaining"), int)
        ]
        if not _check(
            "V1 every row is a dict with int days_remaining",
            not bad_rows,
            f"bad_rows={bad_rows}",
        ):
            fails += 1
            return 1
        days = [r["days_remaining"] for r in v1]
        fails += not _check(
            "V1 ordered by days_remaining ASC",
            days == sorted(days),
            f"days={days}",
        )
        fails += not _check(
            f"V1 days within bounds [{EXPECTED_V1_DAYS_BOUND_LOW}, {EXPECTED_V1_DAYS_BOUND_HIGH}]",
            all(EXPECTED_V1_DAYS_BOUND_LOW <= d <= EXPECTED_V1_DAYS_BOUND_HIGH for d in days),
            f"days={days}",
        )
        fails += not _check(
            f"V1 covers {EXPECTED_V1_DISTINCT_DAYS} distinct days_remaining values",
            len(set(days)) == EXPECTED_V1_DISTINCT_DAYS,
            f"distinct={sorted(set(days))}",
        )

    v6 = _get(base, "/console/clients/retention-queue", user, password)
    if not isinstance(v6, list):
        _check("V6 returns a JSON list", False, f"got {type(v6).__name__}: {v6}")
        return 1
    fails += not _check(
        f"V6 row count == {EXPECTED_V6_ROWS}",
        len(v6) == EXPECTED_V6_ROWS,
        f"got {len(v6)}",
    )
    if v6:
        scheduled = [r.get("scheduled_for") for r in v6]
        fails += not _check(
            "V6 ordered by scheduled_for ASC",
            scheduled == sorted(scheduled),
            f"first={scheduled[0]} last={scheduled[-1]}",
        )
        actions = dict(Counter(r.get("action") for r in v6))
        fails += not _check(
            f"V6 action mix == {EXPECTED_V6_ACTION_MIX}",
            actions == EXPECTED_V6_ACTION_MIX,
            f"got {actions}",
        )

    print()
    print(f"summary: {'OK' if fails == 0 else f'{fails} FAIL'}")
    return 0 if fails == 0 else 1


def verify_clean(base: str) -> int:
    user, password = _credentials()
    fails = 0

    v1 = _get(base, "/console/clients/trial-expiring?window_days=7", user, password)
    fails += not _check(
        "V1 empty after clean",
        isinstance(v1, list) and len(v1) == 0,
        f"got {len(v1) if isinstance(v1, list) else type(v1).__name__}",
    )
    v6 = _get(base, "/console/clients/retention-queue", user, password)
    fails += not _check(
        "V6 empty after clean",
        isinstance(v6, list) and len(v6) == 0,
        f"got {len(v6) if isinstance(v6, list) else type(v6).__name__}",
    )

    print()
    print(f"summary: {'OK' if fails == 0 else f'{fails} FAIL'}")
    return 0 if fails == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_dev_console_seed",
        description=(
            "Assert the DRYRUN-CONSOLE seed shape against the live dev API. "
            "Run after `make dev-seed-console`. With --post-clean, runs after "
            "`make dev-seed-console-clean` to assert empty endpoints."
        ),
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"API base URL (default {DEFAULT_BASE}).",
    )
    parser.add_argument(
        "--post-clean",
        action="store_true",
        help="Assert both endpoints are empty (post-clean invariant).",
    )
    args = parser.parse_args(argv)

    try:
        if args.post_clean:
            return verify_clean(args.base)
        return verify_seeded(args.base)
    except VerifyFail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
