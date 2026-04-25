"""Retention action handlers — anonymise, purge, purge_bookkeeping.

These handlers mutate the DB and (for purge) the filesystem. The caller
(:mod:`src.retention.runner`) wraps each invocation in its own claim
transaction; the functions in this module do NOT call ``BEGIN`` /
``COMMIT`` themselves — they emit the individual ``UPDATE`` / ``DELETE``
statements and trust the runner to commit after ``authorisation_revoked``
is written for Sentinel.

Column-level semantics follow the 2026-04-24 client-memory review
(``docs/architecture/retention-cron-client-memory-review.md``) and the
revised Watchman-zero-retention memo
(``/Users/fsaf/.claude/projects/.../memory/project_retention_cron_decisions.md``).

Summary:

- ``anonymise_client`` is **Sentinel only** (Watchman has no anonymise
  stage). Nulls PII across clients / consent_records / delivery_log /
  delivery_retry / conversion_events / onboarding_stage_log, scrubs
  SANs on cert tables, nulls scraped scan/brief JSON, deletes signup
  tokens, leaves subscriptions + payment_events untouched.
  ``clients.consent_granted`` is NOT flipped here — that happens at
  ``offboarding_triggered`` time in the offboarding handler.
- ``purge_client`` is the hard-delete cascade. For Watchman this is the
  ONLY action (runs at trial expiry, deletes every row attached to the
  CVR including the clients row — no tombstone). Tables wiped:
  finding_status_log, finding_occurrences, scan_history, brief_snapshots,
  client_cert_changes, client_cert_snapshots, consent_records,
  conversion_events, onboarding_stage_log, delivery_retry, delivery_log,
  signup_tokens, client_domains, prospects, clients. For Sentinel,
  called if a plan routing change ever reaches purge after anonymise;
  skips the bookkeeping tables so Bogføringsloven evidence survives.
- ``purge_bookkeeping`` is Sentinel-only, runs at +5 years. Deletes
  ``subscriptions`` + ``payment_events`` for the CVR. No-ops cleanly
  if the clients row is already gone from an earlier purge.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from loguru import logger

from src.db.connection import _now


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _client_data_dir() -> Path:
    """Resolve the on-disk client data dir from env.

    Matches the convention used by the worker and API containers
    (``CLIENT_DATA_DIR`` → ``/data/clients`` in prod, ``data/clients``
    in dev). Tests override via monkeypatch.setenv.
    """
    return Path(os.environ.get("CLIENT_DATA_DIR", "data/clients"))


def _delete_client_filesystem(cvr: str) -> list[str]:
    """Delete the per-client directory (authorisation.json + signed PDFs).

    Layout (from ``src/consent/validator.py``):

        <CLIENT_DATA_DIR>/<cvr>/authorisation.json
        <CLIENT_DATA_DIR>/<cvr>/<signed-consent-pdf>.pdf
        ...

    Deletes the entire ``<cvr>`` subtree. Missing directory is fine (no
    authorisation was ever written; log at debug).

    Path-traversal hardening (Codex P1, 2026-04-24 + 2026-04-24 follow-up):
    CVR is a free-text key in this codebase (``DRYRUN-*`` prefixes already
    exist; operator-manual signups can write arbitrary strings). The guard
    handles two distinct failure modes:

    1. ``candidate == base`` — a malformed CVR like ``""`` or ``"."``
       resolves to ``CLIENT_DATA_DIR`` itself. ``shutil.rmtree(base)``
       would wipe every client's data. ``Path.is_relative_to`` is
       reflexive (returns True for equal paths), so the escape check
       below is NOT sufficient on its own. Logged as
       ``retention_fs_base_dir_rejected``.
    2. ``candidate`` resolves outside ``base`` — e.g. CVR contains
       ``..`` separators. ``shutil.rmtree`` would delete an unrelated
       subtree (a sibling client's ``authorisation.json``, which is
       §263 evidence). Logged as ``retention_fs_path_escape_rejected``.

    Both checks run BEFORE the missing-directory shortcut so that a
    malicious target which happens not to exist is still observable
    in logs. Distinct event names so post-incident greps tell the two
    failure modes apart.

    Returns:
        List of artifacts removed, for audit logging. Empty if nothing
        existed OR if the candidate path was rejected (base-dir target
        or escape). Both rejections are non-fatal — the runner has
        already recorded the DB-side cascade success; the filesystem
        step is best-effort.
    """
    base = _client_data_dir().resolve()
    candidate = (base / cvr).resolve()
    if candidate == base:
        logger.bind(
            context={
                "cvr": cvr,
                "attempted": str(candidate),
                "base": str(base),
            }
        ).warning("retention_fs_base_dir_rejected")
        return []
    if not candidate.is_relative_to(base):
        logger.bind(
            context={
                "cvr": cvr,
                "attempted": str(candidate),
                "base": str(base),
            }
        ).warning("retention_fs_path_escape_rejected")
        return []

    if not candidate.exists():
        return []

    # Enumerate before deletion so we can log what we removed.
    removed: list[str] = []
    for p in candidate.rglob("*"):
        if p.is_file():
            removed.append(str(p.relative_to(candidate)))

    try:
        shutil.rmtree(candidate)
    except OSError as exc:
        logger.bind(cvr=cvr, path=str(candidate)).warning(
            "retention_fs_delete_failed: {}", exc
        )
        raise
    return removed


# ---------------------------------------------------------------------------
# Action: anonymise (Sentinel only)
# ---------------------------------------------------------------------------


def anonymise_client(
    conn: sqlite3.Connection,
    job_row: dict,
) -> dict:
    """Sentinel 30-day anonymise. Nulls PII, preserves bookkeeping.

    Watchman NEVER calls this — the Watchman purge is hard-delete at
    trial-expiry anchor. The runner dispatches Watchman ``purge`` jobs
    to :func:`purge_client`; anonymise is Sentinel-only.

    Columns touched (per client-memory review, 2026-04-24):

    - ``clients``: null PII (telegram_chat_id, contact_*, developer_contact,
      next_scan_date, notes), bump ``data_retention_mode = 'anonymised'``,
      set ``onboarding_stage = NULL``. Does NOT flip ``consent_granted``
      — that happened already at ``offboarding_triggered`` time.
    - ``consent_records``: scrub only ``notes`` (free-text, non-evidentiary);
      flip ``status`` to ``'revoked'`` unless already terminal. Structured
      PII (``authorised_by_name``, ``authorised_by_email``,
      ``consent_document``, dates) is preserved as §263 evidence per
      GDPR Art 17(3)(e) — deleted at +5y purge_bookkeeping.
      (Valdí ruling 2026-04-25; Wernblad confirmation pending on
      5y vs 10y window depending on §263 stk. 3.)
    - ``delivery_log``: null ``message_preview`` / ``external_id`` /
      ``error_message``; timing preserved for funnel analytics.
    - ``delivery_retry``: null ``last_error`` for rows that hang off
      this client's delivery_log ids.
    - ``conversion_events``: null ``payload_json`` (may quote client
      replies).
    - ``onboarding_stage_log``: null ``note``.
    - ``scan_history``: null ``result_json`` (conservative Q3 reading —
      may contain scraped emails / meta author tags).
    - ``brief_snapshots``: null ``brief_json`` (same Q3 reasoning).
    - ``prospects``: scrub ``brief_json`` (→ '{}'), ``interpreted_json``
      (→ NULL), ``error_message`` (→ NULL). Same Q3 reasoning as
      ``scan_history`` / ``brief_snapshots`` — scraped PII (meta author
      tags, contact-page emails, LLM-quoted strings). Operational keys
      (cvr, domain, company_name, campaign, bucket, industry_code,
      industry_name) are preserved.
    - ``client_cert_snapshots`` / ``client_cert_changes``: null the
      JSON fields that may leak customer subdomains (SANs can contain
      ``kunde-navn.domain.dk``). Preserve cert_sha256 / issuer_name /
      timestamps as §263 evidence.
    - ``signup_tokens``: DELETE outright (ephemeral, 30-min TTL, nothing
      to anonymise).

    Explicitly NOT touched: ``subscriptions``, ``payment_events`` —
    Bogføringsloven 5-year invoice retention.

    Args:
        conn: Database connection. Caller is responsible for transaction
            boundaries (this function does not commit; the runner commits
            after writing ``authorisation_revoked`` to conversion_events).
        job_row: The retention_jobs row being processed. ``job_row['cvr']``
            identifies the target.

    Returns:
        Dict with per-table row counts, for audit logging / notes field.
    """
    cvr = job_row["cvr"]
    now = _now()
    bound = logger.bind(cvr=cvr, job_id=job_row["id"], action="anonymise")
    bound.info("retention_anonymise_start")

    counts: dict[str, int] = {}

    # 1) clients — PII nulled, data_retention_mode flipped.
    cur = conn.execute(
        """
        UPDATE clients
           SET telegram_chat_id = NULL,
               contact_name     = NULL,
               contact_email    = NULL,
               contact_phone    = NULL,
               contact_role     = NULL,
               developer_contact = NULL,
               next_scan_date   = NULL,
               notes            = NULL,
               onboarding_stage = NULL,
               data_retention_mode = 'anonymised',
               updated_at       = ?
         WHERE cvr = ?
        """,
        (now, cvr),
    )
    counts["clients"] = cur.rowcount or 0

    # 2) consent_records — Option 3 (Valdí ruling 2026-04-25): scrub
    #    only the free-text ``notes`` column and flip ``status`` to
    #    'revoked' unless already terminal. Structured PII
    #    (authorised_by_name, authorised_by_email, consent_document,
    #    dates, authorised_domains, authorised_by_role) is PRESERVED as
    #    §263 evidence per GDPR Art 17(3)(e). The +5y purge_bookkeeping
    #    handler is responsible for the eventual hard-delete.
    #    Wernblad confirmation pending on 5y vs 10y window depending on
    #    §263 stk. 3 — affects purge_bookkeeping schedule timing only.
    cur = conn.execute(
        """
        UPDATE consent_records
           SET notes      = NULL,
               status     = CASE
                   WHEN status IN ('suspended', 'expired', 'revoked') THEN status
                   ELSE 'revoked'
               END,
               updated_at = ?
         WHERE cvr = ?
        """,
        (now, cvr),
    )
    counts["consent_records"] = cur.rowcount or 0

    # 3) delivery_log — scrub content, keep timing.
    cur = conn.execute(
        """
        UPDATE delivery_log
           SET message_preview = NULL,
               external_id     = NULL,
               error_message   = NULL
         WHERE cvr = ?
        """,
        (cvr,),
    )
    counts["delivery_log"] = cur.rowcount or 0

    # 4) delivery_retry — null last_error on rows linked to this client's
    #    delivery_log. delivery_retry has no cvr column; join via the FK.
    cur = conn.execute(
        """
        UPDATE delivery_retry
           SET last_error = NULL
         WHERE delivery_log_id IN (
             SELECT id FROM delivery_log WHERE cvr = ?
         )
        """,
        (cvr,),
    )
    counts["delivery_retry"] = cur.rowcount or 0

    # 5) conversion_events — payload may quote replies.
    cur = conn.execute(
        "UPDATE conversion_events SET payload_json = NULL WHERE cvr = ?",
        (cvr,),
    )
    counts["conversion_events"] = cur.rowcount or 0

    # 6) onboarding_stage_log — note may be free-form.
    cur = conn.execute(
        "UPDATE onboarding_stage_log SET note = NULL WHERE cvr = ?",
        (cvr,),
    )
    counts["onboarding_stage_log"] = cur.rowcount or 0

    # 7) scan_history — scraped content (Q3 null-at-anonymise).
    cur = conn.execute(
        "UPDATE scan_history SET result_json = NULL WHERE cvr = ?",
        (cvr,),
    )
    counts["scan_history"] = cur.rowcount or 0

    # 8) brief_snapshots — scraped content (Q3 null-at-anonymise).
    cur = conn.execute(
        "UPDATE brief_snapshots SET brief_json = NULL WHERE cvr = ?",
        (cvr,),
    )
    counts["brief_snapshots"] = cur.rowcount or 0

    # 9) prospects — scraped content (Valdí-extended Q3, 2026-04-25).
    #    Outreach-origin row may carry meta author tags / contact-page
    #    emails in ``brief_json`` and LLM-quoted strings in
    #    ``interpreted_json`` / ``error_message``. ``brief_json`` is
    #    NOT NULL in the schema → write '{}' (mirrors the cert-tables
    #    precedent above). Operational keys (cvr/domain/company_name/
    #    campaign/bucket/industry_*) are preserved.
    cur = conn.execute(
        """
        UPDATE prospects
           SET brief_json       = '{}',
               interpreted_json = NULL,
               error_message    = NULL
         WHERE cvr = ?
        """,
        (cvr,),
    )
    counts["prospects"] = cur.rowcount or 0

    # 10) client_cert_snapshots — scrub SANs, preserve cert structure.
    #    dns_names_json defaults to '[]' NOT NULL in the schema, so we
    #    write '[]' rather than NULL to preserve the invariant.
    cur = conn.execute(
        """
        UPDATE client_cert_snapshots
           SET dns_names_json = '[]'
         WHERE cvr = ?
        """,
        (cvr,),
    )
    counts["client_cert_snapshots"] = cur.rowcount or 0

    # 11) client_cert_changes — details_json is NOT NULL. Replace with an
    #     empty object (structure preserved, contents scrubbed).
    cur = conn.execute(
        """
        UPDATE client_cert_changes
           SET details_json = '{}'
         WHERE cvr = ?
        """,
        (cvr,),
    )
    counts["client_cert_changes"] = cur.rowcount or 0

    # 12) signup_tokens — delete outright (ephemeral).
    cur = conn.execute("DELETE FROM signup_tokens WHERE cvr = ?", (cvr,))
    counts["signup_tokens"] = cur.rowcount or 0

    bound.bind(counts=counts).info("retention_anonymise_done")
    return counts


# ---------------------------------------------------------------------------
# Action: purge (Watchman hard-delete / Sentinel post-anonymise)
# ---------------------------------------------------------------------------


def purge_client(
    conn: sqlite3.Connection,
    job_row: dict,
) -> dict:
    """Hard-delete cascade for a client CVR.

    Delete order matters because the schema uses soft FKs (no enforced
    REFERENCES). Children first, parents last.

    Watchman: this is the only action, run at trial-expiry anchor —
    the ``clients`` row is deleted outright along with everything else.
    Only the ``retention_jobs`` audit row itself survives (it has not
    been claimed by this same job-id at the time of DELETE, so the
    ``id != :current_job_id`` guard preserves it).

    Sentinel: if the plan routes a purge here (e.g. operator manually
    schedules one) it still preserves ``subscriptions`` +
    ``payment_events`` rows for the CVR (Bogføringsloven). The sibling
    ``retention_jobs`` sweep at the end of the cascade also explicitly
    preserves any pending ``purge_bookkeeping`` job for the CVR — that
    is the future cleanup tick scheduled at the +5y bookkeeping
    horizon, and dropping it here would leave subscriptions /
    payment_events orphaned indefinitely.

    Filesystem step: delete ``<CLIENT_DATA_DIR>/<cvr>/`` entirely —
    ``authorisation.json`` + any signed consent PDFs.

    Args:
        conn: Database connection. Caller holds the claim transaction.
        job_row: Current retention_jobs row; ``job_row['id']`` is
            preserved through the cascade.

    Returns:
        Dict with per-table deletion counts + ``'filesystem'`` key
        listing the relative paths removed.
    """
    cvr = job_row["cvr"]
    current_job_id = job_row["id"]
    bound = logger.bind(cvr=cvr, job_id=current_job_id, action="purge")
    bound.info("retention_purge_start")

    counts: dict[str, object] = {}

    # --- Scan + finding side ---

    # finding_status_log joins via occurrence_id (no cvr column), so we
    # must delete log rows BEFORE their parent occurrences to avoid
    # leaving orphans. Use a subquery-IN.
    cur = conn.execute(
        """
        DELETE FROM finding_status_log
         WHERE occurrence_id IN (
             SELECT id FROM finding_occurrences WHERE cvr = ?
         )
        """,
        (cvr,),
    )
    counts["finding_status_log"] = cur.rowcount or 0

    cur = conn.execute(
        "DELETE FROM finding_occurrences WHERE cvr = ?", (cvr,)
    )
    counts["finding_occurrences"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM scan_history WHERE cvr = ?", (cvr,))
    counts["scan_history"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM brief_snapshots WHERE cvr = ?", (cvr,))
    counts["brief_snapshots"] = cur.rowcount or 0

    # --- CT monitoring ---

    cur = conn.execute(
        "DELETE FROM client_cert_changes WHERE cvr = ?", (cvr,)
    )
    counts["client_cert_changes"] = cur.rowcount or 0

    cur = conn.execute(
        "DELETE FROM client_cert_snapshots WHERE cvr = ?", (cvr,)
    )
    counts["client_cert_snapshots"] = cur.rowcount or 0

    # --- Consent audit ---

    cur = conn.execute("DELETE FROM consent_records WHERE cvr = ?", (cvr,))
    counts["consent_records"] = cur.rowcount or 0

    # --- Funnel / onboarding ---

    cur = conn.execute("DELETE FROM conversion_events WHERE cvr = ?", (cvr,))
    counts["conversion_events"] = cur.rowcount or 0

    cur = conn.execute(
        "DELETE FROM onboarding_stage_log WHERE cvr = ?", (cvr,)
    )
    counts["onboarding_stage_log"] = cur.rowcount or 0

    # --- Delivery + retry ---

    # delivery_retry hangs off delivery_log.id — kill children first.
    cur = conn.execute(
        """
        DELETE FROM delivery_retry
         WHERE delivery_log_id IN (
             SELECT id FROM delivery_log WHERE cvr = ?
         )
        """,
        (cvr,),
    )
    counts["delivery_retry"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM delivery_log WHERE cvr = ?", (cvr,))
    counts["delivery_log"] = cur.rowcount or 0

    # --- Magic-link tokens + domains ---

    cur = conn.execute("DELETE FROM signup_tokens WHERE cvr = ?", (cvr,))
    counts["signup_tokens"] = cur.rowcount or 0

    cur = conn.execute("DELETE FROM client_domains WHERE cvr = ?", (cvr,))
    counts["client_domains"] = cur.rowcount or 0

    # --- Prospects (outreach origin) ---

    # Most clients originate from an outreach campaign and carry a
    # ``prospects`` row keyed by the same CVR. ``prospects.brief_json``
    # is scraped PII (meta author tags, contact-page emails) and
    # ``delivery_id`` references ``delivery_log(id)`` which we just
    # wiped above — leaving prospects behind would both violate the
    # Watchman zero-retention rule and orphan the FK reference. Delete
    # before the clients row so the cascade matches the rest of the
    # ordering (children → parent).
    cur = conn.execute("DELETE FROM prospects WHERE cvr = ?", (cvr,))
    counts["prospects"] = cur.rowcount or 0

    # --- Clients row ---

    # Watchman hard-delete: no tombstone, no '[purged]' stub — the row
    # is gone. Sentinel preserves subscriptions + payment_events but
    # still loses the clients row at this stage (the 5-year
    # purge_bookkeeping handles the tables that reference CVR
    # explicitly; they don't FK-cascade).
    cur = conn.execute("DELETE FROM clients WHERE cvr = ?", (cvr,))
    counts["clients"] = cur.rowcount or 0

    # --- Sibling retention_jobs rows (keep only the one we're executing) ---

    # Preserve any future ``purge_bookkeeping`` row for this CVR.
    # Sentinel edge case: an operator-triggered early purge MUST NOT
    # cancel the +5y bookkeeping cleanup tick, otherwise subscriptions /
    # payment_events (preserved above for Bogføringsloven) would never
    # be cleaned up at the legal horizon.
    cur = conn.execute(
        """
        DELETE FROM retention_jobs
         WHERE cvr = ? AND id != ? AND action != 'purge_bookkeeping'
        """,
        (cvr, current_job_id),
    )
    counts["retention_jobs"] = cur.rowcount or 0

    # --- Filesystem ---

    try:
        fs_removed = _delete_client_filesystem(cvr)
    except OSError:
        # Filesystem failure should not roll the DB cascade — log and
        # carry on. The runner will see non-zero row counts and mark
        # the job completed. Operator console shows the warning.
        fs_removed = []
    counts["filesystem"] = fs_removed

    bound.bind(counts=counts).info("retention_purge_done")
    return counts


# ---------------------------------------------------------------------------
# Action: purge_bookkeeping (Sentinel +5y)
# ---------------------------------------------------------------------------


def purge_bookkeeping(
    conn: sqlite3.Connection,
    job_row: dict,
) -> dict:
    """Delete Bogføringsloven-protected tables for a Sentinel CVR at +5y.

    At this point the ``clients`` row is expected to have already been
    removed by an earlier purge — but we do not require it. If it is
    still present (e.g. operator manually ran this out of sequence),
    the DELETEs on subscriptions / payment_events still succeed; the
    clients row is NOT touched here.

    Args:
        conn: Database connection. Caller holds the claim transaction.
        job_row: Current retention_jobs row.

    Returns:
        Dict with per-table deletion counts. Zero counts are legitimate
        (the 5y window elapsed and the CVR had no paid activity — e.g.
        a Sentinel subscription that cancelled in its first period).
    """
    cvr = job_row["cvr"]
    bound = logger.bind(
        cvr=cvr, job_id=job_row["id"], action="purge_bookkeeping"
    )
    bound.info("retention_bookkeeping_purge_start")

    counts: dict[str, int] = {}

    # Order: payment_events reference subscriptions.id (soft FK); delete
    # payments first so a surviving subscription does not hold payload
    # references to rows that are about to disappear. The schema's
    # CHECK is nullable on payment_events.subscription_id so even
    # orphaned payments (ad-hoc) get deleted by the cvr filter.
    cur = conn.execute(
        "DELETE FROM payment_events WHERE cvr = ?", (cvr,)
    )
    counts["payment_events"] = cur.rowcount or 0

    cur = conn.execute(
        "DELETE FROM subscriptions WHERE cvr = ?", (cvr,)
    )
    counts["subscriptions"] = cur.rowcount or 0

    bound.bind(counts=counts).info("retention_bookkeeping_purge_done")
    return counts
