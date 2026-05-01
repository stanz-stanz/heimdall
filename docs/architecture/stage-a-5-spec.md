# Stage A.5 — Audit triggers + RBAC decorator + X-Request-ID middleware — Implementation Spec

**Status:** **READY FOR CODEX REVIEW** — DRAFT v2 with all seven §11 forks resolved (six by Federico on 2026-05-01, one by Valdí on 2026-04-30, ruling `valdi-2026-04-30-audit-retention`). Components and sequencing locked. Implementation PR drafts next after Codex SHIP + Federico ratification.
**Sprint:** Stage A.5 (control-plane guarantees on `feat/stage-a-foundation` after slice 3g.5 ships green). Locked sub-decisions: A.5-format = a (one bundled spec), A.5-deploy = b (one bundled Pi5 cutover), A.5-order = c (audit-triggers + X-Request-ID parallel → RBAC after).
**Author:** Application Architect agent, 2026-04-30 v2 redraft after Codex CHANGES-REQUESTED on v1.
**Master spec:** `docs/architecture/stage-a-implementation-spec.md` — cite by section number; never restate contracts here.
**Parent slice spec:** `docs/architecture/stage-a-slice-3g-spec.md` (auth-plane) and `docs/architecture/stage-a-slice-3g-5-spec.md` (production-deploy gate).
**Locks scope from:** `docs/decisions/log.md` 2026-04-27-evening entries D2 / D3 / D4; 2026-04-23 audit-ownership Option B; 2026-04-28 slice 3g §7.10 legacy retirement; 2026-04-25 Valdí ruling on `consent_records` preservation (decision-log line 454).

> Stage A.5 is **bundled** — three components in one PR. **Internal sequencing:** audit triggers + X-Request-ID middleware land in parallel (no dependency); RBAC decorator lands on top. Splitting any component would leave the audit floor incoherent (no correlation IDs, or no permission stamp on audit rows). **Pi5 deploy:** audit triggers ride the first prod deploy via `init_db()` on writer-container startup; no separate install step.

---

## Summary

Stage A's auth plane (slices 1–3g.5) shipped first-class operator identity, server-side session tickets, immutable audit logs in two databases, an authenticated WebSocket handshake, and a SPA login flow. What it does **not** have:

1. **Tamper-proof capture for config-affecting writes.** Today's audit relies on hand-written `write_console_audit_row` calls. A raw-SQL `cursor.execute("UPDATE config_table ...")` skips the wrapper and produces no audit row. D2 ruled this unacceptable: discipline does not scale.
2. **A permission vocabulary on FastAPI handlers.** Every `/console/*` route is reachable by every authenticated operator. The second operator (e.g. an observer) needs a way to deny `RETENTION_FORCE_RUN` without touching every route.
3. **Cross-DB correlation.** The `request_id` schema columns exist (`console-db-schema.sql:177`, `client-db-schema.sql:1093-1126`); nothing populates them. Forensic reconstruction across two databases is best-effort via timestamp proximity.

Stage A.5 closes all three. Triggers in `clients.db` capture every UPDATE / DELETE on tier-1 tables; the new `command_audit` table captures operator command outcomes; repository wrappers in `src/db/audit_context.py` [NEW] stamp actor / intent / `request_id` into a per-connection TEMP table that the trigger reads. A `Permission` enum + `require_permission` decorator gates HTTP handlers; WS handlers use the same enum via an inline check (§4.2.5). An ASGI middleware generates / propagates `X-Request-ID` into `request.state`, loguru, both audit DBs, and the WebSocket adapter.

After A.5 ships: any operator action reads as one `console.audit_log` row + one `clients.audit_log` / `config_changes` row + N log lines, all stitched by one `request_id`. The gate is a single `@require_permission(Permission.X)` line. V2 onboarding is the first feature that consumes the foundation.

---

## Table of contents

§1 Context · §2 Scope · §3 Sequencing · §4 Component design · §5 Schema deltas · §6 Tests · §7 Dependencies & ordering · §8 Risks · §9 Codex checklist · §10 Follow-ups · §11 Open forks · §12 Internal consistency check.

---

## 1. Context

### 1.1 What Stage A shipped (and what it left for A.5)

Stage A's audit-ownership decision (Option B, master spec §1.3) splits the audit log into two SQLite files so each row commits in the same transaction as the mutation:

- **`console.db` → `audit_log`** owns auth events + `command.dispatch` intent rows.
- **`clients.db` → `audit_log`** owns mutation events on client state.

Both tables already carry a `request_id TEXT` column with a partial index (`docs/architecture/console-db-schema.sql:177-202` and `docs/architecture/client-db-schema.sql:1093-1126`). Empty since slice 3a — Stage A deferred the upstream generator to A.5.

Master spec §11 defers to Stage A.5: `Permission` enum + decorator (§4.2); `command_audit` + `config_changes` tables and triggers (§4.1, §5); X-Request-ID middleware (§4.3); read-side audit (deferred to §10 follow-ups, no fork raised in v2); `/console/config/history` (§10).

### 1.2 Decisions consumed verbatim

- **D2 (`docs/decisions/log.md:196`)** — hybrid audit. DB triggers for capture; repository wrappers for validation, intent, actor / request_id propagation. Wrappers stay because the trigger cannot distinguish operator intents on identical column diffs. The wrapper sets actor / intent / request_id in a per-connection TEMP table (§4.1.3) that the trigger reads.
- **D3 (`docs/decisions/log.md:197`)** — code-backed RBAC v1. `Permission` enum + `require_permission` decorator. Table-backed RBAC deferred until >2 roles.
- **D4 (`docs/decisions/log.md:198`)** — three-sprint sequence Stage A → A.5 → V2.
- **Valdí ruling 2026-04-25 (`docs/decisions/log.md:454`)** — anonymise must NOT touch `authorised_by_name` / `authorised_by_email` on `consent_records`; only `notes` scrubbed, `status` flipped to `'revoked'`. Forensic evidence preservation per §263 / GDPR Art 17(3)(e).
- **Valdí ruling 2026-04-30 (`valdi-2026-04-30-audit-retention`, extends the 2026-04-25 ruling)** — `purge_bookkeeping` may extend to hard-delete `clients.audit_log`, `config_changes`, and `command_audit` rows past +5y, **APPROVE-WITH-CONDITIONS** for all three surfaces. Five binding conditions (per-row `occurred_at` cutoff, summary audit row before DELETEs, `data_retention_mode='hold'` short-circuit, `target_pk` carve-out for orphan rows, Wernblad re-eval to 10y if §263 stk. 3 applies). See §4.1.7 for the spec language and §11.5 for the resolved fork.

### 1.3 What this spec is not

- Not a re-litigation of audit-ownership (Option B locked).
- Not a frontend slice (SPA timeline UI is V2 — §10).
- Not a runtime role-administration UI (D3 deferred).
- Not OpenTelemetry / distributed tracing (single process today).

---

## 2. Scope

### 2.1 In scope (locked)

Three components ship in one PR. **Trigger contract (locked v2):** UPDATE + DELETE on tier-1 tables. INSERT triggers are **not** included; row creation already has a canonical audit shape via the repository wrapper's own write paths (see §4.1.3 for the rationale, §5.1 for the SQL surface). This contract appears identically in §2.1 (here), §4.1 (component design), and §5.1 (schema delta).

| ID | Component | Surface area |
|---|---|---|
| (1) | **Audit triggers + repository wrappers (D2 hybrid).** New `command_audit` and `config_changes` tables in `clients.db` [NEW]. DB triggers AFTER UPDATE / AFTER DELETE on each tier-1 table that read actor / intent / request_id from a per-connection TEMP table. Repository wrappers in `src/db/audit_context.py` [NEW] populate the TEMP table inside a `BEGIN ... COMMIT` block. | New tables (clients.db). New module `src/db/audit_context.py`. Edits to `src/api/console.py` retention + commands handlers; edits to `src/db/clients.py`, `src/db/subscriptions.py`, `src/db/consent.py`, `src/db/signup.py`, `src/db/retention.py` (the last per fork (f) resolution — `retention_jobs` joins tier 1). |
| (2) | **RBAC decorator (D3).** New `Permission` enum in `src/api/auth/permissions.py` [NEW] populated from the actual `/console/*` route inventory (§4.2.1). `require_permission(Permission.X)` decorator on every gated console handler. Single `OPERATOR` role mapping. Audit integration: the permission name lands in `audit_log.action` for every gated mutation. 401 vs 403 semantics enforced. WS gates use the same `Permission` enum but via an inline check (see §4.2.5 — locked v2 contract: WS handlers do **not** use `@require_permission`). | New module `src/api/auth/permissions.py`. Decorator imports added across `src/api/console.py`. |
| (3) | **X-Request-ID middleware.** New ASGI middleware `RequestIdMiddleware` in `src/api/auth/request_id.py` [NEW]. Mounts BEFORE `RequestLoggingMiddleware` and `SessionAuthMiddleware` in `create_app` (`src/api/app.py:394-403`). Generates UUIDv4 when `X-Request-ID` is absent; format-guarded passthrough when present. Threads `request.state.request_id` (HTTP scope) and the WebSocket adapter (slice 3g §4.2). Threads into `logger.bind(context={"request_id": ...})` and into `audit_context.bind_audit_context()` for the trigger. Echoes `X-Request-ID` on every response. | New module `src/api/auth/request_id.py`. Edits to `src/api/app.py:394-403` (mount order). Edit to `src/api/console.py:151-168` (`_WSRequestAdapter`) to populate `state.request_id`. No code change required to `src/api/auth/audit.py` (it already reads `request.state.request_id` per `audit.py:137-140`). |

### 2.2 Out of scope for A.5

