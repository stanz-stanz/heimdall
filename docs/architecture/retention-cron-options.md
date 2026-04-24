# Retention-Execution Cron — Architecture Options

> **2026-04-24 revision — supersedes §3 and parts of §4 for Watchman.**
> Watchman is a free trial and retains **no data** past trial expiry.
> `schedule_churn_retention` for Watchman now schedules exactly one
> `purge` job at the trial-expiry anchor (immediate on next tick) — no
> anonymise stage, no 90d/365d window. The clients row is
> **hard-deleted** (Q2 revised from tombstone). Sentinel retention is
> unchanged: 30-day anonymise + 5-year `purge_bookkeeping` for
> `subscriptions` + `payment_events` per Bogføringsloven.
>
> Everywhere §3 or §4 of this doc references "Watchman anonymise at 90d"
> or "Watchman purge at 365d", read "Watchman purge at anchor=0 days,
> hard-delete, no anonymise." Sentinel-specific analysis remains valid.
> Code reference: `src/db/retention.py::schedule_churn_retention`.

**Status:** Proposal (2026-04-24). Decision-ready, not yet implemented.
**Author:** Application Architect
**Scope:** Where and how retention_jobs rows (`anonymise` / `purge` / `export`) are claimed and executed. DB layer (`src/db/retention.py`) shipped today in `9c58bc6` and is frozen for this proposal.
**Related:** D16 (2026-04-23), `src/db/retention.py`, schema §9 + §10, `docs/architecture/pi5-docker-architecture.md`.

---

## 1. Summary

Run retention execution as a **new timer thread inside the existing `heimdall-scheduler` daemon**, polling every 5 minutes, claiming jobs with an atomic `UPDATE ... RETURNING` that transitions `pending → running` under SQLite's `IMMEDIATE` transaction mode. Execute actions in a `src/retention/` module (new, logic-only; no process lifecycle of its own). Anonymise = null the PII columns on `clients` + `consent_records` + `delivery_log`, preserve `subscriptions` / `payment_events` / invoice-linked columns intact for Bogføringsloven. Purge = hard `DELETE` cascading down all scan/finding/brief/signup/conversion tables for the CVR, but leave `subscriptions` + `payment_events` alive until the 5-year Bogføringsloven window expires (a second, separately-scheduled job). Failure semantics mirror `delivery_retry`: exponential backoff, max 5 attempts, terminal `failed` state surfaced to operator console V6 with a Telegram alert. Valdí Gate 1 review required for the anonymise/purge executors and the final-purge `delete_bookkeeping` path, because they mutate client records and scan data.

---

## 2. Where the cron runs

### Option A — Extend `src/scheduler/` daemon (**RECOMMENDED**)

Add a second timer thread inside `src/scheduler/daemon.py` (peer of the existing monitoring timer at line 45), calling a new `src.retention.runner.tick()` every 300 s.

- Pros
  - Zero new container. `heimdall-scheduler` is already a long-lived Docker service with Redis, `client-data`, `/config`, secrets, and `loguru`→`redis_sink` all wired.
  - Pattern parity: the CT monitoring timer already lives here (see daemon line 45, `_start_monitoring_timer`). This is the same shape.
  - Same `loguru` pipeline → operator console "Logs" view automatically shows retention activity.
  - Graceful shutdown already handled (`_shutdown_requested` flag, SIGTERM handlers).
  - Runs identically on Pi5 and Mac (no cron, no launchd, just the container).
- Cons
  - A deadlocked retention execution could starve the operator-command BRPOP loop if the thread crashes badly (mitigated by running in a dedicated daemon thread with a top-level `try/except`, exactly like the monitoring timer).
  - Scheduler container now owns three concerns (command dispatch, CT polling, retention). Acceptable — all three are "time-based light coordination work". None does heavy CPU.

### Option B — Standalone `src/retention/` module invoked by host cron

A `python -m src.retention.runner --tick` entry point, installed as a 5-min cron on Pi5 and a `make dev-retention-tick` target on Mac.

- Pros
  - Strong isolation: retention failure cannot touch the scheduler.
  - Simpler mental model: "the cron runs this script".
