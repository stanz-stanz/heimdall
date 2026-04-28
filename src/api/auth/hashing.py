"""Argon2id password hashing for operator credentials.

Stage A spec §2.5. Used by:
- ``src/db/console_connection.py:_seed_operator_zero`` (slice 2 — hash
  ``CONSOLE_PASSWORD`` once at first startup).
- ``src/api/auth/sessions.py`` and the login handler (slices 3+).

Parameters are RFC 9106's first-recommended defaults for Argon2id and
benchmark in <100ms on a Pi5. Don't widen blindly; widen only after
re-benchmarking on the production target.

Optional pepper: if ``/run/secrets/operator_password_pepper`` exists,
the password is HMAC-SHA256'd with the pepper before being passed to
Argon2id. This is defense-in-depth against a database-only theft (an
attacker with hashes but not the pepper file cannot brute-force the
plaintexts). Stage A ships without a pepper file by default.

**Pepper enablement / rotation locks operators out until re-seeded.**
The PHC string stored in ``operators.password_hash`` does not record
which (if any) pepper produced it, so any change to pepper presence or
value makes existing hashes unverifiable. Enabling pepper after first
boot, or rotating it later, therefore requires running rollback lever
§9.2 (one-shot re-hash inside the api container, ``UPDATE`` the row
by id) for every operator. The seed in
``src/db/console_connection.py:_seed_operator_zero`` is idempotent by
design — it will NEVER re-hash an existing row at startup, even with
a fresh pepper file mounted. The Stage A.5 operator-admin UI is the
right place to ship rolling re-hash; until then, lever 9.2 is the
documented and supported path.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# RFC 9106 first-recommended Argon2id parameters. See spec §2.5.
_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# Pepper path is module-level so tests can monkeypatch it. In production
# the file is mounted by Docker Compose at this exact path or absent.
_PEPPER_PATH = Path("/run/secrets/operator_password_pepper")


def _peppered_input(plaintext: str) -> str:
    """Return the string actually fed to Argon2id.

    With pepper present: HMAC-SHA256(pepper, plaintext) hex digest.
    Without pepper: the plaintext unchanged.

    The pepper file is read on every call so a post-deploy ``docker
    secret rotate`` (or equivalent) takes effect on the next hash
    without an api restart. The file is small (typically 32 bytes) and
    the syscall is cheap relative to Argon2id's tens of milliseconds.
    """
    if _PEPPER_PATH.is_file():
        pepper = _PEPPER_PATH.read_bytes()
        return hmac.new(pepper, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()
    return plaintext


def hash_password(plaintext: str) -> str:
    """Return a PHC-formatted Argon2id hash for *plaintext*.

    Raises:
        ValueError: If *plaintext* is empty. An empty operator password
            is a programmer error at seed time, not a runtime branch we
            silently encode.
    """
    if not plaintext:
        raise ValueError("password must be non-empty")
    return _HASHER.hash(_peppered_input(plaintext))


def verify_password(hash_str: str, plaintext: str) -> bool:
    """True iff *plaintext* matches *hash_str*.

    Returns False on mismatch, malformed hash, or empty plaintext. Never
    raises — the caller wants a boolean for branching, and login flows
    must use the same constant-time False path for "no such user" and
    "wrong password" to avoid a timing oracle (see spec §3.1).
    """
    if not plaintext:
        return False
    try:
        return _HASHER.verify(hash_str, _peppered_input(plaintext))
    except (VerifyMismatchError, InvalidHash, VerificationError):
        return False
