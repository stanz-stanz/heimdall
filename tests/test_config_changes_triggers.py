"""Stage A.5 spec §6.2 — config_changes trigger coverage.

12 triggers (6 tier-1 tables × {UPDATE, DELETE}) × 2 cases (wrapper-
bound + bypass) = 24 parametrised cases. Plus four named tests for
specific contracts:

- ``test_clients_update_noise_skipped`` — WHEN-predicate filters out a
  pure ``updated_at`` bump (no audit-relevant column changed).
- ``test_consent_records_update_preserves_pii_in_old_json`` — Valdí
  ruling 2026-04-25: anonymise UPDATE on consent_records lands the
  authorised_by_* / consent_document fields in old_json verbatim, so
  the trigger snapshot doubles as §263 / GDPR Art 17(3)(e) evidence.
- ``test_signup_tokens_redemption_audit`` — UPDATE consumed_at lands a
  row with the token id as target_pk and intent set by the wrapper.
- ``test_retention_jobs_force_run_via_wrapper_writes_audit`` — wraps
  the real ``force_run_retention_job`` helper and verifies the
  end-to-end stamp (intent, operator_id, request_id) on the row.

The forensic contract: every wrapper-bound case carries actor /
intent / request_id; every bypass case lands NULL on those columns
so a post-incident grep can identify writes that skipped the wrapper.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.db.audit_context import bind_audit_context
from src.db.connection import init_db
from src.db.retention import force_run_retention_job, schedule_retention_job


_NOW = "2026-04-24T00:00:00Z"


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ----------------------------------------------------------------------
# Per-table seed helpers — each returns the target_pk the trigger will
# stamp into config_changes (CVR for cvr-keyed tables; numeric id for
# client_domains and retention_jobs).
# ----------------------------------------------------------------------


def _seed_client(conn, cvr: str = "12345678") -> str:
    conn.execute(
        "INSERT INTO clients (cvr, company_name, status, plan, "
        "created_at, updated_at) "
        "VALUES (?, 'Test ApS', 'prospect', 'watchman', ?, ?)",
        (cvr, _NOW, _NOW),
    )
    conn.commit()
    return cvr


def _seed_subscription(conn, cvr: str = "12345678") -> str:
    _seed_client(conn, cvr)
    conn.execute(
        "INSERT INTO subscriptions (cvr, plan, status, started_at, "
        "amount_dkk, billing_period, created_at, updated_at) "
        "VALUES (?, 'sentinel', 'active', ?, 39900, 'monthly', ?, ?)",
        (cvr, _NOW, _NOW, _NOW),
    )
    conn.commit()
    return cvr


def _seed_consent(conn, cvr: str = "12345678") -> str:
    _seed_client(conn, cvr)
    conn.execute(
        "INSERT INTO consent_records "
        "(cvr, authorised_domains, consent_type, consent_date, "
        " consent_expiry, consent_document, authorised_by_name, "
        " authorised_by_role, authorised_by_email, status, notes, "
        " created_at, updated_at) "
        "VALUES (?, '[\"example.dk\"]', 'written', '2026-04-01', "
        "'2027-04-01', 'consent/sentinel.pdf', 'Peter Nielsen', "
        "'Owner', 'peter@example.dk', 'active', 'signed via MitID', "
        "?, ?)",
        (cvr, _NOW, _NOW),
    )
    conn.commit()
    return cvr


def _seed_signup_token(
    conn, cvr: str = "12345678", token: str = "tok-trg-1"
) -> str:
    _seed_client(conn, cvr)
    conn.execute(
        "INSERT INTO signup_tokens (token, cvr, email, source, "
        "expires_at, created_at) "
        "VALUES (?, ?, 'p@example.dk', 'email_reply', "
        "'2099-01-01T00:00:00Z', ?)",
        (token, cvr, _NOW),
    )
    conn.commit()
    return token


def _seed_client_domain(conn, cvr: str = "12345678") -> str:
    _seed_client(conn, cvr)
    cur = conn.execute(
        "INSERT INTO client_domains (cvr, domain, is_primary, added_at) "
        "VALUES (?, 'example.dk', 1, ?)",
        (cvr, _NOW),
    )
    conn.commit()
    return str(cur.lastrowid)


def _seed_retention_job(conn, cvr: str = "12345678") -> str:
    _seed_client(conn, cvr)
    cur = conn.execute(
        "INSERT INTO retention_jobs (cvr, action, scheduled_for, status, "
        "created_at) VALUES (?, 'purge', ?, 'pending', ?)",
        (cvr, _NOW, _NOW),
    )
    conn.commit()
    return str(cur.lastrowid)


# ----------------------------------------------------------------------
# Mutation helpers — each performs one trigger-firing UPDATE / DELETE
# on the seeded row and commits.
# ----------------------------------------------------------------------


def _mutate_clients_update(conn, target_pk):
    conn.execute(
        "UPDATE clients SET status = 'active' WHERE cvr = ?", (target_pk,)
    )
    conn.commit()


def _mutate_clients_delete(conn, target_pk):
    conn.execute("DELETE FROM clients WHERE cvr = ?", (target_pk,))
    conn.commit()


def _mutate_subscriptions_update(conn, target_pk):
    conn.execute(
        "UPDATE subscriptions SET status = 'cancelled' WHERE cvr = ?",
        (target_pk,),
    )
    conn.commit()


def _mutate_subscriptions_delete(conn, target_pk):
    conn.execute("DELETE FROM subscriptions WHERE cvr = ?", (target_pk,))
    conn.commit()


def _mutate_consent_update(conn, target_pk):
    conn.execute(
        "UPDATE consent_records SET status = 'revoked' WHERE cvr = ?",
        (target_pk,),
    )
    conn.commit()


def _mutate_consent_delete(conn, target_pk):
    conn.execute("DELETE FROM consent_records WHERE cvr = ?", (target_pk,))
    conn.commit()


def _mutate_signup_token_update(conn, target_pk):
    conn.execute(
        "UPDATE signup_tokens SET consumed_at = ? WHERE token = ?",
        (_NOW, target_pk),
    )
    conn.commit()


def _mutate_signup_token_delete(conn, target_pk):
    conn.execute("DELETE FROM signup_tokens WHERE token = ?", (target_pk,))
    conn.commit()


def _mutate_client_domain_update(conn, target_pk):
    conn.execute(
        "UPDATE client_domains SET is_primary = 0 WHERE id = ?",
        (int(target_pk),),
    )
    conn.commit()


def _mutate_client_domain_delete(conn, target_pk):
    conn.execute(
        "DELETE FROM client_domains WHERE id = ?", (int(target_pk),)
    )
    conn.commit()


def _mutate_retention_job_update(conn, target_pk):
    conn.execute(
        "UPDATE retention_jobs SET status = 'cancelled' WHERE id = ?",
        (int(target_pk),),
    )
    conn.commit()


def _mutate_retention_job_delete(conn, target_pk):
    conn.execute(
        "DELETE FROM retention_jobs WHERE id = ?", (int(target_pk),)
    )
    conn.commit()


# ----------------------------------------------------------------------
# 12-trigger × 2-case parametrised matrix = 24 cases.
# Each row: (label, table_name, op, seed_fn, mutate_fn).
# ----------------------------------------------------------------------


_TRIGGER_CASES: list[tuple[str, str, str, Any, Any]] = [
    ("clients_update", "clients", "UPDATE",
     _seed_client, _mutate_clients_update),
    ("clients_delete", "clients", "DELETE",
     _seed_client, _mutate_clients_delete),
    ("subscriptions_update", "subscriptions", "UPDATE",
     _seed_subscription, _mutate_subscriptions_update),
    ("subscriptions_delete", "subscriptions", "DELETE",
     _seed_subscription, _mutate_subscriptions_delete),
    ("consent_records_update", "consent_records", "UPDATE",
     _seed_consent, _mutate_consent_update),
    ("consent_records_delete", "consent_records", "DELETE",
     _seed_consent, _mutate_consent_delete),
    ("signup_tokens_update", "signup_tokens", "UPDATE",
     _seed_signup_token, _mutate_signup_token_update),
    ("signup_tokens_delete", "signup_tokens", "DELETE",
     _seed_signup_token, _mutate_signup_token_delete),
    ("client_domains_update", "client_domains", "UPDATE",
     _seed_client_domain, _mutate_client_domain_update),
    ("client_domains_delete", "client_domains", "DELETE",
     _seed_client_domain, _mutate_client_domain_delete),
    ("retention_jobs_update", "retention_jobs", "UPDATE",
     _seed_retention_job, _mutate_retention_job_update),
    ("retention_jobs_delete", "retention_jobs", "DELETE",
     _seed_retention_job, _mutate_retention_job_delete),
]


@pytest.mark.parametrize(
    "label,table_name,op,seed_fn,mutate_fn",
    _TRIGGER_CASES,
    ids=[c[0] for c in _TRIGGER_CASES],
)
def test_trigger_fires_with_wrapper_stamp(
    db, label, table_name, op, seed_fn, mutate_fn
):
    """Every tier-1 UPDATE / DELETE under ``bind_audit_context`` lands
    a row in ``config_changes`` stamped with the bound context."""
    target_pk = seed_fn(db)
    intent = f"test.{label}"

    with bind_audit_context(
        db,
        intent=intent,
        operator_id=42,
        session_id=7,
        request_id="r-trg-1",
    ):
        mutate_fn(db, target_pk)

    rows = db.execute(
        "SELECT table_name, op, target_pk, intent, operator_id, "
        "session_id, request_id, actor_kind, old_json, new_json "
        "FROM config_changes ORDER BY id"
    ).fetchall()
    assert len(rows) == 1, (
        f"{label}: expected exactly one trigger row, got {len(rows)}"
    )
    row = rows[0]
    assert row["table_name"] == table_name
    assert row["op"] == op
    assert row["target_pk"] == target_pk
    assert row["intent"] == intent
    assert row["operator_id"] == 42
    assert row["session_id"] == 7
    assert row["request_id"] == "r-trg-1"
    assert row["actor_kind"] == "operator"
    assert row["old_json"] is not None
    if op == "UPDATE":
        assert row["new_json"] is not None
    else:
        assert row["new_json"] is None


@pytest.mark.parametrize(
    "label,table_name,op,seed_fn,mutate_fn",
    _TRIGGER_CASES,
    ids=[f"{c[0]}_bypass" for c in _TRIGGER_CASES],
)
def test_trigger_fires_on_bypass_with_null_actor(
    db, label, table_name, op, seed_fn, mutate_fn
):
    """A wrapper-bypass UPDATE / DELETE still fires the trigger; actor
    columns land NULL — forensically detectable at audit-review time
    (Stage A.5 spec §4.1.10 contract)."""
    target_pk = seed_fn(db)

    # No bind_audit_context — bypass path.
    mutate_fn(db, target_pk)

    rows = db.execute(
        "SELECT table_name, op, target_pk, intent, operator_id, "
        "session_id, request_id, actor_kind FROM config_changes "
        "ORDER BY id"
    ).fetchall()
    assert len(rows) == 1, (
        f"{label}: trigger must fire even on wrapper bypass"
    )
    row = rows[0]
    assert row["table_name"] == table_name
    assert row["op"] == op
    assert row["target_pk"] == target_pk
    assert row["intent"] is None
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["request_id"] is None
    # COALESCE in the trigger defaults actor_kind to 'operator' when
    # the UDF returns NULL — surfacing the bypass via NULL on the
    # actor-id columns rather than via an absent row.
    assert row["actor_kind"] == "operator"


# ----------------------------------------------------------------------
# Named contract tests
# ----------------------------------------------------------------------


def test_clients_update_noise_skipped(db):
    """The WHEN predicate on ``trg_clients_audit_update`` filters out a
    pure ``updated_at`` bump — no audit-relevant column changed, so no
    row in config_changes."""
    cvr = _seed_client(db)

    with bind_audit_context(
        db, intent="test.noise", operator_id=1, request_id="r-noise"
    ):
        # Touch only updated_at — the WHEN predicate's column list does
        # not include it, so the trigger body must not run.
        db.execute(
            "UPDATE clients SET updated_at = ? WHERE cvr = ?",
            ("2026-04-25T00:00:00Z", cvr),
        )
        db.commit()

    count = db.execute("SELECT COUNT(*) FROM config_changes").fetchone()[0]
    assert count == 0


def test_consent_records_update_preserves_pii_in_old_json(db):
    """Valdí ruling 2026-04-25 + Stage A.5 spec §4.1.7. The trigger on
    ``consent_records`` snapshots ``authorised_by_name``,
    ``authorised_by_email``, and ``consent_document`` into ``old_json``.
    These columns are §263 / GDPR Art 17(3)(e) evidence and must
    survive the anonymise UPDATE that flips ``status`` to 'revoked'."""
    cvr = _seed_consent(db)

    with bind_audit_context(
        db,
        intent="retention.anonymise",
        actor_kind="system",
    ):
        # Mirror anonymise_client's UPDATE: scrub notes, flip status,
        # leave authorised_by_* / consent_document intact.
        db.execute(
            "UPDATE consent_records "
            "   SET notes = NULL, status = 'revoked', updated_at = ? "
            " WHERE cvr = ?",
            (_NOW, cvr),
        )
        db.commit()

    row = db.execute(
        "SELECT old_json, new_json, intent, actor_kind "
        "FROM config_changes"
    ).fetchone()
    assert row is not None
    assert row["intent"] == "retention.anonymise"
    assert row["actor_kind"] == "system"
    # §263 evidence preserved verbatim in the snapshot.
    assert "Peter Nielsen" in row["old_json"]
    assert "peter@example.dk" in row["old_json"]
    assert "consent/sentinel.pdf" in row["old_json"]
    # The post-revoke snapshot also carries the PII because anonymise
    # only scrubs notes + flips status.
    assert "Peter Nielsen" in row["new_json"]
    assert "peter@example.dk" in row["new_json"]


def test_signup_tokens_redemption_audit(db):
    """UPDATE signup_tokens.consumed_at lands a row keyed by the token
    string (not the rowid). intent stamped from the wrapper."""
    cvr = "23456789"
    token = _seed_signup_token(db, cvr=cvr, token="tok-redeem-1")

    with bind_audit_context(
        db, intent="trial.activated", actor_kind="system"
    ):
        db.execute(
            "UPDATE signup_tokens SET consumed_at = ? WHERE token = ?",
            (_NOW, token),
        )
        db.commit()

    row = db.execute(
        "SELECT table_name, target_pk, intent, actor_kind, op "
        "FROM config_changes"
    ).fetchone()
    assert row["table_name"] == "signup_tokens"
    assert row["target_pk"] == token
    assert row["intent"] == "trial.activated"
    assert row["actor_kind"] == "system"
    assert row["op"] == "UPDATE"


def test_retention_jobs_force_run_via_wrapper_writes_audit(db):
    """End-to-end: wrap the real ``force_run_retention_job`` helper
    under ``bind_audit_context`` and verify the config_changes row
    carries the wrapper's intent + operator_id + request_id.

    Spec §6.2 names this case explicitly because it is the canonical
    operator-driven path through the runner-claim-lock contract."""
    _seed_client(db, cvr="34567890")
    job = schedule_retention_job(
        db, "34567890", "purge", _NOW, notes="initial"
    )
    job_id = job["id"]

    with bind_audit_context(
        db,
        intent="retention.force_run",
        operator_id=11,
        session_id=22,
        request_id="r-force-run-1",
    ):
        force_run_retention_job(db, job_id, operator="console")

    row = db.execute(
        "SELECT table_name, op, target_pk, intent, operator_id, "
        "session_id, request_id, actor_kind FROM config_changes"
    ).fetchone()
    assert row["table_name"] == "retention_jobs"
    assert row["op"] == "UPDATE"
    assert row["target_pk"] == str(job_id)
    assert row["intent"] == "retention.force_run"
    assert row["operator_id"] == 11
    assert row["session_id"] == 22
    assert row["request_id"] == "r-force-run-1"
    assert row["actor_kind"] == "operator"
