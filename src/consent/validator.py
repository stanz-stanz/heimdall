"""Consent validator — reads and validates client authorisation files.

SAFETY-CRITICAL MODULE. This code determines whether Heimdall is legally
permitted to perform active scanning against a target. A fail-open bug here
means criminal liability under Straffeloven §263.

Design principle: **BLOCK on any ambiguity.** Every unexpected type, missing
field, parse error, or unhandled exception results in ``allowed=False``.
There is no code path where an error leads to a scan being permitted.

The ``authorised_by.role`` field is informational only. Legal standing of the
signer is validated by the operator at onboarding, not by this code.
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


def _blocked(
    client_id: str, domain: str, level_requested: int,
    reason: str, level_authorised: int = -1,
    consent_expiry: Optional[str] = None,
) -> ConsentCheckResult:
    """Convenience: build a BLOCKED result. Reduces copy-paste errors."""
    return ConsentCheckResult(
        allowed=False,
        client_id=client_id,
        domain=domain,
        level_requested=level_requested,
        level_authorised=level_authorised,
        reason=reason,
        consent_expiry=consent_expiry,
    )


def load_authorisation(client_dir: Path, client_id: str) -> Optional[dict]:
    """Load and parse authorisation.json for a client.

    Returns the parsed dict, or None if the file is missing or malformed.
    """
    path = client_dir / client_id / "authorisation.json"
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log.warning(
                "authorisation_not_dict",
                extra={"context": {"client_id": client_id, "type": type(data).__name__}},
            )
            return None
        return data
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

    SAFETY CONTRACT:
    - This function NEVER raises. Any internal error returns allowed=False.
    - Level 0 passes immediately (no file I/O).
    - Level 1+ must pass ALL checks: file exists, valid JSON, status active,
      not expired, domain in scope, level sufficient, consent doc exists.
    - Every field is type-checked. Unexpected types → blocked.
    """
    try:
        return _check_consent_inner(client_dir, client_id, domain, level_requested, reference_date)
    except Exception as exc:
        # SAFETY NET: if anything unexpected happens, BLOCK.
        log.error(
            "consent_check_unexpected_error",
            extra={"context": {
                "client_id": client_id, "domain": domain,
                "level_requested": level_requested, "error": str(exc),
            }},
            exc_info=True,
        )
        return _blocked(client_id, domain, level_requested if isinstance(level_requested, int) else -1,
                        f"Internal error during consent check: {exc}")


