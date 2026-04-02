-- =================================================================
-- Heimdall client management database — complete schema
-- Database: data/clients/clients.db
-- Mode: WAL (journal_mode=WAL, synchronous=NORMAL)
-- =================================================================
--
-- This file is the AUTHORITATIVE schema reference for the client
-- management database. All tables are defined here.
--
-- Implementation code in src/client_memory/ should use these
-- CREATE TABLE statements via executescript().
--
-- See ADR-001 for design rationale:
--   docs/architecture/decisions/ADR-001-findings-and-briefs-schema.md
--
-- Note: the enrichment database (data/enriched/companies.db) and
-- vulnerability cache (data/vulndb/wpvuln.db) are separate databases
-- with their own schemas. This file covers the CLIENT-SIDE schema only.
-- =================================================================

-- Enable recommended pragmas (set at connection time, not in schema):
--   PRAGMA journal_mode=WAL;
--   PRAGMA synchronous=NORMAL;
--   PRAGMA foreign_keys=ON;
--   PRAGMA cache_size=-8000;


-- =================================================================
-- SECTION 1: Identity — industries, clients, domains
-- =================================================================

-- -----------------------------------------------------------------
-- industries
-- -----------------------------------------------------------------
-- Normalised industry code lookup. Populated from
-- config/industry_codes.json. One row per Danish industry code.

CREATE TABLE IF NOT EXISTS industries (
    code    TEXT PRIMARY KEY,                       -- e.g. "561010"
    name_da TEXT NOT NULL DEFAULT '',               -- Danish name (populated later)
    name_en TEXT NOT NULL DEFAULT ''                -- English name from industry_codes.json
);


-- -----------------------------------------------------------------
-- clients
-- -----------------------------------------------------------------
-- One row per client or prospect. Prospects start with status
-- 'prospect' and graduate to 'active' on contract signing.
--
-- CVR (Central Business Register / Det Centrale Virksomhedsregister)
-- is the natural key — every Danish company has exactly one, and
-- Heimdall exclusively targets Danish companies.
--
-- Consent is binary: 0 = no consent (Layer 1 only), 1 = consent
-- granted (Layer 1 + Layer 2). The consent_records table holds the
-- audit trail (who, when, document reference).

CREATE TABLE IF NOT EXISTS clients (
    cvr             TEXT PRIMARY KEY,               -- Danish CVR number, e.g. "12345678"
    company_name    TEXT NOT NULL,
    industry_code   TEXT,                            -- FK to industries.code
    plan            TEXT,                            -- watchman | sentinel | guardian | NULL (prospect)
    status          TEXT NOT NULL DEFAULT 'prospect',-- prospect | onboarding | active | churned | paused
    consent_granted INTEGER NOT NULL DEFAULT 0,     -- 0 = Layer 1 only, 1 = Layer 1 + Layer 2
    telegram_chat_id TEXT,                           -- client's Telegram chat for delivery
    contact_name    TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,                   -- ISO-8601 UTC
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_status
    ON clients(status);

CREATE INDEX IF NOT EXISTS idx_clients_industry
    ON clients(industry_code) WHERE industry_code IS NOT NULL;


-- -----------------------------------------------------------------
-- client_domains
-- -----------------------------------------------------------------
-- A client can have multiple domains. This is the mapping table.

CREATE TABLE IF NOT EXISTS client_domains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    domain          TEXT NOT NULL,                   -- e.g. "jellingkro.dk"
    is_primary      INTEGER NOT NULL DEFAULT 1,     -- 1 = primary domain
    added_at        TEXT NOT NULL,
    UNIQUE(cvr, domain)
);

CREATE INDEX IF NOT EXISTS idx_client_domains_domain
    ON client_domains(domain);


-- =================================================================
-- SECTION 2: Consent — legal gate for scanning
-- =================================================================

-- -----------------------------------------------------------------
-- consent_records
-- -----------------------------------------------------------------
-- Audit trail for consent events. The boolean check at scan time
-- uses clients.consent_granted; this table records the history:
-- when consent was granted, by whom, under which document, and
-- any subsequent revocations or expirations.
--
-- Only Layer 2 requires consent. Layer 1 is always permitted
-- (passive, publicly available information). Therefore consent
-- is binary — granted or not — and does not need a
-- layers_permitted column.