| Item | Why excluded | Where it lands |
|---|---|---|
| `/console/config/history` git-shelling endpoint | Read-side; the trigger captures the writes. | V2 or later. §10. |
| Table-backed RBAC | D3 deferred. | When the third role appears. §10. |
| Operator-admin UI (CRUD on operators, role assignment) | Product priority, not architecture. | Post-V2. |
| Read-side audit rows (whoami probes, dashboard fetches) | Master spec §7.3 excluded these from Stage A. | §10 Follow-ups (when operators report a gap). |
| Cross-DB transactional audit (single transaction across both SQLite files) | SQLite WAL does not commit atomically across DB files (master spec §1.3). | Never. |
| OpenTelemetry / distributed tracing | Single-process today. | If Heimdall splits multi-service. |
| Frontend surfacing of `request_id` | The header is set on every response per §4.3.1. | V2 polish. |
| ~~**Audit on file-backed settings**~~ | Was forked at v2 draft (DB triggers can't fire on filesystem writes). **Resolved 2026-05-01: in scope via writer-wrapper, see §4.1.8.** | Remained in §11.2 as resolved-fork rationale-of-record. |

### 2.3 Production-scale framing

Per `feedback_no_pilot_framing` and `feedback_build_for_scale`: this spec assumes Heimdall is running its production load (estimated 200 Sentinel clients × 1 scan/week + ~50 daily operator actions + retention ticks). The audit volume is bounded by operator behaviour, not by client count. If audit volume breaks 1M rows, the scaling lever is partition-by-month, not schema redesign — out of scope here.

---

## 3. Sequencing & dependency graph

### 3.1 Component dependency

```
   Stage A baseline (merged)
   ├── console.db schema + audit writer
   ├── SessionAuthMiddleware mounted
   ├── RequestLoggingMiddleware mounted
   └── clients.db audit_log table exists
                 │
        ┌────────┴────────────┐
        ▼                     ▼
   (1) Audit triggers    (3) X-Request-ID middleware
       + wrappers            (no dep on triggers)
       command_audit         request.state + loguru
       config_changes        + WS adapter
       audit_context.py
        │                     │
        └─────────┬───────────┘
                  ▼
   (2) RBAC decorator
       Permission enum + require_permission
       stamps Permission.value onto audit_log.action
       reads request_id from request.state
                  │
                  ▼
   Pi5 deploy (bundled cutover)
```

### 3.2 Why this order

- **(1) and (3) parallel.** No shared source files; concurrent commits do not collide.
- **(2) after (1) + (3).** The decorator stamps `request_id` (from (3)) into rows that go into `command_audit` (from (1)). Landing it first stamps NULL `request_id` for the entire commit window.

### 3.3 Branching model

Branch: `feat/stage-a-5-audit-rbac-requestid` from `main` post-Stage-A-cutover. Three commits (1)/(3)/(2); PR squashes on merge per CLAUDE.md. Codex review per `feedback_codex_before_commit`.

---

## 4. Component design

> **Section 4.1 trigger contract:** UPDATE + DELETE on tier-1 tables only. INSERT not in scope. This sentence is the binding contract for §4.1, §5.1, and §6.2.

### 4.1 Audit triggers (D2 hybrid)

#### 4.1.1 Two new tables in `clients.db`

`command_audit` captures the operator-command outcome surface. `config_changes` captures every UPDATE / DELETE on config-affecting **DB tables** (see §4.1.2 for the enumerated list). Both live in `clients.db` because both are mutation-event audit rows owned by writer containers + the api per Option B (master spec §1.3).

**Scope boundary, locked v2:** `config_changes` (the trigger-captured table) covers DB-table mutations only. File-backed configuration (the three JSON files written by `src/api/console.py:810-859` — `filters.json` / `interpreter.json` / `delivery.json`) audits via a thin writer-wrapper that emits one `clients.audit_log` row per file write — see §4.1.8. Per fork (b) resolution = (iii) (locked 2026-05-01).

```sql
-- =================================================================
-- SECTION 12 (Stage A.5): Operator command outcome audit
-- =================================================================

CREATE TABLE IF NOT EXISTS command_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL,                       -- ISO-8601 UTC
    command_name    TEXT NOT NULL,                       -- 'run-pipeline', 'interpret', 'send'
    target_type     TEXT,                                -- 'pipeline_run', 'domain', 'delivery', etc.
    target_id       TEXT,                                -- string for type flexibility
    outcome         TEXT NOT NULL,                       -- 'ok', 'error', 'partial'
    payload_json    TEXT,                                -- JSON snapshot of command payload
    error_detail    TEXT,                                -- nullable; populated when outcome != 'ok'
    operator_id     INTEGER,                             -- bare int — see audit_log §1.3
    session_id      INTEGER,                             -- bare int
    request_id      TEXT,                                -- correlates with console.audit_log + clients.audit_log
    actor_kind      TEXT NOT NULL DEFAULT 'operator'     -- 'operator' | 'system'
);

CREATE INDEX IF NOT EXISTS idx_command_audit_occurred
    ON command_audit(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_command_audit_request
    ON command_audit(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_command_audit_command
    ON command_audit(command_name, occurred_at DESC);

-- =================================================================
-- SECTION 13 (Stage A.5): Config-changes audit (trigger-captured)
-- =================================================================
-- Tamper-proof config-write capture. Triggers on every UPDATE / DELETE
-- against tier-1 tables emit one row HERE per mutation. The repository
-- wrapper sets actor / intent / request_id in the per-connection TEMP
-- table _audit_context BEFORE the mutation; the trigger reads the TEMP
-- table into the row. If the wrapper is bypassed, the row still fires
-- — actor columns will be NULL, surfacing the bypass at audit-review
-- time.

CREATE TABLE IF NOT EXISTS config_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL,                       -- ISO-8601 UTC, set by trigger
    table_name      TEXT NOT NULL,                       -- 'clients', 'subscriptions', etc.
    op              TEXT NOT NULL,                       -- 'UPDATE' | 'DELETE' (no INSERT — see §4.1.3)
    target_pk       TEXT NOT NULL,                       -- primary-key value as string
    old_json        TEXT,                                -- JSON snapshot of OLD row
    new_json        TEXT,                                -- JSON snapshot of NEW row (NULL for DELETE)
    intent          TEXT,                                -- repository-supplied intent name (see §4.1.5)
    operator_id     INTEGER,                             -- read from _audit_context TEMP
    session_id      INTEGER,
    request_id      TEXT,
    actor_kind      TEXT NOT NULL DEFAULT 'operator'
);

CREATE INDEX IF NOT EXISTS idx_config_changes_occurred
    ON config_changes(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_config_changes_table
    ON config_changes(table_name, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_config_changes_request
    ON config_changes(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_config_changes_target
    ON config_changes(table_name, target_pk, occurred_at DESC);
```

`command_audit` is INSERT-driven by the api in the same `with conn:` block as the command outcome — no trigger needed because the api owns both writes. `config_changes` is **trigger-driven** because the writer surface is broad (api retention writes, scheduler writes via `src/db/clients.py`, worker hook writes via `src/db/worker_hook.py`); guaranteeing every writer hand-codes the audit row is the discipline-doesn't-scale problem D2 ruled out.

#### 4.1.2 Trigger coverage — which DB tables get triggers

Three tiers of writer surface in `clients.db`. The trigger surface is **tier 1 only** for A.5; tier 2 stays on hand-written `clients.audit_log` rows (§11.6 resolved 2026-05-01 = b: `retention_jobs` joined tier 1; the remaining tier-2 entries below are correct).

**Tier 1 — config-affecting tables (6 tables, triggers required):**

| Table | Why config-affecting | Writer container |
|---|---|---|
| `clients` | Plan changes, churn flips, retention-mode changes are operator-decisive | api (signup), scheduler (lifecycle) |
| `subscriptions` | Billing state machine | api (signup webhook), scheduler (Betalingsservice reconcile) |
| `consent_records` | **Valdí §263 evidence — preservation rule applies (§4.1.7)** | api (signup), scheduler (consent revocation) |
| `signup_tokens` | Magic-link issuance + redemption | api (issuance via `src/db/signup.create_signup_token`); delivery bot (redemption via `src/delivery/bot.py:handle_start_command` → `activate_watchman_trial` — INSERT triggers not installed, so issuance is never trigger-captured; the redemption UPDATE is what fires `trg_signup_tokens_audit_update`). |
| `client_domains` | Authorised-domain scope changes (consent gate input) | api (issuance), scheduler (CT-monitor scoped writes). UPDATE/DELETE writers add their own `bind_audit_context` per call site (none today against tier-1 mutations; trigger is defensive — fires zero rows in current flow). |
| `retention_jobs` | Operator-driven force-run / cancel / retry. Today untracked beyond loguru + free-text `notes` suffix (verified 2026-04-30: `_run_retention_action` at `src/api/console.py:622-654`; `force_run_retention_job` at `src/db/retention.py:320-380`; `retry_failed_retention_job` at `src/db/retention.py:383-437` — none emit `clients.audit_log` rows). Joining tier 1 closes the gap per §11.6 fork (f) = b. CAS UPDATE in `console_retention_cancel` also fires the trigger. | api (operator commands), retention runner (claim + outcome) |

**Tier 2 — operational state machines (no trigger; existing audit_log rows or none):**

| Table | Status | Notes |
|---|---|---|
| `pipeline_runs` | Volume guard. | The run is its own audit. |
| `scan_history` | Volume guard. | |
| `delivery_log` | Volume guard. | |
| `payment_events` | Append-only by Bogføringsloven; UPDATE not part of contract. | If UPDATE happens, that's a violation — caught by trigger if added. |

**Tier 3 — append-only operational logs (no trigger, no audit_log):**

`finding_definitions`, `finding_occurrences`, `finding_status_log`, `brief_snapshots`, `client_cert_snapshots`, `client_cert_changes`, `delivery_retry`, `conversion_events`, `onboarding_stage_log`. Their writes are themselves audit-grade.

#### 4.1.3 Trigger shape — example for `clients`

> **Implementation note (2026-05-01).** The subquery shape shown below (`(SELECT value FROM _audit_context WHERE key='X')`) is illustrative of the value-population pattern. The wire form in the merged code uses `audit_context('X')` calls — see §4.1.10 postscript for the rationale.

One AFTER trigger per (table, operation) pair. **INSERT triggers are not included.** Rationale: a row creation is its own audit when the wrapper writes the canonical creation row (`signup`, `trial.activated`); there is no `OLD` to compare for diff-shape audit, and the canonical creation rows already carry actor/intent. UPDATE and DELETE triggers cover the modify and remove paths.

```sql
-- AFTER UPDATE on clients — one trigger per tier-1 table.
CREATE TRIGGER IF NOT EXISTS trg_clients_audit_update
AFTER UPDATE ON clients
FOR EACH ROW
WHEN (
    -- Skip noise: pure timestamp bumps from refresh_session-style
    -- writes don't change config. The skip predicate lists the
    -- columns that, if they're the ONLY thing that changed, the
    -- trigger should not fire. Maintained alongside the column-add
    -- migrations in src/db/migrate.py.
    OLD.cvr               IS NOT NEW.cvr               OR
    OLD.status            IS NOT NEW.status            OR
    OLD.plan              IS NOT NEW.plan              OR
    OLD.consent_granted   IS NOT NEW.consent_granted   OR
    OLD.monitoring_enabled IS NOT NEW.monitoring_enabled OR
    OLD.data_retention_mode IS NOT NEW.data_retention_mode OR
    OLD.churn_reason      IS NOT NEW.churn_reason      OR
    OLD.churn_purge_at    IS NOT NEW.churn_purge_at    OR
    OLD.onboarding_stage  IS NOT NEW.onboarding_stage  OR
    OLD.trial_started_at  IS NOT NEW.trial_started_at  OR
    OLD.trial_expires_at  IS NOT NEW.trial_expires_at  OR
    OLD.signup_source     IS NOT NEW.signup_source     OR
    OLD.churn_requested_at IS NOT NEW.churn_requested_at
)
BEGIN
    INSERT INTO config_changes (
        occurred_at, table_name, op, target_pk,
        old_json, new_json,
        intent, operator_id, session_id, request_id, actor_kind
    )
    VALUES (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
        'clients',
        'UPDATE',
        NEW.cvr,
        json_object(
            'cvr', OLD.cvr, 'status', OLD.status, 'plan', OLD.plan,
            'consent_granted', OLD.consent_granted,
            'monitoring_enabled', OLD.monitoring_enabled,
            'data_retention_mode', OLD.data_retention_mode,
            'churn_reason', OLD.churn_reason,
            'churn_purge_at', OLD.churn_purge_at,
            'onboarding_stage', OLD.onboarding_stage,
            'trial_started_at', OLD.trial_started_at,
            'trial_expires_at', OLD.trial_expires_at,
            'signup_source', OLD.signup_source,
            'churn_requested_at', OLD.churn_requested_at
        ),
        json_object(
            'cvr', NEW.cvr, 'status', NEW.status, 'plan', NEW.plan,
            'consent_granted', NEW.consent_granted,
            'monitoring_enabled', NEW.monitoring_enabled,
            'data_retention_mode', NEW.data_retention_mode,
            'churn_reason', NEW.churn_reason,
            'churn_purge_at', NEW.churn_purge_at,
            'onboarding_stage', NEW.onboarding_stage,
            'trial_started_at', NEW.trial_started_at,
            'trial_expires_at', NEW.trial_expires_at,
            'signup_source', NEW.signup_source,
            'churn_requested_at', NEW.churn_requested_at
        ),
        (SELECT value FROM _audit_context WHERE key = 'intent'),
        (SELECT value FROM _audit_context WHERE key = 'operator_id'),
        (SELECT value FROM _audit_context WHERE key = 'session_id'),
        (SELECT value FROM _audit_context WHERE key = 'request_id'),
        COALESCE(
            (SELECT value FROM _audit_context WHERE key = 'actor_kind'),
            'operator'
        )
    );
END;

-- AFTER DELETE on clients — purge audit.
CREATE TRIGGER IF NOT EXISTS trg_clients_audit_delete
AFTER DELETE ON clients
FOR EACH ROW
BEGIN
    INSERT INTO config_changes (
        occurred_at, table_name, op, target_pk,
        old_json, new_json,
        intent, operator_id, session_id, request_id, actor_kind
    )
    VALUES (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
        'clients',
        'DELETE',
        OLD.cvr,
        json_object(
            'cvr', OLD.cvr, 'status', OLD.status, 'plan', OLD.plan,
            'consent_granted', OLD.consent_granted,
            'monitoring_enabled', OLD.monitoring_enabled,
            'data_retention_mode', OLD.data_retention_mode,
            'churn_reason', OLD.churn_reason,
            'churn_purge_at', OLD.churn_purge_at,
            'onboarding_stage', OLD.onboarding_stage,
            'trial_started_at', OLD.trial_started_at,
            'trial_expires_at', OLD.trial_expires_at,
            'signup_source', OLD.signup_source,
            'churn_requested_at', OLD.churn_requested_at
        ),
        NULL,
        (SELECT value FROM _audit_context WHERE key = 'intent'),
        (SELECT value FROM _audit_context WHERE key = 'operator_id'),
        (SELECT value FROM _audit_context WHERE key = 'session_id'),
        (SELECT value FROM _audit_context WHERE key = 'request_id'),
        COALESCE(
            (SELECT value FROM _audit_context WHERE key = 'actor_kind'),
            'operator'
        )
    );
END;
```

**Why a `_audit_context` TEMP table not `PRAGMA user_data` or session vars.** SQLite has no per-connection session-variable mechanism that a trigger can read (`PRAGMA user_data` is per-database, not per-connection, and is a single value not a dict). The repository wrapper creates `TEMP TABLE _audit_context (key TEXT PRIMARY KEY, value TEXT)` on the connection (TEMP tables are per-connection-private in SQLite — they vanish when the connection closes, do not appear to other connections). The wrapper UPSERTs the actor / intent / request_id keys at the start of the transaction; the trigger reads them with subqueries. On connection close (every API handler closes its connection in the `finally` block) the temp table drops automatically.

#### 4.1.4 Repository wrappers — `src/db/audit_context.py` [NEW]

> **Implementation note (2026-05-01).** The TEMP-table-based shape shown below was superseded during commit (1) implementation — see §4.1.10 postscript for the UDF replacement. The contract (per-connection scoping, bypass detection via NULL actor columns, exception-safe cleanup) is preserved.

```python
"""Audit-context binding for D2 hybrid trigger-captured writes."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from typing import Iterator

_INIT_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _audit_context (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""


def _ensure_context_table(conn: sqlite3.Connection) -> None:
    conn.execute(_INIT_SQL)


@contextmanager
def bind_audit_context(
    conn: sqlite3.Connection,
    *,
    intent: str,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
    actor_kind: str = "operator",
) -> Iterator[sqlite3.Connection]:
    """Bind audit context for trigger reads. Clears on exit."""
    _ensure_context_table(conn)
    rows = [
        ("intent", intent),
        ("operator_id", str(operator_id) if operator_id is not None else None),
        ("session_id", str(session_id) if session_id is not None else None),
        ("request_id", request_id),
        ("actor_kind", actor_kind),
    ]
    try:
        for key, value in rows:
            if value is None:
                conn.execute("DELETE FROM _audit_context WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO _audit_context (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
        yield conn
    finally:
        for key, _ in rows:
            try:
                conn.execute("DELETE FROM _audit_context WHERE key = ?", (key,))
            except sqlite3.Error:
                pass
```

If the wrapper is bypassed (raw `cursor.execute` outside the context manager), the trigger still fires but actor columns are NULL — forensically detectable at audit-review time. **Sweep checklist.** Every `clients.db` mutation handler converts to call `with bind_audit_context(...)` before `with conn:`. Per-file list in §6.4.

#### 4.1.5 Intent vocabulary

Each repository wrapper passes a hand-coded `intent` string (e.g. `retention.force_run`, `retention.cancel`, `trial.activated`, `retention.anonymise`, `subscription.created`, `subscription.cancelled`). The trigger reads it into `config_changes.intent`. This is application-level intent, distinct from `op` (UPDATE / DELETE). The vocabulary is grep-able; no enum (premature ceremony for a string-typed column).

**Runner-introduced cron intents (commit (1) wrapper sweep, locked 2026-05-02):** `retention.reap`, `retention.claim`, `retention.dryrun_skip`, `retention.<action>` (where `action ∈ {anonymise, purge, purge_bookkeeping, export}`), `retention.backoff`, `retention.terminal_fail`. All emitted by `src/retention/runner.py:tick` with `actor_kind='system'`. The cascade DELETEs inside `purge_client` (consent_records, signup_tokens, client_domains, retention_jobs siblings) inherit the `retention.purge` intent — one logical step → N trigger rows, all uniformly stamped, single grep reconstructs the cascade.

**Known bypass-row writers (NULL actor / NULL intent on the trigger row, by design):**

- `src/client_memory/trial_expiry.py:126` flips `clients.status` from `watchman_active` → `watchman_expired` from a scheduler sweep. High-frequency. Stage A.5 commit (1) leaves this unwrapped — bypass-detection contract holds (NULL actor signals the writer needs review). Wrap with `intent='trial.expired'`, `actor_kind='system'` in commit (2) or (3) if the operator-console timeline UX needs the attribution.
- Operator-set `data_retention_mode='hold'` via raw SQL (V2 will replace with a structured `retention_holds` table per §10) — the manual UPDATE fires `trg_clients_audit_update` with NULL actor. That is the right outcome: hold flips are forensically interesting and should leave a NULL-actor breadcrumb. Do not silently wrap when V2 lands.

#### 4.1.6 `command_audit` writer

`command_audit` is api-INSERT-driven, not trigger-driven, because the api owns the command-dispatch surface end-to-end. A new helper `write_command_audit_row` lives in `src/db/audit.py` [NEW file]:

```python
def write_command_audit_row(
    conn: sqlite3.Connection,
    *,
    command_name: str,
    outcome: str,                                  # 'ok' | 'error' | 'partial'
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict | None = None,
    error_detail: str | None = None,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
    actor_kind: str = "operator",
) -> int:
    """INSERT one row into clients.db command_audit. Caller commits."""
    ...
```

Pair shape (pre-existing pattern from master spec §1.3.b):
- `console.audit_log` row: `action='command.dispatch'`, `target_type='command'`, `target_id=command_name`, `request_id=<rid>`. Written by api in `console_command` handler (`src/api/console.py:862`).
- `command_audit` row: `command_name=<name>`, `outcome='ok'|'error'`, `request_id=<same rid>`. Written by scheduler / worker on command completion.

#### 4.1.7 Forensic preservation — Valdí §263 + GDPR Art 17(3)(e) [RESOLVED 2026-04-30]

Per the 2026-04-25 Valdí ruling (`docs/decisions/log.md:454`), `consent_records` PII is preserved through anonymise; only `notes` is scrubbed and `status` is flipped to `'revoked'`. **A.5's audit triggers ride this rule for `consent_records` itself:** triggers on `consent_records` fire on the anonymise UPDATE; the trigger inserts into `config_changes` with `intent="retention.anonymise"`, `old_json` snapshotting all preserved columns, `new_json` snapshotting the post-revoke state.

**Audit-row preservation horizon — extended ruling (Valdí, 2026-04-30, ruling id `valdi-2026-04-30-audit-retention`).** `clients.audit_log`, `config_changes`, and `command_audit` rows are preserved through `anonymise` and through `purge` (both Watchman hard-delete and Sentinel post-anonymise client-row purge). They are **conditionally hard-deletable by `purge_bookkeeping` at +5y from the row's `occurred_at`**, scoped by CVR correlation (`target_pk` for `config_changes` / `command_audit`; `target_id` for `clients.audit_log`'s CVR-typed rows) and gated by the `clients.data_retention_mode != 'hold'` flag. The horizon is defensible under Straffeloven §93 stk. 1 nr. 1 (2y limitation for §263 stk. 1 — the 5y horizon covers it with margin) and is borrowed from Bogføringsloven's 5y window for handler convenience, **not** as a Bogføringsloven retention obligation per se. If Wernblad confirms §263 stk. 3 (aggravated) plausibly applies to Heimdall's scanning posture, the horizon raises uniformly to 10y; the carve-out shape is unchanged. The retention basis against a data subject's GDPR Art. 17 erasure request is Art. 17(3)(e) — necessary for fastlæggelse / gennemførelse / forsvar af retskrav.

