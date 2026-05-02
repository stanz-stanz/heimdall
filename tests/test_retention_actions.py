"""Tests for src.retention.actions — anonymise / purge / purge_bookkeeping.

Covers:
- Sentinel anonymise column correctness (PII nulled, bookkeeping preserved).
- Purge cascade completeness.
- Bogføringsloven preservation invariant: purge never touches
  subscriptions + payment_events.
- Watchman hard-delete leaves only the retention_jobs audit row.
- Sentinel purge_bookkeeping works even after the clients row is gone.
- Filesystem deletion at purge removes <cvr>/ subtree.

Consent-record handling — Option 3 (Valdí ruling 2026-04-25)
-------------------------------------------------------------

``anonymise_client`` does NOT null ``consent_records.authorised_by_name``
or ``authorised_by_email``. Those columns hold §263 evidence (GDPR Art
17(3)(e)) and are preserved verbatim until the +5y purge_bookkeeping
window. The only mutations the handler performs on consent_records are:

- Flip ``status`` to ``'revoked'`` unless already terminal
  (``'suspended'`` / ``'expired'`` / ``'revoked'`` stay as-is).
- Scrub the free-text ``notes`` column (NULL out).

This also sidesteps the schema's NOT NULL constraints on
``authorised_by_name`` and ``authorised_by_email``
(``client-db-schema.sql`` lines 153 + 155). The previous
implementation's IntegrityError class of bug is gone.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from loguru import logger

from src.db.clients import create_client
from src.db.connection import init_db
from src.retention.actions import (
    _delete_client_filesystem,
    anonymise_client,
    purge_bookkeeping,
    purge_client,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture()
def client_data_dir(tmp_path, monkeypatch):
    """Override CLIENT_DATA_DIR for filesystem-level tests."""
    d = tmp_path / "client-data"
    d.mkdir()
    monkeypatch.setenv("CLIENT_DATA_DIR", str(d))
    return d


@pytest.fixture()
def fake_job(tmp_path):
    """Minimal job_row stub used by action handlers."""
    def _build(cvr: str, action: str = "anonymise") -> dict:
        return {
            "id": 42,
            "cvr": cvr,
            "action": action,
            "scheduled_for": "2026-04-24T00:00:00Z",
            "status": "running",
            "claimed_at": "2026-04-24T00:00:00Z",
            "executed_at": None,
            "notes": None,
            "created_at": "2026-04-01T00:00:00Z",
        }

    return _build


def _seed_full_sentinel(db, cvr: str = "12345678") -> dict:
    """Create a Sentinel client with every attached table populated.

    This gives each test the same "full world" to wipe, making column-level
    assertions reliable.
    """
    client = create_client(
        db,
        cvr=cvr,
        company_name="Test Sentinel Co",
        plan="sentinel",
        status="active",
        telegram_chat_id="555",
        contact_name="Peter Nielsen",
        contact_email="peter@example.dk",
        contact_phone="+4511223344",
    )

    now = "2026-04-24T00:00:00Z"
    # domains
    db.execute(
        """
        INSERT INTO client_domains (cvr, domain, is_primary, added_at)
        VALUES (?, ?, 1, ?)
        """,
        (cvr, "example.dk", now),
    )
    # consent_records — one active row with PII
    db.execute(
        """
        INSERT INTO consent_records
            (cvr, authorised_domains, consent_type, consent_date,
             consent_expiry, consent_document, authorised_by_name,
             authorised_by_role, authorised_by_email, status, notes,
             created_at, updated_at)
        VALUES (?, '["example.dk"]', 'written', '2026-04-01', '2027-04-01',
                'consent/sentinel-12345678.pdf', 'Peter Nielsen', 'Owner',
                'peter@example.dk', 'active', 'signed via MitID', ?, ?)
        """,
        (cvr, now, now),
    )
    # delivery_log with preview + retry
    cursor = db.execute(
        """
        INSERT INTO delivery_log
            (cvr, domain, channel, message_type, message_hash,
             message_preview, external_id, error_message, status,
             sent_at, created_at)
        VALUES (?, 'example.dk', 'telegram', 'scan_report', 'abc123',
                'PII body preview', '999', 'transient error', 'sent',
                ?, ?)
        """,
        (cvr, now, now),
    )
    delivery_id = cursor.lastrowid
    db.execute(
        """
        INSERT INTO delivery_retry
            (delivery_log_id, domain, brief_path, attempt, next_retry_at,
             last_error, status, created_at)
        VALUES (?, 'example.dk', '/briefs/example.dk.json', 0, ?,
                'Claude 529', 'pending', ?)
        """,
        (delivery_id, now, now),
    )
    # conversion_events with payload
    db.execute(
        """
        INSERT INTO conversion_events
            (cvr, event_type, source, payload_json, occurred_at, created_at)
        VALUES (?, 'signup', 'email_click', '{"quote":"private note"}',
                ?, ?)
        """,
        (cvr, now, now),
    )
    # onboarding_stage_log with a note
    db.execute(
        """
        INSERT INTO onboarding_stage_log
            (cvr, from_stage, to_stage, source, note, created_at)
        VALUES (?, NULL, 'upgrade_interest', 'webhook', 'PII note', ?)
        """,
        (cvr, now),
    )
    # scan_history with result_json
    db.execute(
        """
        INSERT INTO scan_history
            (scan_id, cvr, domain, scan_date, status, result_json,
             created_at)
        VALUES ('scan-1', ?, 'example.dk', '2026-04-24', 'completed',
                '{"raw":"scraped meta data including emails"}', ?)
        """,
        (cvr, now),
    )
    # brief_snapshots with brief_json
    db.execute(
        """
        INSERT INTO brief_snapshots
            (domain, scan_date, cvr, brief_json, created_at)
        VALUES ('example.dk', '2026-04-24', ?,
                '{"finding":"PII possibly here"}', ?)
        """,
        (cvr, now),
    )
    # finding_definitions + finding_occurrences + status log
    db.execute(
        """
        INSERT INTO finding_definitions
            (finding_hash, severity, description, first_seen_at)
        VALUES ('hash123', 'high', 'Outdated WP', '2026-04-24')
        """,
    )
    cur_occ = db.execute(
        """
        INSERT INTO finding_occurrences
            (cvr, domain, finding_hash, status, first_seen_at, last_seen_at)
        VALUES (?, 'example.dk', 'hash123', 'open', '2026-04-24', '2026-04-24')
        """,
        (cvr,),
    )
    occurrence_id = cur_occ.lastrowid
    db.execute(
        """
        INSERT INTO finding_status_log
            (occurrence_id, from_status, to_status, source, created_at)
        VALUES (?, NULL, 'open', 'scan:scan-1', ?)
        """,
        (occurrence_id, now),
    )
    # client_cert_snapshots + changes (for SAN scrub)
    db.execute(
        """
        INSERT INTO client_cert_snapshots
            (cvr, domain, cert_sha256, common_name, issuer_name,
             dns_names_json, not_before, not_after, first_seen_at,
             last_seen_at)
        VALUES (?, 'example.dk', 'sha-abc', 'example.dk', 'Let''s Encrypt',
                '["example.dk", "customer-foo.example.dk"]',
                '2026-03-01T00:00:00Z', '2026-06-01T00:00:00Z', ?, ?)
        """,
        (cvr, now, now),
    )
    db.execute(
        """
        INSERT INTO client_cert_changes
            (cvr, domain, change_type, details_json, detected_at, status)
        VALUES (?, 'example.dk', 'new_cert',
                '{"dns_names":["customer-foo.example.dk"]}', ?, 'pending')
        """,
        (cvr, now),
    )
    # signup_tokens
    db.execute(
        """
        INSERT INTO signup_tokens
            (token, cvr, email, source, expires_at, created_at)
        VALUES ('tok-xyz', ?, 'peter@example.dk', 'email_reply',
                '2099-01-01T00:00:00Z', ?)
        """,
        (cvr, now),
    )
    # subscriptions + payment_events (Bogføringsloven)
    cur_sub = db.execute(
        """
        INSERT INTO subscriptions
            (cvr, plan, status, started_at, amount_dkk, billing_period,
             invoice_ref, mandate_id, created_at, updated_at)
        VALUES (?, 'sentinel', 'active', ?, 39900, 'monthly',
                'INV-001', 'PBS-123', ?, ?)
        """,
        (cvr, now, now, now),
    )
    sub_id = cur_sub.lastrowid
    db.execute(
        """
        INSERT INTO payment_events
            (cvr, subscription_id, event_type, amount_dkk, external_id,
             occurred_at, payload_json, created_at)
        VALUES (?, ?, 'payment_succeeded', 39900, 'NETS-abc', ?,
                '{"account":"1234"}', ?)
        """,
        (cvr, sub_id, now, now),
    )
    db.commit()
    return client


# ---------------------------------------------------------------------------
# Sentinel anonymise
# ---------------------------------------------------------------------------


class TestAnonymiseColumns:
    def test_nulls_client_pii(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()

        row = db.execute(
            "SELECT * FROM clients WHERE cvr = ?", ("12345678",)
        ).fetchone()
        assert row["telegram_chat_id"] is None
        assert row["contact_name"] is None
        assert row["contact_email"] is None
        assert row["contact_phone"] is None
        assert row["data_retention_mode"] == "anonymised"

    def test_preserves_client_non_pii(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        row = db.execute(
            "SELECT company_name, plan, cvr FROM clients WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert row["company_name"] == "Test Sentinel Co"
        assert row["plan"] == "sentinel"
        assert row["cvr"] == "12345678"

    def test_revokes_consent_records(self, db, fake_job):
        """Option 3 (Valdí ruling 2026-04-25): authorised_by_name and
        authorised_by_email are PRESERVED verbatim as §263 evidence
        (GDPR Art 17(3)(e)). Only ``notes`` is scrubbed and ``status``
        flipped. The +5y purge_bookkeeping handler deletes the row.
        """
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        row = db.execute(
            """
            SELECT authorised_by_name, authorised_by_email, notes, status,
                   consent_document, authorised_domains
              FROM consent_records WHERE cvr = ?
            """,
            ("12345678",),
        ).fetchone()
        # §263 / GDPR Art 17(3)(e) evidence — preserved verbatim.
        assert row["authorised_by_name"] == "Peter Nielsen"
        assert row["authorised_by_email"] == "peter@example.dk"
        assert row["consent_document"] == "consent/sentinel-12345678.pdf"
        assert row["authorised_domains"] == '["example.dk"]'
        # Free-text scrubbed; status flipped.
        assert row["notes"] is None
        assert row["status"] == "revoked"

    def test_revokes_consent_records_status_only(self, db, fake_job):
        """``status`` flips active→revoked; pre-existing terminal states
        (``expired`` / ``suspended`` / ``revoked``) are left alone.

        This consolidates the CASE-branch coverage in one test: seed
        four consent rows on the same CVR (one of each starting state)
        and assert each lands in the right post-state.
        """
        cvr = "31415926"
        # Build a Sentinel client; we'll write the consent rows directly.
        create_client(
            db,
            cvr=cvr,
            company_name="Status Test Co",
            plan="sentinel",
            status="active",
        )
        now = "2026-04-24T00:00:00Z"
        for status in ("active", "expired", "suspended", "revoked"):
            db.execute(
                """
                INSERT INTO consent_records
                    (cvr, authorised_domains, consent_type, consent_date,
                     consent_expiry, consent_document, authorised_by_name,
                     authorised_by_role, authorised_by_email, status,
                     created_at, updated_at)
                VALUES (?, '["example.dk"]', 'written', '2026-04-01',
                        '2027-04-01', ?, 'Peter Nielsen', 'Owner',
                        'peter@example.dk', ?, ?, ?)
                """,
                (cvr, f"consent/{status}.pdf", status, now, now),
            )
        db.commit()

        anonymise_client(db, fake_job(cvr))
        db.commit()

        rows = db.execute(
            """
            SELECT consent_document, status FROM consent_records
             WHERE cvr = ? ORDER BY id ASC
            """,
            (cvr,),
        ).fetchall()
        # Insert order = active, expired, suspended, revoked.
        # Post-anonymise expectations: active flips to revoked; the
        # other three retain their terminal state.
        actual = {r["consent_document"]: r["status"] for r in rows}
        assert actual == {
            "consent/active.pdf": "revoked",
            "consent/expired.pdf": "expired",
            "consent/suspended.pdf": "suspended",
            "consent/revoked.pdf": "revoked",
        }

    def test_scrubs_consent_records_notes(self, db, fake_job):
        """The ``notes`` column (free-text, may quote owner replies) is
        the ONLY consent_records column that gets nulled. Verified
        explicitly here so the contract does not regress.
        """
        _seed_full_sentinel(db)
        # Sanity: seed populates notes with 'signed via MitID'.
        before = db.execute(
            "SELECT notes FROM consent_records WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert before["notes"] == "signed via MitID"

        anonymise_client(db, fake_job("12345678"))
        db.commit()

        after = db.execute(
            "SELECT notes FROM consent_records WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert after["notes"] is None

    def test_scrubs_delivery_log_content(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        row = db.execute(
            """
            SELECT message_preview, external_id, error_message, sent_at
              FROM delivery_log WHERE cvr = ?
            """,
            ("12345678",),
        ).fetchone()
        assert row["message_preview"] is None
        assert row["external_id"] is None
        assert row["error_message"] is None
        # Timing preserved.
        assert row["sent_at"] == "2026-04-24T00:00:00Z"

    def test_nulls_delivery_retry_last_error(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        row = db.execute(
            """
            SELECT last_error FROM delivery_retry
             WHERE delivery_log_id IN (
                 SELECT id FROM delivery_log WHERE cvr = ?
             )
            """,
            ("12345678",),
        ).fetchone()
        assert row["last_error"] is None

    def test_nulls_scraped_scan_and_brief_json(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        scan = db.execute(
            "SELECT result_json FROM scan_history WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        brief = db.execute(
            "SELECT brief_json FROM brief_snapshots WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert scan["result_json"] is None
        assert brief["brief_json"] is None

    def test_anonymise_scrubs_prospects_pii_columns(self, db, fake_job):
        """Valdí extension of the Q3 ruling (2026-04-25): the same
        scraped-PII reasoning that nulls ``scan_history.result_json`` and
        ``brief_snapshots.brief_json`` extends to ``prospects``. Outreach-
        origin rows can carry meta author tags, contact-page emails, and
        LLM-quoted strings in ``brief_json`` / ``interpreted_json`` /
        ``error_message``. ``brief_json`` is NOT NULL → '{}'; the other
        two are nullable → NULL. Operational keys are preserved.

        Sanity tail: a follow-up ``purge_client`` against the same CVR
        cleanly drops the prospects row — proves the two passes do not
        conflict.
        """
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        # Seed a prospects row with all three PII columns populated.
        now = "2026-04-24T00:00:00Z"
        db.execute(
            """
            INSERT INTO prospects
                (domain, cvr, company_name, campaign, bucket,
                 brief_json, finding_count, critical_count, high_count,
                 interpreted_json, outreach_status, error_message,
                 created_at, updated_at)
            VALUES ('example.dk', ?, 'Test Sentinel Co',
                    '0426-restaurants', 'A',
                    '{"meta_author": "Owner Name <owner@example.dk>"}',
                    5, 1, 2,
                    '{"scoreboard": "..."}',
                    'sent',
                    'failed to parse owner@example.dk',
                    ?, ?)
            """,
            (cvr, now, now),
        )
        db.commit()

        counts = anonymise_client(db, fake_job(cvr))
        db.commit()

        row = db.execute(
            """
            SELECT brief_json, interpreted_json, error_message,
                   cvr, domain, company_name, campaign, bucket
              FROM prospects WHERE cvr = ?
            """,
            (cvr,),
        ).fetchone()

        # 1-3) PII columns scrubbed.
        assert row["brief_json"] == "{}"
        assert row["interpreted_json"] is None
        assert row["error_message"] is None
        # 4) Operational keys untouched.
        assert row["cvr"] == cvr
        assert row["domain"] == "example.dk"
        assert row["company_name"] == "Test Sentinel Co"
        assert row["campaign"] == "0426-restaurants"
        assert row["bucket"] == "A"
        # 5) Counts dict surfaces the prospects rowcount.
        assert counts["prospects"] == 1

        # 6) Sanity: a follow-up purge against the same CVR drops the
        #    prospects row entirely — the anonymise + purge passes do
        #    not conflict (different statements, different intents).
        purge_job = fake_job(cvr, action="purge")
        purge_client(db, purge_job)
        db.commit()
        assert (
            db.execute(
                "SELECT COUNT(*) FROM prospects WHERE cvr = ?", (cvr,)
            ).fetchone()[0]
            == 0
        )

    def test_scrubs_cert_dns_names(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        snap = db.execute(
            """
            SELECT dns_names_json, cert_sha256, issuer_name, not_after
              FROM client_cert_snapshots WHERE cvr = ?
            """,
            ("12345678",),
        ).fetchone()
        assert snap["dns_names_json"] == "[]"
        # §263 evidence preserved.
        assert snap["cert_sha256"] == "sha-abc"
        assert snap["issuer_name"] == "Let's Encrypt"
        assert snap["not_after"] == "2026-06-01T00:00:00Z"

    def test_scrubs_cert_change_details(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        chg = db.execute(
            "SELECT details_json, change_type FROM client_cert_changes WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert chg["details_json"] == "{}"
        assert chg["change_type"] == "new_cert"  # structure preserved

    def test_deletes_signup_tokens(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        count = db.execute(
            "SELECT COUNT(*) FROM signup_tokens WHERE cvr = ?",
            ("12345678",),
        ).fetchone()[0]
        assert count == 0

    def test_preserves_bookkeeping(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        subs = db.execute(
            "SELECT * FROM subscriptions WHERE cvr = ?", ("12345678",)
        ).fetchone()
        pays = db.execute(
            "SELECT * FROM payment_events WHERE cvr = ?", ("12345678",)
        ).fetchone()
        assert subs is not None
        assert subs["invoice_ref"] == "INV-001"
        assert subs["mandate_id"] == "PBS-123"
        assert pays is not None
        # payload_json intact — it's Bogføringsloven evidence.
        assert pays["payload_json"] == '{"account":"1234"}'

    def test_idempotent(self, db, fake_job):
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        db.commit()
        # Second call: columns already nulled, must not crash.
        counts = anonymise_client(db, fake_job("12345678"))
        db.commit()
        # clients still exists (1 row matched).
        assert counts["clients"] == 1

    def test_clients_consent_granted_not_flipped(self, db, fake_job):
        """Per the 2026-04-24 client-memory revision, ``consent_granted``
        is flipped at ``offboarding_triggered`` time, NOT at anonymise.
        Flipping it here would mean Valdí Gate 2 keeps permitting Layer 2
        for the 30 days between offboarding and the anonymise tick.
        """
        _seed_full_sentinel(db)
        # Caller sets consent_granted = 1 (Sentinel client).
        db.execute(
            "UPDATE clients SET consent_granted = 1 WHERE cvr = ?",
            ("12345678",),
        )
        db.commit()

        anonymise_client(db, fake_job("12345678"))
        db.commit()

        row = db.execute(
            "SELECT consent_granted FROM clients WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        # Still 1 — anonymise must not touch this column.
        assert row["consent_granted"] == 1

    def test_consent_records_status_expired_stays_expired(self, db, fake_job):
        """The CASE in the UPDATE preserves any pre-existing terminal
        state (suspended / expired / revoked). Only ``active`` rows flip
        to ``revoked``.
        """
        _seed_full_sentinel(db)
        # Pre-expire the seeded consent record. We must satisfy the
        # NOT NULL constraint on authorised_by_* on UPDATE itself.
        db.execute(
            "UPDATE consent_records SET status = 'expired' WHERE cvr = ?",
            ("12345678",),
        )
        db.commit()

        anonymise_client(db, fake_job("12345678"))
        db.commit()

        row = db.execute(
            "SELECT status FROM consent_records WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert row["status"] == "expired"

    def test_consent_records_active_flips_to_revoked(self, db, fake_job):
        """Mirror of the test above — the active branch of the CASE."""
        _seed_full_sentinel(db)

        anonymise_client(db, fake_job("12345678"))
        db.commit()

        row = db.execute(
            "SELECT status FROM consent_records WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert row["status"] == "revoked"

    def test_caller_owns_transaction_no_internal_commit(self, db, fake_job):
        """The handler emits UPDATEs / DELETEs but does not COMMIT —
        the runner commits after writing authorisation_revoked. We verify
        by mutating, observing on the same connection (visible — uncommitted
        reads to writer), then rolling back and observing the original
        state (proof the action did not commit on its own).
        """
        _seed_full_sentinel(db)
        anonymise_client(db, fake_job("12345678"))
        # Same connection sees uncommitted changes.
        before_commit = db.execute(
            "SELECT contact_email FROM clients WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert before_commit["contact_email"] is None

        # Roll back to prove the action didn't commit on its own.
        db.rollback()
        rolled = db.execute(
            "SELECT contact_email FROM clients WHERE cvr = ?",
            ("12345678",),
        ).fetchone()
        assert rolled["contact_email"] == "peter@example.dk"


# ---------------------------------------------------------------------------
# Purge cascade (Watchman hard-delete semantics)
# ---------------------------------------------------------------------------


class TestPurgeCascade:
    def test_watchman_hard_delete_wipes_everything(
        self, db, fake_job, client_data_dir
    ):
        # Seed a Watchman client (no subscriptions / payment_events).
        create_client(
            db,
            cvr="99999999",
            company_name="Trialist Co",
            plan="watchman",
            status="watchman_expired",
        )
        now = "2026-04-24T00:00:00Z"
        db.execute(
            """INSERT INTO client_domains (cvr, domain, is_primary, added_at)
               VALUES ('99999999', 'trial.dk', 1, ?)""",
            (now,),
        )
        db.execute(
            """INSERT INTO scan_history (scan_id, cvr, domain, scan_date,
               status, created_at) VALUES ('scan-x', '99999999', 'trial.dk',
               '2026-04-24', 'completed', ?)""",
            (now,),
        )
        db.execute(
            """INSERT INTO delivery_log (cvr, channel, message_type, status,
               created_at) VALUES ('99999999', 'telegram', 'welcome',
               'sent', ?)""",
            (now,),
        )
        # Pre-existing retention_jobs row that we want preserved (our job).
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('99999999', 'purge', ?, 'running', ?)""",
            (now, now),
        )
        current_job_id = cur.lastrowid
        # Also a sibling job that should be swept.
        db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('99999999', 'export', ?, 'pending', ?)""",
            (now, now),
        )
        db.commit()

        # Create filesystem artefacts.
        client_dir = client_data_dir / "99999999"
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text('{"test":"data"}')
        (client_dir / "signed.pdf").write_bytes(b"%PDF-1.4")

        job = fake_job("99999999", action="purge")
        job["id"] = current_job_id

        counts = purge_client(db, job)
        db.commit()

        # Every cvr-keyed table is empty.
        for table in (
            "clients",
            "client_domains",
            "scan_history",
            "delivery_log",
            "consent_records",
            "conversion_events",
            "onboarding_stage_log",
            "client_cert_snapshots",
            "client_cert_changes",
            "signup_tokens",
            "finding_occurrences",
            "brief_snapshots",
        ):
            count = db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE cvr = ?",
                ("99999999",),
            ).fetchone()[0]
            assert count == 0, f"{table} still has rows"

        # Only the current job survives; the sibling was swept.
        remaining = db.execute(
            "SELECT id FROM retention_jobs WHERE cvr = ?", ("99999999",)
        ).fetchall()
        assert [r["id"] for r in remaining] == [current_job_id]

        # Filesystem gone.
        assert not client_dir.exists()
        assert "authorisation.json" in counts["filesystem"]
        assert "signed.pdf" in counts["filesystem"]

    def test_sentinel_purge_preserves_bookkeeping(
        self, db, fake_job, client_data_dir
    ):
        _seed_full_sentinel(db)
        # Insert the currently-running job so the cascade leaves it.
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('12345678', 'purge', ?, 'running', ?)""",
            ("2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        current_job_id = cur.lastrowid
        db.commit()

        job = fake_job("12345678", action="purge")
        job["id"] = current_job_id

        purge_client(db, job)
        db.commit()

        # Bogføringsloven rows survive.
        subs = db.execute(
            "SELECT * FROM subscriptions WHERE cvr = ?", ("12345678",)
        ).fetchall()
        pays = db.execute(
            "SELECT * FROM payment_events WHERE cvr = ?", ("12345678",)
        ).fetchall()
        assert len(subs) == 1
        assert len(pays) == 1

        # But the clients row is gone.
        client = db.execute(
            "SELECT * FROM clients WHERE cvr = ?", ("12345678",)
        ).fetchone()
        assert client is None

    def test_purge_client_deletes_prospects_for_cvr(
        self, db, fake_job, client_data_dir
    ):
        """Codex P1 (2026-04-25) regression guard: ``purge_client`` must
        delete ``prospects`` rows for the CVR.

        Most clients originate from an outreach campaign and carry a
        ``prospects`` row keyed by the same CVR. ``prospects.brief_json``
        is scraped PII (meta author tags, contact-page emails). Leaving
        it behind violates the Watchman zero-retention rule and also
        orphans ``prospects.delivery_id`` (FK to ``delivery_log.id``)
        because the cascade has already wiped ``delivery_log``. We seed
        a delivery_log row + a prospects row pointing at it on the same
        CVR, run the purge, and assert both are gone.
        """
        cvr = "13131313"
        create_client(db, cvr=cvr, company_name="Outreach Origin Co",
                      plan="watchman")
        now = "2026-04-24T00:00:00Z"
        # Seed a delivery_log row so we can capture its id and reference
        # it from prospects.delivery_id (FK survives no longer than the
        # delivery_log row itself).
        dlog_cur = db.execute(
            """INSERT INTO delivery_log (cvr, channel, message_type,
               status, created_at) VALUES (?, 'email', 'outreach',
               'sent', ?)""",
            (cvr, now),
        )
        delivery_id = dlog_cur.lastrowid
        # Seed prospects row with the same CVR + scraped brief_json.
        db.execute(
            """INSERT INTO prospects (domain, cvr, company_name, campaign,
               bucket, brief_json, finding_count, critical_count, high_count,
               outreach_status, delivery_id, created_at, updated_at)
               VALUES ('outreach-origin.dk', ?, 'Outreach Origin Co',
               '0426-restaurants', 'A',
               '{"author":"peter@outreach-origin.dk"}', 5, 1, 2,
               'sent', ?, ?, ?)""",
            (cvr, delivery_id, now, now),
        )
        # The currently-running retention job.
        rj_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, now, now),
        )
        job = fake_job(cvr, action="purge")
        job["id"] = rj_cur.lastrowid
        db.commit()

        # Sanity: the prospects row exists before the purge.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM prospects WHERE cvr = ?", (cvr,)
            ).fetchone()[0]
            == 1
        )

        purge_client(db, job)
        db.commit()

        # The prospects row for this CVR is gone (and so is the
        # orphaned delivery_id reference, by virtue of the row itself
        # being deleted).
        assert (
            db.execute(
                "SELECT COUNT(*) FROM prospects WHERE cvr = ?", (cvr,)
            ).fetchone()[0]
            == 0
        )

    def test_purge_deletes_finding_status_log_orphans(
        self, db, fake_job, client_data_dir
    ):
        _seed_full_sentinel(db)
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('12345678', 'purge', ?, 'running', ?)""",
            ("2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        job = fake_job("12345678", action="purge")
        job["id"] = cur.lastrowid
        db.commit()

        purge_client(db, job)
        db.commit()

        # The seeded status-log row was tied to the finding_occurrence
        # we just deleted. It must be gone too.
        orphans = db.execute(
            """
            SELECT COUNT(*) FROM finding_status_log
             WHERE occurrence_id NOT IN (SELECT id FROM finding_occurrences)
            """,
        ).fetchone()[0]
        assert orphans == 0


# ---------------------------------------------------------------------------
# Sentinel +5y bookkeeping purge
# ---------------------------------------------------------------------------


class TestPurgeBookkeeping:
    def test_deletes_subscriptions_and_payment_events(self, db, fake_job):
        _seed_full_sentinel(db)
        purge_bookkeeping(db, fake_job("12345678", action="purge_bookkeeping"))
        db.commit()
        assert (
            db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE cvr = ?",
                ("12345678",),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM payment_events WHERE cvr = ?",
                ("12345678",),
            ).fetchone()[0]
            == 0
        )

    def test_works_after_clients_row_is_gone(self, db, fake_job):
        _seed_full_sentinel(db)
        # Drop the clients row (simulate earlier purge having run).
        db.execute("DELETE FROM clients WHERE cvr = ?", ("12345678",))
        db.commit()

        counts = purge_bookkeeping(
            db, fake_job("12345678", action="purge_bookkeeping")
        )
        db.commit()
        assert counts["subscriptions"] == 1
        assert counts["payment_events"] == 1

    def test_zero_counts_on_empty_cvr(self, db, fake_job):
        """A Sentinel that cancelled before any payment lands should no-op cleanly."""
        counts = purge_bookkeeping(
            db, fake_job("00000000", action="purge_bookkeeping")
        )
        db.commit()
        assert counts["subscriptions"] == 0
        assert counts["payment_events"] == 0


# ---------------------------------------------------------------------------
# Filesystem helper
# ---------------------------------------------------------------------------


class TestFilesystemHelper:
    def test_missing_directory_returns_empty(self, db, fake_job, client_data_dir):
        # No <cvr>/ subdir created.
        create_client(
            db,
            cvr="77777777",
            company_name="No Files Co",
            plan="watchman",
        )
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('77777777', 'purge', ?, 'running', ?)""",
            ("2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        job = fake_job("77777777", action="purge")
        job["id"] = cur.lastrowid
        db.commit()

        counts = purge_client(db, job)
        assert counts["filesystem"] == []


# ---------------------------------------------------------------------------
# _delete_client_filesystem direct unit tests
# ---------------------------------------------------------------------------


class TestDeleteClientFilesystem:
    def test_returns_relative_paths_removed(self, tmp_path, monkeypatch):
        cvr = "12345678"
        client_dir = tmp_path / cvr
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text("{}", encoding="utf-8")
        (client_dir / "consent.pdf").write_bytes(b"%PDF-1.4")
        nested = client_dir / "history"
        nested.mkdir()
        (nested / "old.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("CLIENT_DATA_DIR", str(tmp_path))

        removed = _delete_client_filesystem(cvr)

        assert sorted(removed) == sorted(
            ["authorisation.json", "consent.pdf", "history/old.json"]
        )
        assert not client_dir.exists()

    def test_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLIENT_DATA_DIR", str(tmp_path))
        # No exception raised.
        assert _delete_client_filesystem("87654321") == []

    def test_oserror_on_rmtree_logged_and_reraised(self, tmp_path, monkeypatch):
        cvr = "12345678"
        client_dir = tmp_path / cvr
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("CLIENT_DATA_DIR", str(tmp_path))

        # Force shutil.rmtree to raise an OSError. We patch the symbol on
        # the actions module (where the helper looks it up).
        import src.retention.actions as mod

        def _boom(path):  # noqa: ARG001
            raise OSError("disk explosion")

        monkeypatch.setattr(mod.shutil, "rmtree", _boom)

        with pytest.raises(OSError, match="disk explosion"):
            _delete_client_filesystem(cvr)

    def test_rejects_path_escape_via_malicious_cvr(self, tmp_path, monkeypatch):
        """Codex P1 (2026-04-24) regression guard: a CVR containing ``..``
        must not let the rmtree escape ``CLIENT_DATA_DIR``. The helper
        resolves both base + candidate and refuses the delete unless the
        candidate stays under base. The refusal is logged with the event
        name ``retention_fs_path_escape_rejected`` (Federico's monitoring
        greps for the literal string) and returns an empty list — non-fatal
        because the runner has already recorded the DB-side cascade
        success.
        """
        # Set up an isolated CLIENT_DATA_DIR + a sibling "victim" dir
        # outside it, holding a sentinel file we can prove still exists.
        base = tmp_path / "client-data"
        base.mkdir()
        victim = tmp_path / "victim_outside"
        victim.mkdir()
        sentinel = victim / "do-not-delete.json"
        sentinel.write_text('{"value": "preserved"}', encoding="utf-8")
        monkeypatch.setenv("CLIENT_DATA_DIR", str(base))

        # Capture log output via a fresh loguru sink (mirrors the pattern
        # in tests/test_trial_expiry.py::TestLoggerEventNameContract).
        buf = StringIO()
        logger.remove()
        sink_id = logger.add(buf, level="WARNING", format="{message}")
        try:
            removed = _delete_client_filesystem("../victim_outside")
        finally:
            logger.remove(sink_id)
            import sys
            logger.add(sys.stderr, level="INFO")

        # 1) Empty return — the rejection is reported as "nothing removed".
        assert removed == []
        # 2) The sibling sentinel file must still exist — proof the
        # rmtree was refused before it could escape.
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == '{"value": "preserved"}'
        # 3) Forensic log line — Federico's monitoring greps the literal.
        assert "retention_fs_path_escape_rejected" in buf.getvalue()

    def test_rejects_base_dir_via_empty_cvr(self, tmp_path, monkeypatch):
        """Codex P1 follow-up (2026-04-24): a CVR of ``""`` resolves to
        ``CLIENT_DATA_DIR`` itself (because ``base / "" == base``).
        ``Path.is_relative_to`` is reflexive — equal paths return True —
        so the escape guard below it would have allowed
        ``shutil.rmtree(CLIENT_DATA_DIR)`` and wiped every client's
        files. The explicit ``candidate == base`` check blocks this and
        logs ``retention_fs_base_dir_rejected`` (distinct event name so
        post-incident greps tell base-dir from escape).
        """
        # Set up CLIENT_DATA_DIR with a sibling client subdirectory we
        # can prove still exists after the refused delete.
        base = tmp_path / "client-data"
        base.mkdir()
        sibling = base / "12345678"
        sibling.mkdir()
        sentinel = sibling / "sentinel.json"
        sentinel.write_text('{"value": "preserved"}', encoding="utf-8")
        monkeypatch.setenv("CLIENT_DATA_DIR", str(base))

        buf = StringIO()
        logger.remove()
        sink_id = logger.add(buf, level="WARNING", format="{message}")
        try:
            removed = _delete_client_filesystem("")
        finally:
            logger.remove(sink_id)
            import sys
            logger.add(sys.stderr, level="INFO")

        # 1) Empty return — the rejection is reported as "nothing removed".
        assert removed == []
        # 2) The sibling client's sentinel file must still exist — proof
        # the rmtree was refused before it could touch the base dir.
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == '{"value": "preserved"}'
        # 3) Distinct forensic event name — separates base-dir from escape.
        assert "retention_fs_base_dir_rejected" in buf.getvalue()

    def test_rejects_base_dir_via_dot_cvr(self, tmp_path, monkeypatch):
        """Codex P1 follow-up (2026-04-24): a CVR of ``"."`` also resolves
        to ``CLIENT_DATA_DIR`` itself (``base / "." == base``). Same
        catastrophic outcome as the empty-string case. Asserted separately
        so a future refactor that handles one but not the other still
        fails one test.
        """
        base = tmp_path / "client-data"
        base.mkdir()
        sibling = base / "12345678"
        sibling.mkdir()
        sentinel = sibling / "sentinel.json"
        sentinel.write_text('{"value": "preserved"}', encoding="utf-8")
        monkeypatch.setenv("CLIENT_DATA_DIR", str(base))

        buf = StringIO()
        logger.remove()
        sink_id = logger.add(buf, level="WARNING", format="{message}")
        try:
            removed = _delete_client_filesystem(".")
        finally:
            logger.remove(sink_id)
            import sys
            logger.add(sys.stderr, level="INFO")

        assert removed == []
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == '{"value": "preserved"}'
        assert "retention_fs_base_dir_rejected" in buf.getvalue()


# ---------------------------------------------------------------------------
# Additional purge cascade scenarios required by the spec
# ---------------------------------------------------------------------------


class TestPurgeCascadeOrdering:
    """Order-of-operations regression guards.

    The cascade uses subquery-IN to delete child rows whose parents this
    handler is also about to drop. If the order ever flips, the subquery
    finds no parents and the children survive as orphans. We seed the
    affected child + parent and assert the cascade leaves no orphan.
    """

    def _seed_minimal_purge(
        self, db, fake_job, *, plan: str = "watchman", cvr: str = "55555555"
    ) -> dict:
        create_client(db, cvr=cvr, company_name="X", plan=plan)
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, "2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        job = fake_job(cvr, action="purge")
        job["id"] = cur.lastrowid
        db.commit()
        return job

    def test_finding_status_log_deleted_before_finding_occurrences(
        self, db, fake_job, client_data_dir
    ):
        cvr = "55555555"
        job = self._seed_minimal_purge(db, fake_job, cvr=cvr)
        # finding_definition + occurrence + log row.
        db.execute(
            """INSERT INTO finding_definitions (finding_hash, severity,
               description, first_seen_at) VALUES ('fh-1', 'high', 'd', '2026-04-01')""",
        )
        cur = db.execute(
            """INSERT INTO finding_occurrences (cvr, domain, finding_hash,
               status, first_seen_at, last_seen_at) VALUES (?, 'x.dk',
               'fh-1', 'open', '2026-04-01', '2026-04-01')""",
            (cvr,),
        )
        occ_id = cur.lastrowid
        db.execute(
            """INSERT INTO finding_status_log (occurrence_id, from_status,
               to_status, source, created_at) VALUES (?, NULL, 'open',
               'scan:test', '2026-04-01T00:00:00Z')""",
            (occ_id,),
        )
        db.commit()

        purge_client(db, job)
        db.commit()

        # Both should be gone — and crucially, no orphan log row.
        log_count = db.execute(
            "SELECT COUNT(*) FROM finding_status_log WHERE occurrence_id = ?",
            (occ_id,),
        ).fetchone()[0]
        occ_count = db.execute(
            "SELECT COUNT(*) FROM finding_occurrences WHERE cvr = ?",
            (cvr,),
        ).fetchone()[0]
        assert log_count == 0
        assert occ_count == 0

    def test_delivery_retry_deleted_before_delivery_log(
        self, db, fake_job, client_data_dir
    ):
        cvr = "66666666"
        job = self._seed_minimal_purge(db, fake_job, cvr=cvr)
        cur = db.execute(
            """INSERT INTO delivery_log (cvr, channel, message_type,
               status, created_at) VALUES (?, 'telegram', 'welcome',
               'sent', '2026-04-01T00:00:00Z')""",
            (cvr,),
        )
        log_id = cur.lastrowid
        db.execute(
            """INSERT INTO delivery_retry (delivery_log_id, domain,
               brief_path, attempt, next_retry_at, last_error, status,
               created_at) VALUES (?, 'x.dk', '/tmp/b.json', 1,
               '2026-04-24T01:00:00Z', 'err', 'pending',
               '2026-04-01T00:00:00Z')""",
            (log_id,),
        )
        db.commit()

        purge_client(db, job)
        db.commit()

        retry_count = db.execute(
            "SELECT COUNT(*) FROM delivery_retry WHERE delivery_log_id = ?",
            (log_id,),
        ).fetchone()[0]
        log_count = db.execute(
            "SELECT COUNT(*) FROM delivery_log WHERE cvr = ?", (cvr,)
        ).fetchone()[0]
        assert retry_count == 0
        assert log_count == 0


class TestPurgeFilesystemPath:
    """Filesystem-step scenarios broken out for clarity."""

    def test_dir_removed_when_present(self, db, fake_job, client_data_dir):
        cvr = "55555555"
        create_client(db, cvr=cvr, company_name="FS", plan="watchman")
        client_dir = client_data_dir / cvr
        client_dir.mkdir()
        (client_dir / "authorisation.json").write_text("{}", encoding="utf-8")
        (client_dir / "signed.pdf").write_bytes(b"%PDF-1.4")
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, "2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        job = fake_job(cvr, action="purge")
        job["id"] = cur.lastrowid
        db.commit()

        counts = purge_client(db, job)
        db.commit()

        assert not client_dir.exists()
        assert sorted(counts["filesystem"]) == sorted(
            ["authorisation.json", "signed.pdf"]
        )

    def test_missing_dir_is_noop(self, db, fake_job, client_data_dir):
        cvr = "66666666"
        create_client(db, cvr=cvr, company_name="NoFS", plan="watchman")
        # No client_data_dir/<cvr>/ created.
        cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, "2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        job = fake_job(cvr, action="purge")
        job["id"] = cur.lastrowid
        db.commit()

        counts = purge_client(db, job)
        db.commit()

        assert counts["filesystem"] == []


class TestPurgeRetentionJobsSiblings:
    def test_siblings_for_same_cvr_deleted_current_survives(
        self, db, fake_job, client_data_dir
    ):
        cvr = "55555555"
        create_client(db, cvr=cvr, company_name="Sib", plan="watchman")
        # Sibling job that should be swept.
        sibling_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'export', ?, 'pending', ?)""",
            (cvr, "2099-01-01T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        sibling_id = sibling_cur.lastrowid
        # Unrelated CVR — must survive.
        create_client(db, cvr="88888888", company_name="Other", plan="watchman")
        unrelated_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES ('88888888', 'purge', ?,
               'pending', ?)""",
            ("2099-01-01T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        unrelated_id = unrelated_cur.lastrowid
        # The current job that's "running."
        current_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, "2026-04-24T00:00:00Z", "2026-04-24T00:00:00Z"),
        )
        current_id = current_cur.lastrowid
        db.commit()

        job = fake_job(cvr, action="purge")
        job["id"] = current_id

        purge_client(db, job)
        db.commit()

        ids_for_cvr = [
            r["id"]
            for r in db.execute(
                "SELECT id FROM retention_jobs WHERE cvr = ?", (cvr,)
            ).fetchall()
        ]
        assert ids_for_cvr == [current_id]
        # Sibling deleted.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM retention_jobs WHERE id = ?",
                (sibling_id,),
            ).fetchone()[0]
            == 0
        )
        # Unrelated CVR untouched.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM retention_jobs WHERE id = ?",
                (unrelated_id,),
            ).fetchone()[0]
            == 1
        )

    def test_purge_client_preserves_purge_bookkeeping_jobs(
        self, db, fake_job, client_data_dir
    ):
        """Sentinel edge case: an operator-triggered early ``purge`` must
        NOT delete the future ``purge_bookkeeping`` job for the same CVR.

        ``purge_client`` preserves subscriptions + payment_events for
        Bogføringsloven; the +5y ``purge_bookkeeping`` tick is the only
        scheduled handler that will eventually clean those tables up.
        Dropping the bookkeeping job at early-purge time would orphan
        those rows indefinitely.

        Sibling cleanup behaviour is otherwise preserved: a non-bookkeeping
        sibling job (e.g. ``anonymise``) for the same CVR is still swept.
        """
        cvr = "12121212"
        create_client(db, cvr=cvr, company_name="Sentinel Early Purge",
                      plan="sentinel")

        now = "2026-04-24T00:00:00Z"
        # Terminal anonymise (already executed) — should be swept.
        anon_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'anonymise', ?, 'completed', ?)""",
            (cvr, now, now),
        )
        anon_id = anon_cur.lastrowid
        # The current purge job — survives via the id != current_job_id guard.
        purge_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge', ?, 'running', ?)""",
            (cvr, now, now),
        )
        purge_id = purge_cur.lastrowid
        # Future bookkeeping cleanup at +5y — MUST survive.
        bk_cur = db.execute(
            """INSERT INTO retention_jobs (cvr, action, scheduled_for,
               status, created_at) VALUES (?, 'purge_bookkeeping', ?,
               'pending', ?)""",
            (cvr, "2031-04-24T00:00:00Z", now),
        )
        bk_id = bk_cur.lastrowid
        db.commit()

        job = fake_job(cvr, action="purge")
        job["id"] = purge_id

        purge_client(db, job)
        db.commit()

        remaining_ids = sorted(
            r["id"]
            for r in db.execute(
                "SELECT id FROM retention_jobs WHERE cvr = ?", (cvr,)
            ).fetchall()
        )
        # The current purge row + the future bookkeeping row both survive.
        # The completed anonymise sibling is gone.
        assert remaining_ids == sorted([purge_id, bk_id])
        assert anon_id not in remaining_ids