CREATE TABLE IF NOT EXISTS consent_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr                 TEXT NOT NULL,               -- FK to clients.cvr
    authorised_domains  TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain strings
    consent_type        TEXT NOT NULL DEFAULT 'written', -- written
    consent_date        TEXT NOT NULL,               -- ISO-8601 date
    consent_expiry      TEXT NOT NULL,               -- ISO-8601 date
    consent_document    TEXT NOT NULL,               -- relative path to signed doc
    authorised_by_name  TEXT NOT NULL,
    authorised_by_role  TEXT NOT NULL,
    authorised_by_email TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active', -- active | suspended | revoked | expired
    notes               TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_consent_cvr_status
    ON consent_records(cvr, status);


-- =================================================================
-- SECTION 3: Scanning — pipeline runs, scan history
-- =================================================================

-- -----------------------------------------------------------------
-- pipeline_runs
-- -----------------------------------------------------------------
-- One row per pipeline execution. Replaces the need to iterate
-- every JSON result file for aggregate statistics. The
-- analyze_pipeline.py queries should target this table.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,               -- e.g. "run-2026-04-02-abcd1234"
    run_date        TEXT NOT NULL,                   -- ISO-8601 date
    started_at      TEXT NOT NULL,                   -- ISO-8601 UTC timestamp
    completed_at    TEXT,                            -- NULL if still running
    status          TEXT NOT NULL DEFAULT 'running', -- running | completed | failed | partial
    domain_count    INTEGER NOT NULL DEFAULT 0,     -- total domains attempted
    success_count   INTEGER NOT NULL DEFAULT 0,     -- domains that completed scanning
    error_count     INTEGER NOT NULL DEFAULT 0,     -- domains that failed
    finding_count   INTEGER NOT NULL DEFAULT 0,     -- total findings across all domains
    -- Severity rollups (aggregated at pipeline completion)
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    medium_count    INTEGER NOT NULL DEFAULT 0,
    low_count       INTEGER NOT NULL DEFAULT 0,
    info_count      INTEGER NOT NULL DEFAULT 0,
    -- Bucket distribution (aggregated at pipeline completion)
    bucket_a_count  INTEGER NOT NULL DEFAULT 0,
    bucket_b_count  INTEGER NOT NULL DEFAULT 0,
    bucket_c_count  INTEGER NOT NULL DEFAULT 0,
    bucket_d_count  INTEGER NOT NULL DEFAULT 0,
    bucket_e_count  INTEGER NOT NULL DEFAULT 0,
    -- Timing
    total_duration_ms INTEGER,                      -- wall-clock ms from start to finish
    avg_domain_ms   INTEGER,                        -- average per-domain scan time
    -- Configuration snapshot
    config_json     TEXT,                            -- filters.json + scan config at run time
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date
    ON pipeline_runs(run_date DESC);


-- -----------------------------------------------------------------
-- scan_history
-- -----------------------------------------------------------------
-- One row per domain per scan execution. Links a domain's scan
-- to a pipeline_run and stores the full raw result JSON.
-- This replaces data/results/{domain}/{date}.json.