**Carve-outs (binding).**

1. `purge_bookkeeping` MUST filter by `WHERE occurred_at < cutoff` for all three audit DELETEs. A blanket `WHERE cvr = ?` would over-delete still-evidentiary rows on long-lived CVRs. The existing `payment_events` / `subscriptions` DELETEs do not need the filter (every row is past cutoff by construction); the audit DELETEs do.
2. `purge_bookkeeping` MUST emit a single `clients.audit_log` summary row (`action='retention.bookkeeping_purge'`, `actor_kind='system'`, `target_type='cvr'`, `target_id=<cvr>`, `payload_json={"deleted_counts": {...}, "occurred_at_cutoff": "<ISO>"}`) BEFORE the audit DELETEs run. The summary row survives one cycle, deleted by the next.
3. `purge_bookkeeping` MUST short-circuit the entire run when `clients.data_retention_mode='hold'` for the target CVR. (Manual hold flag until V2 ships a structured `retention_holds` table.)
4. `config_changes` orphan rows (no CVR correlation via `target_pk`) are NOT touched by `purge_bookkeeping`. Their retention is governed by a separate data-minimisation cron (out of scope for A.5).
5. The Valdí preservation rule (anonymise + purge MUST NOT touch any of the three surfaces) is unchanged. `purge_bookkeeping` is the **single permitted writer** for these DELETEs.