- Cons
  - **Does not satisfy "identically on Pi and Mac"** unless we also introduce a Mac launchd job or Makefile polling. Federico uses Mac as dev — the container-parity argument wins here.
  - New cron surface to forget on a Pi5 rebuild. `scripts/healthcheck.sh` + `scripts/backup.sh` are already crontab residents. Adding a third that silently stops is the exact shipping-theater failure mode we are avoiding.
  - Every tick spins up a Python interpreter + imports `src.db.*`. At 5-min cadence × 288 ticks/day, that's unnecessary overhead. A long-lived thread is free.
  - Does not integrate with `heimdall-logs` / `redis_sink` without extra bootstrapping.

### Option C — Standalone `heimdall-retention` Docker service

Dedicated container with its own `asyncio` loop.

- Pros: maximum isolation, independently scalable.
- Cons: at 5-min cadence on ≤500 clients, a whole container is over-engineering. Pi5 is RAM-constrained. Adds another service to `heimdall-verify-secrets`, another healthcheck, another dozzle stream.
- Verdict: reject for current scale. Revisit at >500 clients.

### Recommendation

**Option A.** It satisfies the "identical on Pi and Mac" constraint, reuses existing logging/secret/shutdown plumbing, mirrors the CT monitoring timer pattern already accepted by the architect, and is the smallest delta. The `src/retention/` module stays action-only (pure functions that take a `conn` + `job_row`), and `daemon.py` is the only process that knows about ticking.

---

## 3. What "anonymise" means

**Scheme proposed:** per-column action based on (a) is this PII, (b) is this legally load-bearing for Bogføringsloven. Literal `'anonymised'` sentinel for searchable text fields; `NULL` for free-form fields; keep for invoice-linked.

### `clients` (primary PII surface)

| Column | Action | Rationale |
|--------|--------|-----------|
| `cvr` | **Keep** | Primary key + Bogføringsloven invoice link. Cannot null without FK avalanche. |
| `company_name` | **Keep** | Bogføringsloven: invoice requires legal name. Also no GDPR risk (public CVR data). |
| `industry_code` | Keep | Public CVR data. |
| `plan` | Keep | Operational history, not PII. |
| `status` | Replace with `'churned'` if not already terminal | Business state. |
| `consent_granted` | Set to `0` | Consent revoked at anonymise time. |
| `telegram_chat_id` | **NULL** | PII, direct identifier. |
| `contact_name` | **NULL** | PII. |
| `contact_email` | **NULL** | PII. |
| `contact_phone` | **NULL** | PII. |
| `contact_role` | **NULL** | PII-adjacent, low value post-churn. |
| `developer_contact` | **NULL** | PII (third-party). |
| `preferred_channel` | Keep | Not PII. |
| `preferred_language` | Keep | Not PII. |
| `technical_context` | Keep | Not PII. |
| `has_developer` | Keep | Not PII. |
| `scan_schedule` | Keep | Not PII. |
| `next_scan_date` | **NULL** | No longer scanning. |
| `notes` | **NULL** | Free-form, may contain PII. |
| `gdpr_sensitive` | Keep | Classification metadata. |
| `gdpr_reasons` | Keep | Classification metadata. |
| `trial_started_at` / `trial_expires_at` | Keep | Aggregate funnel analytics. |
| `onboarding_stage` | Set to `NULL` | Funnel terminal. |
| `signup_source` | Keep | Aggregate analytics. |
| `churn_reason` / `churn_requested_at` / `churn_purge_at` | Keep | Retention audit. |
| `data_retention_mode` | Set to `'anonymised'` | Marker for this job's completion. |
| `created_at` / `updated_at` | Keep / bump `updated_at` | Audit. |

### `client_domains`

| Column | Action |
|--------|--------|
| `domain` | **Keep** (not PII by itself; business asset) |
| `is_primary`, `added_at`, `cvr` | Keep |

Rationale: domain name is public. Removing it would lose the Bogføringsloven "what service did we bill for?" thread.

### `consent_records` (legal evidence)

| Column | Action |
|--------|--------|
| `authorised_domains` | Keep |
| `consent_document` (path) | Keep |
| `consent_date` / `consent_expiry` | Keep |
| `authorised_by_name` / `authorised_by_email` | **NULL** (PII of signing individual) |
| `authorised_by_role` | Keep (role, not person) |
| `status` | Set to `'revoked'` if not already |
| `notes` | **NULL** |

**Note:** the signed PDFs on disk (referenced by `consent_document`) are out of scope for DB anonymise but in scope for Sentinel purge (see §4). Anonymise leaves them in place — they are invoice-linked evidence for Bogføringsloven.

