# Stage A — Operator Console Bounded-Context Reframe — Implementation Spec

**Status:** Draft awaiting Federico's review
**Sprint:** Stage A (1 of 3 — Stage A → Stage A.5 → V2)
**Author:** Application Architect agent, 2026-04-27 (late evening)
**Codifies:** the four operator-console reframe decisions resolved 2026-04-27 evening (`docs/decisions/log.md`)
**Last revised:** 2026-04-28 (late afternoon, post-tightening trim) — PR #49 (separate, direct to main, on `fix/api-clients-db-mount`) lands the api `clients.db` `:ro` → `:rw` flip on main. Stage A no longer ships the mount widening; the spec's references to it are reframed as "consumes the fix from PR #49". Edits in §1 header, §2.7, §7/§1.3 cross-DB rationale, §10 D2 amendment, §10 D9 body, Appendix B (entry 1b removed). The narrow-write invariant (audit-paired only) is now enforced by code review on `src/api/routers/retention.py` and `src/api/routers/onboarding.py`, not by mount mode.

**Prior revision:** 2026-04-28 (afternoon, tightening pass after the evening security review) — Federico's three normative fixes applied: rate limiting integrated end-to-end into login flow + tests + Appendix A (D1, §3.1 / §3.1.a / §6.3 / §8 / Appendix A), `config.update` audit explicitly out of scope for Stage A (D8, §7.3 / §7.6 / §11), retention endpoints stay synchronous (D9, §7.2 rewritten + api `clients.db` mount widened to `:rw` narrowly + Appendix B). Two new decisions resolved (D8, D9). The earlier same-day evening pass landed the security review (hash session tokens, audit ownership split, WS auth in handler, whoami split states, password-reset runbook); the morning pass landed D2 / D5 / D7. See "Revision history" at the end of the spec.

> **Post-review pass applied five security/correctness fixes.** The audit guarantee is now genuinely atomic via split ownership (Option B), session tokens are hashed at rest, WS auth is in the handler not the middleware, whoami distinguishes empty-bootstrap from all-disabled, and password reset is case-normalised.
>
> **Tightening pass on top (2026-04-28 afternoon) applied three normative fixes.** Rate limiting is now baked into the login handler, response shapes, and test plan (D1 → integrated, not just "decided"). `config.update` audit is explicitly out of scope in Stage A and lands in Stage A.5 via `config_changes` triggers per D2 (D8). Retention endpoints stay synchronous in Stage A — the architect's earlier async-202 design is reverted; PR #49 (separate, on main) widens the api's `clients.db` mount from `:ro` to `:rw`; Stage A consumes that fix for the three audit-paired retention CAS UPDATEs (D9). See §10 D1, D8, D9 + §14 revision history.

---

## Summary

Stage A carves the operator console's identity, authentication, session, and per-context router skeleton out of the current monolithic `src/api/console.py` + `BasicAuthMiddleware` design. It replaces single-credential HTTP Basic Auth with first-class operator rows, server-side session tickets, an immutable per-action audit log, an authenticated WebSocket handshake, and six router files (Notifications reserved as the 7th, not created in Stage A). The control-plane guarantees that consume this foundation — the `Permission` enum + `require_permission` decorator, `command_audit`, `config_changes` triggers, X-Request-ID middleware, `/console/config/history` — all ship in Stage A.5. V2 (the first onboarding view) ships after Stage A.5 and is the first feature that consumes the foundation.

> **This spec covers Stage A only.** Anything described as "Stage A.5 lands X" is a forward reference; the Stage A.5 spec is not yet written. If the Stage A.5 design needs changes that ripple back into Stage A's tables or columns, the change goes here, not in Stage A.5.

---

## Table of contents