# ---------------------------------------------------------------------------
# Additional purge_bookkeeping scenarios required by the spec
# ---------------------------------------------------------------------------


class TestPurgeBookkeepingChildrenFirst:
    def test_payment_events_deleted_before_subscriptions(self, db, fake_job):
        """Children-first invariant. SQLite has no enforced FK between
        payment_events.subscription_id and subscriptions.id, but the
        semantic order must be: kill the children, then the parents.
        We assert both tables are empty for the CVR after the call —
        if the order ever swapped and a parent-first DELETE somehow
        broke the child cleanup, this would fail.
        """
        cvr = "12345678"
        create_client(db, cvr=cvr, company_name="X", plan="sentinel")
        sub_cur = db.execute(
            """INSERT INTO subscriptions (cvr, plan, status, started_at,
               amount_dkk, billing_period, created_at, updated_at)
               VALUES (?, 'sentinel', 'cancelled', ?, 39900, 'monthly', ?, ?)""",
            (cvr, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
             "2026-01-01T00:00:00Z"),
        )
        sub_id = sub_cur.lastrowid
        for et in ("invoice_issued", "payment_succeeded", "refund"):
            db.execute(
                """INSERT INTO payment_events (cvr, subscription_id,
                   event_type, amount_dkk, occurred_at, created_at)
                   VALUES (?, ?, ?, 39900, ?, ?)""",
                (cvr, sub_id, et, "2026-01-15T00:00:00Z",
                 "2026-01-15T00:00:00Z"),
            )
        db.commit()

        counts = purge_bookkeeping(db, fake_job(cvr, action="purge_bookkeeping"))
        db.commit()

        assert counts["payment_events"] == 3
        assert counts["subscriptions"] == 1

    def test_returns_count_dict(self, db, fake_job):
        """Stage A.5 spec §4.1.7 extended the return shape to cover
        the three audit surfaces. Each key is always present (zero on
        a clean target). The ``held`` key only appears on the short-
        circuit path (see ``test_purge_bookkeeping_respects_hold_flag``).
        """
        cvr = "12345678"
        create_client(db, cvr=cvr, company_name="X", plan="sentinel")
        counts = purge_bookkeeping(db, fake_job(cvr, action="purge_bookkeeping"))
        assert set(counts.keys()) == {
            "payment_events",
            "subscriptions",
            "clients_audit_log",
            "config_changes",
            "command_audit",
        }