**Anti-violation.** Any future PR that proposes deletion of audit rows from any handler other than `purge_bookkeeping`, or proposes shortening the +5y horizon, or proposes removing the `data_retention_mode='hold'` short-circuit, MUST re-route through Valdí Gate review, not architecture. This is binding per `feedback_valdi_guidance_non_overridable`.

**Current code surface (verified 2026-04-30).** `purge_bookkeeping` (`src/retention/actions.py:554-599`) DELETEs from `payment_events` and `subscriptions` only. A.5 extends it to add the three audit-row DELETEs per the carve-outs above. `anonymise_client` (`src/retention/actions.py:150-364`) and `purge_client` (`src/retention/actions.py:373-546`) remain Valdí-preserved and do NOT touch `clients.audit_log` / `config_changes` / `command_audit`.

#### 4.1.8 File-backed settings writer-wrapper (fork (b) = (iii))

`/console/settings/{name}` (PUT, `src/api/console.py:810-859`) writes JSON files to `config/` (`filters.json` / `interpreter.json` / `delivery.json`). DB triggers cannot fire on filesystem writes; per fork (b) resolution = (iii) (locked 2026-05-01), a thin writer-wrapper at the route handler level emits one `clients.audit_log` row per file write.

**Wrapper contract:**

- Read the existing file (if present); compute `old_sha256 = hashlib.sha256(content).hexdigest()`.
- Atomic-write the new content using the same `tempfile.NamedTemporaryFile + Path.rename` pattern the current PUT handler already uses at `src/api/console.py:838` (no separate helper today; A.5 keeps the inline pattern, just wrapped with sha256 capture + audit row).
- Compute `new_sha256` from the new content.
- If `old_sha256 == new_sha256` (no-op write), skip the audit row.
- Otherwise INSERT one row into `clients.audit_log`:
  - `action = 'config.file_write'`
  - `target_type = 'settings_file'`
  - `target_id = <filename>` (e.g. `'filters.json'`)
  - `payload_json = {"old_sha256": "<digest|null>", "new_sha256": "<digest>"}`
  - `operator_id`, `session_id`, `request_id` from `request.state` (the X-Request-ID middleware populates `request_id`).

The wrapper opens `clients.db` after the file write succeeds; writes the audit row in a `with conn:` block. The audit write is NOT wrapped in `bind_audit_context` because `clients.audit_log` is hand-written today (no trigger), and the wrapper supplies all columns directly.

**Bypass detectability.** Direct file edits (operator SSH onto Pi5, manual `cat > config/filters.json`) bypass the wrapper and produce no audit row. The bypass is detectable via filesystem inotify or a periodic SHA-comparison job (out of scope for A.5; flag for V2).

**Tests.** `tests/test_settings_audit_writer.py` [NEW, ~80 LOC]:

- `test_settings_put_writes_audit_row` — PUT `/console/settings/filters` with new content → file changes + one `clients.audit_log` row with both SHA-256 digests + `request_id` populated.
- `test_settings_put_no_change_skips_audit` — PUT identical content → no audit row.
- `test_settings_put_records_request_id` — PUT with `X-Request-ID: abc-123` header → audit row `request_id` exactly matches.
- `test_settings_put_initial_write_old_sha_null` — first-ever PUT (no existing file) → audit row `payload_json.old_sha256 = null`, `new_sha256` populated.

#### 4.1.9 Migration entry points

`src/db/migrate.py` needs:

- `_TABLE_ADDS` (new — does not exist today; today the file has `_COLUMN_ADDS` and `_INDEX_ADDS`) entries for `command_audit` and `config_changes`.
- `_TRIGGER_ADDS` (new) list of `CREATE TRIGGER IF NOT EXISTS` statements, one per (table, op) pair across the 6 tier-1 tables × 2 ops = 12 triggers.
- All entries idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE TRIGGER IF NOT EXISTS`). Re-running `init_db()` on every container start is safe.

The schema additions ride the **first prod deploy of the Stage A.5 PR** via the standard `init_db()` path on container startup. There is no separate "install triggers" runbook step.

#### 4.1.10 Postscript — TEMP-table → UDF pivot (locked 2026-05-01 during implementation)

§4.1.3 and §4.1.4 above describe the locked design: a per-connection `_audit_context` TEMP table that triggers on `clients` / `subscriptions` / `consent_records` / `signup_tokens` / `client_domains` / `retention_jobs` read via subqueries. **That design does not work in stock SQLite.** Verified empirically during commit (1) implementation: triggers raise `sqlite3.OperationalError: no such table: main._audit_context` on first fire. Cause: SQLite documents at https://www.sqlite.org/lang_createtrigger.html that "It is not valid to refer to temporary tables [...] from within the trigger body" when the trigger itself is on a non-temp table. SQLite searches `main` first and refuses to fall through to the temp schema.

**Replacement (Codex-confirmed, Federico-approved 2026-05-01).** The four `(SELECT value FROM _audit_context WHERE key='X')` subqueries in every trigger become `audit_context('X')` calls. `audit_context` is a per-connection user-defined SQL function registered via `sqlite3.Connection.create_function` from `src/db/audit_context.install_audit_context`. The function reads from per-connection state living on a `HeimdallConnection` subclass attribute (`conn._audit_ctx` — a dict; the subclass adds `__dict__` which the base `sqlite3.Connection` does not expose).

**Mandatory registration.** Every write-capable connection MUST have `audit_context` registered before any audited DML fires. The canonical path is `src.db.connection.init_db`, which calls `install_audit_context(conn)` after PRAGMA setup and **before** the schema bundle's `executescript()` (the bundle defines triggers but contains no DML, so registration timing is not load-bearing today; registering early guards against any future SQLite tightening or against bundle-time DML being added). Connections opened outside `init_db` (raw `sqlite3.connect`) skip registration and crash at first trigger fire — that is intentional fail-fast behaviour.

**Type contract.** The UDF returns native Python `int` for `operator_id` / `session_id` (INTEGER columns), TEXT for `intent` / `request_id` / `actor_kind`. Returning native ints rather than stringified `'42'` avoids SQLite's silent type-coercion failure on malformed values (`''`, `'user-42'`, whitespace).

**Files affected by the pivot.** 1) `docs/architecture/client-db-schema.sql` SECTION 14 — all 12 triggers updated. 2) `src/db/migrate.py:_TRIGGER_ADDS` — same change. 3) `src/db/audit_context.py` — `bind_audit_context` now manipulates `conn._audit_ctx` instead of UPSERTing into the TEMP table; the `_INIT_SQL = "CREATE TEMP TABLE..."` block is deleted. 4) `src/db/connection.py` — adds `class HeimdallConnection(sqlite3.Connection)` and passes `factory=HeimdallConnection` to `sqlite3.connect`; calls `install_audit_context(conn)` after PRAGMA setup, before the schema bundle's `executescript`.

**Bypass detection contract preserved.** A wrapper-bypass UPDATE (no `with bind_audit_context`) still fires the trigger; `audit_context()` returns `None` for every key because `conn._audit_ctx` is empty. Actor columns land NULL — forensically detectable at audit-review time, identical to the original design.

**Testing.** `tests/test_audit_context.py` (6 cases, all green) and `tests/test_command_audit_writer.py` (6 cases, all green) cover the pivot. The original test names (e.g. `test_bind_audit_context_temp_table_is_per_connection`) describe the contract not the mechanism — they pass against the new implementation because per-connection scoping is preserved.

**§4.1.3 trigger SQL example status.** The clients UPDATE / DELETE example at lines 245-356 above shows the pre-pivot subquery shape. Treat it as illustrative of the trigger's value-population pattern (intent / operator_id / session_id / request_id / actor_kind) — the exact wire form in the merged code uses `audit_context('intent')` etc. per this postscript.

### 4.2 RBAC decorator (D3)

#### 4.2.1 `Permission` enum — derived from current route inventory

Read of `src/api/console.py` + `src/api/routers/auth.py` + `src/api/signup.py` produces this exact route surface (verified 2026-04-30 against the slice 3g.5 baseline):

**Console routes (gated, require `Permission.X`):**

| Route | Method | Source line | Permission |
|---|---|---|---|
| `/console/status` | GET | `src/api/console.py:89` | `CONSOLE_READ` |
| `/console/dashboard` | GET | `src/api/console.py:252` | `CONSOLE_READ` |
| `/console/pipeline/last` | GET | `src/api/console.py:323` | `CONSOLE_READ` |
| `/console/campaigns` | GET | `src/api/console.py:350` | `CONSOLE_READ` |
| `/console/campaigns/{campaign}/prospects` | GET | `src/api/console.py:374` | `CONSOLE_READ` |
| `/console/briefs/list` | GET | `src/api/console.py:415` | `CONSOLE_READ` |
| `/console/clients/list` | GET | `src/api/console.py:460` | `CONSOLE_READ` |
| `/console/clients/trial-expiring` | GET | `src/api/console.py:565` | `CONSOLE_READ` |
| `/console/clients/retention-queue` | GET | `src/api/console.py:592` | `CONSOLE_READ` |
| `/console/retention-jobs/{id}/force-run` | POST | `src/api/console.py:657` | `RETENTION_FORCE_RUN` |
| `/console/retention-jobs/{id}/cancel` | POST | `src/api/console.py:682` | `RETENTION_CANCEL` |
| `/console/retention-jobs/{id}/retry` | POST | `src/api/console.py:771` | `RETENTION_RETRY` |
| `/console/settings` | GET | `src/api/console.py:796` | `CONSOLE_READ` |
| `/console/settings/{name}` | PUT | `src/api/console.py:810` | `CONFIG_WRITE` |
| `/console/commands/{command}` | POST | `src/api/console.py:862` | `COMMAND_DISPATCH` |
| `/console/logs` | GET | `src/api/console.py:891` | `CONSOLE_READ` |
| `/console/ws` | WS | `src/api/console.py:926` | `CONSOLE_READ` (inline gate, §4.2.5) |
| `/console/briefs` | GET | `src/api/console.py:1066` | `CONSOLE_READ` |
| `/console/demo/start` | POST | `src/api/console.py:1088` | `DEMO_RUN` |
| `/console/demo/ws/{scan_id}` | WS | `src/api/console.py:1110` | `DEMO_RUN` (inline gate, §4.2.5) |

**Public / non-gated routes (no decorator):**

| Route | Method | Source line | Why public |
|---|---|---|---|
| `/console/auth/login` | POST | `src/api/routers/auth.py:217` | Issues the cookie |
| `/console/auth/logout` | POST | `src/api/routers/auth.py:381` | Session-only (cookie + CSRF), no permission gate |
| `/console/auth/whoami` | GET | `src/api/routers/auth.py:436` | 4-state probe |
| `/signup/validate` | POST | `src/api/signup.py:55` | Origin-allowlisted; no operator gate |
| `/health` | GET | `src/api/app.py:421` | Liveness probe |
| `/results/{client_id}` | GET | `src/api/app.py:440` | Client-scoped (separate auth model, master spec §6) |
| `/results/{client_id}/{domain}/dates` | GET | `src/api/app.py:458` | Same |
| `/results/{client_id}/{domain}` | GET | `src/api/app.py:468` | Same |

**Permission count: 7 — listed below.** Each permission gates one or more routes from the table above. Mapping route → permission appears in §4.2.1 (this section); enum definition appears in §4.2.1 below; assertion of the count appears in §4.2.5 and §12.

```python
# src/api/auth/permissions.py [NEW]
from enum import Enum


