"""Consent validator — reads and validates client authorisation files.

Standalone module used by the worker (Gate 2), the API, and the scheduler.
Does NOT create, modify, or delete consent files — read-only validation.

The ``authorised_by.role`` field is informational only. Legal standing of the
signer is validated by the operator at onboarding, not by this code. This is
a deliberate design choice: who is authorised to consent is an open legal
question that will be resolved by Danish legal counsel.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsentCheckResult:
    """Result of a Gate 2 consent validation check."""

    allowed: bool
    client_id: str
    domain: str
    level_requested: int
    level_authorised: int  # -1 if no consent file found
    reason: str
    consent_expiry: Optional[str] = None
    authorised_by_role: Optional[str] = None


def load_authorisation(client_dir: Path, client_id: str) -> Optional[dict]:
    """Load and parse authorisation.json for a client.

    Returns the parsed dict, or None if the file is missing or malformed.
    """
    path = client_dir / client_id / "authorisation.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(
            "authorisation_load_error",
            extra={"context": {"client_id": client_id, "path": str(path), "error": str(exc)}},
        )
        return None


def check_consent(
    client_dir: Path,
    client_id: str,
    domain: str,
    level_requested: int,
    reference_date: Optional[date] = None,
) -> ConsentCheckResult:
    """Validate whether a scan at *level_requested* is permitted for *domain*.

    Gate 2 logic:

    1. Level 0 scans always pass — no consent needed.
    2. For Level >= 1: load authorisation.json, then check status,
       expiry, domain scope, and authorised level.

    The ``reference_date`` parameter defaults to today (UTC) and is
    exposed for deterministic testing.
    """
    if reference_date is None:
        reference_date = date.today()

    # Level 0: no consent required
    if level_requested == 0:
        return ConsentCheckResult(
            allowed=True,
            client_id=client_id,
            domain=domain,
            level_requested=0,
            level_authorised=0,
            reason="Level 0 — no consent required",
        )

    # Level 1+: load and validate consent
    auth = load_authorisation(client_dir, client_id)

    if auth is None:
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=-1,
            reason="No authorisation file found",
        )

    status = auth.get("status", "")
    if status != "active":
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=auth.get("level_authorised", 0),
            reason=f"Consent status is '{status}', not active",
        )

    expiry_str = auth.get("consent_expiry", "")
    try:
        expiry = date.fromisoformat(expiry_str)
    except (ValueError, TypeError):
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=auth.get("level_authorised", 0),
            reason=f"Invalid consent_expiry: '{expiry_str}'",
        )

    if reference_date > expiry:
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=auth.get("level_authorised", 0),
            reason=f"Consent expired on {expiry}",
            consent_expiry=expiry_str,
        )

    authorised_domains = auth.get("authorised_domains", [])
    if domain not in authorised_domains:
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=auth.get("level_authorised", 0),
            reason=f"Domain '{domain}' not in authorised scope: {authorised_domains}",
            consent_expiry=expiry_str,
        )

    level_authorised = auth.get("level_authorised", 0)
    if level_authorised < level_requested:
        return ConsentCheckResult(
            allowed=False,
            client_id=client_id,
            domain=domain,
            level_requested=level_requested,
            level_authorised=level_authorised,
            reason=f"Authorised level {level_authorised} < requested level {level_requested}",
            consent_expiry=expiry_str,
        )

    authorised_by = auth.get("authorised_by", {})
    return ConsentCheckResult(
        allowed=True,
        client_id=client_id,
        domain=domain,
        level_requested=level_requested,
        level_authorised=level_authorised,
        reason="Valid consent on file",
        consent_expiry=expiry_str,
        authorised_by_role=authorised_by.get("role"),
    )


def validate_schema(authorisation: dict) -> list[str]:
    """Validate an authorisation dict against the required fields from the schema.

    Returns a list of error messages (empty = valid). Uses a lightweight
    check against the schema's ``required`` array — no external dependency.
    """
    schema_path = Path(__file__).resolve().parent.parent.parent / "config" / "consent_schema.json"
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ["Could not load consent schema"]

    errors = []
    for field in schema.get("required", []):
        if field not in authorisation:
            errors.append(f"Missing required field: '{field}'")

    # Check authorised_by sub-fields
    auth_by = authorisation.get("authorised_by")
    if isinstance(auth_by, dict):
        auth_by_schema = schema.get("properties", {}).get("authorised_by", {})
        for field in auth_by_schema.get("required", []):
            if field not in auth_by:
                errors.append(f"Missing required field in authorised_by: '{field}'")

    return errors