# ---------------------------------------------------------------------------
# Stage A.5 spec §6.3 — Valdí §263 audit-row preservation tests
# ---------------------------------------------------------------------------


_NOW_FOR_AUDIT = "2026-04-24T00:00:00Z"


def _years_ago_iso(years: int) -> str:
    """Return an ISO-8601 UTC timestamp ``years`` calendar years before
    the test runtime ``now``.

    Codex 2026-05-02 P2: absolute test-seed constants (``2020-04-24``)
    were stable today but would drift past the ``now - 5y`` cutoff
    around 2030, breaking
    ``test_purge_bookkeeping_keeps_recent_audit_rows_for_target``. The
    seeds are now derived from the live clock so the relative
    ordering against the cutoff stays correct as the calendar
    advances.
    """
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=years * 365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _six_years_ago_iso() -> str:
    return _years_ago_iso(6)


def _one_year_ago_iso() -> str:
    return _years_ago_iso(1)


# Computed once at import. ``purge_bookkeeping`` reads the cutoff via
# ``datetime.now(UTC)`` at call time; the few-second drift between
# import and call never moves a row across the +/- 5y boundary.
_SIX_YEARS_AGO = _six_years_ago_iso()
_ONE_YEAR_AGO = _one_year_ago_iso()


def _seed_audit_log_row(
    conn,
    *,
    target_id: str,
    action: str = "retention.force_run",
    occurred_at: str = _NOW_FOR_AUDIT,
    target_type: str = "cvr",
    actor_kind: str = "operator",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO audit_log (
            occurred_at, operator_id, session_id, action,
            target_type, target_id, payload_json,
            source_ip, user_agent, request_id, actor_kind
        )
        VALUES (?, NULL, NULL, ?, ?, ?, '{}', NULL, NULL, NULL, ?)
        """,
        (occurred_at, action, target_type, target_id, actor_kind),
    )
    conn.commit()
    return cur.lastrowid


def _seed_config_changes_row(
    conn,
    *,
    target_pk: str,
    table_name: str = "clients",
    op: str = "UPDATE",
    occurred_at: str = _NOW_FOR_AUDIT,
    intent: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO config_changes (
            occurred_at, table_name, op, target_pk,
            old_json, new_json,
            intent, operator_id, session_id, request_id, actor_kind
        )
        VALUES (?, ?, ?, ?, '{}', '{}', ?, NULL, NULL, NULL, 'operator')
        """,
        (occurred_at, table_name, op, target_pk, intent),
    )
    conn.commit()
    return cur.lastrowid


