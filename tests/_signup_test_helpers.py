"""Shared helpers for the signup-validate + round-trip test files.

Underscore-prefixed so pytest does not collect it as a test module.
"""

from __future__ import annotations

import sqlite3

import fakeredis
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.db.connection import init_db
from src.db.signup import create_signup_token

ORIGIN_DEV_LOCALHOST = "http://localhost:5173"
ORIGIN_DEV_LOOPBACK = "http://127.0.0.1:5173"
ORIGIN_PROD = "https://signup.digitalvagt.dk"
BAD_ORIGIN = "https://attacker.example"

SEED_CVR = "12345678"
SEED_COMPANY = "Test Restaurant ApS"
SEED_NOW = "2026-04-25T10:00:00Z"


def init_seeded_db(db_file_path: str) -> None:
    """Initialise a fresh clients.db with the canonical seed CVR row."""
    conn = init_db(db_file_path)
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (SEED_CVR, SEED_COMPANY, "prospect", "watchman", SEED_NOW, SEED_NOW),
    )
    conn.commit()
    conn.close()


def issue_token(db_path: str, *, email: str | None = None) -> str:
    """Issue a fresh signup token bound to the seeded CVR. Returns the token string."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        result = create_signup_token(conn, cvr=SEED_CVR, email=email)
    finally:
        conn.close()
    return result["token"]


def make_client(db_path: str, tmp_path, monkeypatch) -> TestClient:
    """Build a FastAPI TestClient bound to a fresh DB and fakeredis."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "HeimdallSecurityDEVbot")
    monkeypatch.setenv(
        "SIGNUP_ALLOWED_ORIGINS",
        ",".join([ORIGIN_DEV_LOCALHOST, ORIGIN_DEV_LOOPBACK, ORIGIN_PROD]),
    )
    monkeypatch.chdir(tmp_path)
    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = db_path
    return TestClient(app)
