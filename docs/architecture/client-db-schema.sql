-- =================================================================
-- Heimdall client management database schema
-- Database: data/clients/clients.db
-- Mode: WAL (journal_mode=WAL, synchronous=NORMAL)
-- =================================================================
--
-- This file is the authoritative schema reference.
-- Implementation code in src/client_memory/ should use these
-- CREATE TABLE statements via executescript().
--
-- Existing tables (defined elsewhere, listed for context):
--   operators, clients, client_domains, consent_records,
--   scan_history, delivery_log
--
-- This file defines the two new tables:
--   findings, brief_snapshots
--
-- See ADR-001 for design rationale:
--   docs/architecture/decisions/ADR-001-findings-and-briefs-schema.md
-- =================================================================


-- -----------------------------------------------------------------
-- findings
-- -----------------------------------------------------------------
-- One row per unique finding per domain. A finding that persists
-- across 50 consecutive scans is still one row (with bumped
-- last_seen_at and scan_count), not 50 rows.
--
-- Deduplication key: UNIQUE(domain, finding_hash)
-- finding_hash = sha256(severity_lower + ":" + normalized_desc)[:12]
-- This matches DeltaDetector.generate_finding_id() exactly.
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS findings (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_hash    TEXT    NOT NULL,
    domain          TEXT    NOT NULL,
    client_id       TEXT,

    -- Finding content
    severity        TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    risk            TEXT    NOT NULL DEFAULT '',
    cve_id          TEXT,
    plugin_slug     TEXT,

    -- Provenance
    provenance      TEXT    NOT NULL DEFAULT '',
    provenance_json TEXT,

    -- Lifecycle
    status          TEXT    NOT NULL DEFAULT 'open',
    first_seen_at   TEXT    NOT NULL,
    last_seen_at    TEXT    NOT NULL,
    resolved_at     TEXT,
    scan_count      INTEGER NOT NULL DEFAULT 1,

    -- Scan linkage
    first_scan_id   TEXT    NOT NULL,
    last_scan_id    TEXT    NOT NULL,

    -- Timestamps
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,

    -- Deduplication constraint
    UNIQUE(domain, finding_hash)
);

-- "All critical findings across all clients"
CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON findings(severity) WHERE status != 'resolved';

-- "All CVEs for a specific plugin slug"
CREATE INDEX IF NOT EXISTS idx_findings_plugin_slug
    ON findings(plugin_slug) WHERE plugin_slug IS NOT NULL;

-- "All findings by CVE ID"
CREATE INDEX IF NOT EXISTS idx_findings_cve_id
    ON findings(cve_id) WHERE cve_id IS NOT NULL;

-- "All findings for domain X over time"
CREATE INDEX IF NOT EXISTS idx_findings_domain
    ON findings(domain, last_seen_at DESC);

-- "Open findings for domain X" (delta detection hot path)
CREATE INDEX IF NOT EXISTS idx_findings_domain_status
    ON findings(domain, status);

-- "All findings with provenance=twin-derived"
CREATE INDEX IF NOT EXISTS idx_findings_provenance
    ON findings(provenance) WHERE provenance != '';

-- "All findings for client X"
CREATE INDEX IF NOT EXISTS idx_findings_client
    ON findings(client_id) WHERE client_id IS NOT NULL;

-- "All findings from scan X"
CREATE INDEX IF NOT EXISTS idx_findings_last_scan
    ON findings(last_scan_id);


-- -----------------------------------------------------------------
-- brief_snapshots
-- -----------------------------------------------------------------
-- One row per domain per scan date. Full brief JSON stored as TEXT
-- for archive/replay; key fields extracted into indexed columns
-- for cross-domain querying.
--
-- Brief JSON averages 5-15 KB. Retention policy recommended:
-- keep 90 days full JSON, then either archive or drop brief_json
-- for older rows.
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS brief_snapshots (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT    NOT NULL,
    scan_date       TEXT    NOT NULL,
    scan_id         TEXT,

    -- Extracted summary fields
    bucket          TEXT,
    cms             TEXT,
    finding_count   INTEGER NOT NULL DEFAULT 0,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    medium_count    INTEGER NOT NULL DEFAULT 0,
    plugin_count    INTEGER NOT NULL DEFAULT 0,
    gdpr_sensitive  INTEGER NOT NULL DEFAULT 0,
    has_twin_scan   INTEGER NOT NULL DEFAULT 0,
    ssl_days_remaining INTEGER,

    -- Full brief archive
    brief_json      TEXT    NOT NULL,

    -- Timestamps
    created_at      TEXT    NOT NULL,

    -- One snapshot per domain per scan date
    UNIQUE(domain, scan_date)
);

-- "All Bucket A sites with >10 findings"
CREATE INDEX IF NOT EXISTS idx_briefs_bucket_findings
    ON brief_snapshots(bucket, finding_count DESC);

-- "Brief history for domain X"
CREATE INDEX IF NOT EXISTS idx_briefs_domain_date
    ON brief_snapshots(domain, scan_date DESC);

-- "Latest briefs for date X"
CREATE INDEX IF NOT EXISTS idx_briefs_scan_date
    ON brief_snapshots(scan_date DESC);

-- "CMS distribution"
CREATE INDEX IF NOT EXISTS idx_briefs_cms
    ON brief_snapshots(cms) WHERE cms IS NOT NULL;

-- "SSL certificates expiring soon"
CREATE INDEX IF NOT EXISTS idx_briefs_ssl_expiry
    ON brief_snapshots(ssl_days_remaining)
    WHERE ssl_days_remaining IS NOT NULL AND ssl_days_remaining < 30;
