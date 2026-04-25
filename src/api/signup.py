"""Signup API router — magic-link token validation (read-only)."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from src.db.signup import get_signup_token

router = APIRouter(prefix="/signup", tags=["signup"])


class ValidateBody(BaseModel):
    token: str


_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _allowed_origins() -> set[str]:
    """Return the set of origins that may call /signup/validate.

    Falls back to localhost dev defaults when the env var is absent **or**
    empty (e.g. when compose injects ``SIGNUP_ALLOWED_ORIGINS=`` because
    the host var is unset).
    """
    raw = os.environ.get("SIGNUP_ALLOWED_ORIGINS", "").strip() or _DEFAULT_ORIGINS
    return {o.strip() for o in raw.split(",") if o.strip()}


def _fetch_token_row(db_path: str, token: str) -> dict | None:
    """Open the DB and fetch the token row in a thread-safe sync context.

    Raises :exc:`HTTPException` (503) on ``sqlite3.OperationalError`` so
    the caller never sees a raw 500 on DB open/query failure.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            return get_signup_token(conn, token)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        logger.warning("signup_validate_db_error: {}", exc)
        raise HTTPException(503, "clients_db_unavailable") from exc


@router.post("/validate")
async def validate(request: Request, body: ValidateBody):
    """Read-only check on a magic-link token. Never mutates state.

    Token consumption happens later in
    src/db/onboarding.py:activate_watchman_trial via the Telegram
    /start <token> handler.
    """
    if request.headers.get("origin") not in _allowed_origins():
        raise HTTPException(403, "origin_not_allowed")

    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME")
    if not bot_username:
        logger.error("signup_validate_missing_bot_username")
        raise HTTPException(503, "bot_username_unconfigured")

    db_path = getattr(request.app.state, "db_path", None)
    if not db_path:
        raise HTTPException(503, "clients_db_unavailable")

    row = await asyncio.to_thread(_fetch_token_row, db_path, body.token)

    if row is None:
        return {"ok": False, "reason": "invalid"}
    if row["consumed_at"] is not None:
        return {"ok": False, "reason": "used"}
    expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires_at <= datetime.now(UTC):
        return {"ok": False, "reason": "expired"}

    return {"ok": True, "bot_username": bot_username}