def _seed_command_audit_row(
    conn,
    *,
    target_id: str,
    command_name: str = "send",
    outcome: str = "ok",
    occurred_at: str = _NOW_FOR_AUDIT,
    target_type: str = "cvr",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO command_audit (
            occurred_at, command_name, target_type, target_id,
            outcome, payload_json, error_detail,
            operator_id, session_id, request_id, actor_kind
        )
        VALUES (?, ?, ?, ?, ?, '{}', NULL, NULL, NULL, NULL, 'operator')
        """,
        (occurred_at, command_name, target_type, target_id, outcome),
    )
    conn.commit()
    return cur.lastrowid


class TestValdiAuditPreservation:
    """Spec §6.3 — anonymise / purge MUST NOT touch the three audit
    surfaces; ``purge_bookkeeping`` is the single permitted writer
    under five binding carve-outs (Valdí ruling 2026-04-30).
    """

    def test_anonymise_does_not_touch_audit_surfaces(self, db, fake_job):
        """Anonymise preserves all three audit surfaces — both the
        target-CVR rows and any unrelated rows."""
        _seed_full_sentinel(db)
        cvr = "12345678"
        # Target-CVR rows on each of the three audit surfaces.
        _seed_audit_log_row(db, target_id=cvr, action="trial.activated")
        _seed_config_changes_row(db, target_pk=cvr, table_name="clients")
        _seed_command_audit_row(db, target_id=cvr, command_name="send")

        anonymise_client(db, fake_job(cvr))
        db.commit()

        # All three audit surfaces still hold the seeded rows.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log WHERE target_id = ?",
                (cvr,),
            ).fetchone()[0]
            >= 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes WHERE target_pk = ?",
                (cvr,),
            ).fetchone()[0]
            >= 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM command_audit WHERE target_id = ?",
                (cvr,),
            ).fetchone()[0]
            == 1
        )

    def test_purge_does_not_touch_audit_surfaces(
        self, db, fake_job, client_data_dir
    ):
        """Purge cascades the client subtree but preserves all three
        audit surfaces. The audit rows survive the hard-delete so a
        forensic timeline can be reconstructed against the deleted CVR."""
        cvr = "99999999"
        create_client(
            db, cvr=cvr, company_name="Trialist Co", plan="watchman"
        )
        _seed_audit_log_row(db, target_id=cvr, action="retention.purge")
        _seed_config_changes_row(db, target_pk=cvr, table_name="clients")
        _seed_command_audit_row(
            db, target_id=cvr, command_name="run-pipeline"
        )
        cur = db.execute(
            "INSERT INTO retention_jobs (cvr, action, scheduled_for, "
            "status, created_at) VALUES (?, 'purge', ?, 'running', ?)",
            (cvr, _NOW_FOR_AUDIT, _NOW_FOR_AUDIT),
        )
        job = fake_job(cvr, action="purge")
        job["id"] = cur.lastrowid
        db.commit()

        purge_client(db, job)
        db.commit()

        # The clients row is gone (Watchman hard-delete).
        assert (
            db.execute(
                "SELECT COUNT(*) FROM clients WHERE cvr = ?", (cvr,)
            ).fetchone()[0]
            == 0
        )
        # All three audit surfaces still hold their pre-purge rows.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log WHERE target_id = ?",
                (cvr,),
            ).fetchone()[0]
            >= 1
        )
        # Note: config_changes also contains the trigger-fired DELETE
        # rows from the cascade. We assert the seeded row is still there
        # rather than asserting an exact count.
        seeded_present = db.execute(
            "SELECT COUNT(*) FROM config_changes "
            "WHERE target_pk = ? AND old_json = '{}' AND new_json = '{}'",
            (cvr,),
        ).fetchone()[0]
        assert seeded_present == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM command_audit WHERE target_id = ?",
                (cvr,),
            ).fetchone()[0]
            == 1
        )

    def test_purge_bookkeeping_keeps_recent_audit_rows_for_target(
        self, db, fake_job
    ):
        """Carve-out 1: per-row ``occurred_at < cutoff`` filter. A
        year-old audit row tied to the target CVR survives the purge —
        it's inside the +5y preservation horizon."""
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        _seed_audit_log_row(
            db,
            target_id=cvr,
            action="trial.activated",
            occurred_at=_ONE_YEAR_AGO,
        )
        _seed_config_changes_row(
            db, target_pk=cvr, occurred_at=_ONE_YEAR_AGO
        )
        _seed_command_audit_row(
            db, target_id=cvr, occurred_at=_ONE_YEAR_AGO
        )

        purge_bookkeeping(db, fake_job(cvr, action="purge_bookkeeping"))
        db.commit()

        # All three recent rows survive.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE target_id = ? AND occurred_at = ?",
                (cvr, _ONE_YEAR_AGO),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes "
                "WHERE target_pk = ? AND occurred_at = ?",
                (cvr, _ONE_YEAR_AGO),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM command_audit "
                "WHERE target_id = ? AND occurred_at = ?",
                (cvr, _ONE_YEAR_AGO),
            ).fetchone()[0]
            == 1
        )

    def test_purge_bookkeeping_skips_unrelated_cvrs(self, db, fake_job):
        """Carve-out 1 (extension): rows for unrelated CVRs are
        untouched even when older than the cutoff."""
        cvr = "12345678"
        unrelated = "99999999"
        _seed_full_sentinel(db, cvr=cvr)
        # 6-year-old row tied to a different CVR.
        _seed_audit_log_row(
            db, target_id=unrelated, occurred_at=_SIX_YEARS_AGO
        )
        _seed_config_changes_row(
            db, target_pk=unrelated, occurred_at=_SIX_YEARS_AGO
        )
        _seed_command_audit_row(
            db, target_id=unrelated, occurred_at=_SIX_YEARS_AGO
        )

        purge_bookkeeping(db, fake_job(cvr, action="purge_bookkeeping"))
        db.commit()

        # Unrelated rows untouched.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log WHERE target_id = ?",
                (unrelated,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes WHERE target_pk = ?",
                (unrelated,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM command_audit WHERE target_id = ?",
                (unrelated,),
            ).fetchone()[0]
            == 1
        )

    def test_purge_bookkeeping_deletes_old_audit_rows_for_target(
        self, db, fake_job
    ):
        """6-year-old rows on the target CVR are hard-deleted."""
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        _seed_audit_log_row(
            db, target_id=cvr, occurred_at=_SIX_YEARS_AGO
        )
        _seed_config_changes_row(
            db, target_pk=cvr, occurred_at=_SIX_YEARS_AGO
        )
        _seed_command_audit_row(
            db, target_id=cvr, occurred_at=_SIX_YEARS_AGO
        )

        counts = purge_bookkeeping(
            db, fake_job(cvr, action="purge_bookkeeping")
        )
        db.commit()

        assert counts["clients_audit_log"] == 1
        assert counts["config_changes"] == 1
        assert counts["command_audit"] == 1

        # The aged rows are gone.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE target_id = ? AND occurred_at = ?",
                (cvr, _SIX_YEARS_AGO),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes "
                "WHERE target_pk = ? AND occurred_at = ?",
                (cvr, _SIX_YEARS_AGO),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM command_audit "
                "WHERE target_id = ? AND occurred_at = ?",
                (cvr, _SIX_YEARS_AGO),
            ).fetchone()[0]
            == 0
        )

    def test_purge_bookkeeping_respects_hold_flag(self, db, fake_job):
        """Carve-out 3: ``data_retention_mode='hold'`` short-circuits
        the entire run. Zero DELETEs even on aged rows."""
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        _seed_audit_log_row(
            db, target_id=cvr, occurred_at=_SIX_YEARS_AGO
        )
        _seed_config_changes_row(
            db, target_pk=cvr, occurred_at=_SIX_YEARS_AGO
        )
        _seed_command_audit_row(
            db, target_id=cvr, occurred_at=_SIX_YEARS_AGO
        )

        # Set the hold flag directly via SQL — set_data_retention_mode
        # rejects 'hold' (V2 will replace with a structured table).
        db.execute(
            "UPDATE clients SET data_retention_mode = 'hold' WHERE cvr = ?",
            (cvr,),
        )
        db.commit()

        counts = purge_bookkeeping(
            db, fake_job(cvr, action="purge_bookkeeping")
        )
        db.commit()

        # All counts zero; held flag set.
        assert counts.get("held") is True
        assert counts["payment_events"] == 0
        assert counts["subscriptions"] == 0
        assert counts["clients_audit_log"] == 0
        assert counts["config_changes"] == 0
        assert counts["command_audit"] == 0

        # Aged rows still present — short-circuit fired before any DELETE.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE target_id = ? AND occurred_at = ?",
                (cvr, _SIX_YEARS_AGO),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes "
                "WHERE target_pk = ? AND occurred_at = ?",
                (cvr, _SIX_YEARS_AGO),
            ).fetchone()[0]
            == 1
        )
        # Bookkeeping rows still present too.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE cvr = ?",
                (cvr,),
            ).fetchone()[0]
            == 1
        )

    def test_purge_bookkeeping_emits_summary_row_before_deletes(
        self, db, fake_job
    ):
        """Carve-out 2: one summary ``clients.audit_log`` row lands
        before the DELETEs run, with per-surface deleted_counts in
        ``payload_json`` and ``occurred_at_cutoff`` in ISO-8601 form."""
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        # Seed two aged audit_log rows + one config_changes + one
        # command_audit so the summary's deleted_counts is non-trivial.
        _seed_audit_log_row(
            db,
            target_id=cvr,
            action="trial.activated",
            occurred_at=_SIX_YEARS_AGO,
        )
        _seed_audit_log_row(
            db,
            target_id=cvr,
            action="retention.force_run",
            occurred_at=_SIX_YEARS_AGO,
        )
        _seed_config_changes_row(
            db, target_pk=cvr, occurred_at=_SIX_YEARS_AGO
        )
        _seed_command_audit_row(
            db, target_id=cvr, occurred_at=_SIX_YEARS_AGO
        )

        purge_bookkeeping(db, fake_job(cvr, action="purge_bookkeeping"))
        db.commit()

        # The summary row lands with action='retention.bookkeeping_purge'
        # and survives the cycle (its occurred_at is ~now, well past
        # the cutoff).
        summary_rows = db.execute(
            "SELECT occurred_at, target_type, target_id, payload_json, "
            "actor_kind FROM audit_log WHERE action = ?",
            ("retention.bookkeeping_purge",),
        ).fetchall()
        assert len(summary_rows) == 1
        summary = summary_rows[0]
        assert summary["target_type"] == "cvr"
        assert summary["target_id"] == cvr
        assert summary["actor_kind"] == "system"

        payload = json.loads(summary["payload_json"])
        assert "deleted_counts" in payload
        assert "occurred_at_cutoff" in payload
        assert payload["deleted_counts"]["clients_audit_log"] == 2
        assert payload["deleted_counts"]["config_changes"] == 1
        assert payload["deleted_counts"]["command_audit"] == 1
        assert payload["deleted_counts"]["payment_events"] == 1
        assert payload["deleted_counts"]["subscriptions"] == 1
        # Cutoff ISO-8601 with 'Z' suffix.
        assert payload["occurred_at_cutoff"].endswith("Z")

    def test_purge_bookkeeping_skips_non_cvr_audit_log_rows(
        self, db, fake_job
    ):
        """Codex 2026-05-02 P2 follow-up: ``clients.audit_log`` rows
        whose ``target_type`` is something other than ``'cvr'`` are
        NOT touched, even when their ``target_id`` happens to match
        the CVR string. Prevents a future writer from accidentally
        deleting (e.g.) a settings_file row whose target_id is a
        filename that collides with a CVR.
        """
        cvr = "12345678"
        _seed_full_sentinel(db, cvr=cvr)
        # A non-CVR audit row with a colliding target_id. Aged so the
        # cutoff filter does not protect it; only the target_type
        # filter must.
        _seed_audit_log_row(
            db,
            target_id=cvr,
            action="config.file_write",
            target_type="settings_file",
            occurred_at=_SIX_YEARS_AGO,
        )

        counts = purge_bookkeeping(
            db, fake_job(cvr, action="purge_bookkeeping")
        )
        db.commit()

        # The non-CVR row was not counted toward this CVR's deletion.
        assert counts["clients_audit_log"] == 0
        # And it survives.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE target_id = ? AND target_type = ?",
                (cvr, "settings_file"),
            ).fetchone()[0]
            == 1
        )

    def test_purge_bookkeeping_skips_orphan_config_changes(
        self, db, fake_job
    ):
        """Carve-out 4: a 6-year-old ``config_changes`` row whose
        ``target_pk`` does not match any CVR is preserved. Its
        retention is governed by a separate data-minimisation cron
        (out of scope for A.5)."""
        cvr = "12345678"
        orphan_pk = "1492"  # numeric id from a client_domains row
        _seed_full_sentinel(db, cvr=cvr)
        # The orphan: target_pk does not match the target CVR. It is
        # also older than the cutoff.
        _seed_config_changes_row(
            db,
            target_pk=orphan_pk,
            table_name="client_domains",
            occurred_at=_SIX_YEARS_AGO,
        )

        counts = purge_bookkeeping(
            db, fake_job(cvr, action="purge_bookkeeping")
        )
        db.commit()

        # The orphan was not counted toward this CVR's deletion.
        assert counts["config_changes"] == 0
        # And it is still present in the table.
        assert (
            db.execute(
                "SELECT COUNT(*) FROM config_changes WHERE target_pk = ?",
                (orphan_pk,),
            ).fetchone()[0]
            == 1
        )
