"""Sentinel-tier Certificate Transparency monitoring.

Polls SSLMate's CertSpotter API for each Sentinel client's domains, diffs
the returned certificates against stored snapshots in the clients.db,
writes new snapshots, emits change rows for new_cert / new_san / ca_change
events, and publishes them on the Redis ``client-cert-change`` channel so
the delivery runner can compose Telegram alerts.

Watchman-tier clients are filtered out at the scheduler-handler level, not
here. This module trusts its caller. The tier check lives in
``src/scheduler/daemon.py::_handle_monitor_clients``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger

from src.core.secrets import get_secret

_CERTSPOTTER_URL = os.environ.get(
    "CERTSPOTTER_URL", "https://api.certspotter.com/v1/issuances"
)
_CHANNEL = "client-cert-change"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_issuances(
    domain: str,
    api_key: str | None,
    http_client: httpx.Client,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """Call CertSpotter for one domain, following pagination until empty.

    Returns a list of issuance dicts with the keys we care about.
    """
    headers = {"User-Agent": "Heimdall/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    params = {
        "domain": domain,
        "include_subdomains": "true",
        "expand": ["dns_names", "issuer"],
    }
    all_issuances: list[dict[str, Any]] = []
    after: str | None = None

    for _ in range(max_pages):
        page_params = dict(params)
        if after:
            page_params["after"] = after
        try:
            resp = http_client.get(
                _CERTSPOTTER_URL, params=page_params, headers=headers
            )
        except httpx.HTTPError as exc:
            logger.bind(context={"domain": domain, "error": str(exc)}).warning(
                "certspotter_http_error"
            )
            break

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "0")
            logger.bind(
                context={"domain": domain, "retry_after": retry_after}
            ).warning("certspotter_rate_limited")
            break
        if resp.status_code >= 400:
            logger.bind(
                context={"domain": domain, "status": resp.status_code}
            ).warning("certspotter_bad_status")
            break

        try:
            page = resp.json()
        except ValueError:
            logger.bind(context={"domain": domain}).warning(
                "certspotter_bad_json"
            )
            break
        if not isinstance(page, list) or not page:
            break

        all_issuances.extend(page)
        after = page[-1].get("id")
        if not after:
            break

    return all_issuances


def _normalize_issuance(issuance: dict[str, Any]) -> dict[str, Any]:
    """Return a compact dict of the fields we persist and diff on."""
    dns_names = issuance.get("dns_names") or []
    issuer = issuance.get("issuer") or {}
    return {
        "cert_sha256": issuance.get("cert_sha256") or "",
        "common_name": (dns_names[0] if dns_names else ""),
        "issuer_name": issuer.get("friendly_name") or issuer.get("name") or "",
        "dns_names": sorted({str(n).lower() for n in dns_names if n}),
        "not_before": issuance.get("not_before") or "",
        "not_after": issuance.get("not_after") or "",
    }


def _classify_change(
    new_cert: dict[str, Any], prior: list[sqlite3.Row]
) -> str | None:
    """Decide whether *new_cert* is a relevant change vs *prior* snapshots.

    Returns ``new_cert``, ``new_san``, ``ca_change``, or None.
    """
    prior_hashes = {row["cert_sha256"] for row in prior}
    if new_cert["cert_sha256"] in prior_hashes:
        return None  # exact cert already seen

    if not prior:
        return "new_cert"  # first cert we've ever stored for this domain

    # SAN / CA comparison is against the most recent prior snapshot.
    latest = max(
        prior, key=lambda r: r["last_seen_at"] or r["first_seen_at"] or ""
    )

    new_sans = set(new_cert["dns_names"])
    old_sans = set(json.loads(latest["dns_names_json"] or "[]"))
    if new_sans - old_sans:
        return "new_san"

    if new_cert["issuer_name"] and latest["issuer_name"] and (
        new_cert["issuer_name"] != latest["issuer_name"]
    ):
        return "ca_change"

    return "new_cert"  # new sha but no interesting diff — still a fresh issuance


def _dedupe_recent_change(
    conn: sqlite3.Connection,
    cvr: str,
    domain: str,
    change_type: str,
    window_hours: int,
) -> bool:
    """True if a change of this type was already recorded for (cvr, domain) inside the window."""
    cutoff = datetime.now(UTC).timestamp() - window_hours * 3600
    rows = conn.execute(
        """
        SELECT detected_at FROM client_cert_changes
        WHERE cvr = ? AND domain = ? AND change_type = ?
        ORDER BY detected_at DESC LIMIT 1
        """,
        (cvr, domain, change_type),
    ).fetchall()
    if not rows:
        return False
    try:
        ts = datetime.fromisoformat(rows[0][0].replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return False
    return ts >= cutoff


def _upsert_snapshot(
    conn: sqlite3.Connection,
    cvr: str,
    domain: str,
    norm: dict[str, Any],
) -> None:
    """Insert or refresh a client_cert_snapshots row."""
    now = _now()
    conn.execute(
        """
        INSERT INTO client_cert_snapshots
            (cvr, domain, cert_sha256, common_name, issuer_name,
             dns_names_json, not_before, not_after,
             first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cvr, domain, cert_sha256) DO UPDATE SET
            last_seen_at = excluded.last_seen_at
        """,
        (
            cvr,
            domain,
            norm["cert_sha256"],
            norm["common_name"],
            norm["issuer_name"],
            json.dumps(norm["dns_names"]),
            norm["not_before"],
            norm["not_after"],
            now,
            now,
        ),
    )


def poll_and_diff_client(
    cvr: str,
    primary_domain: str,
    db_conn: sqlite3.Connection,
    redis_conn: Any,
    *,
    api_key: str | None = None,
    http_timeout_s: float = 30.0,
    dedupe_window_hours: int = 24,
) -> dict[str, int]:
    """Poll CertSpotter for *primary_domain* and emit changes for *cvr*.

    Returns a summary dict: ``{"issuances": N, "new_snapshots": X, "changes": Y}``.

    Reads snapshots from ``client_cert_snapshots``, writes new rows, writes
    ``client_cert_changes`` entries, publishes events on Redis, and updates
    ``clients.ct_last_polled_at``.
    """
    api_key = api_key or get_secret("certspotter_api_key", "CERTSPOTTER_API_KEY") or None
    summary = {"issuances": 0, "new_snapshots": 0, "changes": 0}

    with httpx.Client(timeout=http_timeout_s) as client:
        issuances = _fetch_issuances(primary_domain, api_key, client)
    summary["issuances"] = len(issuances)

    prior = db_conn.execute(
        """
        SELECT cert_sha256, dns_names_json, issuer_name, first_seen_at, last_seen_at
        FROM client_cert_snapshots
        WHERE cvr = ? AND domain = ?
        """,
        (cvr, primary_domain),
    ).fetchall()

    first_poll = not prior

    for issuance in issuances:
        norm = _normalize_issuance(issuance)
        if not norm["cert_sha256"]:
            continue

        change_type = _classify_change(norm, prior)
        _upsert_snapshot(db_conn, cvr, primary_domain, norm)
        summary["new_snapshots"] += 1

        if change_type is None or first_poll:
            # First poll = baseline only. No alerts from historical certs.
            continue

        if _dedupe_recent_change(
            db_conn, cvr, primary_domain, change_type, dedupe_window_hours
        ):
            logger.bind(
                context={"cvr": cvr, "domain": primary_domain, "type": change_type}
            ).debug("ct_change_deduped")
            continue

        details = {
            "cert_sha256": norm["cert_sha256"],
            "common_name": norm["common_name"],
            "issuer_name": norm["issuer_name"],
            "dns_names": norm["dns_names"],
            "not_before": norm["not_before"],
            "not_after": norm["not_after"],
        }
        cursor = db_conn.execute(
            """
            INSERT INTO client_cert_changes
                (cvr, domain, change_type, details_json, detected_at, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (cvr, primary_domain, change_type, json.dumps(details), _now()),
        )
        change_id = cursor.lastrowid
        summary["changes"] += 1

        if redis_conn is not None:
            try:
                redis_conn.publish(
                    _CHANNEL,
                    json.dumps(
                        {
                            "change_id": change_id,
                            "cvr": cvr,
                            "domain": primary_domain,
                            "change_type": change_type,
                        }
                    ),
                )
            except Exception as exc:  # Redis publish is best-effort
                logger.bind(context={"error": str(exc)}).warning(
                    "ct_change_publish_failed"
                )

    db_conn.execute(
        "UPDATE clients SET ct_last_polled_at = ? WHERE cvr = ?",
        (_now(), cvr),
    )
    db_conn.commit()

    logger.bind(
        context={"cvr": cvr, "domain": primary_domain, **summary}
    ).info("ct_poll_complete")
    return summary