### `delivery_log` (message history)

| Column | Action |
|--------|--------|
| `cvr`, `domain`, `channel`, `message_type`, `scan_id` | Keep |
| `approved_by` | Keep (operator identity, not client PII) |
| `message_hash` | Keep |
| `message_preview` | **NULL** (free-form content, may quote client) |
| `external_id` (Telegram msg id) | **NULL** |
| `sent_at` / `delivered_at` / `read_at` / `replied_at` | Keep (aggregate timing) |
| `error_message` | **NULL** |

### `conversion_events` / `onboarding_stage_log`

| Column | Action |
|--------|--------|
| `cvr`, `event_type`, `source`, `occurred_at`, `from_stage`, `to_stage` | Keep |
| `payload_json` | **NULL** (may contain quoted reply text) |
| `note` (on stage log) | **NULL** |

### `client_cert_snapshots` / `client_cert_changes`

Keep intact **until purge**. Cert SANs and issuer names are not PII of an individual — they are business-level observations. Anonymise does not touch these.

### `scan_history` / `finding_occurrences` / `finding_definitions` / `brief_snapshots`

Scan-side data. Not anonymised at the 30d/90d mark. They are **purge-only** (see §4) because:
- `finding_definitions` is shared across all domains — cannot anonymise per-client
- `scan_history.result_json` and `brief_snapshots.brief_json` may include PII (meta author tags, contact pages), but the D16 policy targets them at purge time, not anonymise
- Keeping scan data during the anonymise window (Watchman: 90d→365d) supports "client reactivates at month 10" reconnection

### Bogføringsloven-protected columns (EXPLICIT FLAG)

These columns on `subscriptions` and `payment_events` **must be preserved intact** through anonymise. Five-year statutory retention from invoice issuance:

- `subscriptions`: every column (`cvr`, `plan`, `status`, `started_at`, `current_period_end`, `cancelled_at`, `invoice_ref`, `amount_dkk`, `billing_period`, `mandate_id`, `created_at`, `updated_at`)
- `payment_events`: every column (`cvr`, `subscription_id`, `event_type`, `amount_dkk`, `external_id`, `occurred_at`, `payload_json`, `created_at`)

`payload_json` on payment_events may contain client bank account fragments (from NETS webhook payloads). This is fine — it is the invoice-linked evidence the statute requires. Do not null.

### Anonymise sequence (recommended, one transaction)

```
BEGIN IMMEDIATE;
UPDATE clients SET telegram_chat_id=NULL, contact_name=NULL, ...
    data_retention_mode='anonymised', updated_at=now WHERE cvr=?;
UPDATE consent_records SET authorised_by_name=NULL, authorised_by_email=NULL,
    notes=NULL, status='revoked' WHERE cvr=?;
UPDATE delivery_log SET message_preview=NULL, external_id=NULL,
    error_message=NULL WHERE cvr=?;
UPDATE conversion_events SET payload_json=NULL WHERE cvr=?;
UPDATE onboarding_stage_log SET note=NULL WHERE cvr=?;
-- DO NOT TOUCH subscriptions, payment_events, finding_*, scan_history,
--             brief_snapshots, client_cert_*
COMMIT;
```

Confidence: **MEDIUM-HIGH.** PII inventory is complete. The grey zone is `scan_history.result_json` and `brief_snapshots.brief_json` — they may contain PII (meta author tags, emails on contact pages scraped during passive Layer 1). Argument for keeping them during anonymise: D16 explicitly says "anonymise PII at 90d, delete at 1yr" for Watchman. "PII" in that decision is structured PII on clients+consent — not free-text scraped content. Scraped content is purged at the `purge` job, not the `anonymise` job. Flagging this for §9.

---

## 4. What "purge" means

**Hard `DELETE`** on rows keyed by `cvr`. Not tombstones — this is a GDPR erasure right and a Bogføringsloven expiry job. Tombstones keep PII by design; wrong tool.

### Cascade plan (executed in one transaction per CVR)

Order matters — delete children before parents to avoid FK violations (noting the schema uses soft FKs via naming convention, not enforced `REFERENCES`, but ordering still matters for logical consistency).

