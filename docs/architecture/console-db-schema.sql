-- =================================================================
-- Heimdall console database — complete schema (Stage A)
-- Database: /data/console/console.db
-- Mode: WAL (journal_mode=WAL, synchronous=NORMAL)
-- =================================================================
--
-- This file is the AUTHORITATIVE schema for console.db. It is the
-- counterpart to client-db-schema.sql (which owns clients.db). The
-- two databases are physically separate SQLite files mounted on
-- different volumes; no cross-DB FKs, no ATTACH at runtime.
--
-- Replaces the single-credential CONSOLE_USER / console_password
-- HTTP Basic Auth scheme (currently in src/api/app.py:53-91) with
-- first-class operator rows, server-side session tickets, and an
-- immutable per-action audit log.
--
-- Single-tenant today (Federico is operator #1) but designed for a
-- small ops team. Identity provider is local password (Argon2id);
-- MitID Erhverv is for clients (signup), not operators.
--
-- See docs/architecture/stage-a-implementation-spec.md §1 for the
-- design rationale and the cross-DB ownership rule (Option B audit
-- split: each audit row in the same SQLite transaction as the row
-- it records). This file owns auth-side audit only; mutation-side
-- audit lives in clients.db's audit_log (added to
-- client-db-schema.sql in the same Stage A slice).
-- =================================================================

-- Enable recommended pragmas (set at connection time, not in schema):
--   PRAGMA journal_mode=WAL;
--   PRAGMA synchronous=NORMAL;
--   PRAGMA foreign_keys=ON;
--   PRAGMA cache_size=-8000;


-- =================================================================
-- SECTION 1: Operators — first-class identity rows
-- =================================================================

-- -----------------------------------------------------------------
-- operators
-- -----------------------------------------------------------------
-- One row per console operator. The username is the login handle;
-- display_name is what we show in the UI ("logged in as Federico"
-- vs "logged in as fede1"). password_hash is Argon2id; pepper, if
-- any, lives in /run/secrets/operator_password_pepper.
--
-- role_hint is free-text in Stage A. Stage A.5's require_permission
-- decorator reads it and maps via an in-code Permission table; until
-- then it's purely informational. Acceptable values seeded by Stage
-- A migrations: 'owner', 'operator', 'observer'. The string is not
-- validated by SQLite — Stage A.5's decorator validates at lookup.
--
-- disabled_at is a timestamp (not a boolean) so the column doubles
-- as the offboarding audit trail. NULL = active operator.

CREATE TABLE IF NOT EXISTS operators (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,                -- login handle, lowercase
    display_name    TEXT NOT NULL,                       -- shown in UI
    password_hash   TEXT NOT NULL,                       -- Argon2id, full PHC string
    role_hint       TEXT NOT NULL DEFAULT 'operator',    -- free-text in Stage A; Stage A.5 maps to Permission enum
    disabled_at     TEXT,                                -- ISO-8601 UTC; non-NULL = no login allowed
    last_login_at   TEXT,                                -- ISO-8601 UTC; updated on successful login
    last_login_ip   TEXT,                                -- forensic only, not for binding
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Case-insensitive uniqueness — guards against `Federico` vs `federico` collisions.
CREATE UNIQUE INDEX IF NOT EXISTS idx_operators_username_lower
    ON operators(LOWER(username));

-- "All active operators" — partial index keeps the index small.
CREATE INDEX IF NOT EXISTS idx_operators_active
    ON operators(disabled_at) WHERE disabled_at IS NULL;


-- =================================================================
-- SECTION 2: Sessions — server-side session tickets
-- =================================================================

-- -----------------------------------------------------------------
-- sessions
-- -----------------------------------------------------------------
-- Server-side session tickets. The browser holds the plaintext token
-- in a cookie; the database stores ONLY the SHA-256 digest of that
-- token in token_hash. The cookie value is never persisted server-
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
-- Last-seen IP and user-agent are forensic only. They are NOT used
-- to bind the session (no IP-pinning, no UA-pinning) because mobile
-- clients legitimately roam IPs and headless test runners change UA.

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
    last_seen_ua        TEXT,                            -- forensic, not load-bearing (truncate to 512 chars at write time)
    csrf_token          TEXT NOT NULL,                   -- 32 random bytes, base64url, 43 chars; double-submit value
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE
);

-- Hot-path lookup: presented cookie → sha256 → row. Partial index excludes
-- revoked sessions (dead weight for lookup).
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash_active
    ON sessions(token_hash) WHERE revoked_at IS NULL;

-- "All sessions for operator X" — used by logout-all-sessions and audit views.
CREATE INDEX IF NOT EXISTS idx_sessions_operator
    ON sessions(operator_id);

-- Background reaper: sweep expired (but not yet revoked) rows.
CREATE INDEX IF NOT EXISTS idx_sessions_expires
    ON sessions(expires_at) WHERE revoked_at IS NULL;


-- =================================================================
-- SECTION 3: Audit log — auth-event ownership (console.db side)
-- =================================================================

-- -----------------------------------------------------------------
-- audit_log
-- -----------------------------------------------------------------
-- Immutable append-only log of api-side state-changing events. The
-- api container writes here in the SAME transaction as the mutation
-- it records (which, for this DB, means: session issuance/revocation,
-- operator updates, WS handshake, login attempts).
--
-- Operator-initiated retention writes are SYNCHRONOUS in Stage A
-- (per spec §10 D8 / D9): the api opens a clients.db connection,
-- runs the CAS UPDATE on retention_jobs, and writes the audit row in
-- clients.audit_log in the SAME transaction. NO intent row in this
-- table for retention.
--
-- The single Stage A retained two-row pattern is /console/commands/*:
-- api writes a 'command.dispatch' intent row HERE, and whichever
-- container handles the command writes the 'command.<name>' outcome
-- row in clients.audit_log. See spec §7.2.
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
    user_agent      TEXT,                                -- truncated to 512 chars at write time
    request_id      TEXT,                                -- NULL until Stage A.5 wires X-Request-ID; correlates with clients.audit_log row
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id)  REFERENCES sessions(id)   ON DELETE RESTRICT
);

-- "Most recent audit events" — operator console default timeline view.
CREATE INDEX IF NOT EXISTS idx_console_audit_log_occurred
    ON audit_log(occurred_at DESC);

-- "All events for operator X" — partial because system rows are common
-- and would otherwise bloat this index.
CREATE INDEX IF NOT EXISTS idx_console_audit_log_operator
    ON audit_log(operator_id, occurred_at DESC) WHERE operator_id IS NOT NULL;

-- "All events for target Y" — e.g. all WS connects for a given session.
CREATE INDEX IF NOT EXISTS idx_console_audit_log_target
    ON audit_log(target_type, target_id, occurred_at DESC);

-- "All events of action Z" — e.g. all auth.login_failed across operators.
CREATE INDEX IF NOT EXISTS idx_console_audit_log_action
    ON audit_log(action, occurred_at DESC);

-- "Cross-DB correlation" — request_id is NULL until Stage A.5 wires
-- X-Request-ID middleware. Partial index keeps it small in the meantime.
CREATE INDEX IF NOT EXISTS idx_console_audit_log_request
    ON audit_log(request_id) WHERE request_id IS NOT NULL;
