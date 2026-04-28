"""Tests for src.api.auth.hashing — Stage A Argon2id wrapper.

Stage A spec §2.5 + §8.2 (test_auth_hashing.py block). The wrapper is a
thin facade over ``argon2.PasswordHasher`` with explicit RFC 9106
parameters and an optional pepper read from
``/run/secrets/operator_password_pepper``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.auth import hashing
from src.api.auth.hashing import hash_password, verify_password


# ---------------------------------------------------------------------------
# hash_password
# ---------------------------------------------------------------------------


def test_hash_password_returns_argon2id_phc_string() -> None:
    """hash_password emits an Argon2id PHC-formatted string."""
    h = hash_password("correct horse battery staple")
    assert isinstance(h, str)
    assert h.startswith("$argon2id$"), f"expected argon2id PHC string, got {h!r}"


def test_hash_password_rejects_empty() -> None:
    """Empty plaintext is a programmer error, not a runtime fall-through."""
    with pytest.raises(ValueError):
        hash_password("")


def test_hash_password_accepts_long_password() -> None:
    """A 256-char password hashes without truncation or error."""
    pw = "x" * 256
    h = hash_password(pw)
    assert h.startswith("$argon2id$")
    assert verify_password(h, pw) is True


def test_hash_password_uses_random_salt() -> None:
    """Two hashes of the same plaintext differ — random salt is in effect."""
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b, "expected different hashes for same plaintext (random salt)"


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------


def test_verify_password_true_for_match() -> None:
    h = hash_password("hunter2")
    assert verify_password(h, "hunter2") is True


def test_verify_password_false_for_mismatch() -> None:
    h = hash_password("hunter2")
    assert verify_password(h, "wrong") is False


def test_verify_password_false_for_empty_plaintext() -> None:
    """Empty plaintext returns False (callers want a boolean, never an exception)."""
    h = hash_password("hunter2")
    assert verify_password(h, "") is False


def test_verify_password_false_for_malformed_hash() -> None:
    """Malformed PHC string returns False, not a crash."""
    assert verify_password("not-a-real-hash", "anything") is False


# ---------------------------------------------------------------------------
# Pepper (optional defense-in-depth, off by default)
# ---------------------------------------------------------------------------


def test_pepper_present_changes_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the pepper file exists, the resulting hash differs from no-pepper.

    The pepper is HMAC-SHA256'd with the password before passing to
    Argon2id, so the Argon2 input differs and the hash output differs.
    Verifies via roundtrip that the same pepper still verifies.
    """
    pepper_file = tmp_path / "operator_password_pepper"
    pepper_file.write_bytes(b"pepper-secret-value")
    monkeypatch.setattr(hashing, "_PEPPER_PATH", pepper_file)

    pw = "same-password"
    peppered_hash = hash_password(pw)
    assert verify_password(peppered_hash, pw) is True

    # Disable the pepper, verify must now fail (different Argon2 input).
    monkeypatch.setattr(hashing, "_PEPPER_PATH", tmp_path / "missing")
    assert verify_password(peppered_hash, pw) is False


def test_pepper_absent_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stage A ships without a pepper file — hash + verify roundtrip works as-is."""
    monkeypatch.setattr(hashing, "_PEPPER_PATH", tmp_path / "no-such-pepper")
    h = hash_password("plain")
    assert verify_password(h, "plain") is True