def _check_consent_inner(
    client_dir: Path,
    client_id: str,
    domain: str,
    level_requested: int,
    reference_date: Optional[date],
) -> ConsentCheckResult:
    """Inner implementation. May raise — caller catches everything."""

    if reference_date is None:
        reference_date = date.today()

    # ---- Input validation ----
    if not isinstance(level_requested, int) or isinstance(level_requested, bool):
        return _blocked(client_id, domain, -1,
                        f"level_requested must be int, got {type(level_requested).__name__}")

    if level_requested < 0:
        return _blocked(client_id, domain, level_requested,
                        f"level_requested must be >= 0, got {level_requested}")

    # Normalise domain to lowercase (DNS is case-insensitive)
    domain = domain.strip().lower().rstrip(".")

    if not domain:
        return _blocked(client_id, domain, level_requested, "Empty domain")

    # ---- Level 0: no consent required ----
    if level_requested == 0:
        return ConsentCheckResult(
            allowed=True,
            client_id=client_id,
            domain=domain,
            level_requested=0,
            level_authorised=0,
            reason="Level 0 — no consent required",
        )

    # ---- Level 1+: load and validate consent ----
    auth = load_authorisation(client_dir, client_id)

    if auth is None:
        return _blocked(client_id, domain, level_requested,
                        "No authorisation file found")

    # -- Status check --
    status = auth.get("status")
    if not isinstance(status, str) or status != "active":
        return _blocked(client_id, domain, level_requested,
                        f"Consent status is '{status}', not 'active'",
                        level_authorised=_safe_int(auth.get("level_authorised")))

    # -- Expiry check --
    expiry_str = auth.get("consent_expiry")
    if not isinstance(expiry_str, str):
        return _blocked(client_id, domain, level_requested,
                        f"consent_expiry must be a string, got {type(expiry_str).__name__}",
                        level_authorised=_safe_int(auth.get("level_authorised")))
    try:
        expiry = date.fromisoformat(expiry_str)
    except (ValueError, TypeError):
        return _blocked(client_id, domain, level_requested,
                        f"Invalid consent_expiry: '{expiry_str}'",
                        level_authorised=_safe_int(auth.get("level_authorised")))

    if reference_date > expiry:
        return _blocked(client_id, domain, level_requested,
                        f"Consent expired on {expiry}",
                        level_authorised=_safe_int(auth.get("level_authorised")),
                        consent_expiry=expiry_str)

    # -- Domain scope check (case-insensitive) --
    authorised_domains_raw = auth.get("authorised_domains")
    if not isinstance(authorised_domains_raw, list):
        return _blocked(client_id, domain, level_requested,
                        f"authorised_domains must be a list, got {type(authorised_domains_raw).__name__}",
                        level_authorised=_safe_int(auth.get("level_authorised")),
                        consent_expiry=expiry_str)

    # Normalise all authorised domains: lowercase, strip, no trailing dot
    authorised_domains = [
        d.strip().lower().rstrip(".")
        for d in authorised_domains_raw
        if isinstance(d, str)
    ]

    if domain not in authorised_domains:
        return _blocked(client_id, domain, level_requested,
                        f"Domain '{domain}' not in authorised scope: {authorised_domains}",
                        level_authorised=_safe_int(auth.get("level_authorised")),
                        consent_expiry=expiry_str)

    # -- Level check --
    level_authorised = auth.get("level_authorised")
    if not isinstance(level_authorised, int) or isinstance(level_authorised, bool):
        return _blocked(client_id, domain, level_requested,
                        f"level_authorised must be int, got {type(level_authorised).__name__}",
                        consent_expiry=expiry_str)

    if level_authorised < level_requested:
        return _blocked(client_id, domain, level_requested,
                        f"Authorised level {level_authorised} < requested level {level_requested}",
                        level_authorised=level_authorised,
                        consent_expiry=expiry_str)

    # -- Consent document existence check --
    consent_doc_path = auth.get("consent_document")
    if not isinstance(consent_doc_path, str) or not consent_doc_path.strip():
        return _blocked(client_id, domain, level_requested,
                        "No consent_document path specified",
                        level_authorised=level_authorised,
                        consent_expiry=expiry_str)

    doc_full_path = (client_dir / client_id / consent_doc_path).resolve()
    client_root = (client_dir / client_id).resolve()
    if client_root not in doc_full_path.parents and doc_full_path != client_root:
        return _blocked(client_id, domain, level_requested,
                        f"Consent document path escapes client directory: {consent_doc_path}",
                        level_authorised=level_authorised,
                        consent_expiry=expiry_str)
    if not doc_full_path.is_file():
        return _blocked(client_id, domain, level_requested,
                        f"Consent document not found: {consent_doc_path}",
                        level_authorised=level_authorised,
                        consent_expiry=expiry_str)

    # -- All checks passed --
    authorised_by = auth.get("authorised_by", {})
    role = authorised_by.get("role") if isinstance(authorised_by, dict) else None

    return ConsentCheckResult(
        allowed=True,
        client_id=client_id,
        domain=domain,
        level_requested=level_requested,
        level_authorised=level_authorised,
        reason="Valid consent on file",
        consent_expiry=expiry_str,
        authorised_by_role=role,
    )


def _safe_int(value) -> int:
    """Extract an int from a value, defaulting to -1 for non-int types."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return -1


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