```sql
BEGIN IMMEDIATE;
-- Scan + finding side (all children of CVR)
DELETE FROM finding_occurrences WHERE cvr = ?;
-- finding_status_log: cascaded via occurrence_id — delete orphans separately
DELETE FROM finding_status_log WHERE occurrence_id NOT IN
    (SELECT id FROM finding_occurrences);
DELETE FROM scan_history WHERE cvr = ?;
DELETE FROM brief_snapshots WHERE cvr = ?;

-- CT / cert monitoring
DELETE FROM client_cert_changes WHERE cvr = ?;
DELETE FROM client_cert_snapshots WHERE cvr = ?;

-- Onboarding + funnel
DELETE FROM signup_tokens WHERE cvr = ?;
DELETE FROM conversion_events WHERE cvr = ?;
DELETE FROM onboarding_stage_log WHERE cvr = ?;

-- Delivery + retry
DELETE FROM delivery_retry WHERE delivery_log_id IN
    (SELECT id FROM delivery_log WHERE cvr = ?);
DELETE FROM delivery_log WHERE cvr = ?;

-- Consent audit
DELETE FROM consent_records WHERE cvr = ?;

-- Domains
DELETE FROM client_domains WHERE cvr = ?;

-- The retention_jobs themselves (all jobs for this CVR — keep only the
-- 'purge' row currently executing; mark it completed afterwards)
DELETE FROM retention_jobs WHERE cvr = ? AND id != :current_job_id;

-- Client row itself
UPDATE clients
   SET data_retention_mode = 'purged',
       telegram_chat_id=NULL, contact_name=NULL, contact_email=NULL,
       contact_phone=NULL, notes=NULL, developer_contact=NULL,
       company_name='[purged]',
       updated_at=now
 WHERE cvr = ?;

COMMIT;
```

### Critical: `clients` row NOT deleted at Watchman purge (1yr) either

Two reasons:
1. **Foreign-key integrity with `payment_events` / `subscriptions`.** Even Watchman clients who never paid have no payment_events rows — but the operator console joins `clients` for every historical reference. Losing the row breaks V5 funnel analytics forever.
2. **Future `do_not_contact` / suppression list.** If a Watchman trialist says "never contact me again," we need the CVR on record to block future outreach campaigns.

The row survives, with all PII nulled and `company_name='[purged]'`, and `data_retention_mode='purged'`. This is not a tombstone — it is a scrubbed identifier row.

### Sentinel split: scan data purged at 30d, invoices kept 5y

D16 is explicit: Sentinel cancelled → anonymise at 30d, invoices 5yr. So `schedule_churn_retention` for Sentinel schedules only one anonymise job today. The **second** job (5-year bookkeeping purge) is a policy Federico must decide whether to schedule now or defer:

- **Option 4a (recommended):** At Sentinel cancellation, schedule BOTH jobs: the 30d anonymise AND a 5-year `purge` job. The purge job at year-5 deletes `subscriptions` + `payment_events` + the `clients` row entirely.
- **Option 4b:** Schedule only the 30d anonymise. At year-5 a separate annual sweep detects `data_retention_mode='anonymised'` AND `cancelled_at > 5y ago` AND schedules the final purge.

Option 4a is simpler and self-documenting. Option 4b is more flexible if Bogføringsloven interpretation changes. Flagging for §9.

### What the `purge` action code path actually does

1. Load the retention_jobs row, claim it (see §6), read CVR.
2. Decide sub-mode: is this a **Watchman final purge** (clients row stays, all scan data deleted) or a **Sentinel bookkeeping purge** (5yr mark — delete everything including payment_events)? Distinguished by inspecting `clients.data_retention_mode` + `subscriptions` history.
3. Run the cascade above.
4. `VACUUM` is NOT run inside the same transaction. Freelist reuse is sufficient for weekly cadence. Schedule a monthly `VACUUM` separately if DB bloats beyond target.
5. Mark job `completed`.

Confidence: **MEDIUM.** Cascade order is correct. The "Watchman vs Sentinel purge sub-mode" dispatch is new and not spec'd in D16 — it's an inference from D16's constraints. This deserves explicit Federico sign-off before code.

---

## 5. Failure semantics

Pattern-match against `delivery_retry` (schema §9): `attempt` counter, `next_retry_at`, `status ∈ {pending, succeeded, exhausted}`, `last_error`.

### Proposal

Add **no new table.** Reuse `retention_jobs.notes` + `status` + `executed_at`. Add two new status values:
- `running` — claimed by a cron tick, executing now (see §6 for lock semantics).
- Keep existing `failed` as terminal state after max attempts.