CREATE TABLE IF NOT EXISTS scan_history (
    scan_id         TEXT PRIMARY KEY,               -- e.g. "scan-2026-04-02-678249fc"
    run_id          TEXT,                            -- FK to pipeline_runs (NULL for ad-hoc scans)
    cvr             TEXT,                            -- FK to clients (NULL for prospects)
    domain          TEXT NOT NULL,
    scan_date       TEXT NOT NULL,                   -- ISO-8601 date
    status          TEXT NOT NULL DEFAULT 'completed', -- completed | failed | skipped | timeout
    -- Timing
    total_ms        INTEGER,
    timing_json     TEXT,                            -- per-scan-type breakdown as JSON
    -- Cache performance
    cache_hits      INTEGER DEFAULT 0,
    cache_misses    INTEGER DEFAULT 0,
    -- Raw result archive (the full scan_result + brief, replaces JSON files)
    result_json     TEXT,                            -- complete scan result (raw_httpx, dns, etc.)
    -- Metadata
    error_message   TEXT,                            -- non-NULL only if status = failed
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_history_domain
    ON scan_history(domain, scan_date DESC);

CREATE INDEX IF NOT EXISTS idx_scan_history_run
    ON scan_history(run_id) WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_scan_history_date
    ON scan_history(scan_date DESC);

CREATE INDEX IF NOT EXISTS idx_scan_history_cvr
    ON scan_history(cvr) WHERE cvr IS NOT NULL;


-- =================================================================
-- SECTION 4: Findings — per-domain vulnerability tracking
-- =================================================================

-- -----------------------------------------------------------------
-- findings
-- -----------------------------------------------------------------
-- One row per unique finding per domain. A finding that persists
-- across 50 consecutive scans is still ONE row (with bumped
-- last_seen_at and scan_count), NOT 50 rows.
--
-- Deduplication key: UNIQUE(domain, finding_hash)
-- finding_hash = sha256(severity_lower + ":" + normalized_desc)[:12]
-- This matches DeltaDetector.generate_finding_id() exactly.
--
-- Scale estimate (from real data):
--   1,169 domains x 12.6 findings avg = ~14,700 active rows (Phase 0)
--   1,000 clients x 10 domains x 15 findings = ~150,000 active rows (Phase 2)
--   Resolved findings accumulate: ~500K/year at scale.
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS findings (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_hash    TEXT    NOT NULL,               -- sha256(severity + ":" + normalized_description)[:12]
    domain          TEXT    NOT NULL,               -- e.g. "jellingkro.dk"
    cvr             TEXT,                            -- FK to clients; NULL for prospects

    -- Finding content
    severity        TEXT    NOT NULL,               -- critical | high | medium | low | info
    description     TEXT    NOT NULL,               -- human-readable finding description
    risk            TEXT    NOT NULL DEFAULT '',    -- risk explanation text
    cve_id          TEXT,                            -- extracted CVE ID (e.g. "CVE-2024-28000"), NULL if not a CVE
    plugin_slug     TEXT,                            -- WP plugin slug (e.g. "litespeed-cache"), NULL if not plugin-related

    -- Confidence classification
    -- "confirmed" = version matched against known affected range
    -- "potential" = plugin detected but version unknown, CVE may or may not apply
    -- NULL = not yet classified (legacy or non-CVE findings)
    confidence      TEXT,                           -- confirmed | potential | NULL

    -- Provenance
    provenance      TEXT    NOT NULL DEFAULT '',    -- "" (Layer 1 direct) | "twin-derived"
    provenance_json TEXT,                           -- full provenance_detail as JSON TEXT

    -- Lifecycle
    status          TEXT    NOT NULL DEFAULT 'open',-- open | acknowledged | in_progress | resolved
    first_seen_at   TEXT    NOT NULL,               -- ISO-8601 date of first detection
    last_seen_at    TEXT    NOT NULL,               -- ISO-8601 date of most recent detection
    resolved_at     TEXT,                            -- ISO-8601 date when resolved
    scan_count      INTEGER NOT NULL DEFAULT 1,    -- number of scans that detected this

    -- Client engagement tracking
    follow_ups_sent INTEGER NOT NULL DEFAULT 0,    -- number of follow-up messages sent about this finding
    last_follow_up  TEXT,                            -- ISO-8601 date of last follow-up

    -- Scan linkage
    first_scan_id   TEXT    NOT NULL,               -- scan_history.scan_id that first detected this
    last_scan_id    TEXT    NOT NULL,               -- scan_history.scan_id that most recently detected this

    -- Timestamps
    created_at      TEXT    NOT NULL,               -- row creation timestamp (ISO-8601 UTC)
    updated_at      TEXT    NOT NULL,               -- last modification timestamp

    -- Deduplication constraint
    UNIQUE(domain, finding_hash)
);

-- "All critical findings across all clients"
CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON findings(severity) WHERE status != 'resolved';

-- "All CVEs for a specific plugin slug"
CREATE INDEX IF NOT EXISTS idx_findings_plugin_slug
    ON findings(plugin_slug) WHERE plugin_slug IS NOT NULL;

-- "All findings by CVE ID" — cross-domain: "which domains have CVE-2024-28000?"
CREATE INDEX IF NOT EXISTS idx_findings_cve_id
    ON findings(cve_id) WHERE cve_id IS NOT NULL;

-- "All findings for domain X over time"
CREATE INDEX IF NOT EXISTS idx_findings_domain
    ON findings(domain, last_seen_at DESC);

-- "Open findings for domain X" (delta detection hot path)
CREATE INDEX IF NOT EXISTS idx_findings_domain_status
    ON findings(domain, status);

-- "All twin-derived findings"
CREATE INDEX IF NOT EXISTS idx_findings_provenance
    ON findings(provenance) WHERE provenance != '';

-- "All findings for client (by CVR)"
CREATE INDEX IF NOT EXISTS idx_findings_cvr
    ON findings(cvr) WHERE cvr IS NOT NULL;

-- "All findings from scan X"
CREATE INDEX IF NOT EXISTS idx_findings_last_scan
    ON findings(last_scan_id);

-- "All confirmed/potential findings" — confidence split queries
CREATE INDEX IF NOT EXISTS idx_findings_confidence
    ON findings(confidence) WHERE confidence IS NOT NULL;

-- Compound: "Confirmed critical findings for plugin X" — the high-value query
CREATE INDEX IF NOT EXISTS idx_findings_plugin_severity_confidence
    ON findings(plugin_slug, severity, confidence)
    WHERE plugin_slug IS NOT NULL AND status != 'resolved';


-- =================================================================
-- SECTION 5: Briefs — versioned snapshots of per-domain analysis
-- =================================================================

-- -----------------------------------------------------------------
-- brief_snapshots
-- -----------------------------------------------------------------
-- One row per domain per scan date. Full brief JSON stored as TEXT
-- for archive/replay; key fields extracted into indexed columns
-- for cross-domain querying without parsing JSON.
--
-- Scale: 1,169 domains x 1 run/day = ~1,169 rows/day = ~427K rows/year.
-- Brief JSON averages 5-15 KB. At 427K rows x 10 KB avg = ~4.3 GB/year.
--
-- Retention policy: keep 90 days full JSON, then SET brief_json = NULL
-- for older rows (summary columns remain queryable indefinitely).
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS brief_snapshots (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT    NOT NULL,
    scan_date       TEXT    NOT NULL,               -- ISO-8601 date (YYYY-MM-DD)
    scan_id         TEXT,                            -- FK to scan_history.scan_id
    run_id          TEXT,                            -- FK to pipeline_runs.run_id

    -- Extracted summary fields (indexed for cross-domain queries)
    bucket          TEXT,                            -- A | B | C | D | E | NULL
    cms             TEXT,                            -- "WordPress" | "Joomla" | etc. | NULL
    hosting         TEXT,                            -- "LiteSpeed" | "Cloudflare" | etc. | NULL
    server          TEXT,                            -- web server string
    finding_count   INTEGER NOT NULL DEFAULT 0,    -- len(findings[])
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    medium_count    INTEGER NOT NULL DEFAULT 0,
    low_count       INTEGER NOT NULL DEFAULT 0,
    info_count      INTEGER NOT NULL DEFAULT 0,
    plugin_count    INTEGER NOT NULL DEFAULT 0,    -- len(technology.detected_plugins[])
    theme_count     INTEGER NOT NULL DEFAULT 0,    -- len(technology.detected_themes[])
    subdomain_count INTEGER NOT NULL DEFAULT 0,    -- subdomains.count
    gdpr_sensitive  INTEGER NOT NULL DEFAULT 0,    -- 1 if gdpr_sensitive = true
    gdpr_reasons    TEXT,                            -- JSON array of reason strings
    has_twin_scan   INTEGER NOT NULL DEFAULT 0,    -- 1 if twin_scan section present
    twin_finding_count INTEGER NOT NULL DEFAULT 0, -- findings where provenance = "twin-derived"
    ssl_valid       INTEGER,                        -- 1 = valid, 0 = invalid, NULL = no SSL
    ssl_issuer      TEXT,
    ssl_days_remaining INTEGER,                     -- technology.ssl.days_remaining, NULL if no SSL
    -- Agency detection (populated during brief generation)
    meta_author     TEXT,                            -- meta author tag value
    footer_credit   TEXT,                            -- footer credit text
    -- Company reference
    company_name    TEXT,
    cvr             TEXT,

    -- Full brief archive (NULLed after retention window)
    brief_json      TEXT,                            -- complete brief JSON; NULL after 90-day retention

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

-- "All GDPR-sensitive sites"
CREATE INDEX IF NOT EXISTS idx_briefs_gdpr
    ON brief_snapshots(gdpr_sensitive) WHERE gdpr_sensitive = 1;

-- "Twin-enriched sites with findings"
CREATE INDEX IF NOT EXISTS idx_briefs_twin
    ON brief_snapshots(has_twin_scan) WHERE has_twin_scan = 1;

-- Pipeline run linkage
CREATE INDEX IF NOT EXISTS idx_briefs_run
    ON brief_snapshots(run_id) WHERE run_id IS NOT NULL;


-- =================================================================
-- SECTION 6: Delivery — message log
-- =================================================================

-- -----------------------------------------------------------------
-- delivery_log
-- -----------------------------------------------------------------
-- One row per message delivered to a client via any channel.
-- Tracks what was sent, when, and whether delivery succeeded.
--
-- approved_by records who approved the message (e.g. "federico").
-- Operator configuration (Telegram chat IDs for routing) lives in
-- environment/config, not in the database.

CREATE TABLE IF NOT EXISTS delivery_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    domain          TEXT,                            -- which domain the message concerns
    channel         TEXT NOT NULL,                   -- telegram | email | whatsapp
    message_type    TEXT NOT NULL,                   -- scan_report | alert | follow_up | welcome | custom
    scan_id         TEXT,                            -- FK to scan_history (NULL for non-scan messages)
    -- Approval
    approved_by     TEXT NOT NULL DEFAULT '',        -- who approved this message, e.g. "federico"
    -- Content
    message_hash    TEXT,                            -- sha256 of message text for dedup
    message_preview TEXT,                            -- first 200 chars for log readability
    -- Delivery status
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | sent | delivered | failed | rejected
    error_message   TEXT,
    -- External IDs
    external_id     TEXT,                            -- Telegram message_id, etc.
    -- Timestamps
    sent_at         TEXT,
    delivered_at    TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delivery_cvr
    ON delivery_log(cvr, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_delivery_domain
    ON delivery_log(domain) WHERE domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_delivery_status
    ON delivery_log(status) WHERE status != 'delivered';


-- =================================================================
-- SECTION 7: Analytics views
-- =================================================================
-- These views replace the queries that analyze_pipeline.py currently
-- computes by iterating JSON files. They operate on the latest
-- pipeline run's data.

-- Latest completed pipeline run
CREATE VIEW IF NOT EXISTS v_latest_run AS
SELECT * FROM pipeline_runs
WHERE status = 'completed'
ORDER BY run_date DESC, completed_at DESC
LIMIT 1;

-- Current brief snapshot for every domain (most recent scan_date)
CREATE VIEW IF NOT EXISTS v_current_briefs AS
SELECT b.*
FROM brief_snapshots b
INNER JOIN (
    SELECT domain, MAX(scan_date) AS max_date
    FROM brief_snapshots
    GROUP BY domain
) latest ON b.domain = latest.domain AND b.scan_date = latest.max_date;

-- Bucket distribution (replaces Counter(b.get("bucket")) loop)
CREATE VIEW IF NOT EXISTS v_bucket_distribution AS
SELECT bucket, COUNT(*) AS domain_count,
       SUM(finding_count) AS total_findings,
       SUM(critical_count) AS total_critical,
       SUM(gdpr_sensitive) AS gdpr_count
FROM v_current_briefs
GROUP BY bucket;

-- Severity breakdown across all current findings
CREATE VIEW IF NOT EXISTS v_severity_breakdown AS
SELECT severity, COUNT(*) AS finding_count
FROM findings
WHERE status != 'resolved'
GROUP BY severity;

-- Plugin vulnerability exposure (cross-domain, replaces JSON iteration)
CREATE VIEW IF NOT EXISTS v_plugin_exposure AS
SELECT plugin_slug,
       COUNT(DISTINCT domain) AS affected_domains,
       COUNT(*) AS total_cves,
       SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_cves,
       SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS high_cves,
       SUM(CASE WHEN confidence = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
       SUM(CASE WHEN confidence = 'potential' THEN 1 ELSE 0 END) AS potential
FROM findings
WHERE plugin_slug IS NOT NULL AND status != 'resolved'
GROUP BY plugin_slug
ORDER BY critical_cves DESC, affected_domains DESC;

-- Top prospects: Bucket A + GDPR + most findings
CREATE VIEW IF NOT EXISTS v_top_prospects AS
SELECT domain, company_name, finding_count, critical_count, high_count,
       plugin_count, ssl_days_remaining, cms, gdpr_reasons
FROM v_current_briefs
WHERE bucket = 'A' AND gdpr_sensitive = 1
ORDER BY critical_count DESC, finding_count DESC;

-- CVE cross-reference: which domains are affected by a given CVE
CREATE VIEW IF NOT EXISTS v_cve_domains AS
SELECT cve_id, plugin_slug, severity, confidence,
       COUNT(DISTINCT domain) AS affected_domains,
       GROUP_CONCAT(DISTINCT domain) AS domain_list
FROM findings
WHERE cve_id IS NOT NULL AND status != 'resolved'
GROUP BY cve_id
ORDER BY affected_domains DESC;

-- Finding trend: new findings per pipeline run
CREATE VIEW IF NOT EXISTS v_finding_trend AS
SELECT pr.run_id, pr.run_date, pr.domain_count,
       pr.finding_count, pr.critical_count, pr.high_count
FROM pipeline_runs pr
WHERE pr.status = 'completed'
ORDER BY pr.run_date DESC;