class Permission(str, Enum):
    """Code-backed permission vocabulary for FastAPI handlers.

    Stage A.5 D3 (locked 2026-04-27 evening): table-backed RBAC is
    deferred until Heimdall has more than two real roles or requires
    runtime role administration. The single ``OPERATOR`` role mapping
    in ``ROLE_PERMISSIONS`` grants every permission below.

    Each permission stamps onto ``audit_log.action`` (console.db) and
    ``command_audit.command_name`` (clients.db) for the gated mutation,
    so the audit timeline reads as the permission name rather than a
    free-text route literal.
    """

    # Read surface (most of the console)
    CONSOLE_READ = "console.read"

    # Retention controls — three permissions kept per fork (c) = 7
    # (RESOLVED 2026-05-01).
    RETENTION_FORCE_RUN = "retention.force_run"
    RETENTION_CANCEL = "retention.cancel"
    RETENTION_RETRY = "retention.retry"

    # Config writes — DB tables only via this gate. File-backed
    # settings audited via the §4.1.8 writer-wrapper (separate audit
    # surface; same `CONFIG_WRITE` gate covers both writes).
    CONFIG_WRITE = "config.write"

    # Command dispatch
    COMMAND_DISPATCH = "command.dispatch"

    # Demo replay
    DEMO_RUN = "demo.run"


# Single role in v1 (D3). Maps OPERATOR → all permissions.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "operator": frozenset(Permission),
    # Future: 'observer': frozenset({Permission.CONSOLE_READ}),
}
```

The 7 permissions are:
1. `CONSOLE_READ` (gates 13 GET / WS routes from the table above)
2. `RETENTION_FORCE_RUN` (1 route)
3. `RETENTION_CANCEL` (1 route)
4. `RETENTION_RETRY` (1 route)
5. `CONFIG_WRITE` (1 route)
6. `COMMAND_DISPATCH` (1 route)
7. `DEMO_RUN` (2 routes — POST + WS)

7 permissions × routes = 20 gates total. (The route inventory is 20 console routes; `DEMO_RUN` covers two — POST + WS — and the other six permissions each gate exactly one route. 13 + 1 + 1 + 1 + 1 + 1 + 2 = 20 gates from 7 permission values across 20 routes.)

#### 4.2.2 `require_permission` decorator

Decorator contract (full implementation in `src/api/auth/permissions.py` [NEW]):

- Extract `Request` from kwargs (FastAPI inject) or args (positional). If none → `RuntimeError` at call (programming error, surfaces in pytest collection).
- Read `operator_id`, `session_id`, `role_hint` from `request.state`.
- If `operator_id is None` → `HTTPException(401, "not_authenticated")` (defense-in-depth; middleware should have already 401'd).
- If `permission not in ROLE_PERMISSIONS.get(role_hint or "", frozenset())` → write `auth.permission_denied` audit row to `console.audit_log` via `write_console_audit_row(conn, request, action="auth.permission_denied", target_type="permission", target_id=permission.value, payload={"role_hint": role_hint}, operator_id=operator_id, session_id=session_id)` then `HTTPException(403, {"error": "permission_denied", "permission": permission.value})`.
- On allow, await handler with original args/kwargs.

The audit-write `conn` opens via `get_console_conn(request.app.state.console_db_path)` and closes in a `finally`. The audit write commits via `with conn:`.

#### 4.2.3 Decorator placement on every gated handler

```python
# src/api/console.py — after Stage A.5
from src.api.auth.permissions import Permission, require_permission

@router.get("/dashboard")
@require_permission(Permission.CONSOLE_READ)
async def console_dashboard(request: Request):
    ...

@router.post("/retention-jobs/{job_id}/force-run")
@require_permission(Permission.RETENTION_FORCE_RUN)
async def console_retention_force_run(job_id: int, request: Request):
    ...
```

Decorator goes **inside** the FastAPI router decorator (`@router.get` outermost; `@require_permission` next).

#### 4.2.4 401 vs 403 semantics

| Condition | Status | Body | Audit row |
|---|---|---|---|
| No session cookie / cookie does not validate | 401 | `{"error": "not_authenticated"}` | None (middleware path) |
| Cookie validates, role_hint not in `ROLE_PERMISSIONS` | 403 | `{"error": "permission_denied", "permission": "<value>"}` | `auth.permission_denied` in console.audit_log |
| Cookie validates, permission in role mapping | per handler | per handler | per handler |

#### 4.2.5 WebSocket auth + permission — locked v2: inline gate, no decorator

**Locked v2 contract:** WebSocket handlers (`/console/ws`, `/console/demo/ws/{scan_id}`) do NOT use `@require_permission`. They perform an inline permission check inside `_authenticate_ws` (`src/api/console.py:176-249`). This is intentional, not an oversight, and §9 below does NOT claim parity between HTTP and WS gates.

**Why inline, not decorator.** The decorator pulls `request: Request` out of FastAPI's kwargs to read `state.operator_id` and write the denial audit row. WebSocket handlers receive `websocket: WebSocket`, not `Request`, and the slice-3g `_WSRequestAdapter` (`src/api/console.py:151-168`) is constructed inside the handler — there is no `request` argument to pull from. Rewriting `require_permission` to switch on parameter type (Request vs WebSocket) would conflate two distinct call patterns: (a) HTTP middleware has already populated `request.state` before the decorator runs; (b) WS auth runs inside the handler after `websocket.accept()`. The inline check uses the same `Permission` enum + `ROLE_PERMISSIONS` mapping; the audit row uses the same `auth.permission_denied` action; only the call shape differs.

**Inline check, after `validate_session_by_hash` succeeds in `_authenticate_ws`:**

```python
operator_role = _fetch_role_hint(conn, operator_id)
if Permission.CONSOLE_READ not in ROLE_PERMISSIONS.get(operator_role, frozenset()):
    with conn:
        write_console_audit_row(
            conn,
            pseudo_request,
            action="auth.permission_denied",
            target_type="permission",
            target_id=Permission.CONSOLE_READ.value,
            payload={"role_hint": operator_role},
            operator_id=operator_id,
            session_id=session_id,
        )
    await websocket.accept()
    await websocket.close(code=4403)  # WS analogue of HTTP 403
    return None