Add one new column via migration (`src/db/migrate.py::_COLUMN_ADDS`): `attempt INTEGER NOT NULL DEFAULT 0`.

### Backoff schedule

| Attempt | Retry after | Rationale |
|---------|-------------|-----------|
| 1 (fail) | +15 min | Transient Redis/disk blip |
| 2 (fail) | +1 h | Something slower |
| 3 (fail) | +4 h | Hardware/DB trouble |
| 4 (fail) | +24 h | Operator needs to wake up |
| 5 (fail) | — terminal `failed` | Manual intervention |

On each failure, the cron tick updates `retention_jobs.scheduled_for = now + backoff`, bumps `attempt`, sets `notes = 'attempt N: <error>'`, reverts `status` to `pending`. On 5th failure, sets `status='failed'`, freezes `scheduled_for`.

### Alerting

On `status='failed'` transition, publish a Redis pub/sub message on channel `operator:retention-alert` with `{cvr, action, scheduled_for, last_error}`. The delivery bot's listener (already subscribed to multiple channels) sends a Telegram message to the operator chat. This is parity with how CT-change publishing fails over today.

Operator console V6 already surfaces the pending queue; extend to also show `failed` jobs with a "Retry" button that resets status → pending + scheduled_for → now.

### Dead-letter

No separate DLQ. The terminal `failed` state IS the dead letter. Rows are never auto-deleted; they stay in `retention_jobs` for audit until an operator manually cancels or retries.

---

## 6. Concurrency + locking

### Today's hole

`list_due_retention_jobs` is a plain `SELECT`. Two cron ticks 1 second apart both see the same pending jobs and both execute them. Double-anonymise is idempotent (setting NULL twice is fine). Double-purge is catastrophic: second tick sees nothing to delete, marks job complete, fine — but if the first tick crashed mid-transaction with partial deletes, the second tick doesn't know to resume cleanly.

In Option A (single scheduler container), two concurrent ticks in the same process is prevented by a `threading.Lock` on the timer. But future-proofing for multiple scheduler replicas, or manual operator-triggered ticks while the timer is running, demands DB-level locking.

### Proposal: `UPDATE ... RETURNING` claim (SQLite 3.35+)

Local SQLite is **3.50.4** (verified). `RETURNING` is supported.

```sql
UPDATE retention_jobs
   SET status = 'running',
       executed_at = ?  -- claim time, not completion time
 WHERE id = (
     SELECT id FROM retention_jobs
      WHERE status = 'pending' AND scheduled_for <= ?
      ORDER BY scheduled_for ASC, id ASC
      LIMIT 1
 )
 RETURNING *;
```

Run inside `BEGIN IMMEDIATE;` so the single writer lock is held for the full claim. Returns the claimed row (or empty — no work).

### Semantic changes

- Introduce `'running'` status. Update `VALID_RETENTION_JOB_STATUSES` in `src/db/retention.py`.
- `list_due_retention_jobs` stays for operator console read-only use. Rename the cron's path to `claim_next_retention_job(conn)` — new function in `src/db/retention.py`, added in a separate commit.
- On process crash mid-execution: next tick sees `status='running'` and ignores. **Add a reaper:** on scheduler startup, run `UPDATE retention_jobs SET status='pending' WHERE status='running'` once. (Scheduler startup is a safe barrier — nothing else is running yet.)
- Executed_at semantics: now "claim time for running, completion time for completed/failed". Document this in the column comment. Alternative: add a `claimed_at` column. Federico's call — flagging for §9.

### Why not `claimed_by` sentinel column

`UPDATE ... RETURNING` is atomic under SQLite's `IMMEDIATE` write lock. A `claimed_by` string column is noise for a single-container deployment. If we ever go multi-scheduler, revisit and add `claimed_by` with a hostname+PID tag so the reaper can distinguish "my old claim" from "peer's in-flight claim". Not today.

---

## 7. Valdí surfaces

Per `CLAUDE.md` hierarchy, Valdí has veto on scan data + client records. Surfaces:

### Gate 1 required (new code must have approval token)