1. [DDL for the three new tables](#1-ddl-for-the-three-new-tables)
2. [Migration order](#2-migration-order)
3. [Auth flow diagrams](#3-auth-flow-diagrams)
4. [Session ticket spec](#4-session-ticket-spec)
5. [WebSocket auth handshake](#5-websocket-auth-handshake)
6. [Router carve mapping](#6-router-carve-mapping)
7. [`audit_log` write contract](#7-audit_log-write-contract)
8. [Test plan](#8-test-plan)
9. [Rollback plan](#9-rollback-plan)
10. [Decisions still open](#10-decisions-still-open)
11. [Out of scope (deferred)](#11-out-of-scope-deferred)
12. [Appendix A — file map](#12-appendix-a--file-map)
13. [Appendix B — infra surface flagged for the danger-zone hook](#13-appendix-b--infra-surface-flagged-for-the-danger-zone-hook)
14. [Revision history](#14-revision-history)

---

## 1. DDL for the new tables (split across two DBs)

Stage A introduces **four** new tables across two databases — three in `console.db` and one in `clients.db`. The split keeps every audit row in the same SQLite transaction as the mutation it records (see §1.3 for the Option B rationale):

- **In `console.db`** (new file at `docs/architecture/console-db-schema.sql`, mirroring the style of `docs/architecture/client-db-schema.sql`): `operators`, `sessions`, `audit_log` (auth-event ownership). These DO NOT extend `client-db-schema.sql`; per D2 (resolved 2026-04-28), operator identity / sessions / api-side audit live in a separate SQLite database file `console.db` mounted RW on the api container only.
- **In `clients.db`** (added to `docs/architecture/client-db-schema.sql`): `audit_log` (mutation-event ownership). This is the post-review Option B addition that gives Stage A its real atomicity guarantee for retention / trial / onboarding / config mutations — the writer container (scheduler / worker / delivery) inserts the audit row in the same transaction as the mutation.

The api's `clients.db` mount is `:rw` (provided by PR #49, separate, direct to main). Stage A relies on that capability for the synchronous retention CAS UPDATEs and the paired audit-row writes (§7.2). The narrow-write invariant — api only writes retention/trial CAS UPDATEs + paired audit rows on `clients.db`, never anything else — is enforced by code review on `src/api/routers/retention.py` and `src/api/routers/onboarding.py`, not by mount mode. All other writes to `clients.db` continue to come from the scheduler / worker / delivery RW mounts, exactly as today.

The new console-side schema file is loaded by a new `init_db_console()` factory (see §2.5) at api startup via `executescript`. The clients-side `audit_log` is loaded by the existing `init_db()` via `client-db-schema.sql` after Stage A appends its CREATE TABLE block. Every CREATE TABLE statement is `IF NOT EXISTS` — idempotent.

### 1.1 `operators`

```sql
-- =================================================================
-- console.db — Operator identity, sessions, and audit log (Stage A)
-- =================================================================
--
-- This file is the AUTHORITATIVE schema for console.db. It is the
-- counterpart to client-db-schema.sql (which owns clients.db). The
-- two databases are physically separate SQLite files mounted on
-- different volumes; no cross-DB FKs, no ATTACH at runtime.
--
-- Replaces the single-credential CONSOLE_USER / console_password
-- Basic Auth scheme (src/api/app.py:53-91) with first-class operator
-- rows, server-side session tickets, and an immutable per-action
-- audit log.
--
-- Single-tenant today (Federico is operator #1) but designed for a
-- small ops team. Identity provider is local password (Argon2id);
-- MitID Erhverv is for clients (signup), not operators.

-- -----------------------------------------------------------------
-- operators
-- -----------------------------------------------------------------
-- One row per console operator. The username is the login handle;
-- display_name is what we show in the UI ("logged in as Federico"
-- vs "logged in as fede1"). Hashed password is Argon2id; pepper, if
-- any, lives in /run/secrets/operator_password_pepper.
--
-- role_hint is free-text in Stage A. Stage A.5's require_permission
-- decorator reads it and maps via an in-code Permission table; until
-- then it's purely informational. Acceptable values seeded by Stage
-- A migrations: 'owner', 'operator', 'observer'. The string is not
-- validated by SQLite — Stage A.5's decorator validates at lookup.

CREATE TABLE IF NOT EXISTS operators (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    username            TEXT NOT NULL UNIQUE,            -- login handle, lowercase
    display_name        TEXT NOT NULL,                   -- shown in UI
    password_hash       TEXT NOT NULL,                   -- Argon2id, full PHC string
    role_hint           TEXT NOT NULL DEFAULT 'operator',
                                                         -- free-text in Stage A; Stage A.5 maps to Permission enum
    disabled_at         TEXT,                            -- ISO-8601 UTC; non-NULL = no login allowed
    last_login_at       TEXT,                            -- ISO-8601 UTC; updated on successful login
    last_login_ip       TEXT,                            -- forensic only, not for binding
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_operators_username_lower
    ON operators(LOWER(username));

CREATE INDEX IF NOT EXISTS idx_operators_active
    ON operators(disabled_at) WHERE disabled_at IS NULL;
```

**FK actions / constraints rationale.**

- `username UNIQUE` is the natural-key constraint. The case-insensitive functional index above guards against `Federico` vs `federico` collisions.
- No FK to anything else from `operators` — it's the root identity table.
- `role_hint NOT NULL DEFAULT 'operator'` so Stage A.5's decorator can read a value on every row without NULL handling.
- `disabled_at` instead of `is_disabled` boolean — the timestamp doubles as the audit trail of when the operator was offboarded. NULL = active.
- No `email` column. Operator email is not a product surface today; if Stage A.5 needs it for password-reset, it's a `NULL`able add via `_COLUMN_ADDS`.

### 1.2 `sessions`

```sql
-- -----------------------------------------------------------------
-- sessions
-- -----------------------------------------------------------------
-- Server-side session tickets. The browser holds the plaintext token
-- in a cookie; the database stores ONLY the SHA-256 digest of that
-- token in `token_hash`. The cookie value is never persisted server-
-- side — if the database is leaked, the attacker cannot use the
-- digests to impersonate operators, because every authenticated
-- request must present the matching plaintext cookie that hashes
-- back to a row.
--
-- A session is valid when:
--   revoked_at IS NULL
--   AND expires_at > now
--   AND absolute_expires_at > now
--   AND sha256(presented_cookie_value).hexdigest() = token_hash
--
-- Sliding-window refresh: each authenticated request bumps
-- expires_at to now + IDLE_TTL (15min default). absolute_expires_at
-- is set at issue time and never extended — hard cap at 12h.
--
-- Last-seen IP and user-agent are forensic only. They are not used
-- to bind the session (no IP-pinning, no UA-pinning) because mobile
-- clients legitimately roam IPs and headless test runners change UA.
-- Recorded for post-incident audit.

CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash          TEXT NOT NULL UNIQUE,            -- sha256 hex digest (64 chars) of the plaintext token; the
                                                         -- presented cookie is hashed at the start of each request and
                                                         -- looked up here. The plaintext cookie is NEVER stored.
    operator_id         INTEGER NOT NULL,                -- FK to operators.id
    issued_at           TEXT NOT NULL,                   -- ISO-8601 UTC, set at login
    expires_at          TEXT NOT NULL,                   -- ISO-8601 UTC, sliding (refreshed on use)
    absolute_expires_at TEXT NOT NULL,                   -- ISO-8601 UTC, never extended (hard cap)
    revoked_at          TEXT,                            -- ISO-8601 UTC, non-NULL = logged out
    last_seen_at        TEXT,                            -- ISO-8601 UTC, updated each authenticated request
    last_seen_ip        TEXT,                            -- forensic, not load-bearing
    last_seen_ua        TEXT,                            -- forensic, not load-bearing (truncate to 512 chars)
    csrf_token          TEXT NOT NULL,                   -- 32 random bytes, base64url, 43 chars; double-submit value
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_token_hash_active
    ON sessions(token_hash) WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sessions_operator
    ON sessions(operator_id);

CREATE INDEX IF NOT EXISTS idx_sessions_expires
    ON sessions(expires_at) WHERE revoked_at IS NULL;
```

**FK actions / constraints rationale.**

- `ON DELETE CASCADE` on `operator_id`. If an operator row is hard-deleted, their sessions go with it. We do not hard-delete operators in normal operation (we set `disabled_at`), so the cascade only matters in disaster-recovery scenarios.
- `token_hash UNIQUE` — collisions are mathematically impossible at 32 random bytes pre-hash, but the constraint catches the implementation bug where two sessions accidentally share a digest.
- **The presented cookie is never the database key.** The route handler / middleware computes `hashlib.sha256(cookie_value.encode()).hexdigest()` on the inbound cookie and looks up that digest in `token_hash`. A leak of `console.db` exposes only the digests, which are not directly usable as session tickets.
- No PBKDF (Argon2 / bcrypt / scrypt) on the session token. These tokens are 256 bits of entropy from `secrets.token_urlsafe(32)` — they are not human passwords; the time-cost of a password KDF buys nothing against a brute-force attacker that already cannot enumerate the keyspace. SHA-256 is fast enough that auth latency stays in the sub-millisecond range while still neutralising the "DB read = full impersonation" attack.
- `csrf_token` lives in the row (not derived from the session token) so the cookie can be `HttpOnly` while the JS app reads the CSRF value from a non-`HttpOnly` companion cookie / a `/console/auth/whoami` response. See [§4.4 CSRF defense](#44-csrf-defense). The CSRF token is stored as a 256-bit random value the same way; we accept the lower-stakes asymmetry (CSRF tokens are not stored hashed) because the CSRF token's threat model is different — it must be readable by the SPA on every refreshable load, and a DB-only leak of the CSRF value cannot be used standalone (the attacker also needs the matching session cookie).
- The two timestamp columns `expires_at` (sliding) and `absolute_expires_at` (hard cap) bound the worst-case session lifetime at the absolute cap regardless of activity.
- Partial indexes on `revoked_at IS NULL` keep the index small — revoked sessions are dead weight for lookup.
- No FK to `audit_log.session_id` from this side; the audit row references this table via `session_id` (see §1.3) and we don't want a circular FK.

### 1.3 `audit_log` (split ownership per Option B)

**Why split.** A single `audit_log` table in `console.db` cannot be transactional with mutations in `clients.db` — SQLite WAL does not give atomic commit across two database files (even via `ATTACH DATABASE`, the two journals commit independently and a crash between them is observable). The Stage A spec's earlier wording ("audit row written in the same transaction as the underlying mutation") was therefore false for any client-side mutation: retention force-runs, trial activations, onboarding writes all live in `clients.db` and only their api-side audit row would have lived in `console.db`. We resolve the false-atomicity by splitting audit ownership along the DB boundary, so each audit row is genuinely in the same SQLite transaction as the mutation it records.

**The split.**

| Table | Lives in | Written by | Records |
|---|---|---|---|
| `console.audit_log` | `console.db` | `api` container (this Stage A scope) | Auth events: `auth.login_ok`, `auth.login_failed`, `auth.logout`, `auth.session_rejected_disabled`, `liveops.ws_connected`, and any future api-only mutation that writes to `console.db` |
| `clients.audit_log` | `clients.db` | `api` (sync retention writes — see §10 D8) + `scheduler`, `worker`, `delivery` containers (the existing writers of `clients.db`) | Mutation events on client-side state: `retention.force_run`, `retention.cancel`, `retention.retry`, `trial.activated`, `trial.expired`, `command.dispatch`, plus any system-initiated mutation (CT monitor, retention timer firing). **`config.update` is intentionally NOT in this list — see §7.6 (deferred to Stage A.5).** |

Each audit row is in the same SQLite transaction as the row it records — real atomicity, no reconciler needed. The cost is two audit tables, two query surfaces, and a UNION VIEW the operator console reads when it wants a unified timeline.

**Cross-DB ownership rule for operator-initiated mutations.** Per D8 / D9 (decided 2026-04-28 afternoon), Stage A's operator-initiated retention writes are **synchronous and single-row**: the api itself opens a `clients.db` connection, runs the CAS UPDATE on `retention_jobs`, and writes the `clients.audit_log` row in the same transaction. There is no api-side intent row, no writer-container outcome row, no async dispatch. One operator action, one audit row, in `clients.audit_log`. `config.update` is **not audited in Stage A at all** — full capture lands in Stage A.5 via `config_changes` triggers per D2 (see §7.6).

The single Stage A retained two-row pattern is `/console/commands/{command}` POST: the api writes an intent row in `console.audit_log` and pushes the command envelope onto `queue:operator-commands`; whichever container handles the command writes the outcome row in `clients.audit_log`. Commands are genuinely async (the queue is the existing dispatch mechanism for every operator-command flow today); retention was async only because the architect's earlier design speculatively introduced the queue, not because the dispatch needed it. Cross-DB correlation between the two command rows is by `target_id` + `occurred_at` proximity in Stage A, exact via `request_id` once Stage A.5 wires X-Request-ID middleware.

**No cross-DB pairs in Stage A's retention path.** A reviewer scanning the audit timeline for a retention force-run sees exactly one row in `clients.audit_log`. A reviewer scanning for a command dispatch sees one row in `console.audit_log` (the intent) and one in `clients.audit_log` (the outcome) — same as before. Auth events (`auth.login_ok`, `auth.login_failed`, `auth.logout`, `liveops.ws_connected`) live entirely in `console.audit_log`; trial/system events (`trial.activated`, `trial.expired`, `retention.tick`, `ct.delta_observed`) live entirely in `clients.audit_log`.

#### 1.3.a `console.audit_log` (in `console.db`)

```sql
-- -----------------------------------------------------------------
-- console.audit_log  (lives in console.db)
-- -----------------------------------------------------------------
-- Immutable append-only log of api-side state-changing events. The
-- api container writes here in the SAME transaction as the mutation
-- it records (which, for this DB, means: session issuance/revocation,
-- operator updates, WS handshake).
--
-- Operator-initiated retention writes are SYNCHRONOUS in Stage A
-- (per §10 D8 / D9, decided 2026-04-28 afternoon): the api opens a
-- clients.db connection, runs the CAS UPDATE on retention_jobs, and
-- writes the audit row in clients.audit_log in the SAME transaction.
-- No intent row in console.audit_log for retention.
--
-- The single Stage A retained two-row pattern is /console/commands/*:
-- api writes a 'command.dispatch' intent row HERE, and whichever
-- container handles the command writes the 'command.<name>' outcome
-- row in clients.audit_log. See §7.2.
--
-- Stage A: action is free-text, populated by hand in each route
-- handler. Stage A.5 introduces the Permission enum and migrates
-- action to the enum value.

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL,                       -- ISO-8601 UTC
    operator_id     INTEGER,                             -- FK to operators.id; NULL for system / unauthenticated
    session_id      INTEGER,                             -- FK to sessions.id; NULL for system actions
    action          TEXT NOT NULL,                       -- free-text in Stage A, e.g. 'auth.login_ok', 'auth.logout', 'liveops.ws_connected', 'command.dispatch'
    target_type     TEXT,                                -- e.g. 'session', 'operator', 'websocket', 'command'
    target_id       TEXT,                                -- string for FK flexibility (int / cvr / config name)
    payload_json    TEXT,                                -- JSON snapshot of request body or relevant state
    source_ip       TEXT,
    user_agent      TEXT,                                -- truncated to 512 chars
    request_id      TEXT,                                -- NULL until Stage A.5 wires X-Request-ID; correlates with clients.audit_log row
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id)  REFERENCES sessions(id)   ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_console_audit_log_occurred
    ON audit_log(occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_console_audit_log_operator
    ON audit_log(operator_id, occurred_at DESC) WHERE operator_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_console_audit_log_target
    ON audit_log(target_type, target_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_console_audit_log_action
    ON audit_log(action, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_console_audit_log_request
    ON audit_log(request_id) WHERE request_id IS NOT NULL;
```

#### 1.3.b `clients.audit_log` (in `clients.db`)

A parallel `audit_log` table is added to `clients.db` via a Stage A entry in `_COLUMN_ADDS` / `_TABLE_ADDS` (see §2.1 for placement). Same shape, different writers, no FK to `operators` / `sessions` (those tables don't exist in `clients.db`).

```sql
-- -----------------------------------------------------------------
-- clients.audit_log  (lives in clients.db — added by Stage A)
-- -----------------------------------------------------------------
-- Immutable append-only log of mutation events on client-side state.
-- Written by the SAME container that does the mutation, in the SAME
-- SQLite transaction as the mutation. This is the table that gives
-- Stage A its real atomicity guarantee for retention / trial /
-- onboarding mutations.
--
-- Writers in Stage A:
--   - api: operator-initiated retention writes (force-run, cancel,
--     retry) — synchronous per §10 D8 / D9, single audit row per
--     action, same transaction as the CAS UPDATE on retention_jobs.
--     Requires api's clients.db mount to be RW (Appendix B).
--   - scheduler / worker / delivery: system-initiated mutations
--     (trial.activated, trial.expired, retention.tick,
--     ct.delta_observed, command outcomes) from those containers'
--     existing RW mounts.
--
-- config.update is NOT written here in Stage A (§7.6); full capture
-- lands in Stage A.5 via config_changes triggers per D2.
--
-- No FK to operators / sessions — those tables live in console.db
-- and SQLite does not support cross-DB FKs. The columns are stored
-- as bare integers; correlation back to operator identity goes
-- through request_id (Stage A.5) or via the api's intent row in
-- console.audit_log when the operator action is /console/commands/*
-- (the only Stage A endpoint that retains the two-row pattern).

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL,                       -- ISO-8601 UTC
    operator_id     INTEGER,                             -- bare int — NOT a FK; correlates to console.operators.id
    session_id      INTEGER,                             -- bare int — NOT a FK; correlates to console.sessions.id
    action          TEXT NOT NULL,                       -- e.g. 'retention.force_run', 'trial.activated'
    target_type     TEXT,                                -- e.g. 'retention_job', 'client', 'config'
    target_id       TEXT,                                -- string for type flexibility
    payload_json    TEXT,
    source_ip       TEXT,                                -- propagated from api when the mutation was operator-initiated
    user_agent      TEXT,
    request_id      TEXT,                                -- NULL until Stage A.5 wires X-Request-ID
    actor_kind      TEXT NOT NULL DEFAULT 'operator'     -- 'operator' | 'system' (CT monitor, retention timer)
);

CREATE INDEX IF NOT EXISTS idx_clients_audit_log_occurred
    ON audit_log(occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_clients_audit_log_operator
    ON audit_log(operator_id, occurred_at DESC) WHERE operator_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_clients_audit_log_target
    ON audit_log(target_type, target_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_clients_audit_log_action
    ON audit_log(action, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_clients_audit_log_request
    ON audit_log(request_id) WHERE request_id IS NOT NULL;
```

#### 1.3.c Unified timeline view

The operator console wants one chronological "what happened" feed. With the split, the api builds the unified view at query time by querying both tables. Two implementation paths — pick one in the implementing PR; both are documented for completeness:

**Path 1 (recommended): application-layer UNION at the read endpoint.** The future `GET /console/audit/timeline` endpoint (Stage A.5 surface; Stage A doesn't ship the read endpoint yet) opens both `console.db` and `clients.db` connections, runs a SELECT with matching shape against each, merges in Python by `occurred_at`, paginates, returns. No SQLite ATTACH, no cross-DB query, no schema coupling.

**Path 2: SQLite ATTACH + UNION VIEW.** At the api connection's request scope, `ATTACH DATABASE 'file:/data/clients/clients.db?mode=ro' AS clients_db` is run, then a VIEW named `audit_log_unified` is queried. WAL-mode caveats apply (read-only attach is fine; the timeline endpoint is read-only). The cost is the api needs `clients.db` mounted (which it already does — `:rw` as of PR #49 on main; the read-only `mode=ro` flag on the ATTACH URI still narrows this connection's view to read-only). The benefit is single-statement queries with SQL-side filtering / ORDER BY / LIMIT.

Stage A documents both paths but does not ship the read endpoint. Path 1 is the spec's recommendation: less coupling, no ATTACH lifecycle to manage, easier to test in isolation. Stage A.5's `GET /console/audit/timeline` design will pick.

**FK actions / constraints rationale (both tables).**

- `console.audit_log`: `ON DELETE RESTRICT` on both FKs. We never want an audit row orphaned to a dead operator/session — the audit row IS the record that the operator/session existed. If a hard-delete is attempted on an operator with audit rows, the delete fails. (Operationally: we use `disabled_at` instead of deleting, so this is a defense, not a design.)
- `clients.audit_log`: no FKs by design — `operators` and `sessions` live in a different SQLite file and SQLite does not support cross-DB FKs. The integer columns are bare correlations, validated at write time by the application.
- `target_id TEXT` — flexible across `retention_jobs.id INTEGER`, `clients.cvr TEXT`, `config` filenames. Cheap denormalisation; the type is recoverable from `target_type`.
- `payload_json TEXT` — application-side validates JSON before insert; SQLite stores as text. No `CHECK (json_valid(payload_json))` because it slows hot-path inserts and the application layer is already validating via Pydantic.
- `request_id` — column exists in Stage A so Stage A.5 can fill it without a migration; Stage A leaves it NULL. The Stage A.5 X-Request-ID wiring is what makes the two-row correlation usable.
- `actor_kind` (clients.audit_log only) — distinguishes operator-initiated mutations from system-initiated ones (CT monitor publishing a delta, retention timer firing). The api never writes `actor_kind = 'system'` (its rows are always operator-initiated by definition); the scheduler / worker / delivery writers can write either.

### 1.4 What does NOT change in Stage A

- `clients`, `client_domains`, `consent_records`, `prospects`, `brief_snapshots`, `findings`, `finding_occurrences`, `delivery_log`, `pipeline_runs`, `signup_tokens`, `subscriptions`, `payment_events`, `conversion_events`, `onboarding_stage_log`, `retention_jobs` — all untouched as far as their existing schema. They live in `clients.db`, which the api container mounts `:rw` (provided by PR #49 on main; Stage A's writes against this DB are limited to retention CAS UPDATEs + paired audit rows per the narrow-write invariant in §2.7).
- `client-db-schema.sql` — gets ONE addition for Option B: a new SECTION at the end of the file for `audit_log` (clients-side). The three Stage A tables that live in `console.db` (operators, sessions, console.audit_log) go into the new `console-db-schema.sql` instead (D2, 2026-04-28). The `clients.audit_log` table is the only Stage A schema touch on `client-db-schema.sql`.
- No new columns on the existing `clients.db` tables. (Stage A.5 adds `request_id` propagation, but that's middleware, not schema.)

---

## 2. Migration order

Stage A introduces a SECOND `init_db_*` pipeline alongside the existing `init_db()` (clients.db). The new factory `init_db_console()` (see §2.5 for placement) follows the same shape as `init_db()` — `executescript(schema_sql) → apply_pending_migrations(conn)` — but operates against `/data/console/console.db`. Both factories are invoked at api startup; the order is `init_db()` first (clients.db, no change), `init_db_console()` second. Neither depends on the other.

### 2.1 Schema-add pass

**Console side.** The three console-side CREATE TABLE statements (operators, sessions, audit_log) live in `docs/architecture/console-db-schema.sql`, alongside their indexes. The new factory `init_db_console()` loads this file via `executescript` at startup, and every statement is `IF NOT EXISTS`, so no entry in any `_COLUMN_ADDS` table is needed for table creation itself.

**Clients side (Option B addition).** `docs/architecture/client-db-schema.sql` gets ONE addition: a new SECTION at the end of the file with the `clients.audit_log` CREATE TABLE block from §1.3.b plus its five indexes. The existing `apply_pending_migrations(conn)` flow against `clients.db` picks this up via `executescript`. The fresh-DB path (every dev `make dev-up`, every prod first-deploy of Stage A) gets the table from the schema file. The upgrade path (existing prod DB rolling forward to Stage A) gets the table from a Stage A entry in `_TABLE_ADDS` (or whatever the existing migration helper is named in `src/db/migrate.py`) so that already-running databases gain the table on api/scheduler startup without a manual SQL step. The `IF NOT EXISTS` guard makes both paths safe to run twice.

`apply_pending_migrations(conn)` for `clients.db` continues to read its existing `_COLUMN_ADDS` registry from `src/db/migrate.py`; Stage A adds one new entry for the `audit_log` table via the `_TABLE_ADDS` mechanism (or, if no such mechanism exists today, via a single new entry at the bottom of `client-db-schema.sql` plus a one-shot CREATE TABLE in a `_TABLE_ADDS` list — implementing PR picks the simpler path; both are idempotent). For `console.db` we ship a separate (initially empty) migration registry — see §2.5.

### 2.2 Operator #1 seed (one-time)

After the tables exist in `console.db`, operator #1 must be seeded from the existing file-backed `console_password`. This is the only data migration in Stage A.

The seed runs inside `init_db_console()`, after the per-DB `apply_pending_migrations(conn)`, gated by:

1. The `operators` table (in `console.db`) is empty.
2. `get_secret("console_password", "CONSOLE_PASSWORD")` returns a non-empty value. The secret file path is unchanged — `console.db` is the destination of the WRITE; the secret is still mounted on the api container the same way.
3. `os.environ.get("CONSOLE_USER")` returns a non-empty value.

If all three hold, insert one row INTO `console.db`'s `operators` table. **Username normalisation at seed time** (security review 2026-04-28 evening — Amendment 5):

- `username = CONSOLE_USER.strip().lower()` — explicit normalisation: trim surrounding whitespace, then lowercase. Stored in lowercase in the DB. This is the canonical form; every login lookup and every runbook path uses the same `.strip().lower()` to match. The `CREATE UNIQUE INDEX idx_operators_username_lower ON operators(LOWER(username))` from §1.1 enforces case-insensitive uniqueness at the DB level too — the application normalises by convention, the index is the safety net.
- `display_name = CONSOLE_USER.strip()` — same trim, but case preserved for the UI ("logged in as Federico" vs "logged in as federico"). Operator can edit later via Stage A.5 admin UI; not in scope for Stage A.
- `password_hash = argon2id_hash(console_password)` — see §2.5 for the hashing module placement
- `role_hint = 'owner'`
- `created_at = updated_at = _now()`

The seed code logs the normalised username at INFO level so any case-mismatch confusion is operationally visible at first start: `INFO: seeded operator #0 username=admin (from CONSOLE_USER='Admin')`.

If any of the three preconditions fail, the seed is a silent no-op (logs a single INFO line) — `init_db_console()` does not raise. This means a fresh dev `console.db` without `CONSOLE_USER` set will start with zero operators. The API responds to that empty-operators state per D5 (resolved 2026-04-28): `/console/auth/whoami` returns **204 with empty body** (signaling "no operators seeded — bootstrap state, not auth failure"); `/console/auth/login` continues to return 401 (the SPA still surfaces the login form, but with the splash branch keyed off the 204 from `/whoami`). The "operators exist but all disabled" state is its own 409 wire signal per §3.5 (security review 2026-04-28 evening). That's the right default — there's no "anyone can log in" failure mode.

### 2.3 Idempotency

- Re-running `init_db_console()` on a `console.db` with operator #1 already seeded: the seed checks `SELECT COUNT(*) FROM operators` and skips when non-zero. It does NOT re-hash and overwrite — that would invalidate any existing sessions on every container start.
- Changing `CONSOLE_PASSWORD` and restarting: the seed does not re-fire. The new password is ignored. To rotate operator #1's password in Stage A, Federico edits the row directly in SQLite — using the `api` container, which is the only container with RW on `console-data` (see §2.7 below) — or waits for Stage A.5's admin UI. Document this in the rollback section.

### 2.4 Backwards compatibility for existing dev workflows

Two existing flows break when Basic Auth is removed:

1. **`scripts/dev/verify_dev_console_seed.py`** — currently issues `curl -u admin:devpassword http://127.0.0.1:8001/console/...`. This script must be updated as part of the Stage A PR. The replacement uses a two-step shell: (a) `POST /console/auth/login` to obtain a session ticket, (b) re-curl with the cookie attached. A small helper function `_console_session_curl()` lives at the top of the verify script.

2. **Any operator habit of `curl -u admin:pw` from the host shell.** Documented in `docs/development.md`'s troubleshooting section as "operators now log in via the SPA at `http://localhost:8001/app`; for shell-side curls use `scripts/dev/console_login.sh` which prints a `Cookie: heimdall_session=...` header."

A new helper script `scripts/dev/console_login.sh`:

- Reads `CONSOLE_USER` + `CONSOLE_PASSWORD` from `.env.dev` or arg overrides.
- POSTs to `/console/auth/login`.
- Prints the `Set-Cookie` value to stdout in `Cookie: heimdall_session=...; heimdall_csrf=...` form, ready to paste into a `curl -H` flag.
- Exits 1 with a clear error message on auth failure.

This is the migration path for the existing `make dev-seed-console`-style workflow. No machine-account flow; the dev shell uses Federico's operator credentials for the duration of Stage A. Stage A.5 may revisit if a CI smoke needs to call `/console/*` without a human.

### 2.5 Hashing module placement + console-DB connection module

**Argon2id hashing** lives at `src/api/auth/hashing.py` (new file, ~30 LOC):

- Wraps `argon2.PasswordHasher` from the `argon2-cffi` package.
- Single instance with explicit parameters: `time_cost=2, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16`. These match argon2-cffi's RFC 9106 first-recommended defaults and run in <100ms on a Pi5.
- Optional pepper: if `/run/secrets/operator_password_pepper` exists, it's HMAC-SHA256-prefixed onto the password before passing to Argon2 (a defense-in-depth against DB-only theft). Stage A ships WITHOUT a pepper file by default; Federico can add the secret post-deploy if desired without a code change.
- Two functions: `hash_password(plaintext: str) -> str` and `verify_password(hash: str, plaintext: str) -> bool`.

Add `argon2-cffi` to `requirements.txt` and the API container's `Dockerfile.api`. This is a new pip dep, so the next push will trigger an image rebuild.

**Console DB connection** lives at `src/db/console_connection.py` (new file, ~80 LOC) — kept separate from `src/db/connection.py` so the existing module stays focused on `clients.db`. Per D2 (2026-04-28), splitting the connection modules makes the boundary obvious in code-review; a single `connection.py` with two factory functions blurs the line.

`src/db/console_connection.py` exports:

- `CONSOLE_DB_PATH` constant — resolved once at import via `os.environ.get("CONSOLE_DB_PATH", "/data/console/console.db")`.
- `init_db_console()` — mirrors `init_db()` from `src/db/connection.py`: opens the connection, runs `executescript(open("docs/architecture/console-db-schema.sql").read())`, applies any pending migrations from a separate `_CONSOLE_COLUMN_ADDS` registry (initially empty, lives in the same module — no need for a separate `migrate.py` until the schema actually grows), invokes `_seed_operator_zero(conn)`, runs `PRAGMA wal_checkpoint(TRUNCATE)`, closes.
- `get_console_conn() -> sqlite3.Connection` — context-manager-friendly factory used by the auth router and the audit-log helper. Sets `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL` (idempotent), `timeout=5`.
- `_seed_operator_zero(conn)` — internal helper invoked by `init_db_console()`.

The auth/session/audit code (`src/api/auth/sessions.py`, `src/api/auth/audit.py`, `src/api/auth/middleware.py`, `src/api/routers/auth.py`) calls `get_console_conn()` for ALL its DB work — never `get_conn()` (clients.db). The two connection paths are independent; nothing in Stage A needs cross-DB JOINs.

(Optional, not required for Stage A: a `src/db/console/` subpackage with `connection.py` + `seeds.py` + future `migrate.py`. For now a single flat `src/db/console_connection.py` is sufficient and avoids spec churn — revisit when the second console-side migration arrives.)

### 2.6 Migration ordering summary

```
1. Container starts (api).
2. init_db()  [clients.db — UNCHANGED in Stage A]:
   a. executescript(client-db-schema.sql) (idempotent).
   b. apply_pending_migrations() runs — no Stage A entries in _COLUMN_ADDS.
   c. wal_checkpoint(TRUNCATE).
3. init_db_console()  [console.db — NEW in Stage A]:
   a. executescript(console-db-schema.sql) creates the three tables (idempotent).
   b. apply_pending_migrations() against console.db — no entries yet.
   c. _seed_operator_zero(conn) — inserts operator #1 if conditions met.
   d. wal_checkpoint(TRUNCATE).
4. FastAPI app boots — SessionAuthMiddleware engages AFTER step 3 has
   committed. The middleware reads /data/console/console.db; if the
   factory hasn't run, the middleware fails closed (401 on every protected
   route). create_app() awaits both init functions in its lifespan
   before yielding the app to uvicorn.
5. Existing CONSOLE_USER + console_password env/secret REMAIN MOUNTED in
   docker-compose.yml — they're now used only by the seed at step 3c.
   Removed in a follow-up PR after one production release of Stage A.
```

### 2.7 Container access matrix for `console-data`

A new named volume `console-data` is added to `infra/compose/docker-compose.yml`. Container access:

| Container | `console-data` mount | Why |
|---|---|---|
| `api` | `/data/console:rw` | Issues sessions, writes audit rows, runs `init_db_console()` + the operator-#0 seed at startup, performs `whoami`/login/logout. Only Stage A writer. |
| `scheduler` | not mounted | Does not authenticate operators. Retention timer + CT timer write to `clients.db` only. If Stage A.5 introduces operator-attributed scheduler actions (e.g. an operator forces a scan), the action is dispatched via Redis from `api` — which writes the audit row in its own transaction — keeping `console-data` writer-set = `{api}`. |
| `worker` | not mounted | Pure scan executor. No operator state. |
| `delivery` | not mounted | Telegram bot; receives client-side `/start` / "Got it" callbacks, not operator-attributed. |
| `signup` (SvelteKit static + dev Vite) | not mounted | Public-facing site; no operator surface. |

Stage A's writer set for `console.db` is therefore exactly `{api}`. This keeps SQLite WAL contention trivial (single writer, no need to think about checkpoint coordination).

**Stage A inherits the api's `:rw` mount on `clients.db` (provided by PR #49, separate, direct to main).** The api's *new* writer surface against `clients.db` in Stage A is exactly the rows listed in §7.3 (retention CAS UPDATEs + paired audit rows). All other writes to `clients.db` continue to come from scheduler / worker / delivery, exactly as today. The widening is provided by main; Stage A consumes it.

| Endpoint | Write |
|---|---|
| `POST /console/retention-jobs/{id}/force-run` | CAS UPDATE on `retention_jobs` + INSERT into `clients.audit_log` |
| `POST /console/retention-jobs/{id}/cancel` | CAS UPDATE on `retention_jobs` + INSERT into `clients.audit_log` |
| `POST /console/retention-jobs/{id}/retry` | CAS UPDATE on `retention_jobs` + INSERT into `clients.audit_log` |

The "narrow blast radius" stance from D2 is preserved by code review (not by mount mode): the api's only writes against `clients.db` are the three audit-paired retention CAS UPDATEs above, no other tables, no other call sites. A reviewer auditing the api's `sqlite3.connect(clients_db_path)` usage greps the codebase and finds exactly the retention router file. D2's split (`console.db` for the bulk of control-plane state) is the bigger blast-radius reduction and is unchanged.

If a future stage adds a second console-side writer (e.g. scheduler writing `console.audit_log` for an operator-attributed scheduler action), this table is the place to widen — and the corresponding `add :rw mount` is a danger-zone diff just like Stage A's initial mount.

---

## 3. Auth flow diagrams

All flows below are over HTTPS in production (terminating at the Pi5's reverse proxy / Cloudflare in front of the API). In dev, plain HTTP on `localhost:8001` is acceptable; the `Secure` cookie attribute is set conditionally based on `os.environ.get("HEIMDALL_COOKIE_SECURE", "1") == "1"`.

### 3.1 Login flow

The handler runs in a fixed three-phase order: **(1) per-IP rate-limit pre-check (Redis)**, **(2) credential lookup + Argon2id verify (SQLite)**, **(3) session issue + audit + Set-Cookie (SQLite)**. The rate-limit gate is the FIRST step — username lookup and Argon2id are NEVER reached until the rate-limit check passes. This is normative; the implementing PR must order the steps as specified.

```
Browser                    FastAPI / api container          Redis            console.db
   |                                |                          |                |
   |  POST /console/auth/login      |                          |                |
   |  Body: {username, password}    |                          |                |
   | -----------------------------> |                          |                |
   |                                |                          |                |
   |                                |  STEP 1 — rate limit     |                |
   |                                |  key = f"auth:fail:      |                |
   |                                |        {client_ip}"      |                |
   |                                |  fail_count =            |                |
   |                                |    int(redis.get(key)    |                |
   |                                |         or 0)            |                |
   |                                | -----------------------> |                |
   |                                | <----------------------- |                |
   |                                |  IF fail_count >= 5:     |                |
   |                                |    ttl = redis.ttl(key)  |                |
   |                                |    return 429            |                |
   |                                |    Retry-After: ttl      |                |
   |                                |    body: {"error":       |                |
   |                                |      "rate_limited"}     |                |
   |                                |                          |                |
   |                                |  IF Redis is DOWN:       |                |
   |                                |    log warning,          |                |
   |                                |    fall through to       |                |
   |                                |    STEP 2 (fail-open).   |                |
   |                                |    See §3.1.a.           |                |
   |                                |                          |                |
   |                                |  STEP 2 — credentials    |                |
   |                                |  SELECT * FROM operators |                |
   |                                |  WHERE LOWER(username)=? |                |
   |                                |    AND disabled_at IS NULL                |
   |                                | -----------------------------------------> |
   |                                | <----------------------------------------- |
   |                                |                          |                |
   |                                |  argon2.verify(hash, pw) |                |
   |                                |  - constant-time compare |                |
   |                                |  - ~50ms CPU on Pi5      |                |
   |                                |  - if no row matched, run|                |
   |                                |    against a dummy hash  |                |
   |                                |    to keep timing flat   |                |
   |                                |                          |                |
   |                                |  IF mismatch (no row OR  |                |
   |                                |    bad password):        |                |
   |                                |    # Single failure path |                |
   |                                |    # — never distinguish |                |
   |                                |    # "no such user" from |                |
   |                                |    # "wrong password" in |                |
   |                                |    # body, status, or    |                |
   |                                |    # rate-limit counter. |                |
   |                                |    new = redis.incr(key) |                |
   |                                | -----------------------> |                |
   |                                |    IF new == 1:          |                |
   |                                |      redis.expire(       |                |
   |                                |        key, 900)         |                |
   |                                | -----------------------> |                |
   |                                |    audit_log INSERT      |                |
   |                                |    (action='auth.        |                |
   |                                |     login_failed')       |                |
   |                                | -----------------------------------------> |
   |                                |    return 401            |                |
   |                                |                          |                |
   |                                |  STEP 3 — success path         |
   |                                |  redis.delete(key)              |
   |                                |  (clear the per-IP fail counter |
   |                                |   on every successful login —   |
   |                                |   a legitimate operator after a |
   |                                |   typo recovers full quota)     |
   |                                |                                |
   |                                |  Generate plaintext session    |
   |                                |    token = secrets              |
   |                                |      .token_urlsafe(32)        |
   |                                |    (43 chars, 256 bits entropy)|
   |                                |  Compute token_hash =          |
   |                                |    hashlib.sha256(             |
   |                                |      token.encode()            |
   |                                |    ).hexdigest()               |
   |                                |  Generate csrf_token            |
   |                                |   (32 random bytes, base64url) |
   |                                |                                |
   |                                |  BEGIN IMMEDIATE               |
   |                                |  INSERT INTO sessions          |
   |                                |    (token_hash, csrf_token,    |
   |                                |     operator_id, ...)          |
   |                                |  UPDATE operators              |
   |                                |    SET last_login_at, *_ip     |
   |                                |  INSERT INTO audit_log         |
   |                                |    (action='auth.login_ok')    |
   |                                |    [console.audit_log — see §7]|
   |                                |  COMMIT                        |
   |                                |                                |
   |                                |  The plaintext token is held   |
   |                                |  in memory just long enough to |
   |                                |  set the Set-Cookie header,    |
   |                                |  then dropped. It is never     |
   |                                |  written to any DB row, log,   |
   |                                |  or file.                      |
   |                                |                                |
   |  200 OK                        |                                |
   |  Set-Cookie: heimdall_session  |                                |
   |    (HttpOnly, Secure, SameSite |                                |
   |     =Strict, Path=/, 12h)      |                                |
   |  Set-Cookie: heimdall_csrf     |                                |
   |    (Secure, SameSite=Strict,   |                                |
   |     Path=/, 12h, NOT HttpOnly) |                                |
   |  Body: {                       |                                |
   |    operator: {id, username,    |                                |
   |               display_name,    |                                |
   |               role_hint},      |                                |
   |    expires_at,                 |                                |
   |    absolute_expires_at,        |                                |
   |    csrf_token                  |                                |
   |  }                             |                                |
   | <----------------------------- |                                |
```

Failure modes:
- Unknown username, wrong password, or `disabled_at IS NOT NULL` → 401 with body `{"error": "invalid_credentials"}`. We do NOT distinguish "no such user" from "wrong password" in the body — same shape, same timing (the verify still runs against a dummy hash if the username is missing, to avoid timing oracle).
- Per-IP rate-limit exceeded (≥5 fails in the last 15 min from the same source IP) → 429 with `Retry-After: <seconds>` header (the value is the current Redis TTL on `auth:fail:<ip>`, which is ≤ 900) and body `{"error": "rate_limited"}`. The counter is keyed on source IP, NOT on username — distinguishing "bad password" from "bad username" via the rate-limit signal would leak user enumeration. A 401 increments the counter regardless of whether the username exists; the user-enumeration oracle is closed at the rate-limit layer the same way it is at the response layer.
- DB error → 503.

**What counts as a "fail".** Any 401 returned from `/console/auth/login` increments the per-IP counter — this includes "no such user", "wrong password", and "operator disabled". Any 200 from the same endpoint clears the counter. 429 itself is NOT a fail (the counter is already saturated; we don't compound). 503 is NOT a fail (DB error is not an attacker signal).

#### 3.1.a Rate-limit Redis contract

| Item | Value |
|---|---|
| Key format | `auth:fail:<client_ip>` — exactly this string; the IP comes from `request.client.host`, NOT from `X-Forwarded-For` (that header is operator-controlled at the reverse proxy and any production deploy that puts a proxy in front of api MUST set `forwarded-allow-ips` on uvicorn so `request.client.host` is the trusted upstream value) |
| Threshold | 5 fails |
| Window | 15 min (900s) — implemented as the TTL on the key |
| Counter mechanic | `redis.incr(key)`; if the return value is 1 (the key was just created by this INCR), immediately `redis.expire(key, 900)` to install the TTL. Subsequent INCRs in the same window inherit the TTL set by the first one (Redis does not reset the TTL on INCR, which is what we want — a sliding window would let an attacker pace 4 attempts every 14 min indefinitely). |
| `Retry-After` header source | `redis.ttl(key)` at the moment of the 429 decision. Value is in seconds; clamp to `[1, 900]` to defend against TTL of -1 / -2 edge cases (e.g. a key that lost its TTL via manual ops). |
| Counter cleared on | success (`redis.delete(key)` in step 3 of §3.1) |
| Per-username counter | NOT used. Per-username lockout enables targeted DoS (an attacker locks out a known operator with five wrong attempts from any IP, denying legitimate access). Per-IP only, by design. |
| Per-username audit | The `audit_log` row written on `auth.login_failed` records the attempted username (or `NULL` if the username didn't exist — same shape). Forensic correlation lives in audit, not in the rate-limit counter. |

**Redis-down behaviour: fail-open.** If `redis.get` / `redis.incr` raises (Redis container down, network blip, password rotated), the rate-limit pre-check logs a WARNING and falls through to STEP 2 unconditionally. The login proceeds against Argon2id — auth itself is still enforced, just not throttled. Rationale: Redis is a degraded-mode dependency for this surface, not a primary one; treating its outage as auth-down would let a single Redis incident lock every operator out of the console for the duration of the outage. Argon2id's ~50ms cost gives us 20 attempts/s/IP as the worst-case throughput while Redis is down, which is well below the rate at which a weak password falls — a Redis outage of seconds-to-minutes is a brief degradation, not a security disaster. The fail-open decision is logged at WARNING level (one line per request) so the operator sees the throttle is off, and the underlying Redis incident is the actual fix.

**Why fail-open, not fail-closed.** The alternative is "Redis down → 503 every login". That converts a Redis-availability incident into an auth-availability incident. Heimdall's operator console is the control plane; locking the operator out of the control plane during any Redis blip is a harder failure mode than the brief throttle gap. The choice is recorded explicitly here so a future change cannot silently flip it.

The Redis client + helpers live at `src/api/auth/rate_limit.py` — see Appendix A. Lifting the Redis call out of the router makes it testable in isolation (mock the rate-limit module, exercise the router; mock the underlying Redis client, exercise the rate-limit module).

### 3.2 Authenticated request flow

```
Browser                    FastAPI middleware                console.db
   |                                |                                |
   |  GET /console/dashboard        |                                |
   |  Cookie: heimdall_session=...  |                                |
   | -----------------------------> |                                |
   |                                |                                |
   |                                | SessionAuthMiddleware:         |
   |                                |  Extract heimdall_session      |
   |                                |  cookie value (plaintext, the  |
   |                                |  raw secrets.token_urlsafe(32) |
   |                                |  string the browser holds).    |
   |                                |                                |
   |                                |  IF cookie missing:            |
   |                                |    return 401                  |
   |                                |                                |
   |                                |  Compute lookup digest:        |
   |                                |    presented_hash =            |
   |                                |      hashlib.sha256(           |
   |                                |        cookie_value.encode()   |
   |                                |      ).hexdigest()             |
   |                                |  (The plaintext cookie value   |
   |                                |   is NEVER used as a DB key    |
   |                                |   and NEVER persisted server-  |
   |                                |   side. It exists only on the  |
   |                                |   wire and in browser memory.) |
   |                                |                                |
   |                                |  SELECT * FROM sessions s      |
   |                                |  JOIN operators o ON ...       |
   |                                |  WHERE s.token_hash = ?        |
   |                                |    AND s.revoked_at IS NULL    |
   |                                |    AND s.expires_at > now      |
   |                                |    AND s.absolute_expires_at   |
   |                                |        > now                   |
   |                                |    AND o.disabled_at IS NULL   |
   |                                |  (param: presented_hash)       |
   |                                | -----------------------------> |
   |                                | <----------------------------- |
   |                                |                                |
   |                                |  IF no row (fail closed —      |
   |                                |  same shape and timing as      |
   |                                |  "cookie missing" so an        |
   |                                |  attacker cannot distinguish   |
   |                                |  "no such session" from        |
   |                                |  "expired/revoked"):           |
   |                                |    Set-Cookie: heimdall_*=     |
   |                                |       (clear)                  |
   |                                |    return 401                  |
   |                                |                                |
   |                                |  IF state-changing method      |
   |                                |     (POST/PUT/PATCH/DELETE):   |
   |                                |    Verify X-CSRF-Token header  |
   |                                |    matches s.csrf_token        |
   |                                |    constant_time_compare       |
   |                                |    IF mismatch: return 403     |
   |                                |                                |
   |                                |  Sliding-window refresh:       |
   |                                |  IF (now - last_seen_at) > 60s |
   |                                |    UPDATE sessions             |
   |                                |     SET expires_at=now+IDLE,   |
   |                                |         last_seen_at=now,      |
   |                                |         last_seen_ip=?,        |
   |                                |         last_seen_ua=?         |
   |                                |    (capped at                  |
   |                                |     absolute_expires_at)       |
   |                                |                                |
   |                                |  Attach to request.state:      |
   |                                |    operator_id, session_id,    |
   |                                |    role_hint                   |
   |                                |                                |
   |                                |  call_next(request)            |
   |                                |  → route handler runs          |
   |                                |  → response returned            |
   |                                |                                |
   |  200 OK                        |                                |
   | <----------------------------- |                                |
```

Refresh debouncing: we don't UPDATE the session row on every request — only when `last_seen_at` is stale by ≥60 seconds. This cuts write traffic on the session table by ~10–100x without losing meaningful fidelity (a request-by-request audit of session activity is not a Stage A goal; that's the audit log's job).

### 3.3 Refresh / sliding-window semantics

There is no separate refresh endpoint. Each authenticated request that passes the middleware also acts as the refresh trigger (subject to the 60-second debounce above). The contract:

- `IDLE_TTL = 15 minutes` — the sliding window. If the operator goes idle for >15 min, the session expires.
- `ABSOLUTE_TTL = 12 hours` — the hard cap. After 12h since `issued_at`, the session is dead regardless of activity. Operator must log in again.
- On each refresh, the new `expires_at = min(now + IDLE_TTL, absolute_expires_at)`.

The browser does not need to call any endpoint to refresh. The cookie's own `Max-Age` is set to `ABSOLUTE_TTL`, but the server is the source of truth for validity.

### 3.4 Logout flow

```
Browser                    FastAPI                          console.db
   |                                |                                |
   |  POST /console/auth/logout     |                                |
   |  Cookie: heimdall_session=...  |                                |
   |  X-CSRF-Token: ...             |                                |
   | -----------------------------> |                                |
   |                                |  Middleware validates session  |
   |                                |  (sha256 of presented cookie → |
   |                                |  token_hash lookup), validates |
   |                                |  CSRF.                         |
   |                                |                                |
   |                                |  UPDATE sessions               |
   |                                |    SET revoked_at = now        |
   |                                |    WHERE token_hash = ?        |
   |                                |      AND revoked_at IS NULL    |
   |                                |    (param: sha256(cookie))     |
   |                                |  INSERT INTO audit_log         |
   |                                |    (action='auth.logout')      |
   |                                |    [console.audit_log — see §7]|
   | <----------------------------- |                                |
   |  204 No Content                |                                |
   |  Set-Cookie: heimdall_session=;|                                |
   |    Max-Age=0; Path=/           |                                |
   |  Set-Cookie: heimdall_csrf=;   |                                |
   |    Max-Age=0; Path=/           |                                |
```

Idempotent: a second logout with the now-revoked token gets 401 (the middleware refuses it before reaching the handler). The browser still receives the cleared cookies on the way out.

### 3.5 `/console/auth/whoami` — split system states

Per D5 (resolved 2026-04-28) plus the 2026-04-28 evening security review, `/console/auth/whoami` distinguishes **four** system states, not three. The earlier draft conflated "genuine empty bootstrap" with "operators exist but all disabled" under a single 204 — that was wrong: the SPA needs to render a different UX for each, and the wire signal must say which is which.

| # | Condition | Status | Body | SPA branch |
|---|---|---|---|---|
| 1 | `operators` table has **zero rows total** (regardless of `disabled_at`). Genuine empty bootstrap, fresh install. | **204 No Content** | empty | "no operators seeded — bootstrap state, run the seed step" splash |
| 2 | At least one row exists, but **every** row has `disabled_at IS NOT NULL`. Operators exist but all disabled (compromise lockdown, staff turnover, or post-rotation cleanup). | **409 Conflict** | `{"error": "all_operators_disabled"}` | "all operators disabled — contact owner / re-enable via runbook" splash |
| 3 | At least one active operator exists, valid session cookie present and matches an active operator. | **200 OK** | `{operator: {...}, session: {...}, csrf_token}` | normal authenticated UI |
| 4 | At least one active operator exists, AND the request is unauthenticated (cookie missing, invalid, expired, or the matched operator is disabled). | **401 Unauthorized** | `{"error": "not_authenticated"}` | login form |

The pre-check distinguishes states 1, 2, and "active operators exist" via two SQL probes (cheap; both rows from a tiny table):

```python
total = conn.execute("SELECT COUNT(*) FROM operators").fetchone()[0]
active = conn.execute("SELECT COUNT(*) FROM operators WHERE disabled_at IS NULL").fetchone()[0]

if total == 0:
    return Response(status_code=204)                       # State 1
if active == 0:
    return JSONResponse(
        status_code=409,
        content={"error": "all_operators_disabled"},
    )                                                       # State 2
# else fall through to cookie validation → 200 or 401
```

**Why 409 (not 503) for state 2.** 409 Conflict is HTTP-native semantics for "the resource exists but is in a state that prevents the operation" — operators exist, they just can't sign in right now. 503 Service Unavailable would also fit ("service is up, but degraded") but it implies an infrastructure-level issue that load balancers / monitoring tools may treat as backend-down. The state is a deliberate operational posture, not an outage; 409 communicates that the right response is administrative (re-enable an operator) rather than wait-and-retry.

The 204 and 409 branches are computed BEFORE any cookie inspection. No audit row written, no DB state mutated, no pretense that an auth attempt happened in either bootstrap branch.

The login endpoint (`POST /console/auth/login`) is unchanged by this amendment — still 401 on bad credentials, including the "no operators seeded" case (manifests as "no such user" on every login attempt) and the "all disabled" case (manifests as "no such user" because the SELECT filters on `disabled_at IS NULL`). The 204 / 409 wire signals live only on `/whoami`; the SPA's boot flow probes `/whoami` first and decides which UI branch to render before showing any login form.

Why a body-less 204 for state 1: 204 is the HTTP-native "request succeeded, nothing to return" code. The bootstrap state is a binary fact ("no operators exist") and a body adds nothing. Why an explicit JSON body for state 2: 409 is generic enough that the SPA wants to disambiguate via a sentinel string in case future variants of "all disabled" carry richer context (e.g. "all disabled because compromise was detected at time T" — Stage A.5 territory).

### 3.6 WebSocket handshake — see §5

Note: WebSocket auth does NOT go through `SessionAuthMiddleware`. Per §5, the middleware is HTTP-only (Starlette's `BaseHTTPMiddleware` does not reliably gate WS scopes), and `/console/ws` performs auth inside the handler — read cookie → SHA-256 → look up `token_hash` → accept or close with code 4401 before `ws.accept()`. This is a deliberate departure from the original draft, which assumed middleware would gate the upgrade.

---

## 4. Session ticket spec

### 4.1 Cookie names

- `heimdall_session` — the opaque session token. `HttpOnly`, `Secure` (production), `SameSite=Strict`, `Path=/`, `Max-Age=43200` (12h matching `ABSOLUTE_TTL`).
- `heimdall_csrf` — the CSRF double-submit token. NOT `HttpOnly` (the SPA must read it via `document.cookie` to put in `X-CSRF-Token`). `Secure` (production), `SameSite=Strict`, `Path=/`, `Max-Age=43200`.

`SameSite=Strict` is acceptable for Heimdall because the console is single-origin (no cross-site embedding, no third-party redirects we want to preserve session through). `Lax` would be strictly worse for our threat model.

### 4.2 Token format

**Plaintext on the wire, SHA-256 digest at rest.**

- The plaintext token is `secrets.token_urlsafe(32)` — 32 random bytes from the OS CSPRNG, encoded as base64url (43 chars, no padding).
- The browser receives the **plaintext** value in the `heimdall_session` cookie and presents it on every subsequent request.
- The server stores **only** the digest: `hashlib.sha256(token.encode()).hexdigest()` (64 hex chars) in `sessions.token_hash`. The unhashed plaintext is never persisted server-side — not in `sessions`, not in any log, not in any audit row, not on disk anywhere.
- On every authenticated request, the middleware (or WS handler — see §5) computes `sha256(presented_cookie_value)` and looks up the matching row in `sessions` by `token_hash`. The plaintext value is dropped after the lookup completes.
- **No PBKDF.** The token is 256 bits of entropy from `secrets.token_urlsafe(32)`. It is not a human password; the brute-force / dictionary attack space that justifies Argon2/bcrypt/scrypt for `password_hash` does not apply here. SHA-256 is fast enough that auth latency stays sub-millisecond. The point of hashing the session token is solely to make a database leak non-equivalent to a session-impersonation oracle — not to slow down a brute-force attempt against the token itself, which is unattackable at 2^256.
- The token is the entire identity. It is opaque to the client. There is no payload, no signature, no claims — server-side `token_hash` lookup is the only validation path.

The CSRF token is generated identically (32 bytes, base64url, 256 bits of entropy) and stored verbatim in `sessions.csrf_token`. It is NOT hashed at rest, because the SPA needs to read its plaintext value from the `heimdall_csrf` cookie on every refreshable load and echo it back as the `X-CSRF-Token` header — a hashed CSRF token would force the server to send the plaintext on every response, which adds wire traffic with no security gain (a DB-only leak of CSRF values is not standalone-usable; the attacker would still need the matching session cookie that has not been leaked). The CSRF token is a per-session value — re-issued on each new session, never rotated mid-session (see §4.4).

Lifecycle, in one sentence: plaintext exists in three places — the OS CSPRNG buffer at issue time, the api process memory between generation and `Set-Cookie`, and the browser's cookie jar. Everywhere else, only the digest exists.

### 4.3 TTL + absolute cap + refresh semantics

| Setting | Value | Source |
|---|---|---|
| `IDLE_TTL` | 15 min | `os.environ.get("CONSOLE_SESSION_IDLE_TTL_MIN", "15")` |
| `ABSOLUTE_TTL` | 12 h | `os.environ.get("CONSOLE_SESSION_ABSOLUTE_TTL_MIN", "720")` |
| `REFRESH_DEBOUNCE` | 60 s | constant in `src/api/auth/sessions.py` |

Both env vars are read once at app startup (not per request). Document the override pattern in `docs/development.md`'s "Console session" subsection.

### 4.4 CSRF defense

Strategy: **`SameSite=Strict` cookie + double-submit token (header).**

Why both: `SameSite=Strict` blocks cross-site form-POST and cross-site `fetch()`-with-credentials in modern browsers, which covers the realistic browser-based CSRF threat. The double-submit header `X-CSRF-Token` is a defense-in-depth against the small population of older browsers that don't honor SameSite, and against any future SameSite bypass.

How it works:

1. On login, the server generates `csrf_token` and sets it in the `heimdall_csrf` cookie (NOT HttpOnly).
2. The SPA's API wrapper reads `document.cookie['heimdall_csrf']` and includes it as `X-CSRF-Token: <value>` on every state-changing request (POST/PUT/PATCH/DELETE). GET/HEAD/OPTIONS are exempt.
3. The middleware compares the header value against `sessions.csrf_token` for the active session, using `secrets.compare_digest`.
4. Mismatch → 403 with `{"error": "csrf_mismatch"}`. The session is NOT revoked on CSRF failure (a buggy client should not log out the operator); only auth failures revoke.

The CSRF token stays the same for the lifetime of the session. We do NOT rotate per-request — the operational complexity (race conditions on parallel requests) outweighs the marginal security gain when `SameSite=Strict` already covers the realistic threat.

### 4.5 Multi-process correctness

Heimdall's api container runs uvicorn. If `--workers >1` is ever introduced (today it's 1), nothing in the session design assumes single-process: every read/write goes through SQLite, which is the synchronization point. The 60-second refresh debounce uses `last_seen_at` from the row itself, not a process-local cache, so two workers reading the same session don't double-write.

---

## 5. WebSocket auth handshake

### 5.1 Today's state

`/console/ws` (`src/api/console.py:811-933`) accepts the upgrade unconditionally and relies on `BasicAuthMiddleware` to have already authenticated the upgrade request via the `Authorization` header. This works for browser clients (they auto-send Basic Auth on upgrade requests after a previous auth challenge) but doesn't work for any client that opens a WebSocket without first making an HTTP request — and it means the auth credential rides on every upgrade request, which we're moving away from.

### 5.2 Why HTTP middleware does not authenticate the upgrade — and the fix

**`BaseHTTPMiddleware` does NOT reliably gate WebSocket upgrades.** Starlette's `BaseHTTPMiddleware` (and any FastAPI middleware that derives from it via `app.add_middleware(...)` with a `dispatch`-style class) is documented and implemented as HTTP-only. The WebSocket upgrade handshake passes through the ASGI app via the `websocket` scope, not the HTTP scope; the `dispatch` method's `Request` / `call_next` machinery is built around `http` scope semantics, and there is a long-running issue chain on this in encode/starlette confirming the gap. Earlier drafts of this spec (and the original Stage A planning) assumed the middleware would gate WS upgrades the same way it gates HTTP — that assumption is wrong on its face, and any spec that builds on it would ship a WS endpoint that is publicly reachable in dev and prod, regardless of the middleware's HTTP-side behaviour.

There are two ways to fix this. Both are documented; Stage A picks the second.

**Option 1 — raw ASGI middleware that branches on `scope['type']`.** The middleware is written as a bare `async def __call__(self, scope, receive, send)` callable (not a `BaseHTTPMiddleware` subclass), inspects `scope['type']` (`'http'` vs `'websocket'`), and handles both branches explicitly. Skeleton:

```python
class SessionAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # HTTP branch: validate cookie, fail closed with 401 if invalid,
            # else attach state and forward.
            ...
        elif scope["type"] == "websocket":
            # WS branch: validate cookie BEFORE forwarding to the app. On
            # failure, send the 'websocket.close' message with code 4401
            # before the handler is reached.
            ...
        else:
            # 'lifespan' etc. — pass through.
            await self.app(scope, receive, send)
```

This works but has two drawbacks: (a) the middleware now contains DB lookups twice (once for HTTP, once for WS), (b) error handling for the `websocket.close` ASGI message is subtle (you have to send `{"type": "websocket.close", "code": 4401}` correctly, and the upgrade-reject vs after-accept paths are different ASGI messages).

**Option 2 (chosen) — auth inside the WebSocket handler itself, before `await ws.accept()`.** The HTTP middleware no longer touches `/console/ws` at all. The WS route is publicly reachable at the HTTP-middleware layer (because WS scope bypasses the middleware), but the handler refuses to accept without auth. The handler reads the session cookie from `ws.cookies` (Starlette / FastAPI exposes it on `WebSocket` connections), validates against `console.db`, and either accepts or closes with code 4401 before the upgrade completes from the client's perspective.

This is simpler, more explicit, and grep-able. It also keeps the middleware focused on HTTP — its only job — and removes the temptation to grow a second DB code path inside it.

### 5.3 Stage A WS auth contract (chosen path)

The WS handler at `/console/ws` (in `src/api/routers/liveops.py` per §6) follows this entry contract:

```python
@router.websocket("/console/ws")
async def console_ws(ws: WebSocket) -> None:
    # 1. Read the session cookie BEFORE accepting the upgrade.
    cookie_value = ws.cookies.get("heimdall_session")
    if not cookie_value:
        # Per RFC 6455, you MUST accept before you can close cleanly.
        # FastAPI's WebSocket exposes `close(code=...)` which sends the
        # close frame; we accept-then-close so the client sees a
        # well-formed 4401 instead of a brutal HTTP-level 403.
        await ws.accept()
        await ws.close(code=4401)
        return

    # 2. Hash the presented cookie and look up in console.db.
    presented_hash = hashlib.sha256(cookie_value.encode()).hexdigest()
    session_row = await asyncio.to_thread(
        validate_session_by_hash, presented_hash
    )
    if session_row is None:
        await ws.accept()
        await ws.close(code=4401)
        return

    # 3. The handler now knows operator_id / session_id without
    #    relying on middleware state.
    operator_id = session_row["operator_id"]
    session_id  = session_row["id"]

    # 4. NOW accept and proceed.
    await ws.accept()

    # 5. Write the per-WS audit row in the same DB transaction that
    #    refreshes session.last_seen_at — both in console.db.
    write_console_audit_row(...)

    # 6. Existing /console/ws body — pubsub forwarding etc.
    ...
```

`validate_session_by_hash(presented_hash)` is a thin wrapper around the same SELECT the middleware uses (§3.2): joins `sessions` to `operators`, checks `revoked_at IS NULL`, `expires_at > now`, `absolute_expires_at > now`, `operators.disabled_at IS NULL`. On match, returns the row; on miss, returns None. The function is sync (sqlite3) and called via `asyncio.to_thread` to keep the event loop unblocked.

CSRF is NOT checked on the WS handshake. The session cookie + `SameSite=Strict` is the cross-site defense; an attacker on a third-party origin cannot persuade the browser to attach the cookie to a same-origin WS upgrade in a meaningful way (and we're not protecting against an attacker who already has the session cookie — that's a session-theft scenario, not a CSRF one).

### 5.4 Non-browser / cookie-less clients (deferred path)

The earlier "first-frame ticket" fallback (Stage A draft §5.2 Stage 2) is **deferred out of Stage A**. Once Stage A ships the cookie-only path, any non-browser ops script can use `scripts/dev/console_login.sh` to capture the session cookie and pass it via standard WebSocket libraries' cookie headers (Python's `websockets`, Node's `ws`, etc.). The first-frame fallback adds API surface (the auth_required → auth → auth_ok dance), audit-row corner cases (which operator did the connect originate from before the first frame?), and timeout state machines that we don't need today.

If a future stage discovers a non-browser client that genuinely cannot set cookies on the upgrade, the first-frame path can land then — at that point it lives entirely inside the WS handler too (consistent with §5.2 Option 2's "auth in the handler" stance), so the design ripple is local.

### 5.5 `/console/demo/ws/{scan_id}` — same path

The demo WS endpoint (`src/api/console.py:983` today, `src/api/routers/liveops.py` post-carve) follows the same contract: read cookie, hash, validate, accept-or-close-with-4401. Demo replay is operator-only by design.

### 5.6 What the middleware does NOT do

Concretely, the SessionAuthMiddleware (HTTP-only, in `src/api/auth/middleware.py`) explicitly does NOT register itself for `scope['type'] == 'websocket'`. If Starlette were to start passing WS scopes through HTTP middleware in some future version, the middleware should still no-op: a defensive `if scope.get("type") == "websocket": return await self.app(scope, receive, send)` at the top of `__call__` is cheap insurance. Document this in the middleware's module docstring.

The HTTP middleware's whitelist (`/console/auth/login`, `/console/auth/whoami`, `/health`, `/results/...`, `/signup/...`) does NOT need to add `/console/ws` — that path was never going to hit the middleware anyway. Keeping the whitelist list to the routes that genuinely traverse HTTP middleware avoids implying the middleware has reach it doesn't.

### 5.7 Close codes

| Code | Meaning |
|---|---|
| 1000 | Normal closure (operator navigated away, server shutdown) |
| 1008 | Policy violation — used today for "Unknown scan_id" on `/console/demo/ws/{scan_id}`; retain |
| **4401** | **Authentication required / failed** — new in Stage A. Used when the cookie is missing, the cookie's hash doesn't match a row, the session is revoked/expired, or the operator was disabled mid-session |
| 4403 | Reserved (no Stage A use; the first-frame CSRF case from the deferred path) |

The 44xx range is the application-defined private range per RFC 6455 §7.4.2. We use 4401 to mirror HTTP 401.

### 5.8 Per-WS audit row

A single audit row is written when the WS handshake completes successfully (after the handler's `ws.accept()`):

- `action = 'liveops.ws_connected'`
- `target_type = 'websocket'`
- `target_id = NULL`
- `payload_json = {"path": "/console/ws"}`
- Written to `console.audit_log` (same DB as the session row that authorized the connection — atomic with the session's `last_seen_at` refresh).

Disconnect does not write a row. This is a deliberate Stage A simplification — connection-level activity is high-volume and adds little signal vs the per-action rows the route handlers write.

---

## 6. Router carve mapping

### 6.1 Target file layout

```
src/api/
├── app.py                       # thin assembler (see §6.4)
├── auth/
│   ├── __init__.py              # public re-exports
│   ├── hashing.py               # Argon2id wrapper (§2.5)
│   ├── sessions.py              # session lifecycle (issue/refresh/revoke)
│   ├── middleware.py            # SessionAuthMiddleware
│   └── audit.py                 # write_audit_row() helper (§7)
├── routers/
│   ├── __init__.py
│   ├── auth.py                  # NEW — /console/auth/login, logout, whoami
│   ├── tenant.py                # client/domain/onboarded list
│   ├── findings.py              # briefs/findings views
│   ├── onboarding.py            # trial-expiring (V1), conversion funnel
│   ├── billing.py               # placeholder (Stage A.5+ Betalingsservice surface)
│   ├── retention.py             # retention-queue (V6) + force-run/cancel/retry
│   └── liveops.py               # status/dashboard/pipeline/logs/ws/demo/settings/commands
│   # NOTE: notifications.py is reserved as the 7th file but NOT created in
│   # Stage A. CT-change alerts, retention-failure alerts, and Message 0
│   # email continue running from their current modules. The Notifications
│   # carve is a separate sprint after V2.
├── console.py                   # → DELETED. Existing imports (router) re-exported
                                 #   from src/api/routers/__init__.py for one
                                 #   release as a deprecation shim.
└── signup.py                    # unchanged
```

### 6.2 Endpoint mapping

Every endpoint currently in `src/api/console.py` (and its line range) maps to a target file. New endpoints added by Stage A are listed at the bottom.

| Today's endpoint | Source line | Target file | Notes |
|---|---|---|---|
| `GET /console/status` | console.py:80 | routers/liveops.py | runtime telemetry; queue depths + recent scans |
| `GET /console/dashboard` | console.py:137 | routers/liveops.py | aggregate stats for the SPA dashboard |
| `GET /console/pipeline/last` | console.py:208 | routers/liveops.py | latest pipeline run summary |
| `GET /console/campaigns` | console.py:235 | routers/tenant.py | campaign list — touches the prospect→client funnel |
| `GET /console/campaigns/{campaign}/prospects` | console.py:259 | routers/tenant.py | per-campaign prospects |
| `GET /console/briefs/list` | console.py:300 | routers/findings.py | dashboard "briefs" + "critical" indicators |
| `GET /console/clients/list` | console.py:345 | routers/tenant.py | onboarded clients (active/onboarding) |
| `GET /console/clients/trial-expiring` | console.py:450 | routers/onboarding.py | V1 — Watchman trials expiring; onboarding-funnel concern |
| `GET /console/clients/retention-queue` | console.py:477 | routers/retention.py | V6 — retention jobs about to run; retention concern |
| `POST /console/retention-jobs/{id}/force-run` | console.py:542 | routers/retention.py | retention action |
| `POST /console/retention-jobs/{id}/cancel` | console.py:567 | routers/retention.py | retention action |
| `POST /console/retention-jobs/{id}/retry` | console.py:656 | routers/retention.py | retention action |
| `GET /console/settings` | console.py:681 | routers/liveops.py | config-file read (filters/interpreter/delivery); no audit (read-only) |
| `PUT /console/settings/{name}` | console.py:695 | routers/liveops.py | config-file write; **no audit in Stage A** (§7.6) — full capture lands in Stage A.5 via `config_changes` triggers per D2 |
| `POST /console/commands/{command}` | console.py:747 | routers/liveops.py | operator-command queue dispatch |
| `GET /console/logs` | console.py:776 | routers/liveops.py | ring-buffer log query |
| `WS /console/ws` | console.py:811 | routers/liveops.py | live updates (queues, pubsub, logs) |
| `GET /console/briefs` | console.py:939 | routers/liveops.py | demo brief selector |
| `POST /console/demo/start` | console.py:961 | routers/liveops.py | demo replay registration |
| `WS /console/demo/ws/{scan_id}` | console.py:983 | routers/liveops.py | demo replay stream |

Edge-case calls justified:

- `/console/clients/trial-expiring` → **onboarding.py**, not retention.py. The view is "trials about to expire and the operator might want to nudge them" — a conversion-funnel question. The fact that some trials will eventually flow into retention is incidental; the read filter excludes any client with conversion-intent events.
- `/console/clients/retention-queue` + the three action endpoints → **retention.py**. Pure retention concerns; the read query targets `retention_jobs`, the writes mutate `retention_jobs`. Onboarding never touches `retention_jobs` directly.
- `/console/settings` and `/console/commands` → **liveops.py** in Stage A. Stage A.5 introduces `config_changes` triggers and adds `GET /console/config/history` — at that point the settings endpoints might split into a dedicated `routers/config.py`. Stage A keeps them in liveops to avoid pre-creating a context that's not yet needed.
- `WS /console/ws` → **liveops.py**. It's a runtime-orchestration channel — queue status, pubsub forwarding, log streaming. Not tenant-specific.
- `WS /console/demo/ws/{scan_id}` and the demo brief endpoints → **liveops.py**. Demo is operator-internal runtime tooling; doesn't fit any tenant/findings/onboarding/retention/billing context cleanly.

### 6.3 New endpoints introduced by Stage A

| Method | Path | File | Purpose |
|---|---|---|---|
| `POST` | `/console/auth/login` | routers/auth.py | issue session ticket; rate-limited per source IP (5 fails / 15 min) |
| `POST` | `/console/auth/logout` | routers/auth.py | revoke session |
| `GET` | `/console/auth/whoami` | routers/auth.py | echo current operator + session metadata; used by SPA on boot |

**`POST /console/auth/login` response shapes** (normative — the implementing PR matches this table verbatim):

| Status | Headers | Body | Notes |
|---|---|---|---|
| 200 OK | `Set-Cookie: heimdall_session=...`, `Set-Cookie: heimdall_csrf=...` | `{operator, expires_at, absolute_expires_at, csrf_token}` | success path; per-IP rate-limit counter cleared via `redis.delete("auth:fail:<ip>")` |
| 401 Unauthorized | — | `{"error": "invalid_credentials"}` | bad credentials, unknown username, or disabled operator — single shape, same timing; per-IP counter incremented |
| **429 Too Many Requests** | **`Retry-After: <seconds>`** | **`{"error": "rate_limited"}`** | per-IP counter ≥ 5 fails in the last 15 min; `<seconds>` is the current Redis TTL on `auth:fail:<ip>` (clamped to [1, 900]); counter is keyed on source IP, NOT on username (per-username lockout enables targeted DoS) |
| 503 Service Unavailable | — | `{"error": "service_unavailable"}` | DB error reaching `console.db`. Redis-down does NOT return 503 — the rate-limit gate fails open per §3.1.a so the login still proceeds |

`/console/auth/whoami` has **four** response shapes per D5 (resolved 2026-04-28) plus the 2026-04-28 evening security review; see §3.5 for the full semantics and SQL pre-check:

- **204 No Content** with empty body — when `operators` table has **zero rows total**. Genuine empty bootstrap (fresh install). SPA renders "no operators seeded — bootstrap state" splash.
- **409 Conflict** `{"error": "all_operators_disabled"}` — when rows exist but **every** row has `disabled_at IS NOT NULL`. Operators exist but all are disabled. SPA renders "all operators disabled — contact owner" splash. Distinct from 204 because the operational response is different (re-enable, not seed).
- **200 OK** `{operator: {...}, session: {expires_at, absolute_expires_at}, csrf_token}` — when a valid session cookie matches an active operator. Normal authenticated state. This is the only endpoint that returns the CSRF token in the response body (for clients that can't read the companion cookie).
- **401 Unauthorized** `{"error": "not_authenticated"}` — when at least one active operator exists but the request is unauthenticated.

The 204 and 409 branches are checked BEFORE cookie validation. The middleware (§3.2) does not run on `/console/auth/whoami` — the route handler owns the full auth-state probe. Whitelist `/console/auth/whoami` alongside `/console/auth/login` in `SessionAuthMiddleware` so it never short-circuits with 401 before the handler can return 204 or 409.

### 6.4 `src/api/app.py` becomes the assembler

Today `app.py` (~500 LOC) holds: middleware classes, pubsub listeners, `_handle_scan_complete`, and a handful of inline routes (`/health`, `/results/...`).

After Stage A:

- `BasicAuthMiddleware` (lines 53-91) → DELETED.
- `SessionAuthMiddleware` (new) → imported from `src/api/auth/middleware.py`.
- `RequestLoggingMiddleware` (lines 94-114) → unchanged, stays in `app.py`.
- The two pubsub listeners (`_listen_console_logs`, `_listen_scan_complete`) → unchanged, stay in `app.py`. They are not console-router concerns.
- `_handle_scan_complete` (lines 249-336) → unchanged. It's the scan-complete glue between the worker pubsub and the messages dir; lives here.
- The `/health` and `/results/...` routes → unchanged, stay in `app.py`. They are not under the `/console` prefix and have no auth.
- `app.include_router(console_router)` → replaced by six `app.include_router(...)` calls, one per file in `src/api/routers/`. The order doesn't matter functionally; we order them tenant → findings → onboarding → billing → retention → liveops → auth for grep-ability.

After the carve, `app.py` is conceptually:

```
1. Middleware classes / pubsub listener async functions (unchanged).
2. create_app() lifespan:
   - call init_db()           [clients.db, unchanged]
   - call init_db_console()   [console.db, NEW — must complete before
                               SessionAuthMiddleware sees its first
                               request; see §2.6]
   - existing pubsub task starts
3. Add RequestLoggingMiddleware.
4. Add SessionAuthMiddleware (replaces BasicAuthMiddleware). Its
   whitelist includes /console/auth/login and /console/auth/whoami so
   the route handlers can implement the 401-vs-204 distinction (D5).
5. Include all routers from src/api/routers/.
6. Include signup_router (unchanged).
7. Mount /static and /app StaticFiles (unchanged).
8. Inline /health and /results/... routes (unchanged).
9. Return app.
```

`init_db_console()` is awaited inside `create_app()`'s lifespan (or invoked synchronously before middleware registration if we keep the current pre-`yield` pattern). The auth middleware MUST NOT engage on any request before `init_db_console()` has returned — otherwise the first request can hit a missing `operators` table. The lifespan ordering (or pre-yield init) makes this race impossible.

Approximate LOC after Stage A: `app.py` ≈ 410 LOC (down from 506; +10 for the second init call), each router file 60-200 LOC.

### 6.5 Notifications context (D1) — reserved, not created

A `routers/notifications.py` file is NOT created in Stage A. The CT-change Telegram alerts (`src/client_memory/ct_monitor.py` → delivery), retention-failure operator alerts (`src/retention/runner.py` → operator Telegram), and Message 0 magic-link emails (signup site → SES/SMTP) all continue to run from their current modules. The Notifications carve is a follow-up sprint after V2; it will lift those send paths into a unified dispatcher with template / channel-preference / retry-backoff / delivery-log retention.

This is documented as a comment block at the top of `src/api/routers/__init__.py` so a developer scanning the directory sees the seventh-context placeholder.

### 6.6 Deprecation shim for `src/api/console.py`

The old file is deleted, but there are imports of `from src.api.console import router as console_router` in `app.py` and possibly tests. The Stage A PR replaces `src/api/console.py` with a 5-line shim file:

```python
# Deprecation shim — the monolithic console router is split as of Stage A.
# This file will be deleted in the release after Stage A ships in prod.
from src.api.routers import (  # noqa: F401
    auth_router as router,  # the single-router import path used by app.py
)
```

Actually, app.py is updated in the same PR to import each router by name, so the shim is only needed if external scripts/tests import `from src.api.console import ...`. Quick grep before merge to confirm; if no external imports, no shim — just delete `src/api/console.py`. Mark this in "Decisions still open".

---

## 7. `audit_log` write contract (split ownership per Option B)

Stage A's audit pattern is **manual, in-handler writes** — no decorator, no middleware. Each route handler / system worker that mutates state calls a `write_audit_row` helper inside the same DB transaction as the mutation. Stage A.5 layers the `Permission` decorator on top, which can auto-fill `action` from the enum value.

The split-DB design (§1.3) means there are TWO helpers — one per audit table — and each is bound to its DB. There is no helper that writes "the audit log"; there is a console-side helper that writes `console.audit_log`, and a clients-side helper that writes `clients.audit_log`. The caller picks based on which DB the mutation lives in. This explicitness is intentional: it forces the writer to think about which DB it is mutating, which is the same question Option B's atomicity guarantee depends on.

### 7.1 The two helpers

**`src/api/auth/audit.py` — writes `console.audit_log` only.** Used by the api container.

```
write_console_audit_row(
    conn: sqlite3.Connection,        # connection to console.db
    request: Request,
    *,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    payload: dict | None = None,
) -> int
```

- Reads `operator_id` and `session_id` from `request.state` (set by middleware). Both NULL for unauthenticated calls (login_failed before identification, ws_connected before middleware completes — handler fills NULLs intentionally).
- Reads `request.client.host` for `source_ip` and `request.headers.get("user-agent", "")[:512]` for `user_agent`.
- Reads `request.state.request_id` if Stage A.5 has populated it; NULL in Stage A.
- Serializes `payload` via `json.dumps(payload, default=str)`. The handler is responsible for stripping any secret-bearing fields before calling.
- Inserts into `audit_log` (which lives in `console.db`) and returns the new `id`.
- Does NOT commit. The caller's `with conn:` block (or explicit commit) is the boundary. This is the rule that ties audit-write to mutation-write atomically *within* `console.db`.

**`src/db/clients_audit.py` — writes `clients.audit_log` only.** Used by scheduler / worker / delivery containers (and by the api when it dispatches an operator command, but only via the writer container — the api never writes `clients.db` itself).

```
write_clients_audit_row(
    conn: sqlite3.Connection,        # connection to clients.db
    *,
    action: str,
    operator_id: int | None,         # bare int; correlates to console.operators.id, NOT a FK
    session_id: int | None,          # bare int; correlates to console.sessions.id, NOT a FK
    actor_kind: str = 'operator',    # 'operator' | 'system'
    target_type: str | None = None,
    target_id: str | int | None = None,
    payload: dict | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,   # NULL in Stage A
) -> int
```

- No `Request` object — the writer is often the scheduler/worker/delivery container, which has no FastAPI request context. Operator/session/IP/UA come in as explicit kwargs, propagated via the operator-command queue payload from the api.
- For system-initiated mutations (CT monitor publishing a delta, retention timer firing), the caller passes `actor_kind='system'`, `operator_id=None`, `session_id=None`. The audit row makes "system did this" visible distinctly from "operator did this".
- Inserts into `audit_log` (which lives in `clients.db`) and returns the new `id`.
- Does NOT commit. Same atomicity contract as the console helper — bound to the `with conn:` of the underlying mutation.

### 7.2 Operator-initiated retention writes (synchronous, single audit row)

Per D8 / D9 (decided 2026-04-28 afternoon), the three retention endpoints (`/console/retention-jobs/{id}/{force-run,cancel,retry}`) stay **synchronous** in Stage A. No Redis enqueue, no writer-container outcome row, no 202 Accepted. The api opens a `clients.db` connection, runs the CAS UPDATE on `retention_jobs`, writes a single `clients.audit_log` row in the same transaction, commits, returns 200 with the updated row. This matches PR #46's already-shipped behaviour byte-for-byte; Stage A's only addition is the in-transaction audit-row write.

The architect's earlier async-dispatch + dispatch_intent + outcome design is **reverted** out of this spec. If async retention dispatch is the right answer for V2 / A.5, it is a separate spec; Stage A is auth / identity / router carve, not workflow redesign.

```
1. api receives POST /console/retention-jobs/{id}/force-run.
   - Validates session, CSRF (and Stage A.5 will validate role).
   - Opens clients.db connection.
   - BEGIN IMMEDIATE.
   - CAS UPDATE retention_jobs
       SET scheduled_for = now    -- (force-run case)
        or SET status = 'cancelled', executed_at = now, notes = COALESCE(?, notes)  -- (cancel case)
        or SET status = 'pending', scheduled_for = now, attempt = ...  -- (retry case)
       WHERE id = ?
         AND status = ?           -- (CAS predicate matching PR #46 exactly)
       RETURNING *
     If rowcount == 0: SELECT to distinguish "not found" (404) from
     "wrong state" (404 with a state-specific message — same shape
     as today's `Retention job N is not pending (status=...)`).
   - INSERT into clients.audit_log:
       action       = 'retention.force_run' (or 'retention.cancel' / 'retention.retry')
       actor_kind   = 'operator'
       operator_id  = request.state.operator_id   -- bare int, no FK
       session_id   = request.state.session_id     -- bare int, no FK
       target_type  = 'retention_job'
       target_id    = updated_row.id
       source_ip    = request.client.host
       user_agent   = request.headers.get('user-agent', '')[:512]
       payload      = {<action-specific>}
       request_id   = NULL in Stage A (Stage A.5 wires X-Request-ID)
   - COMMIT.
     Both rows (mutation + audit) commit together inside clients.db
     in the same SQLite transaction. If anything in this block raises,
     both roll back.
   - Publish operator-action event on Redis console:activity (matches
     PR #46's existing _publish_retention_action; the publish is
     fire-and-forget, NOT part of the transaction — failure to publish
     is logged but does not roll the audit row back).
   - Return 200 OK with the updated row in the body.
```

**One audit row per action, not two.** The api is the writer that performs the SQL UPDATE in Stage A's retention path, so the api also writes the `clients.audit_log` row — same DB as the row it audits, same SQLite transaction, real atomicity per Option B (§1.3). There is no api-side intent row in `console.audit_log` for retention actions; the operator-attributed write IS the `clients.audit_log` row.

**Why the api can write `clients.audit_log` despite D2.** PR #49 (separate, direct to main) resolves the original D2 contradiction — `:ro` was incompatible with PR #46's already-shipped retention CAS UPDATEs. With the mount widened on main, Stage A can write `clients.audit_log` rows in the same SQLite transaction as the retention/trial mutations. The narrow-write invariant is preserved by code review on `src/api/routers/retention.py` and `src/api/routers/onboarding.py` (the only routes that touch `clients.db` writes); D2's larger `console.db` split for sessions/operators/auth-event audit is unchanged and remains the bigger blast-radius reduction.

**Trial activation, trial expiry, retention-tick, ct.delta_observed.** These are system-initiated mutations — written by `delivery` (trial activation), `scheduler` (trial expiry, retention timer firing, CT monitor). They write `clients.audit_log` rows from those containers' existing RW mounts of `clients.db`, with `actor_kind='system'`. No api involvement, no cross-DB choreography.

**`/console/commands/{command}` retains the api intent + writer outcome split.** Stage A's command-dispatch endpoint is the only retained two-row pattern: the api writes a `command.dispatch` intent row to `console.audit_log` and pushes the command envelope onto `queue:operator-commands`; whichever container handles the command writes the outcome row to `clients.audit_log`. This pattern stays because commands are genuinely async (the queue is the dispatch mechanism today, used by every existing operator-command flow); the retention path was async only because the architect's earlier design speculatively introduced the queue, not because the dispatch itself needed it.

### 7.3 Endpoints that must write audit rows in Stage A

All endpoints under `/console/*` whose HTTP method is POST/PUT/PATCH/DELETE write at least one audit row. GET endpoints do NOT write rows in Stage A — read-side audit is a Stage A.5 / Notifications-carve consideration (high volume, low marginal value, potential PII concerns if we record query strings).

The "where" column says which audit table receives the row.

| Endpoint | Method | `action` string | Where | `target_type` / `target_id` | Notes |
|---|---|---|---|---|---|
| `/console/auth/login` | POST | `auth.login_ok` / `auth.login_failed` | `console.audit_log` | `operator` / username (failed) or operator_id (ok) | api writes; failure rows have `operator_id=NULL`, `session_id=NULL` |
| `/console/auth/logout` | POST | `auth.logout` | `console.audit_log` | `session` / session_id | api writes |
| `/console/settings/{name}` | PUT | — | — | `config` / name | **not audited in Stage A**; full capture lands in Stage A.5 via `config_changes` triggers per D2. Endpoint behaviour (the actual config write) is unchanged from current `src/api/console.py`; only the audit-row write is deferred. See §7.6 below. |
| `/console/commands/{command}` | POST | `command.dispatch` (intent) → followed by writer-side `command.<name>` (outcome) | both | `command` / command name | api writes intent row to console.audit_log; whichever container handles the command writes the outcome row to clients.audit_log |
| `/console/retention-jobs/{id}/force-run` | POST | `retention.force_run` | `clients.audit_log` | `retention_job` / id | api writes (sync, see §7.2 + §10 D8); single audit row per action |
| `/console/retention-jobs/{id}/cancel` | POST | `retention.cancel` | `clients.audit_log` | `retention_job` / id | api writes (sync); payload = `{notes_provided: bool}` |
| `/console/retention-jobs/{id}/retry` | POST | `retention.retry` | `clients.audit_log` | `retention_job` / id | api writes (sync) |
| WS `/console/ws` (handshake) | — | `liveops.ws_connected` | `console.audit_log` | `websocket` / NULL | api writes; written once after successful handshake |
| Trial activation (signup → Watchman flip) | n/a | `trial.activated` | `clients.audit_log` | `client` / cvr | delivery container writes; `actor_kind='operator'` (the client is the actor) |
| Trial expiry (sweeper firing) | n/a | `trial.expired` | `clients.audit_log` | `client` / cvr | scheduler writes; `actor_kind='system'` |
| Retention timer firing | n/a | `retention.tick`, `retention.<action>` | `clients.audit_log` | `retention_job` / id | scheduler writes; `actor_kind='system'` |
| CT monitor publishing a delta | n/a | `ct.delta_observed` | `clients.audit_log` | `client_domain` / id | scheduler writes (via `ct_monitor.py`); `actor_kind='system'` |

### 7.4 Why in-handler, not decorator

A decorator would be cleaner but premature in Stage A. The decorator design space (where to read `target_id` from? how to declare the payload shape? how to skip on the dry-run path? which audit table to write to in the cross-DB case?) is a Stage A.5 concern that compounds with the `Permission` enum and the X-Request-ID middleware. Stage A keeps the contract concrete and grep-able: every state-changing handler/worker has an obvious `write_*_audit_row(...)` call right next to the DB write.

### 7.5 Atomicity rule (real this time)

Each writer follows this pattern, scoped to the DB it owns. The writer set per Stage A:

- **`console.audit_log`** — written by the api container only (auth events, WS handshake).
- **`clients.audit_log`** — written by the api container (operator-initiated retention writes, sync per §7.2 + §10 D8/D9), AND by scheduler / worker / delivery (system-initiated mutations, command outcomes). Multiple writers, same DB; SQLite WAL handles the contention.

The pattern is identical regardless of writer:

```
with sqlite3.connect(db_path, timeout=5) as conn:
    conn.row_factory = sqlite3.Row
    # ... do the mutation against the same conn ...
    write_<console|clients>_audit_row(conn, ..., action=..., target_type=..., target_id=..., payload=...)
    # `with conn:` commits on exit; both mutation and audit row commit together
    # within this DB. SQLite WAL gives us atomic commit per DB file.
```

If any step raises, both rows in **this DB** roll back. There is no "audit a write that didn't happen" or "lose the audit for a write that did happen" failure mode *within a single DB*.

What Stage A does NOT promise: cross-DB atomicity between the api's `console.audit_log` intent row and the writer's `clients.audit_log` outcome row. SQLite cannot give us that — we acknowledged the limit in §1.3 and chose the split rather than pretend. The intent row commits to console.db before the queue push; the outcome row commits to clients.db when the writer processes the queue envelope. The worst-case observable failure is "intent row exists, no outcome row" — which is operationally readable as "the dispatch never landed; operator can retry". The *opposite* failure (outcome with no intent) cannot happen because the intent row commits before the queue push.

The original spec's claim of single-transaction atomicity across DBs was wrong; this section now says what actually holds.

### 7.6 Explicitly out of audit scope in Stage A: `config.update`

**The decision.** `/console/settings/{name}` PUT — the operator-config edit endpoint — does NOT write an audit row in Stage A. Full capture lands in Stage A.5 via the `config_changes` table + DB triggers per D2. This is intentional, normative, and recorded here as an explicit gap rather than a silent omission.

**Why exempt, not best-effort.** The Stage A audit guarantee ("every operator-mutating endpoint writes an audit row in the same transaction as the mutation it records") only holds for endpoints whose mutation lands on a SQLite row inside a DB the api can transactionally write to. Config edits are different in two ways: (1) they may write to `clients.db`, to a JSON file in `config-data`, to an env var, or to no persistent store at all — depending on the `name` parameter — and the spec for which writes go where is itself the Stage A.5 `config_changes` design; (2) the formal capture contract (D2) is "DB triggers for capture, repository wrappers for validation/intent/actor", which is a Stage A.5 concern. A best-effort Stage A audit row would either lie about which endpoint really wrote what (api-side row says "config.update", actual write may have been to a JSON file the api can edit but which has no transactional pairing with `console.audit_log`), or duplicate work that Stage A.5 will replace.

**What this means concretely.**

- `/console/settings` GET and `/console/settings/{name}` PUT continue to work in Stage A exactly as they do today in `src/api/console.py`. The router carve (§6.2) moves them to `routers/liveops.py` unchanged in behaviour.
- The Stage A audit guarantee is restated as: "every operator-mutating endpoint *that is in scope for Stage A audit* writes an audit row in the same transaction as the mutation it records". The set of in-scope endpoints is exactly the rows in §7.3's table that have a non-`—` `action` string. Config is the only mutating endpoint that has a `—`.
- Stage A.5 lands `config_changes` (table + triggers + repository wrappers + `GET /console/config/history`), at which point config writes become first-class audited mutations and the §7.3 row is updated with the proper `action` strings.

This exclusion is recorded in §11 (Out of scope), in §10 D8 (the "decided 2026-04-28 afternoon" entry), and in §14 revision history. A reviewer scanning the spec for "where is config audit?" finds the answer in three places, all consistent.

---

## 8. Test plan

### 8.1 Test file layout

```
tests/
├── test_auth_hashing.py             # NEW — Argon2 wrapper
├── test_auth_sessions.py            # NEW — session lifecycle (issue/refresh/revoke)
├── test_auth_middleware.py          # NEW — SessionAuthMiddleware behaviour
├── test_auth_login_logout.py        # NEW — login/logout/whoami endpoint unit tests (incl. 204 empty-operators branch, D5)
├── test_auth_rate_limit.py          # NEW — per-IP login rate limit (5 fails / 15 min via Redis); separate file because the Redis dependency is distinct from the SQLite-only login/logout tests
├── test_auth_csrf.py                # NEW — double-submit token behaviour
├── test_audit_log_writer.py         # NEW — write_audit_row helper
├── test_session_auth.py             # RENAMED from tests/test_console_auth.py (D7, 2026-04-28)
│                                    #   — repurposed for session-cookie auth
├── test_console_ws_auth.py          # NEW — WS handshake (cookie path + first-frame path)
├── test_router_carve.py             # NEW — every endpoint reaches its target router
└── test_console_integration.py      # NEW — login → ws → state-change → logout round trip (incl. rate-limit scenario)
```

Per D7 (resolved 2026-04-28), the existing `tests/test_console_auth.py` is RENAMED to `tests/test_session_auth.py` — not deleted-and-recreated. The implementation PR's commit MUST use `git mv` so `git log --follow` continues to track the file's history. The commit message MUST mention the rename explicitly so anyone grepping for the old filename in PR descriptions or chat history finds the breadcrumb. Recommended commit subject: `tests(auth): rename test_console_auth.py → test_session_auth.py (Stage A D7)`.

Grep continuity is treated as a documentation problem (this paragraph + the decision-log entry + the commit message), not a test-naming problem. The mental model the new filename encodes — "tests for session-based auth, not the legacy Basic-Auth console" — is more important than preserving stale grep hits.

### 8.2 Per-file assertions

**`test_auth_hashing.py`** (~10 tests)
- `hash_password(pw)` returns a PHC-formatted string starting with `$argon2id$`.
- `verify_password(hash, pw)` returns True for the matching plaintext.
- `verify_password(hash, "wrong")` returns False (and runs in roughly the same time as the True case — sanity check, not a strict timing assertion).
- Empty password rejected (raises ValueError).
- 256-char password accepted.
- Pepper presence test: with `/run/secrets/operator_password_pepper` mocked to a known value, the hash differs from the no-pepper case.

**`test_auth_sessions.py`** (~15 tests)
- `issue_session(conn, operator_id, ip, ua)` creates a row with both expiry timestamps populated correctly.
- `refresh_session(conn, token)` extends `expires_at` but never past `absolute_expires_at`.
- `refresh_session` is debounced — calling twice within 60s touches the row only once.
- `validate_session(conn, token)` returns the row when valid, None when revoked, None when expired (idle), None when expired (absolute), None when operator disabled.
- `revoke_session(conn, token)` is idempotent.
- Concurrent refresh from two threads converges (last-write-wins is acceptable because both writes contain the same intent).

**`test_auth_middleware.py`** (~13 tests — HTTP-only middleware; WS auth tests live in `test_console_ws_auth.py`)
- Missing cookie → 401 on `/console/*`.
- Valid cookie + `/console/dashboard` → 200 (with `request.state.operator_id` set). Middleware computes `sha256(cookie)` and looks up `token_hash`, not the cookie value directly.
- **DB lookup uses `token_hash`, not the raw cookie:** mock the cookie to a value whose SHA-256 matches a pre-seeded `sessions.token_hash` row, assert middleware-attached `request.state.operator_id` matches; mock the cookie to a value that does NOT hash to any row, assert 401. (Security review 2026-04-28 evening.)
- Valid cookie + revoked session → 401 + clear-cookie response.
- Valid cookie + expired session → 401 + clear-cookie.
- Valid cookie + disabled operator → 401 + clear-cookie + audit row written (`auth.session_rejected_disabled`).
- `/health` and `/results/...` still no auth.
- `/app/...` requires auth (parity with today).
- `/signup/...` no auth (signup is unauthenticated).
- POST without `X-CSRF-Token` → 403.
- POST with wrong `X-CSRF-Token` → 403 (no session revoke).
- GET without `X-CSRF-Token` → 200 (CSRF check skips safe methods).
- **Middleware does NOT touch WebSocket scope:** assert that a `scope['type'] == 'websocket'` request bypasses the middleware's HTTP code path (the defensive early-return in `__call__`). Auth for WS lives in the handler — see `test_console_ws_auth.py`.

**`test_auth_login_logout.py`** (~14 tests — incl. 204/409/200/401 whoami split + token-hash storage assertion)
- Valid credentials → 200 + Set-Cookie + body shape. **Plus: assert that the database row's `token_hash` is the SHA-256 hex digest of the plaintext token in the Set-Cookie header, AND that the database row's `token_hash` is NOT EQUAL to the cookie value.** (Security review 2026-04-28 evening: this is the cookie-vs-DB-key separation.)
- **Hash-equality test:** issue a session, capture both the Set-Cookie value and the `sessions.token_hash` row, assert `hashlib.sha256(cookie_value.encode()).hexdigest() == db_row.token_hash` AND `cookie_value != db_row.token_hash`. The cookie is the only way to derive the lookup key.
- Wrong password → 401 + audit row.
- Unknown username → 401 + audit row (with `operator_id=NULL`).
- Disabled operator → 401 + audit row.
- Logout → 204 + Set-Cookie clearing both cookies + session row revoked + audit row.
- Logout without auth → 401.
- Logout twice → second call 401.
- Whoami with valid session → 200 with operator + session metadata + csrf_token.
- Whoami without auth, with operators seeded → 401 `{"error": "not_authenticated"}`. (D5)
- **Whoami when `operators` table has zero rows total → 204 No Content with empty body.** (D5 + security review 2026-04-28 evening — split state 1.) Assertions: status code, empty body bytes (`b""`), no `Set-Cookie` header, no audit row written, response NOT cached by the framework's middleware.
- **Whoami when rows exist but every row has `disabled_at IS NOT NULL` → 409 Conflict with `{"error": "all_operators_disabled"}`.** (Security review 2026-04-28 evening — split state 2.) Assertions: status code 409, JSON body matches exactly, no `Set-Cookie` header, no audit row written. Distinct test from the 204 case to lock in the split.
- **Whoami when at least one row is enabled and another is disabled → falls through to 200 / 401 path** (the disabled row does not poison the active-operator branch).
- Login when operators table is empty → 401 (no-such-user path; documented behaviour — login semantics are unchanged; only `whoami` differentiates the bootstrap and all-disabled states).
- Login when all operators disabled → 401 (same path as no-such-user; the SELECT filters on `disabled_at IS NULL`).

**`test_auth_rate_limit.py`** (~10 tests; ~150 LOC NEW file — kept separate from `test_auth_login_logout.py` so the dependency on Redis is explicit and isolatable. Uses fakeredis or a redis-fixture pattern; the SQLite-only login/logout tests must NOT need a Redis fixture)
- `test_rate_limit_blocks_after_5_fails` — five consecutive 401s from one source IP, sixth attempt returns 429 with `Retry-After` header set to a value in `[1, 900]` and body `{"error": "rate_limited"}`. Assert the 6th request never reaches the SELECT against `operators` (mock the DB layer, assert no call) — the rate-limit gate is the FIRST step.
- `test_rate_limit_resets_on_success` — four 401s, then one 200 (correct credentials), then one fresh 401 from the same IP — the post-success 401 returns 401 (not 429). Assert `redis.delete("auth:fail:<ip>")` was called between steps 5 and 6, and the post-success 401 starts a fresh INCR=1 with a fresh 900s TTL.
- `test_rate_limit_separate_ips` — IP A makes 5 failed attempts (blocked at the 6th with 429); IP B from the same test makes 1 attempt and gets the normal 401 (NOT 429). Confirms the counter is per-IP, not global.
- `test_rate_limit_redis_failure_fail_open` — patch the Redis client to raise `ConnectionError` on `get`/`incr`; submit 10 failed login attempts in a row from the same IP; assert all 10 return 401 (NOT 429), assert exactly 10 WARNING-level loglines record the fail-open decision, assert the SQLite path was reached on every attempt. **The choice is fail-open per §3.1.a; this test locks it in.**
- `test_rate_limit_429_does_not_increment` — once an IP is at the 429 threshold, additional attempts return 429 but do NOT compound the counter further (`redis.incr` is NOT called in the 429 branch). The TTL stays bounded at the original 900s, so the operator's own block window does not extend itself just by retrying.
- `test_rate_limit_503_does_not_increment` — when the DB returns 503 (mock `console.db` connect to raise `OperationalError`), the rate-limit counter is NOT incremented. DB errors are not attacker signals.
- `test_rate_limit_unknown_username_increments` — submit 5 logins with non-existent usernames from one IP; 6th attempt returns 429. Confirms the user-enumeration oracle is closed at the rate-limit layer the same way it is at the response layer.
- `test_rate_limit_key_format` — assert the Redis key is exactly `f"auth:fail:{client_ip}"` (no prefix variations, no per-environment namespace) — locks the contract for ops alerts that grep Redis keys.
- `test_rate_limit_ttl_set_on_first_incr_only` — first failed login: `redis.incr` returns 1 → `redis.expire(key, 900)` is called. Second failed login: `redis.incr` returns 2 → `redis.expire` is NOT called (the TTL inherited from the first). Locks the sliding-window-reset bug from re-emerging.
- `test_rate_limit_retry_after_clamped` — manually set the key to a non-positive TTL (-1, simulating a TTL-loss bug); next 429 returns `Retry-After: 1` (clamped to ≥1, never 0/negative).

**`test_auth_csrf.py`** (~6 tests)
- POST with header matching cookie → 200.
- POST with header not matching cookie → 403.
- POST with header but no cookie → 403.
- POST with cookie but no header → 403.
- DELETE / PATCH same behaviour.
- GET with no header → 200 (skip-on-safe-methods).

**`test_audit_log_writer.py`** (~8 tests)
- Row is written with all expected fields populated.
- Operator_id / session_id are read from `request.state`.
- Payload is JSON-serialized correctly.
- Payload with `default=str` falls back for datetime values.
- IP and UA are pulled from request and truncated.
- `request_id` is None in Stage A (Stage A.5 will populate).
- Roll-back: when the caller's transaction rolls back, the audit row is gone too.

**`test_session_auth.py`** (RENAMED from `test_console_auth.py` per D7, 2026-04-28; ~12 tests)
- The existing 11 tests are rewritten against the cookie-based flow. Old `Authorization: Basic` assertions become `Cookie: heimdall_session=...` assertions. The `test_no_middleware_when_env_vars_absent` test is repurposed as `test_no_middleware_when_no_operators_seeded` — when the `operators` table is empty, `/console/*` returns 401 (rather than the today's "no middleware = open" behaviour, which is wrong on its face but currently the case). Note: the empty-operators 204 contract for `/whoami` lives in `test_auth_login_logout.py` (D5) — this file owns the protected-route 401 contract for the same state.
- Implementation PR uses `git mv tests/test_console_auth.py tests/test_session_auth.py` so `git log --follow` continues to track history. Commit subject: `tests(auth): rename test_console_auth.py → test_session_auth.py (Stage A D7)`.

**`test_console_ws_auth.py`** (~7 tests — auth lives in the handler, NOT in HTTP middleware; security review 2026-04-28 evening)
- WS connect with valid cookie → handler reads `ws.cookies['heimdall_session']`, hashes via SHA-256, finds matching `token_hash` row, calls `ws.accept()`, normal pubsub stream proceeds. Audit row `liveops.ws_connected` written to `console.audit_log`.
- **WS connect with no cookie → handler calls `ws.accept()` then `ws.close(code=4401)` BEFORE any pubsub setup.** Client sees a clean WS close with code 4401, not an HTTP-level rejection. Assert: no audit row written, no DB session refresh, no pubsub subscription.
- **WS connect with cookie that does not hash to any row → close(4401)** before accept-pipeline. Same assertions as the no-cookie case.
- **WS connect with cookie matching a revoked session → close(4401).**
- **WS connect with cookie matching an expired session → close(4401).**
- **WS connect with cookie matching a session whose operator was disabled → close(4401).**
- **HTTP middleware does NOT auth the WS upgrade:** spin up the app with the SessionAuthMiddleware registered, send a WS upgrade with no cookie to `/console/ws`, assert the handler is reached (not the middleware) — verify by patching the handler to record entry, confirm the call. This locks in the design that the handler is the gate, so future Starlette versions changing middleware behaviour don't silently re-introduce middleware-side auth.

**`test_router_carve.py`** (~6 tests)
- Every endpoint listed in §6.2 is reachable at its expected path.
- `from src.api.routers.tenant import router` exists and is non-empty.
- Same for findings, onboarding, billing, retention, liveops, auth.
- `routers.billing` is allowed to be empty in Stage A (placeholder); test asserts the file exists and exports `router` even if no endpoints.
- `from src.api.console import router` either works (shim) or import-errors (deleted) — pick one and lock in the test.

**`test_console_integration.py`** (~4 tests)
- End-to-end happy path: POST /login → GET /dashboard → POST /retention-jobs/1/cancel → audit_log has 3 rows for this session → POST /logout.
- Session expiry path: login, manually fast-forward the row's `expires_at`, request → 401 + cookie cleared.
- Operator disabled mid-session: login, set `disabled_at`, request → 401 + audit row + cookie cleared.
- **Rate-limit scenario (full Redis path).** Real Redis (or fakeredis with TTL expiry support): five POST /login with bad credentials from the same IP → all 401 + counter hits 5; sixth POST /login → 429 with `Retry-After: <ttl>`. Wait until the TTL elapses (test-time fast-forward via fakeredis or a small TTL override for this test) → next POST /login with correct credentials → 200 + counter cleared. This walks the full Redis → 429 → wait-for-TTL → success path that the unit tests cover in isolation.

### 8.3 Coverage target

The 65% floor (from CLAUDE.md) holds. Stage A's new `src/api/auth/*` files should each be >90% covered (small surface, easy to exercise). The router files (`src/api/routers/*.py`) inherit their existing coverage from the rewritten `test_console_*.py` suite — no regression.

### 8.4 Pre-commit Codex review

Per `precommit_codex_review_guard.py`, the Stage A commit will need `HEIMDALL_CODEX_REVIEWED=1`. The Codex review for Stage A should specifically check:

- Constant-time comparison on session token / CSRF token / password verify (use `secrets.compare_digest`).
- No PII in `payload_json` for `auth.login_failed` rows (only username, never the attempted password).
- The "60-second debounce" math is timezone-correct (UTC throughout).
- The migration seed at §2.2 is idempotent across multi-worker startup.
- Cookie attributes match §4.1 exactly.
- WS first-frame timeout is enforced server-side, not just expected client-side.

---

## 9. Rollback plan

Stage A is a structural change; "undo" is not as simple as reverting a feature flag. Three rollback levers, in order of preference. Per D2 (resolved 2026-04-28), all three are reshaped around the split-DB design: rollback removes the new `console-data` volume mount on the api container and falls back to legacy Basic Auth via `HEIMDALL_LEGACY_BASIC_AUTH=1`. The lever (env flag) is the same as the original spec; the cleanup is different.

### 9.1 Lever 1 — keep Basic Auth path live behind an env flag (one release)

The Stage A PR does NOT delete `BasicAuthMiddleware`. It renames it to `LegacyBasicAuthMiddleware` and gates its inclusion on `os.environ.get("HEIMDALL_LEGACY_BASIC_AUTH", "0") == "1"`. When the flag is set, the legacy middleware runs INSTEAD of `SessionAuthMiddleware`; the new `console.db` is still created (idempotent) but the runtime path is the old one. The `console-data` volume can stay mounted on the api container during the rollback — the flag short-circuits any read/write against it.

Rollback in prod (operator session corruption, auth lockout, or unforeseen middleware bug):

1. Edit `infra/compose/.env` on the Pi5: add `HEIMDALL_LEGACY_BASIC_AUTH=1`.
2. `docker compose -f docker-compose.yml up -d --no-deps api`.
3. Browser hits `/console` → Basic Auth challenge again.

This takes ~30s. Federico keeps `console_password` mounted regardless; the legacy middleware reads it when the flag is set. The `console-data` volume contents are preserved (so re-enabling Stage A later is a single env-flag flip back).

The flag is removed in the release after Stage A ships in prod.

### 9.1a Lever 1b — `console.db` corruption-only rollback

If the failure mode is specifically "console.db is corrupted" (not "the new auth code is buggy"), there's a tighter cleanup path:

1. Edit `infra/compose/.env`: add `HEIMDALL_LEGACY_BASIC_AUTH=1`.
2. `docker compose -f docker-compose.yml stop api`.
3. Remove the offending DB file from the volume: `docker run --rm -v heimdall_console-data:/d alpine rm -f /d/console.db /d/console.db-wal /d/console.db-shm`.
4. `docker compose -f docker-compose.yml up -d --no-deps api`.
5. Next deploy: re-enable Stage A by removing the env flag; `init_db_console()` re-creates the schema, `_seed_operator_zero` re-seeds operator #1 from `CONSOLE_USER` + `console_password`. All historical session rows and audit rows are lost — acceptable trade-off because the alternative is keeping a corrupted DB.

### 9.2 Lever 2 — operator #1 password reset (case-normalised; query then update by id)

If operator #1's password is forgotten (or the seed didn't fire because `CONSOLE_PASSWORD` was unset at first start), Federico recovers via SQLite directly. Per D2, the RW writer for `console.db` is the `api` container — that's the container we exec into for this.

**The bug we are explicitly avoiding** (security review 2026-04-28 evening — Amendment 5): an earlier draft of this runbook used `WHERE username = 'admin'`. If `CONSOLE_USER` was set to `Admin` in `.env` but stored as `admin` in the DB (or vice versa, across some mismatched seed/runbook history), the UPDATE would silently affect zero rows. The operator gets no error, the password isn't actually reset, and they discover the lie only at the next failed login. This is the case-sensitivity bug Federico flagged.

**The fix:** never target the row by username string match. Always (a) query the row to confirm it exists and capture its `id`, then (b) UPDATE by `id`. This is robust against typos in the env var, against case skew between seed time and runbook time, and against any row that may have been renamed.

```bash
# 1. SSH into the Pi5.
ssh pi5

# 2. Generate the new hash inside the api container.
docker compose -f docker-compose.yml exec api \
    python -c "from src.api.auth.hashing import hash_password; \
               import sys; print(hash_password(sys.argv[1]))" 'newpw'
# Copy the printed hash.

# 3. Identify the target operator by querying first — DO NOT
#    target by username string match. The lookup is
#    case-insensitive via LOWER() so a CONSOLE_USER of 'Admin' or
#    'admin' or '  ADMIN ' all resolve to the same row.
docker compose -f docker-compose.yml exec api \
    sqlite3 /data/console/console.db \
    "SELECT id, username, display_name, disabled_at
       FROM operators
       WHERE LOWER(TRIM(username)) = LOWER(TRIM('${CONSOLE_USER}'));"
# Confirm exactly one row, capture the id (e.g. 1).

# 4. Update by id (NOT by username) using the captured id from step 3.
docker compose -f docker-compose.yml exec api \
    sqlite3 /data/console/console.db \
    "UPDATE operators
        SET password_hash = '<paste_hash_from_step_2>',
            updated_at    = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
      WHERE id = <id_from_step_3>;"

# 5. Verify the change took effect.
docker compose -f docker-compose.yml exec api \
    sqlite3 /data/console/console.db \
    "SELECT id, username, length(password_hash), updated_at
       FROM operators WHERE id = <id_from_step_3>;"
# Expect: one row with the new updated_at and a 90-100ish char hash.
```

If step 3 returns zero rows: the `operators` table is in the empty-bootstrap or all-disabled state. Reset is not possible via this lever. Use the lever 1b path (wipe `console.db`, re-seed from `CONSOLE_USER` + `CONSOLE_PASSWORD`) instead.

If step 3 returns more than one row: the DB is in an inconsistent state (the unique index on `LOWER(username)` should make this impossible). Stop, capture the table contents, escalate. Do not blindly UPDATE.

This runbook is documented verbatim in `docs/runbook-prod-deploy.md` under "operator password reset". (Pre-D2 versions of this spec used the `scheduler` container because the api was `:ro` on `clients.db`. With the split, `api` is the right and only writer for `console.db`.)

### 9.3 Lever 3 — full revert

If the Stage A schema additions corrupt something subtle and levers 1 / 1b aren't enough, the full revert path is:

1. `git revert <stage-A-merge-sha>`.
2. Push to `prod` (with `HEIMDALL_APPROVED=1`).
3. SSH Pi5, `heimdall-deploy`.
4. After redeploy, the api container is back on Basic Auth and no longer mounts `console-data`. The `console-data` named volume can be left in place (cheap, gitignored) or removed via `docker volume rm heimdall_console-data` — neither affects `clients.db`.
5. The new `console-db-schema.sql` file persists in the repo (now unused by the runtime) but is harmless. A follow-up cleanup PR can delete it if Stage A is being abandoned permanently rather than re-attempted.

---

## 10. Decisions still open

> **Note (2026-04-28 afternoon, after the evening security review):** Five security/correctness fixes were applied 2026-04-28 evening per Federico's review; three additional normative tightening fixes (D1 rate-limit integration, D8 config.update exempt, D9 retention sync) were applied 2026-04-28 afternoon. The fixes override prior recommendations recorded in this section in places where the §1 / §3 / §4 / §5 / §7 / §9 prose changed. The text below for D1–D7 is the resolved-on-2026-04-28-morning state and is preserved for the audit trail; D8 and D9 sit at the end of the list and are the new tightening-pass decisions. For the currently-authoritative state of every section, see §14 revision history and the corresponding section bodies above. Highlights: D2's `console.db` carve stands, and per D9 the api's `clients.db` mount is `:rw` (provided by PR #49, direct to main); Stage A consumes the fix and adds no further mount surface; D1's rate-limit decision is now integrated end-to-end into the login flow / response shapes / tests / file map (no longer "decided + invisible"); D8 makes config.update audit explicitly out of scope (deferred to Stage A.5's `config_changes` triggers per D2); §3.5's whoami signal is four states (204 / 409 / 200 / 401), the WS auth path is in the handler, session tokens are hashed at rest, password-reset runbook is case-normalised.

These surfaced while drafting the spec. **All nine were decided 2026-04-28.** D1–D7 resolved earlier in the day (morning + evening security review); D8 and D9 added 2026-04-28 afternoon during the tightening pass and resolved in the same session. Original discussion preserved for context; the chosen path is recorded under each item.

1. **Account lockout / brute-force defense.** The spec has no per-IP / per-username rate limit on `/console/auth/login`. Argon2id at our parameters takes ~50ms, so a single attacker can attempt ~20 passwords/s, ~1.7M/day per IP — enough to break a weak password. Options: (a) per-IP rate limit (5 fails / 15 min) implemented via Redis `INCR` + TTL; (b) per-username lockout (5 fails → disabled_at set, manual unlock); (c) defer to Stage A.5 / a separate rate-limit PR. Recommend (a) for Stage A as the lowest-cost defense; happy to move to A.5 if you'd rather keep Stage A surface minimal.

   **Decided 2026-04-28 — option (a): per-IP rate limit (5 fails / 15 min via Redis `INCR` + TTL) lands inside Stage A.** Federico confirmed the recommendation.

   **Implementation pointer (added 2026-04-28 afternoon, normative-integration pass).** The decision is now baked into the spec body, not just recorded here. See: §3.1 step 1 (rate-limit gate is the FIRST step of the login handler, before username lookup or Argon2id), §3.1.a (Redis contract — key format, TTL, Retry-After source, fail-open behaviour), §6.3 (`/console/auth/login` 429 response shape with `Retry-After` header and `{"error": "rate_limited"}` body), §8.2 ten rate-limit tests in the new `tests/test_auth_rate_limit.py`, §8.3 integration scenario, Appendix A `tests/test_auth_rate_limit.py` (~150 LOC) and `src/api/auth/rate_limit.py` (~60 LOC; Redis client + check/incr/clear helpers lifted out of the router).

2. **`api` container DB write access.** ~~Today the api container mounts `client-data:/data/clients:ro` (`infra/compose/docker-compose.yml:140`). Stage A requires the api to write (sessions, audit_log, operator last_login). Options: (a) flip the api mount to RW and accept the broader write surface; (b) keep api `:ro` and proxy auth writes through the scheduler container via Redis (a queue request, an async write, a callback) — much heavier; (c) split clients.db so audit/sessions/operators live in a separate `console.db` that api mounts RW while clients.db stays `:ro` for the api. Recommend (a)~~

   **Decided 2026-04-28 — option (c): split into a separate `console.db` mounted RW.** Federico's reasoning: "Flipping the main client DB from RO to RW in the API widens the blast radius at exactly the layer you are trying to harden. Auth/session/audit data is control-plane state; it does not need to share a write surface with core client/scanning data." Implementation: new SQLite DB at `/data/console/console.db`, new compose volume `console-data` mounted RW on `api` only, new `docs/architecture/console-db-schema.sql`, new `src/db/console_connection.py` with `init_db_console()` factory invoked at api startup alongside `init_db()`. See §1, §2.5–§2.7, §6.4, §9, Appendix A, Appendix B for the full ripple.

   **Amendment 2026-04-28 (afternoon, per D9):** The original framing here said "the existing `client-data:/data/clients:ro` mount on api is unchanged". The D9 investigation found that PR #46's already-shipped retention CAS UPDATEs would raise `OperationalError` against the `:ro` mount in production — i.e. D2's `:ro` framing did not match the runtime. **PR #49 (separate, direct to main) widens the api's `clients.db` mount narrowly from `:ro` to `:rw`.** The widening is provided by main, not by Stage A. Stage A's role is to consume that capability for the audit-paired retention/trial writes (§7.2). D9 is the source of truth for the api's `clients.db` mount mode (now `:rw`); D2 stands as the source of truth for the `console.db` carve.

3. **Deprecation shim vs hard delete of `src/api/console.py`.** §6.6 says quick-grep for external imports, then either ship a 5-line shim or hard-delete. Quick grep before merge will tell us; want me to do that grep as part of plan refinement, or should the implementing PR decide?

   **Decided 2026-04-28 — implementing PR runs the grep and decides at carve time.** Federico confirmed the recommendation. If no external imports of `src.api.console`, hard-delete; otherwise ship the 5-line shim that re-exports each new router for one release window.

4. **Cookie `Secure` in dev.** The spec sets `Secure` to `os.environ.get("HEIMDALL_COOKIE_SECURE", "1") == "1"`. Default secure-on means dev (HTTP localhost) needs `HEIMDALL_COOKIE_SECURE=0` in `.env.dev`. Alternative: default to `0` and have prod set `HEIMDALL_COOKIE_SECURE=1` in `.env`. Standard practice is "default secure, opt out for dev" but it adds one more env var for `make dev-up` to remember. Recommend the secure-default path; flag for confirmation.

   **Decided 2026-04-28 — default `HEIMDALL_COOKIE_SECURE=1` (secure-on); `.env.dev` opts out with `=0`.** Federico confirmed the recommendation.

5. **`/console/auth/whoami` behaviour when operators table is empty.** ~~The login flow returns 401 in this case (§8.2 `test_auth_login_logout.py`). Should `whoami` also return 401, or a sentinel `204` "no operators seeded — login impossible" so the SPA can render a "talk to your admin" splash instead of the login form? Recommend 401 for symmetry~~

   **Decided 2026-04-28 — return 204 from `/console/auth/whoami` when operators table is empty (not 401).** Federico's reasoning: "Empty-operator bootstrap is a distinct system state, not an auth failure. Returning 401 makes the product lie about what is happening and forces the SPA into the wrong UX branch." Body-less 204 is the wire signal; the SPA renders a "no operators seeded — talk to your admin" splash. The login endpoint behavior is unchanged — still 401 on bad credentials. See §3.5, §6.3, §8.2 for the contract + tests.

6. **Notifications-context placeholder file.** §6.5 says no `routers/notifications.py` file is created. Should `__init__.py` carry a comment-block placeholder, or should we ship an empty `notifications.py` with just a comment so the file is grep-able as "this is where Notifications goes"? Recommend the comment-block in `__init__.py` only; an empty file invites premature additions.

   **Decided 2026-04-28 — comment-block in `routers/__init__.py` only; no `notifications.py` file in Stage A.** Federico confirmed the recommendation.

7. **Test-file evolution vs. delete-and-recreate for `test_console_auth.py`.** ~~The existing test file has shape `test_console_*` that other developers grep for; renaming to `test_session_auth.py` makes more sense semantically but breaks grep continuity. Recommend keep the filename, evolve the contents.~~

   **Decided 2026-04-28 — rename `tests/test_console_auth.py` → `tests/test_session_auth.py`.** Federico's reasoning: "Keeping the old filename preserves grep continuity, but it also preserves the wrong mental model. If you care, leave a short note in the decision log and make grep continuity a documentation problem, not a test-naming problem." Implementation: `git mv` (not delete + recreate); commit message must mention the rename so `git log --follow` works for anyone who greps for the old name. See §8.1, §8.2 for the test plan.

8. **`config.update` audit in Stage A: atomic or exempt?** Federico's framing 2026-04-28 afternoon: "decide whether `config.update` is truly atomic in Stage A or explicitly exempt." Earlier draft of this spec hand-waved an api-side intent + writer-side outcome split for config edits, parallel to the retention choreography. That conflated two things: (a) the config-update workflow itself (which depends on whether config edits land in `clients.db`, in `console.db`, in JSON files, or in env vars — itself a Stage A.5 design point), and (b) the formal capture contract (D2: DB triggers + repository wrappers), which is unambiguously Stage A.5.

   **Decided 2026-04-28 (afternoon) — `config.update` audit in Stage A is explicitly out of scope.** Picked exempt over best-effort. The `/console/settings/{name}` PUT endpoint ships in Stage A's router carve unchanged in behaviour (it does the same write today's `src/api/console.py` does); it does NOT write a `console.audit_log` row in Stage A; it writes its `config_changes` row only when Stage A.5 lands the trigger machinery per D2. The Stage A audit guarantee is restated as "every operator-mutating endpoint *that is in scope for Stage A audit* writes an audit row in the same transaction as the mutation it records" — config is the only mutating endpoint outside that set, and the exclusion is recorded explicitly so reviewers don't expect coverage. Ripples: §1 (clients.audit_log action list), §6.2 (`/console/settings/*` row annotation), §7.3 (mutation table row), §7.6 (new explicit-out-of-scope subsection), §11 (Out of Scope row added). Don't relitigate D2 — the trigger design lives there.

9. **Retention dispatch semantics in Stage A: synchronous or async 202?** Federico's framing 2026-04-28 afternoon: "Stage A scope is drifting into workflow-behavior redesign via async retention dispatch. State clearly whether retention endpoints remain synchronous in Stage A or intentionally switch to async 202 dispatch semantics." The earlier draft introduced an "intent → enqueue → writer container does SQL → outcome" async dispatch design for the three retention endpoints with a 202 Accepted response. That was a workflow redesign smuggled into an auth / identity / router carve sprint.

   **Decided 2026-04-28 (afternoon) — Stage A retention endpoints remain synchronous.** No async 202. No dispatch-intent + outcome split. The architect's async design is reverted out of this spec; if it's the right answer for V2 / A.5, it's a separate spec. Picked synchronous to keep Stage A scope focused on auth/identity/router carve, not workflow redesign. Behaviour matches PR #46 verbatim: api opens a SQLite connection to `clients.db`, runs a CAS UPDATE on `retention_jobs`, returns 200 with the updated row. The Stage A addition is a single audit row in `clients.audit_log` written in the same transaction as the CAS UPDATE — one row per action, not two. Ripples: §3.x and §6.3 retention rows (200, not 202), §7.3 (single audit row, action strings without `dispatch_intent`), §7.2 (rewritten as sync + same-transaction audit), §1 DDL action list (no `retention.dispatch_intent`), Appendix A LOC budget (no Redis enqueue helper, no api-side dispatch-intent writer; the api now becomes a clients.audit_log writer for retention/trial events).

   **Api mount investigation outcome (Federico requested).** Compose review (`infra/compose/docker-compose.yml:140`) confirmed api previously mounted `client-data:/data/clients:ro`. PR #46's retention endpoints write directly via `sqlite3.connect(db_path).commit()` against `data/clients/clients.db`. With the existing `:ro` mount this MUST raise `OperationalError: attempt to write a readonly database` in production — i.e. Outcome C (PR #46 inherited a broken assumption). **PR #49 (separate, opened 2026-04-28 afternoon, direct to main, on `fix/api-clients-db-mount`) flips api's `clients.db` mount from `:ro` to `:rw`** to fix the latent PR #46 bug surfaced by this investigation. PR #49 also ships `scripts/dev/verify_api_clients_db_write.sh` (BEGIN IMMEDIATE / ROLLBACK probe inside the running api container) and the `make dev-verify-api-write` target. Stage A consumes that fix; no further mount change is in scope here. The audit-paired narrow-write invariant — api only writes retention/trial CAS UPDATEs + paired audit rows on `clients.db` — is enforced by code review on `src/api/routers/retention.py` and `src/api/routers/onboarding.py`, not by mount mode. D2's `console.db` carve is preserved unchanged.

   This investigation outcome (resolved on main via PR #49) supersedes the earlier "api stays `:ro` on clients.db" framing. See Appendix B for what remains in Stage A's compose surface (just D2's `console-data` add).

---

## 11. Out of scope (deferred)

Each item below is explicitly NOT in Stage A. The "Lands in" column is binding — these are forward references that the Stage A.5 spec must honor.

| Item | Lands in | One-line description |
|---|---|---|
| `Permission` enum | Stage A.5 | Code-backed enum at `src/api/auth/permissions.py`; values like `Permission.RETENTION_FORCE_RUN` |
| `require_permission(Permission.X)` decorator | Stage A.5 | Wraps a route handler; checks `request.state.operator_role_hint` against a permission map |
| `command_audit` table | Stage A.5 | Separate table for command-level audit (richer than `audit_log`'s per-action rows) |
| `config_changes` table | Stage A.5 | Captures every config-affecting write |
| DB triggers populating `config_changes` | Stage A.5 | Per D2: triggers for capture, repository wrappers for intent/actor |
| `config.update` audit (the operator-config-edit `/console/settings/{name}` PUT writing an audit row) | Stage A.5 | Per D8 (decided 2026-04-28 afternoon): exempt in Stage A — see §7.6. Endpoint behaviour ships unchanged in the Stage A router carve; only the audit-row write is deferred until A.5's `config_changes` triggers land. |
| Repository wrappers for actor/trace_id propagation | Stage A.5 | Sets SQLite session-state vars that triggers read |
| X-Request-ID middleware | Stage A.5 | Generates / propagates a per-request UUID; populates `audit_log.request_id` |
| `trace_id` propagation through loguru context | Stage A.5 | Binds `request_id` into loguru's per-task context |
| `GET /console/config/history` | Stage A.5 | Reads `config_changes` + git-shells to compare config-file revisions |
| Table-backed RBAC (`roles` / `permissions` / `role_permissions`) | Post-Stage-A.5 (TBD) | Per D3, deferred until >2 roles or runtime role admin needed |
| Notifications context (`routers/notifications.py`) | Post-V2 sprint | Per D1, the 7th context; unifies CT-change / retention-failure / Message 0 / future SMS |
| Operator admin UI (create/disable/role-edit operators) | Stage A.5 or later | Stage A creates rows manually via SQL; admin UI is a follow-up |
| Read-side audit (GET endpoints write rows) | Notifications-carve sprint | Volume + PII concerns; not in Stage A |
| Per-WS-disconnect audit row | Not in any planned sprint | Documented as deliberate Stage A simplification |

---

## 12. Appendix A — file map

Files added in Stage A:

```
docs/architecture/stage-a-implementation-spec.md          # this file
docs/architecture/console-db-schema.sql                   # NEW — DDL home for operators / sessions / console.audit_log (D2)
src/api/auth/__init__.py                                  # ~10 LOC
src/api/auth/hashing.py                                   # ~50 LOC (Argon2id wrapper for passwords)
src/api/auth/sessions.py                                  # ~170 LOC (issue/refresh/revoke; SHA-256 token-hash helper for the cookie-vs-DB split)
src/api/auth/middleware.py                                # ~130 LOC (HTTP-only; computes sha256(cookie) → token_hash lookup; defensive WS scope early-return)
src/api/auth/audit.py                                     # ~60 LOC (write_console_audit_row — writes ONLY to console.audit_log; security review 2026-04-28 evening)
src/api/auth/rate_limit.py                                # ~60 LOC NEW (Redis client + check/incr/clear helpers; lifted out of the auth router so it's testable in isolation; fail-open on Redis errors per §3.1.a)
src/db/clients_audit.py                                   # ~70 LOC NEW (write_clients_audit_row — writes ONLY to clients.audit_log from scheduler/worker/delivery; Option B helper)
src/api/routers/__init__.py                               # ~30 LOC (placeholder for Notifications too)
src/api/routers/auth.py                                   # ~140 LOC (login + logout + whoami; login wires the rate_limit module in as STEP 1 before any DB lookup; whoami covers 200/204/409/401 per D5 + security review)
src/api/routers/tenant.py                                 # ~150 LOC (extracted from console.py)
src/api/routers/findings.py                               # ~80 LOC
src/api/routers/onboarding.py                             # ~80 LOC
src/api/routers/billing.py                                # ~10 LOC (placeholder, empty router)
src/api/routers/retention.py                              # ~200 LOC
src/api/routers/liveops.py                                # ~530 LOC (bulk of console.py's runtime + demo + WS; WS handler does its own auth — read cookie, sha256, validate, accept-or-close-with-4401)
src/db/console_connection.py                              # ~80 LOC (init_db_console, get_console_conn, _seed_operator_zero — D2; seed normalises CONSOLE_USER.strip().lower())
scripts/dev/console_login.sh                              # ~40 LOC
tests/test_auth_hashing.py                                # ~80 LOC
tests/test_auth_sessions.py                               # ~250 LOC
tests/test_auth_middleware.py                             # ~270 LOC (HTTP-only assertions + token_hash-lookup test + WS-scope-bypass test; security review)
tests/test_auth_login_logout.py                           # ~270 LOC (whoami 200/204/409/401 + token-hash storage assertion + rate-limit integration in login table; security review)
tests/test_auth_rate_limit.py                             # ~150 LOC NEW (per-IP rate limit; ~10 tests; isolatable Redis fixture)
tests/test_auth_csrf.py                                   # ~120 LOC
tests/test_audit_log_writer.py                            # ~180 LOC (covers BOTH write_console_audit_row and write_clients_audit_row helpers)
tests/test_console_ws_auth.py                             # ~180 LOC (handler-level auth; close-with-4401 before accept; middleware-bypass assertion)
tests/test_router_carve.py                                # ~100 LOC
tests/test_console_integration.py                         # ~190 LOC (cross-DB audit timeline read — both rows present after a retention force-run; full Redis → 429 → TTL → success rate-limit scenario)
```

Files RENAMED in Stage A (use `git mv` so `git log --follow` continues to track history):

```
tests/test_console_auth.py  →  tests/test_session_auth.py    # D7 (2026-04-28)
                                                             # commit subject must explicitly mention rename
```

Files modified in Stage A:

```
src/api/app.py                                            # -90 LOC (BasicAuthMiddleware), +40 LOC (six include_router calls + init_db_console invocation in lifespan)
src/db/connection.py                                      # NO CHANGE — operator #0 seed lives in src/db/console_connection.py instead (D2)
src/db/migrate.py                                         # +5–15 LOC: one new _TABLE_ADDS (or equivalent) entry to provision clients.audit_log on existing prod DBs (Option B)
docs/architecture/client-db-schema.sql                    # +1 SECTION at the end — clients.audit_log CREATE TABLE + 5 indexes (Option B; security review 2026-04-28 evening)
src/scheduler/runner.py + src/worker/main.py + src/delivery/bot.py
                                                          # ~3 small call sites each — invoke write_clients_audit_row(conn, ...) inside the existing
                                                          # `with conn:` block of every state-changing system mutation (trial.expired, retention.tick,
                                                          # ct.delta_observed, command.<name>). Operator-initiated retention writes are SYNC from api
                                                          # per §10 D8 — those call sites land in src/api/routers/retention.py, NOT here. config.update
                                                          # is NOT audited in Stage A (§7.6). +10–20 LOC each container; the helper is the only new import.
requirements.txt                                          # +1 line: argon2-cffi
infra/compose/docker-compose.yml                          # see Appendix B for danger-zone touches (new console-data volume + RW mount on api)
infra/compose/.env.example, .env.dev.example              # add CONSOLE_SESSION_IDLE_TTL_MIN, _ABSOLUTE_TTL_MIN, HEIMDALL_COOKIE_SECURE, CONSOLE_DB_PATH
scripts/dev/verify_dev_console_seed.py                    # use console_login.sh / cookie auth instead of -u admin:pw
docs/development.md                                       # add "Operator login" subsection + cookie troubleshooting
docs/runbook-prod-deploy.md                               # add "Operator password reset" runbook step (case-normalised: query-by-LOWER → UPDATE-by-id; security review 2026-04-28 evening)
```

Files DELETED in Stage A:

```
src/api/console.py                                        # → split into routers/* (modulo §6.6 shim decision)
infra/compose/secrets/console_password                    # NOT deleted in Stage A — kept for legacy lever rollback (§9.1); deleted in next release
```

Estimated total diff: +2500 / -700 LOC across ~34 files (one extra schema file, one extra connection module, one extra clients-audit helper, plus the writer-container call sites for clients.audit_log per Option B). Codex-friendly: every file is small, every error contract explicit, no metaprogramming.

---

## 13. Appendix B — infra surface flagged for the danger-zone hook

Per CLAUDE.md "Hook-Based Enforcement" and `.claude/hooks/infra_danger_zone.py`, the following file edits will trigger the danger-zone hook on the implementation PR. Per D2 (2026-04-28 morning), Stage A's compose surface adds the `console-data` volume + RW mount on api. The `client-data` mount on api is `:rw` as of PR #49 (separate, direct to main); Stage A inherits that and does NOT touch the `client-data` mount. Single danger-zone diff, inside the api service block.

1. **`infra/compose/docker-compose.yml`** — TWO changes total: a new top-level volume entry, and a single new mount line inside the api service block. The `client-data` mount on api is NOT touched in Stage A (PR #49 already widened it on main).

   1a. **NEW top-level volume entry** (in the `volumes:` block at the bottom of the compose file):

   ```yaml
   volumes:
     # ... existing entries unchanged ...
     console-data:
       driver: local
       # No bind — Stage A uses Docker-managed volume.
       # PROD/DEV split (M37) does not currently apply because there is
       # no host source-of-truth for console.db. If a host bind-mount
       # becomes operationally desirable post-Stage-A, add it then.
   ```

   1b. **`console-data` mount added to api** (Stage A's only mount-related change to the api service):

   ```yaml
   services:
     api:
       # ... unchanged ...
       volumes:
         - client-data:/data/clients       # :rw — provided by PR #49 on main; Stage A does NOT touch this line
         - console-data:/data/console:rw   # NEW — Stage A operators/sessions/auth-event audit_log live here
         # ... other existing mounts unchanged ...
   ```

   The secrets block is unchanged in Stage A (`console_password` stays mounted for the legacy lever; a follow-up PR removes it).

   Per §2.7, no other container (`scheduler`, `worker`, `delivery`) gets the `console-data` mount in Stage A.

2. **`infra/compose/.env.example`** — adds `CONSOLE_SESSION_IDLE_TTL_MIN`, `CONSOLE_SESSION_ABSOLUTE_TTL_MIN`, `HEIMDALL_COOKIE_SECURE`, `HEIMDALL_LEGACY_BASIC_AUTH`, `CONSOLE_DB_PATH` (defaults to `/data/console/console.db`). (Optional: also add `OPERATOR_PASSWORD_PEPPER` reference if pepper is used; not required.)

3. **`infra/compose/.env.dev.example`** — same additions, with dev-friendly defaults (`HEIMDALL_COOKIE_SECURE=0`). `CONSOLE_DB_PATH` does NOT need a dev override unless we later add a host bind-mount for dev observability — for now the named volume is the same in dev and prod.

4. **`requirements.txt`** — adds `argon2-cffi` pin.

5. **`infra/compose/Dockerfile.api`** — no change required if `argon2-cffi` is in `requirements.txt` and the Dockerfile already does `pip install -r requirements.txt`. Confirm before merge.

6. **`docs/architecture/console-db-schema.sql`** — NEW file (per D2). Three CREATE TABLE blocks + indexes. Replaces the pre-D2 plan to append SECTION 13 to `client-db-schema.sql`.

7. **`docs/runbook-prod-deploy.md`** — adds operator-password-reset section. Uses the `api` container per §9.2 (post-D2 — pre-D2 used `scheduler`).

8. **`docs/development.md`** — adds operator-login subsection.

The `ci_config_reminder.py` hook will fire when the Dockerfile / requirements.txt / docker-compose.yml are touched. Plan to push and `gh run watch` after merge.

---

## 14. Revision history

| Date | Change |
|---|---|
| 2026-04-27 (late evening) | Initial draft. Codifies the four operator-console reframe decisions resolved 2026-04-27 evening. Seven decisions remain open (§10). |
| **2026-04-28 (morning)** | **Federico's call on three of the seven open decisions:** **D2** — split into separate `console.db` mounted RW (rejected the recommended option (a) of flipping `clients.db` to RW; control-plane state is carved out from core client/scanning data). New schema file `docs/architecture/console-db-schema.sql`, new connection module `src/db/console_connection.py` with `init_db_console()` factory, new `console-data` volume RW on `api` only. Ripples through §1, §2.5–§2.7, §6.4, §9, Appendix A, Appendix B. **D5** — `/console/auth/whoami` returns 204 (not 401) when the `operators` table has zero non-disabled rows; login endpoint behaviour unchanged. Ripples through §3.5, §6.3, §8.2. **D7** — `tests/test_console_auth.py` is renamed (via `git mv`) to `tests/test_session_auth.py`; commit message must mention the rename so `git log --follow` works. Ripples through §8.1, §8.2, Appendix A. Items 1, 3, 4, 6 remain as-is (Federico approved the recommendations). Spec updated in place. |
| **2026-04-28 (afternoon)** | **Federico tightening pass — three fixes, all normative.** (1) **Rate limiting integrated end-to-end (D1).** §10 had recorded the decision but the spec body never showed it; rate-limit was effectively "decided + invisible". Now baked in: §3.1 step 1 makes the per-IP gate the FIRST step of the login handler (before username lookup or Argon2id), §3.1.a documents the Redis contract (key `auth:fail:<ip>`, threshold 5, window 900s, `redis.expire` only on first INCR, success clears via `redis.delete`, fail-open on Redis errors with WARNING-level log), §6.3 adds the 429 response shape with `Retry-After: <seconds>` header and `{"error": "rate_limited"}` body, §8.1 adds a new `tests/test_auth_rate_limit.py` file (~150 LOC, 10 tests including the fail-open lock-in), §8.3 adds an integration scenario walking the full Redis → 429 → wait-for-TTL → success path, Appendix A adds `src/api/auth/rate_limit.py` (~60 LOC; Redis client + check/incr/clear helpers lifted out of the router for isolated testability) and bumps `src/api/routers/auth.py` to ~140 LOC. §11 (Out of scope) row removed; §10 D1 gets an "Implementation pointer" line citing every section. (2) **`config.update` audit explicitly out of scope (D8).** Earlier draft hand-waved an api-side intent + writer-side outcome split for config edits, parallel to retention. That conflated two things: the config-update workflow itself (Stage A.5 design point) and the formal capture contract (D2: triggers + repository wrappers, also Stage A.5). Picked exempt over best-effort: §7.3 mutation-table row reads "not audited in Stage A; full capture lands in Stage A.5", §7.6 (new subsection) documents the rationale, §1 `clients.audit_log` action list strips `config.update`, §6.2 router carve annotates `/console/settings/*` as "no audit in Stage A", §11 adds the explicit out-of-scope row. The Stage A audit guarantee is restated as "every operator-mutating endpoint *that is in scope for Stage A audit* writes an audit row" — the in-scope set is exactly §7.3's table rows with non-`—` `action` strings; config is the only mutating endpoint outside the set. (3) **Retention dispatch synchronous in Stage A, NOT async 202 (D9).** Federico's framing: "Stage A scope is drifting into workflow-behavior redesign via async retention dispatch." Picked synchronous. The architect's "intent → enqueue → writer outcome" design with 202 Accepted is reverted out of this spec. §7.2 rewritten end-to-end as sync + same-transaction audit (one row per action, in `clients.audit_log`, written by api itself), §3.x and §6.3 retention rows stay 200, §1 DDL action list strips `retention.dispatch_intent`, Appendix A LOC budgets shrink (no Redis enqueue helper). Investigation outcome on the api mount: compose review confirmed `client-data:/data/clients:ro` today, but PR #46's CAS UPDATEs would raise `OperationalError` against `:ro` — i.e. PR #46 inherits a broken assumption (Outcome C). Resolved by **flipping api's `clients.db` mount from `:ro` to `:rw`** narrowly for the three retention CAS-UPDATE endpoints (audit-paired in the same transaction); other clients.db tables are reachable but not written by api, enforced by code review (not mount mode). D2's `console.db` carve stands; the `:ro` → `:rw` flip on `clients.db` is a narrower scoped concession. Ripples through §1 (audit rationale paragraph), §1.3 (cross-DB ownership rule rewritten), §1.3.b (writer comment rewritten), §2.7 (api now widens `clients.db` mount, table added), Appendix B (compose stanza updated with explicit `:ro` → `:rw` flip + code-review gate). |
| **2026-04-28 (late afternoon)** | **Mount-widening prose moved out of the spec.** PR #49 (separate, direct to main, opened by Federico the same day, on `fix/api-clients-db-mount`) lands the api `clients.db` `:ro` → `:rw` fix on main; Stage A consumes the fix instead of shipping it. PR #49 also ships `scripts/dev/verify_api_clients_db_write.sh` (BEGIN IMMEDIATE / ROLLBACK probe inside the running api container; PASS/FAIL on stdout, exit 0/1) and the `make dev-verify-api-write` target. Edits in §1 header, §2.7, §7/§1.3 cross-DB rationale, §10 D2 amendment, §10 D9 body, Appendix B (entry 1b removed). The narrow-write invariant (audit-paired only — api only writes retention/trial CAS UPDATEs + paired audit rows on `clients.db`) is now enforced by code review on the retention/onboarding routers (`src/api/routers/retention.py`, `src/api/routers/onboarding.py`), not by mount mode. D9 is preserved as a load-bearing decision (synchronous retention; audit ownership rule). |
| **2026-04-28 (evening)** | **Federico security review applied. Five fixes:** (1) **Hash session tokens at rest** — `sessions.token` renamed to `sessions.token_hash` storing SHA-256 of the plaintext; the cookie still carries the plaintext, the server hashes the presented value at the start of each request and looks up the hash in the table; the unhashed token is never persisted server-side. No PBKDF on the token (256-bit entropy from `secrets.token_urlsafe(32)`, not a human password). Ripples through §1.2, §3.1, §3.2, §3.4, §4.2, §8.2 (`test_auth_login_logout.py` adds the cookie-vs-DB-key separation assertion; `test_auth_middleware.py` adds the `token_hash`-lookup test). (2) **Audit ownership split per Option B** — the false-atomicity claim ("audit row in same transaction as the mutation") could not be honored across the post-D2 console.db / clients.db split. Resolved by splitting audit ownership: `console.audit_log` lives in `console.db` and is written by the `api` container for auth events; `clients.audit_log` lives in `clients.db` and is written by `scheduler` / `worker` / `delivery` for retention / trial / onboarding / config mutations. Each row is in the SAME SQLite transaction as the mutation it records — real atomicity. Operator-initiated mutations write TWO rows (intent on api side, outcome on writer side); correlation is by `request_id` once Stage A.5 wires X-Request-ID. Ripples through §1, §2.1, §7, Appendix A. (3) **WS auth in the handler, not the middleware** — Starlette's `BaseHTTPMiddleware` does not reliably gate WebSocket upgrades (HTTP-only by design). Auth moved into the WS handler: read `ws.cookies['heimdall_session']`, hash via SHA-256, validate against `console.db`, accept-or-close-with-4401 before `ws.accept()`. The first-frame fallback path is deferred out of Stage A. Middleware explicitly does NOT touch `/console/ws`. Ripples through §3.6, §5, §8.2 (`test_console_ws_auth.py` rewritten for handler-level auth). (4) **Whoami split states 204 / 409 / 200 / 401** — earlier draft conflated "genuine empty bootstrap" with "operators exist but all disabled" under a single 204. Now distinguished: 204 for zero rows total (genuine bootstrap), **409 Conflict** with `{"error": "all_operators_disabled"}` for the all-disabled state, 200 for authenticated, 401 for unauthenticated. Ripples through §3.5, §6.3, §8.2 (`test_auth_login_logout.py` adds the all-disabled test case). (5) **Password-reset runbook normalises username case** — the earlier runbook targeted by `WHERE username = 'admin'` which silently failed on case skew. Replaced with query-by-LOWER → UPDATE-by-id, robust against typos in `CONSOLE_USER` or case skew between seed time and runbook time. Operator #0 seed also normalises explicitly: `CONSOLE_USER.strip().lower()` is the canonical form stored in the DB. Ripples through §2.2, §9.2. |

---

**End of spec.**