```

The demo WS endpoint check uses `Permission.DEMO_RUN`. **Close code 4403** is the WS-protocol analogue of HTTP 403; RFC 6455 reserves 4000-4999 for application use; slice 3g uses 4401 for unauthenticated.

**Permission count assertion:** the same 7 `Permission` enum values are used by both HTTP decorator gates and WS inline gates. `CONSOLE_READ` and `DEMO_RUN` appear in WS code paths; the other 5 are HTTP-only.

#### 4.2.6 Public surfaces stay public

Per the public-route table in §4.2.1: `/console/auth/login`, `/console/auth/whoami`, `/console/auth/logout`, `/signup/validate`, `/health`, `/results/*`, `/static/*`, the SPA shell + assets — none of these get a decorator. They are middleware-bypassed. The decorator is for the **gated** surface only.

`/console/auth/logout` is **session-only** — middleware-protected (cookie + CSRF), but no permission gate.

### 4.3 X-Request-ID middleware

#### 4.3.1 Wire contract

Inbound:
- `X-Request-ID` header present and matches `^[A-Za-z0-9_-]{1,128}$` → use it verbatim.
- Header present but malformed (length / charset) → ignore, generate UUIDv4.
- Header absent → generate UUIDv4.

Outbound: every response carries `X-Request-ID: <value>` in headers.

The format-guard prevents header-splitting (`\r\n` injection) or 4096-character strings polluting the audit log. The 128-char cap matches sensible distributed-tracing IDs (W3C `traceparent` is 55 chars). The character class `[A-Za-z0-9_-]` covers UUID, ULID, hex, base64url-without-padding.

#### 4.3.2 Module shape — `src/api/auth/request_id.py` [NEW]

```python
"""X-Request-ID middleware. Mounts before RequestLogging + SessionAuth."""
from __future__ import annotations
import re
import uuid
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_or_generate(value: str | None) -> str:
    if value and _REQUEST_ID_PATTERN.match(value):
        return value
    return str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw = headers.get(REQUEST_ID_HEADER.encode("latin-1"))
        request_id = _validate_or_generate(
            raw.decode("latin-1", errors="replace") if raw else None
        )
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.append(
                    (REQUEST_ID_HEADER.encode("latin-1"),
                     request_id.encode("latin-1"))
                )
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
```

#### 4.3.3 Mount order in `create_app`

`src/api/app.py:394-403` becomes:

```python
# Order matters: RequestIdMiddleware mounts FIRST (outermost) so every
# other middleware + handler sees request.state.request_id already
# populated. Starlette / FastAPI add_middleware pushes onto the head
# of the stack — the LAST add_middleware call is the OUTERMOST.
app.add_middleware(
    SessionAuthMiddleware,
    console_db_path=app.state.console_db_path,
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
```

#### 4.3.4 Loguru `logger.bind` integration

Codebase uses **loguru** (verified — `src/api/app.py` imports `from loguru import logger`; no structlog imports anywhere in `src/`). The Stage A.5 edit to `RequestLoggingMiddleware.dispatch` reads `request_id = getattr(request.state, "request_id", None)` and adds `"request_id": request_id` to the existing `logger.bind(context={...})` dict for both `http_request` and `http_error` log lines. Per-handler log lines stay as-is for A.5 per §11.7 resolution = A (Federico 2026-05-01); the auto-injection move is option C, flagged as follow-up.

#### 4.3.5 Audit writer integration

`src/api/auth/audit.py:137-140` already reads `request.state.request_id` if not explicitly passed. With the middleware mounted, `write_console_audit_row` needs no code change. The `audit_context.py` wrapper accepts `request_id` as a kwarg and threads it into the trigger via `_audit_context`. Caller pattern (retention force-run example):

```python
@router.post("/retention-jobs/{job_id}/force-run")
@require_permission(Permission.RETENTION_FORCE_RUN)
async def console_retention_force_run(job_id: int, request: Request):
    request_id = getattr(request.state, "request_id", None)
    operator_id = getattr(request.state, "operator_id", None)
    session_id = getattr(request.state, "session_id", None)
    # ... open conn, then:
    with bind_audit_context(
        conn,
        intent="retention.force_run",
        operator_id=operator_id,
        session_id=session_id,
        request_id=request_id,
    ):
        with conn:
            updated = force_run_retention_job(conn, job_id)
```

#### 4.3.6 WebSocket integration

`_WSRequestAdapter` (`src/api/console.py:151-168`) currently exposes `client`, `headers`, `state=SimpleNamespace()` (empty). A.5 edit: read `websocket.headers.get("x-request-id")`, pass through `_validate_or_generate` from `request_id.py`, set `state = SimpleNamespace(request_id=<value>)`. The `liveops.ws_connected` audit row then carries `request_id` automatically (audit writer reads `request.state.request_id`).

---

## 5. Schema deltas

> **Trigger contract for §5.1:** UPDATE + DELETE on tier-1 tables. INSERT not in scope. Identical statement appears in §2.1 and §4.1.

All schema additions are **idempotent** (`CREATE TABLE / TRIGGER / INDEX IF NOT EXISTS`) and ride `init_db()` on writer-container startup.

### 5.1 `clients.db` additions

Append to `docs/architecture/client-db-schema.sql` after SECTION 11 (existing audit_log block):

- **SECTION 12 — `command_audit` table.** Schema and indexes per the SQL block in §4.1.1 (lines 188-214 of this spec). 12 columns, 3 indexes (`occurred_at`, `request_id` partial, `command_name + occurred_at`).
- **SECTION 13 — `config_changes` table.** Schema and indexes per the SQL block in §4.1.1. 12 columns, 4 indexes (`occurred_at`, `table_name + occurred_at`, `request_id` partial, `table_name + target_pk + occurred_at`).
- **SECTION 14 — `config_changes` triggers.** AFTER UPDATE + AFTER DELETE per tier-1 table. INSERT triggers omitted per §4.1.3. 6 tier-1 tables × 2 ops = 12 triggers:

  ```
  trg_clients_audit_update           trg_clients_audit_delete
  trg_subscriptions_audit_update     trg_subscriptions_audit_delete
  trg_consent_records_audit_update   trg_consent_records_audit_delete
  trg_signup_tokens_audit_update     trg_signup_tokens_audit_delete
  trg_client_domains_audit_update    trg_client_domains_audit_delete
  trg_retention_jobs_audit_update    trg_retention_jobs_audit_delete
  ```

  Each trigger follows the shape of `trg_clients_audit_update` in §4.1.3 — it reads from `_audit_context` and INSERTs into `config_changes`. Per-table column lists differ; the trigger SQL is mechanical from each table's column inventory.

### 5.2 `console.db` — no additions

`console.audit_log.request_id` already exists (`docs/architecture/console-db-schema.sql:177`). A.5 does not add tables or columns to `console.db`. The decorator's new `auth.permission_denied` action lands in the existing table without schema change because `action` is free-text.

### 5.3 `src/db/migrate.py` additions

`_TABLE_ADDS: list[str]` (NEW — file currently has `_COLUMN_ADDS` + `_INDEX_ADDS` only) holds two `CREATE TABLE IF NOT EXISTS` statements for `command_audit` and `config_changes` matching §5.1.

`_TRIGGER_ADDS: list[str]` (NEW) holds 12 `CREATE TRIGGER IF NOT EXISTS` statements (6 tier-1 tables × {UPDATE, DELETE}); see §4.1.3 for the per-statement shape.

`apply_pending_migrations` extends the existing phase order with two new phases:
1. `_COLUMN_ADDS` (existing)
2. `_check_payment_events_duplicates` (existing)
3. `_INDEX_ADDS` (existing)
4. `_TABLE_ADDS` [new] — after columns + indexes
5. `_TRIGGER_ADDS` [new] — after tables (depends on them)

Idempotent. Re-running on every container start is safe.

### 5.4 No additions to `console-db-schema.sql`

The console-db schema file does not change in A.5.

---

## 6. Tests

### 6.1 New test files

Six new files [NEW], approx 1,300 LOC total:
- `tests/test_audit_context.py` (~180) — `bind_audit_context` happy path, exception cleanup, TEMP-table isolation, bypass detection.
- `tests/test_config_changes_triggers.py` (~320) — 12 triggers × {wrapper-bound, bypass} = 24 cases.
- `tests/test_command_audit_writer.py` (~120) — `write_command_audit_row` happy path, NULL columns, payload JSON.
- `tests/test_permissions.py` (~200) — Enum coverage (7 values), `ROLE_PERMISSIONS` shape, decorator allow/deny, WS-decorator-skipped assertion (§4.2.5).
- `tests/test_console_permission_gates.py` (~300) — 18 gated HTTP routes × 2 cases = 36 parameterised assertions.
- `tests/test_request_id_middleware.py` (~220) — header passthrough / generation / format-guard, response echo, log + audit + WS correlation.

Existing test adjustments: ~150 LOC.

### 6.2 Audit triggers — test matrix

9 tests. Each tier-1 table has wrapper-bound + wrapper-bypassed coverage; the noise-skip predicate has a dedicated test; cross-connection isolation has a dedicated test.

- `test_clients_update_via_wrapper_writes_audit` — bind context, UPDATE → one row with `intent`, `operator_id`, `request_id` populated; `old_json`/`new_json` snapshot the changed columns.
- `test_clients_update_bypass_writes_audit_with_null_actor` — no `bind_audit_context`, UPDATE → row fires with NULL actor columns. **Bypass detectable.**
- `test_clients_update_noise_skipped` — UPDATE only `updated_at` → zero rows (WHEN predicate filtered).
- `test_subscriptions_delete_via_wrapper_writes_audit` — DELETE → row with `op='DELETE'`, `new_json=NULL`.
- `test_consent_records_update_preserves_pii_in_old_json` — anonymise UPDATE on consent_records → `old_json` includes `authorised_by_name`, `authorised_by_email`, `consent_document` (Valdí preservation rule).
- `test_signup_tokens_redemption_audit` — UPDATE redeemed_at → row with intent, target_pk = token id.
- `test_client_domains_delete` — DELETE → one row. (No INSERT test — out of scope per §4.1.3.)
- `test_retention_jobs_force_run_via_wrapper_writes_audit` — wrap `force_run_retention_job` (`src/db/retention.py:320`) under `bind_audit_context(intent='retention.force_run', ...)`, run UPDATE on `retention_jobs.scheduled_for` → one `config_changes` row with `table_name='retention_jobs'`, `intent='retention.force_run'`, `target_pk=<job_id>`, populated `operator_id` / `request_id`.
- `test_temp_table_isolation_across_connections` — Conn A binds, Conn B writes → no leakage.

### 6.3 Forensic preservation tests (Valdí §263 + 2026-04-30 ruling)

Tests assert the **resolved** behaviour per the 2026-04-30 Valdí ruling: `anonymise_client` and `purge_client` preserve `config_changes` / `command_audit` / `clients.audit_log` indefinitely; `purge_bookkeeping` extends to hard-delete those rows past +5y under five binding conditions (per-row `occurred_at` cutoff, summary row before DELETEs, `data_retention_mode='hold'` short-circuit, `target_pk` carve-out, Wernblad re-eval if §263 stk. 3 applies).

| Test | Setup | Assertion |
|---|---|---|
| `test_anonymise_does_not_touch_audit_surfaces` | Seed `config_changes` / `command_audit` / `clients.audit_log` rows for cvr=12345678. Run `anonymise_client(conn, '12345678', ...)`. | Zero rows DELETED from any of the three audit surfaces. |
| `test_purge_does_not_touch_audit_surfaces` | Seed rows. Run `purge_client(...)`. | Zero rows DELETED from any of the three audit surfaces. |
| `test_purge_bookkeeping_keeps_recent_audit_rows_for_target` | Seed a year-old audit row tied to the purge target CVR. Run `purge_bookkeeping(...)`. | The recent row is preserved (newer than `now - 5y` cutoff). |
| `test_purge_bookkeeping_skips_unrelated_cvrs` | Seed a 6y-old audit row for an unrelated CVR. Run `purge_bookkeeping(...)` for the target CVR. | Zero rows deleted on the unrelated CVR. |
| `test_purge_bookkeeping_deletes_old_audit_rows_for_target` | Seed a 6y-old `config_changes` / `command_audit` / `clients.audit_log` row tied to the purge target CVR. Run `purge_bookkeeping(...)`. | All three 6y-old rows are deleted. |
| `test_purge_bookkeeping_respects_hold_flag` | Seed 6y-old audit rows tied to the target. Set `clients.data_retention_mode='hold'`. Run `purge_bookkeeping(...)`. | Zero rows deleted; short-circuit fires before any DELETE. |
| `test_purge_bookkeeping_emits_summary_row_before_deletes` | Seed audit rows older than cutoff. Run `purge_bookkeeping(...)`. | One `clients.audit_log` row with `action='retention.bookkeeping_purge'`, `actor_kind='system'`, `payload_json` containing `deleted_counts` per surface; the summary row's `occurred_at` is newer than the cutoff (it survives this cycle). |
| `test_purge_bookkeeping_skips_orphan_config_changes` | Seed a 6y-old `config_changes` row whose `target_pk` does not match any CVR. Run `purge_bookkeeping(...)` for the target CVR. | Zero rows deleted on the orphan; `target_pk` carve-out holds. |

### 6.4 RBAC decorator — route coverage

Every gated `/console/*` HTTP route gets two parameterised tests (allowed for OPERATOR role, denied for empty-permission role). 18 HTTP routes × 2 = 36 cases parameterised over `(method, path, permission)` tuples. Each denied case asserts:
- `r.status_code == 403`
- `r.json() == {"error": "permission_denied", "permission": permission.value}`
- One row in `console.audit_log WHERE action='auth.permission_denied'` with `target_id=permission.value`.

Plus one assertion that 401 precedes 403 (unauthenticated POST returns `{"error": "not_authenticated"}`, status 401).

#### 6.4.1 WS auth + permission tests (inline gate)

`tests/test_console_ws_auth.py` (slice 3g) appends three cases for the **inline** check per §4.2.5:

| # | Test | Assertion |
|---|---|---|
| 9 | `test_ws_no_permission_closes_4403` | Operator with `role_hint='unknown'`. Login, attempt WS connect. close(4403). audit_log row with `action='auth.permission_denied'`, `target_id='console.read'`. |
| 10 | `test_ws_demo_permission_required` | Same logic for `/console/demo/ws/{scan_id}`, `target_id='demo.run'`. |
| 11 | `test_ws_permission_audit_includes_request_id` | Connect with `X-Request-ID: r-ws-1`. Denial audit row has `request_id='r-ws-1'`. |

### 6.5 X-Request-ID middleware tests

10 tests:
- `test_header_passthrough` — valid `X-Request-ID` echoed verbatim on response.
- `test_header_generated_when_absent` — UUIDv4 shape on response.
- `test_header_too_long_regenerated` — 200-char input → fresh UUIDv4.
- `test_header_invalid_chars_regenerated` — `foo\nbar` → fresh UUIDv4 (no header-splitting).
- `test_log_line_includes_request_id` — loguru output `request_id` matches response header.
- `test_audit_row_includes_request_id` — authenticated POST → `console.audit_log.request_id` matches response header.
- `test_config_changes_row_includes_request_id` — POST mutating a tier-1 table → `clients.config_changes.request_id` matches.
- `test_ws_scope_passthrough` — `/console/ws` connect → `liveops.ws_connected` audit row has non-NULL `request_id`.
- `test_health_endpoint_carries_request_id` — GET `/health` → response has header.
- `test_request_id_propagated_across_two_dbs` — authenticated retention force-run → same UUID in `console.audit_log` AND `clients.config_changes` AND response header AND ≥1 log line. **Canonical cross-DB correlation proof.**

### 6.6 Existing tests that adjust

- `tests/test_audit_log_writer.py` — add `request_id` assertions to existing cases.
- `tests/test_auth_middleware.py` — add `request_id` plumbing to seeded scope.
- `tests/test_console_endpoints.py` — fixtures must seed `role_hint='operator'` on the test operator (today may be unset; without it, every test 403s under the new decorator).
- `tests/test_console_ws_auth.py` — cases 9-11 appended; 1-8 unchanged.
- `tests/test_session_auth.py` — no change.
- `tests/test_db_connection.py` — migration test for new tables + triggers (idempotent re-apply does not double-insert audit rows).

---

## 7. Dependencies & ordering

### 7.1 Internal sequence

Per §3 and Federico's locked decision A.5-order = c:
1. **Audit triggers + repository wrappers (1)** AND **X-Request-ID middleware (3)** in parallel.
2. **RBAC decorator (2)** after both.
3. Squash to one commit on PR merge.

### 7.2 External dependencies

- **Slice 3g.5 must be merged** to `main` first (per slice 3g spec §7.11 Option B).
- **Pi5 cutover** of Stage A must complete before A.5 deploys.
- **PR #49 mount widening** — `clients.db` mount on api container is `:rw`. A.5 inherits this.
- **Wernblad confirmation pending** on `consent_records` retention window (5y vs 10y, per `docs/decisions/log.md:477`). Affects `purge_bookkeeping` schedule timing only. A.5 does not block on this.
- **Valdí ruling 2026-04-30** APPROVE-WITH-CONDITIONS for option (ii) — `purge_bookkeeping` extends to hard-delete audit rows past +5y under five binding conditions (per-row `occurred_at` cutoff, summary row before DELETEs, `data_retention_mode='hold'` short-circuit, `target_pk` carve-out, Wernblad re-eval to 10y if §263 stk. 3 applies). See §4.1.7.

### 7.3 No external library additions

UUIDv4: stdlib `uuid`. ASGI middleware: Starlette (transitive dep of FastAPI). Decorator: stdlib `functools`. No new pip packages, no new container images, no new env vars.

### 7.4 Pi5 deploy / bundled cutover (decision A.5-deploy = b)

Standard Pi5 deploy flow (`heimdall-deploy` per `scripts/pi5-aliases.sh`). Three things ride the first prod deploy:

1. Schema migrations via `init_db()` add 2 tables + 12 triggers. Idempotent.
2. Trigger install: first writer container running `init_db()` against `clients.db` installs them. Compose brings api/scheduler/worker up in a ~30s window; Federico is the only operator. Verification: `scripts/verify_audit_triggers.sh` [NEW] runs `SELECT name FROM sqlite_master WHERE type='trigger'` and asserts all 12 trigger names present.
3. Decorator gates every gated route from minute zero. `role_hint='operator'` is seeded by Stage A; OPERATOR maps to all permissions.

### 7.5 Rollback

`git revert <stage-a-5-merge-sha>` → push → `heimdall-deploy`. ~5 minutes. New tables stay in `clients.db` (revert keeps schema; idempotent migration is a no-op on the next start). Empty tables are inert. Decorator code is gone; handlers ungated. Middleware stack reverts to slice 3g.5 baseline.

---

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Trigger fires before tables exist (writer container starts mid-deploy) | Low — compose brings containers together | Idempotent `CREATE TABLE IF NOT EXISTS`; `scripts/verify_audit_triggers.sh` post-deploy. |
| `_audit_context` TEMP table leaks between connections | Zero — TEMP is per-connection by SQLite contract | `test_temp_table_isolation_across_connections`. |
| WHEN predicate misses a future column | Medium | Codex §9 #2 cross-references `_COLUMN_ADDS` against trigger predicates. |
| Decorator mis-applies on a non-`request` handler | Low | Decorator raises `RuntimeError` early; pytest collection catches it. |
| `X-Request-ID` header-splitting injection | Medium | `_REQUEST_ID_PATTERN` regex rejects newlines / charset violations. |
| Federico locked out post-deploy (NULL `role_hint`) | Low — Stage A seeds `role_hint='operator'` | Verification script also runs `SELECT role_hint FROM operators` and fails deploy on NULL. |
| Triggers slow high-volume writes | Low — tier 1 has 6 low-volume tables | Volume-guard tier-2 list; benchmark target <2ms per fire on Pi5. |
| Migration on read-only mount | Resolved | A.5 inherits PR #49's `:rw` mount on api. |

---

## 9. Codex review checklist

Pre-merge Codex review (per `feedback_codex_before_commit`) must verify:

1. Every gated `/console/*` HTTP route has `@require_permission`. Public routes (§4.2.1 public table) have none. **WS routes deliberately do NOT use the decorator** per §4.2.5 — Codex must NOT flag as regression; it is locked v2 contract.
2. Trigger WHEN predicate matches `_COLUMN_ADDS` in `src/db/migrate.py`. Canonical test case: `data_retention_mode` (added 2026-04-23).
3. Every `bind_audit_context` call site uses `with`. `grep -n "bind_audit_context" src/` returns only `with` lines.
4. End-to-end: same UUID in `console.audit_log`, `clients.config_changes`, response header, at least one log line. `test_request_id_propagated_across_two_dbs` is the canonical proof.
5. `RequestIdMiddleware` is `add_middleware`-d LAST in `create_app` (outermost). Inline comment explains.
6. No decorator on `/health`, `/signup/*`, `/static/*`, SPA shell.
7. **Valdí preservation rule + bounded purge (extended 2026-04-30).** The retention `anonymise` action (`src/retention/actions.py:200-364`) does not include `config_changes`, `command_audit`, or `clients.audit_log` in its UPDATE set. The retention `purge` action (`src/retention/actions.py:368+`) does not DELETE from these tables. **`purge_bookkeeping`** is the only handler permitted to delete from them, gated by (a) `occurred_at < (now - 5y)` cutoff, (b) CVR correlation via `target_pk` / `target_id`, and (c) `data_retention_mode != 'hold'` short-circuit. The handler MUST emit a `clients.audit_log` summary row (`action='retention.bookkeeping_purge'`, `actor_kind='system'`) before the DELETEs run. Codex verifies by:
   - `grep -n "config_changes\|command_audit" src/retention/` returns hits ONLY in `purge_bookkeeping`.
   - `grep -n "DELETE FROM clients\|DELETE FROM audit_log" src/retention/actions.py` returns hits ONLY in `purge_bookkeeping`.
   - `grep -n "occurred_at" src/retention/actions.py` finds the cutoff filter on each audit DELETE.
   - `grep -n "data_retention_mode" src/retention/actions.py` finds the hold short-circuit at the top of `purge_bookkeeping`.
   - At least one new test in `tests/test_retention_actions.py` asserts: a year-old audit row tied to the target CVR is preserved; a 6y-old audit row tied to the target is deleted; a 6y-old audit row tied to the target survives when `data_retention_mode='hold'`.
8. No accidental `config_changes` writer outside the trigger. `grep -rn "INSERT INTO config_changes" src/` returns zero hits.
9. Decorator audit row uses `Permission.X.value` (lowercase), not `.name`.
10. No `request_id` in URL paths or query strings — header / state / log field only.
11. SQLite `json_object` requires 3.38+; Pi5 OS ships 3.40+. Test container matches.
12. WS inline check uses the same `auth.permission_denied` action + `Permission.X.value` target_id as the HTTP decorator. Audit vocabulary shared; decorator not shared.

---

## 10. Follow-ups

- `/console/config/history` git-shelling endpoint → V2 (read-side, consumes substrate).
- Table-backed RBAC → when third role appears (D3 deferral).
- Operator-admin UI → post-V2.
- `request_id` via contextvars to per-handler logs → V2 polish (§11.7 fork).
- Read-side audit rows (whoami probes, dashboard fetches) → when operators report a gap. Listed as out-of-scope in §2.2.
- Audit timeline UI in SPA → V2.
- `command_audit.outcome='partial'` semantics → when first multi-step command lands.
- OpenTelemetry / distributed tracing → multi-service rewrite.
- Direct-edit detection on `config/*.json` (operator SSH bypasses the §4.1.8 writer-wrapper) → filesystem inotify or periodic SHA-comparison job, V2 polish.

---

## 11. Forks (all resolved)

Seven forks. Six resolved by Federico on 2026-05-01; (e) resolved by Valdí on 2026-04-30 (ruling `valdi-2026-04-30-audit-retention`, binding per `feedback_valdi_guidance_non_overridable`). Original options preserved as rationale-of-record; the resolved option is marked **APPROVED** in each table.

### 11.1 Fork (a) — Trigger contract: INSERT, UPDATE+DELETE, or all three [RESOLVED 2026-05-01 = A]

| Option | Status | Description |
|---|---|---|
| A | **APPROVED** | UPDATE + DELETE only. Canonical creation rows live in repository wrappers. Matches §2.1 / §4.1 / §5.1 locked contract. |
| B | rejected | INSERT only. Drops audit on UPDATE — most common case. |
| C | rejected | INSERT + UPDATE + DELETE. Forensic completeness but adds 5 more triggers and double-captures wrapper-written creation rows on signup / trial activation. |

**Resolution: A.** Federico ruled 2026-05-01: matches the locked A.5 contract, avoids duplicate creation noise from wrapper-written INSERT paths.

### 11.2 Fork (b) — `config_changes` scope for file-backed settings [RESOLVED 2026-05-01 = (iii)]

**Federico ruled (iii)** on 2026-05-01: a thin writer-wrapper around the file-write path emits `clients.audit_log` rows with `action='config.file_write'`. See §4.1.8 for the wrapper design + tests. Original options preserved as rationale-of-record:

| Option | Status | Description |
|---|---|---|
| (i) | rejected | DB-only `config_changes`. File-backed settings keep `CONFIG_WRITE` gate but no audit row beyond loguru info. Leaves a known audit gap. |
| (ii) | rejected | DB-merged. Move `filters.json` / `interpreter.json` / `delivery.json` into a new `clients.db` table; trigger captures changes. Bundles a config-storage rewrite into A.5. |
| (iii) | **APPROVED** | Split surfaces. Thin writer-wrapper around the file-write path emits `clients.audit_log` rows with `action='config.file_write'`, `payload={old_sha256, new_sha256}`. ~30 LOC wrapper + tests. Two row shapes for "config write"; future timeline UI handles both. |

### 11.3 Fork (c) — Permission count: 7 (collapsed) or 10 (named) [RESOLVED 2026-05-01 = 7]

| Option | Status | Description |
|---|---|---|
| 7 | **APPROVED** | `CONSOLE_READ` + 3 retention + `CONFIG_WRITE` + `COMMAND_DISPATCH` + `DEMO_RUN`. 13 read routes share `CONSOLE_READ`. |
| 10 | rejected | Split `CONSOLE_READ` into `BRIEFS_READ` (`/console/briefs/list`, `/console/briefs`), `CLIENTS_READ` (`/console/clients/*`), `LOGS_READ` (`/console/logs`, `/console/ws`). 3 more audit-row shapes for read denials. |

**Resolution: 7.** Federico ruled 2026-05-01: one `CONSOLE_READ` is the right grain for the current product; splitting reads adds policy vocabulary without a concrete role need yet. Splitting is mechanical when the observer role appears.

### 11.4 Fork (d) — WS permission pattern: inline or decorator [RESOLVED 2026-05-01 = inline]

| Option | Status | Description |
|---|---|---|
| Inline | **APPROVED** | WS handlers run the check inside `_authenticate_ws` after `validate_session_by_hash`. Same `Permission` enum + audit vocabulary as HTTP; different call shape. ~20 LOC. §9 item 1 explicitly asks Codex NOT to flag the asymmetry. |
| Decorator | rejected | Rewrite `require_permission` to dispatch on parameter type (Request vs WebSocket). ~60 LOC polymorphic ASGI scope handling. |

**Resolution: inline.** Federico ruled 2026-05-01: the WS flow already has its own accepted-then-close / auth-audit shape (`src/api/console.py:176`); a polymorphic decorator adds abstraction without simplifying the real path.

### 11.5 Fork (e) — §263 audit preservation [RESOLVED 2026-04-30 = (ii) APPROVED-WITH-CONDITIONS]

**Valdí ruled APPROVE-WITH-CONDITIONS for option (ii)** on 2026-04-30 (ruling id `valdi-2026-04-30-audit-retention`). `purge_bookkeeping` extends to hard-delete `clients.audit_log`, `config_changes`, and `command_audit` rows past +5y across all three surfaces under five binding conditions enumerated in §4.1.7. Tests in §6.3 cover the conditions; Codex checklist in §9 item 7.

Original options preserved as rationale-of-record:

| Option | Status | Description |
|---|---|---|
| (i) | rejected | Preserved indefinitely (no purge clause). Conservative but the surface grows monotonically. |
| (ii) | **APPROVED-WITH-CONDITIONS** | Hard-delete past +5y via `purge_bookkeeping` extension. Five binding conditions (per-row `occurred_at` cutoff, summary audit row before DELETEs, `data_retention_mode='hold'` short-circuit, `target_pk` carve-out for orphan `config_changes` rows, Wernblad re-eval to 10y if §263 stk. 3 applies). |
| (iii) | rejected | Per-surface retention with shorter `command_audit` window. Valdí ruled uniform horizon at 5y is correct; differential is in carve-outs, not the cutoff. |

Implementation lands per the carve-outs in §4.1.7. Spec language is binding per `feedback_valdi_guidance_non_overridable`.

### 11.6 Fork (f) — `retention_jobs` tier [RESOLVED 2026-05-01 = B]

**Federico ruled B** on 2026-05-01: add `retention_jobs` to the tier-1 trigger surface. Closes the real audit gap (force-run / cancel / retry today only emit a loguru info line; UPDATE-via-trigger produces the durable timeline entry). Tier-1 count rises from 5 to 6 tables; trigger count from 10 to 12. Implementation propagates to §2.1 row (1) writer-module list (adds `src/db/retention.py`), §4.1.2 tier-1 table, §4.1.9 (Migration) + §5.1 + §5.3 trigger counts, §6.1 + §6.2 test matrix, §7.4 verification script. Original options preserved as rationale-of-record:

| Option | Status | Description |
|---|---|---|
| A | rejected | Status quo. No audit on `retention_jobs` beyond loguru + notes suffix. Leaves a real audit gap on operator force-run / cancel / retry. |
| B | **APPROVED** | Add `retention_jobs` to tier 1. Trigger captures UPDATE + DELETE. CAS UPDATE in `console_retention_cancel` (`src/api/console.py:715-725`) also fires the trigger. |
| C | rejected | Hand-written `clients.audit_log` rows in `_run_retention_action`. Reintroduces D2's discipline-doesn't-scale problem. |

### 11.7 Fork (g) — `request_id` propagation into per-handler `logger.bind` [RESOLVED 2026-05-01 = A for A.5]

| Option | Status | Description |
|---|---|---|
| A | **APPROVED for A.5** | No change. Only `RequestLoggingMiddleware`'s log line carries `request_id`. Correlation comes from middleware log line + audit rows + response header. |
| B | rejected | Mechanical sweep — add `request_id` to every per-handler `logger.bind(context=...)` (~15 sites in `src/api/console.py`). 15+ touch points; missed sites silent. Fragile. |
| C | follow-up | `contextvars.ContextVar` populated by `RequestIdMiddleware`; patch loguru `bind` to auto-merge. Automatic, no per-call discipline. ~30 LOC patch module hooking loguru internals. The cleaner long-term move; not this slice. |

**Resolution: A for A.5; C as a follow-up.** Federico ruled 2026-05-01: correlation already comes from three primitives (middleware log line, audit rows, response header). Mechanical sweep is fragile; contextvars is cleaner long-term but follow-up, not this slice.

---

## 12. Internal consistency check

Cross-reference for the load-bearing facts. Federico's pre-Codex review verifies each against the actual codebase + against the spec's other sections.

**Trigger contract: UPDATE + DELETE on tier-1 tables.** Identical statement appears in §2.1, §4.1 banner, §4.1.3, §5 banner, §5.1 inline comment. §6.2 test matrix has 9 tests across UPDATE / DELETE / noise-skip / bypass / cross-connection / retention_jobs — no INSERT trigger test.

**Permission count: 7.** Defined in §4.2.1 enum block (7 values). Asserted in §4.2.1 list, §4.2.5 paragraph 5, §11.3 fork framing, §12 (here).
1. `CONSOLE_READ` (13 routes)
2. `RETENTION_FORCE_RUN` (1)
3. `RETENTION_CANCEL` (1)
4. `RETENTION_RETRY` (1)
5. `CONFIG_WRITE` (1)
6. `COMMAND_DISPATCH` (1)
7. `DEMO_RUN` (2 routes — POST + WS)

**Console routes: 20 in `src/api/console.py`.** Verified by `grep -nE "^@router\." src/api/console.py | wc -l` → 20. Lines: 89, 252, 323, 350, 374, 415, 460, 565, 592, 657, 682, 771, 796, 810, 862, 891, 926, 1066, 1088, 1110. Each mapped to exactly one of the 7 permissions in §4.2.1.

**WS permission pattern: inline, not decorator.** §2.1 row (2), §4.2.5 paragraph 1, §9 item 1, §11.4 — all aligned.

**`config_changes` scope: DB-table mutations via trigger; file-backed settings via writer-wrapper.** Per fork (b) resolution = (iii) (Federico, 2026-05-01). DB triggers fire on `clients.db` mutations; file-backed `filters.json` / `interpreter.json` / `delivery.json` writes go through the §4.1.8 writer-wrapper that emits `clients.audit_log` rows with `action='config.file_write'`. §4.1.1 paragraph 2 ("Scope boundary, locked v2"), §4.1.8 (writer-wrapper), §2.2 row, §11.2 fork — all aligned.

**Trigger count: 12.** 6 tier-1 tables × 2 ops (UPDATE + DELETE) = 12 triggers. Tier-1 tables: `clients`, `subscriptions`, `consent_records`, `signup_tokens`, `client_domains`, `retention_jobs` (the last per fork (f) = b, Federico 2026-05-01). Asserted in §4.1.2 tier-1 table, §4.1.9 (Migration), §5.1 SECTION 14 prose + trigger names list, §5.3 `_TRIGGER_ADDS`, §7.4 verification-script assertion.

**Fork resolutions (all seven, summary).** §11.1 (a) trigger contract = A (UPDATE+DELETE only). §11.2 (b) file-backed settings = (iii) writer-wrapper (§4.1.8). §11.3 (c) permission count = 7. §11.4 (d) WS pattern = inline. §11.5 (e) §263 audit preservation = (ii) APPROVE-WITH-CONDITIONS per Valdí 2026-04-30 (§4.1.7 binding language). §11.6 (f) `retention_jobs` tier = B (joins tier 1). §11.7 (g) `request_id` propagation = A for A.5, C as follow-up.

**§263 audit preservation: RESOLVED 2026-04-30 — Valdí APPROVE-WITH-CONDITIONS for option (ii).** §1.2 second Valdí bullet, §4.1.7 (binding language + 5 conditions), §6.3 (8-test matrix covering all conditions), §9 item 7 (Codex grep checklist), §11.5 (resolved with rationale-of-record). Five binding conditions: per-row `occurred_at` cutoff, summary audit row before DELETEs, `data_retention_mode='hold'` short-circuit, `target_pk` carve-out for orphan `config_changes` rows, Wernblad re-eval to 10y if §263 stk. 3 applies.

**File path inventory.**
- [EXISTING] `src/api/console.py` (1,161 lines) — route lines verified by grep.
- [EXISTING] `src/api/app.py` (495 lines) — mount block 394-403; `/health` at 421; `/results/*` at 440/458/468.
- [EXISTING] `src/api/auth/audit.py` (240 lines) — `state.request_id` read at 137-140.
- [EXISTING] `src/api/routers/auth.py` — `/login` at 217, `/logout` at 381, `/whoami` at 436.
- [EXISTING] `src/api/signup.py` — `/signup/validate` at 55. (v1 cited `/signup/start` — does NOT exist.)
- [EXISTING] `src/db/retention.py` — `force_run_retention_job` at 320, `retry_failed_retention_job` at 383.
- [EXISTING] `src/retention/actions.py` — `anonymise_client` at 150, `purge_client` at 373, `purge_bookkeeping` at 554. **`purge_bookkeeping` (lines 588-596) deletes only `payment_events` + `subscriptions` — does NOT touch any audit surface today.**
- [EXISTING] `src/db/migrate.py` (7,966 bytes) — has `_COLUMN_ADDS` + `_INDEX_ADDS`; `_TABLE_ADDS` + `_TRIGGER_ADDS` are [NEW] in this slice.
- [EXISTING] `docs/architecture/client-db-schema.sql` — `audit_log` at 1093-1126; sections 12-14 are new appends.
- [EXISTING] `docs/architecture/console-db-schema.sql` — `audit_log` at 177-202.
- [NEW] `src/api/auth/permissions.py` — `Permission` enum + `require_permission`.
- [NEW] `src/api/auth/request_id.py` — `RequestIdMiddleware`.
- [NEW] `src/db/audit_context.py` — `bind_audit_context`.
- [NEW] `src/db/audit.py` — `write_command_audit_row` (no file at this path today; verified).
- [NEW] `scripts/verify_audit_triggers.sh`.

**Decision references** (verified against `docs/decisions/log.md`):
- D2 — line 196.
- D3 — line 197.
- D4 — line 198.
- Valdí 2026-04-25 — line 454.
- Wernblad pending — line 477.
- Audit-ownership Option B — line 8 (2026-04-28 entry) and master spec §1.3.

---

**End of Stage A.5 spec — DRAFT v2 + 2026-05-01 fork resolutions.** All seven §11 forks resolved (six by Federico on 2026-05-01, one by Valdí on 2026-04-30 — ruling `valdi-2026-04-30-audit-retention`). Components + sequencing locked; binding contract on retention/audit per §4.1.7. Spec is ready for Codex review; implementation PR drafts after Codex SHIP + Federico ratification.