- **`src/retention/anonymise.py::anonymise_client(conn, cvr)`** — mutates `clients` + `consent_records` + `delivery_log` + `conversion_events` + `onboarding_stage_log`. Touches client records. **Must have Gate 1.**
- **`src/retention/purge.py::purge_client(conn, cvr)`** — hard-deletes scan_history + finding_occurrences + brief_snapshots (scan data) + cert snapshots + client-side tables. Scan data deletion. **Must have Gate 1.**
- **`src/retention/purge.py::purge_bookkeeping(conn, cvr)`** (Sentinel 5yr, if Option 4a selected) — deletes `subscriptions` + `payment_events` + final `clients` row. Client records + legal evidence destruction. **Must have Gate 1.**

These three functions should live in their own module (not `src/db/retention.py`, which is pure CRUD and already shipped). Valdí reviews the destructive logic, not the scheduling logic.

### Gate 1 NOT required

- `src/retention/runner.py::tick()` — the loop that claims jobs and dispatches to anonymise/purge. Pure orchestration, no data mutation logic.
- `src/scheduler/daemon.py` timer-thread addition. Scheduling, no data logic.
- The existing `src/db/retention.py` helpers. Already reviewed as part of `9c58bc6` (`schedule_retention_job`, `mark_*`). No destructive execution in them.
- The `retention_jobs` schema itself. Already in `client-db-schema.sql`.

### Forensic logging

Every call to anonymise/purge writes a Valdí forensic log entry via existing `.claude/agents/valdi/logs/` pattern. Payload: `{action, cvr, job_id, rows_affected_per_table, duration_ms, approval_token, executed_at}`. This mirrors the existing scan approval logging. Operator can reconstruct "what did Heimdall delete for CVR X on date Y" for any GDPR erasure-proof request.

---

## 8. Test plan

Reference `tests/test_db_retention.py` for the shape (fixture-based, class-grouped, pytest).

### New test file: `tests/test_retention_runner.py`

Exercises `src/retention/runner.py::tick()` against an in-memory DB seeded with various job states.

| Test class | Cases |
|------------|-------|
| `TestClaim` | (a) claim returns single pending+due job; (b) concurrent claims via two connections return distinct jobs or None; (c) future-dated jobs not claimed; (d) already-running jobs not re-claimed; (e) completed/failed not re-claimed. |
| `TestReaper` | Startup sweep flips `'running'` to `'pending'`; does not touch other statuses. |
| `TestDispatch` | `action='anonymise'` invokes `anonymise_client` exactly once with the correct CVR; `action='purge'` invokes `purge_client`; `action='export'` raises `NotImplementedError` (we don't ship export yet). |
| `TestBackoff` | Failure N sets `scheduled_for` to now + expected delta; bumps `attempt`; leaves `status='pending'`. Fifth failure sets `status='failed'`. |
| `TestAlerting` | Terminal failure publishes to `operator:retention-alert`. Uses a `fakeredis` fixture. |

### New test file: `tests/test_retention_anonymise.py`

| Test class | Cases |
|------------|-------|
| `TestColumnScrub` | After anonymise, `clients.contact_name` is NULL, `consent_records.authorised_by_name` is NULL, `delivery_log.message_preview` is NULL, `conversion_events.payload_json` is NULL. |
| `TestBookkeepingPreserved` | After anonymise, `subscriptions` row for CVR intact; `payment_events` rows intact. Every column byte-identical to pre-anonymise state (assert via SELECT hash). |
| `TestIdempotent` | Calling `anonymise_client` twice is a no-op on second call (NULLs stay NULL). |
| `TestModeTransition` | `clients.data_retention_mode` becomes `'anonymised'`. |
| `TestConsentRevoked` | `consent_records.status` becomes `'revoked'`. |

### New test file: `tests/test_retention_purge.py`

| Test class | Cases |
|------------|-------|
| `TestWatchmanPurge` | After purge, `client_domains`, `scan_history`, `finding_occurrences`, `brief_snapshots`, `client_cert_*`, `signup_tokens`, `conversion_events`, `onboarding_stage_log`, `delivery_log`, `delivery_retry`, `consent_records` all have zero rows for CVR. `clients` row still exists with `company_name='[purged]'` + `data_retention_mode='purged'`. |
| `TestWatchmanLeavesBookkeeping` | After Watchman purge, `subscriptions` + `payment_events` rows for CVR untouched (if any — Watchman typically has none, but confirm via fixture that sets them up anyway). |
| `TestSentinelBookkeepingPurge` | (Only if Option 4a chosen.) After `purge_bookkeeping`, subscriptions + payment_events + clients row all deleted. |
| `TestForeignKeyIntegrity` | After purge, no orphan rows in `finding_status_log` (no occurrence_id references a deleted occurrence). |
| `TestRetentionJobsPreserved` | The currently-executing purge job row is NOT deleted by the cascade (cannot delete ourselves mid-transaction). |

### E2E: extend `make dev-smoke`

New target `make dev-retention-smoke` that:
1. Seeds a synthetic Watchman client (CVR prefix `DRYRUN-RET-`) with scan history + findings + briefs.
2. Calls `schedule_churn_retention(..., anchor_at=now-91d)` (so anonymise is due immediately).
3. Calls `src.retention.runner.tick()` directly (bypasses the 5-min sleep).
4. Asserts client is anonymised, bookkeeping preserved, job row is `completed`.
5. Cleans up by CVR prefix.

Cost guard: zero API calls, no Telegram. Safe to run in CI.

### Property-level check

Add a pytest fixture that, after any retention-executing test, asserts `subscriptions` + `payment_events` for the test CVR are unchanged from a pre-test snapshot. Catches accidental Bogføringsloven violations in future edits.

---

## 9. Open questions for Federico

1. **Purge sub-mode dispatch (§4).** Should the `action='purge'` job distinguish Watchman-final (clients row stays, bookkeeping untouched) from Sentinel-bookkeeping (everything deleted including `payment_events`) by inspecting `clients.data_retention_mode` + subscription history, OR should we add a new action `'purge_bookkeeping'` to `VALID_RETENTION_ACTIONS` and schedule it explicitly? Option 4a vs 4b in §4. Architect leans toward adding `'purge_bookkeeping'` as a distinct action — makes intent readable in the DB. But that touches the already-shipped `VALID_RETENTION_ACTIONS` set.
2. **Sentinel 5-year job — schedule now or sweep later?** At Sentinel cancellation, do we schedule the 5-year bookkeeping purge immediately (predictable, visible in operator console) or run an annual sweep that promotes eligible clients to a new purge job (lazy, flexible if law changes)?
3. **`clients` row final deletion.** Proposal keeps the `clients` row after Watchman purge (PII nulled, `company_name='[purged]'`) to preserve V5 funnel analytics and future do-not-contact blocks. Is that acceptable, or does Federico want a true hard-delete of the clients row at 1yr?
4. **Scan content and anonymise.** `scan_history.result_json` and `brief_snapshots.brief_json` may contain scraped PII (meta author tags, emails from contact pages). D16 is silent on this. Anonymise at 90d/30d, or defer to purge at 365d/5y? Architect leans "defer to purge" — the whole point of a scan archive is replay, and nulling `result_json` kills that. But a conservative reading of GDPR pushes toward anonymise.
5. **`executed_at` column semantics after introducing `'running'`.** Reuse the column for "claim time when running, completion time when done"? Or add a `claimed_at` column via migration? Schema touch is cheap but adds another column the operator console must understand.
6. **Retention for `pipeline_runs` and `finding_definitions`.** These tables are not per-client but contain history. Do we trim them on retention (cross-client rollup), or leave them as "system observability, no PII"? Architect's read: they are system-level and out of scope for D16. Confirm.
7. **Synthetic / dry-run CVRs.** `cert_change_dry_run.py` uses `DRYRUN-` prefix and is self-cleaning. Retention tick will see DRYRUN jobs too. Skip any CVR starting with `DRYRUN-` by convention, or let them exercise the real path? Architect recommends a one-line skip filter in `tick()` — the DRYRUN prefix is already a load-bearing convention.
8. **Export action.** `VALID_RETENTION_ACTIONS` includes `'export'` but D16 does not specify where an export goes, what format, or what auth is required to retrieve it. Scope `'export'` as `NotImplementedError` in the dispatcher for now, or design it in this proposal? Architect recommends: defer. Export is a GDPR data-subject request path, not a churn-retention path — merits its own ADR once the first request arrives.
9. **Alert channel for terminal failures.** Re-use the operator Telegram chat (same `TELEGRAM_OPERATOR_CHAT_ID` that receives Approve/Reject buttons), or dedicated `TELEGRAM_RETENTION_ALERT_CHAT_ID`? Operator chat is simpler; dedicated chat avoids losing a retention failure in scan-approval noise.
