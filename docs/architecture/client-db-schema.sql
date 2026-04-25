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
-- See ADR-002 for findings normalisation rationale:
--   docs/architecture/decisions/ADR-002-findings-normalisation.md
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
    plan            TEXT,                            -- watchman | sentinel | NULL (prospect)
    status          TEXT NOT NULL DEFAULT 'prospect',
                                                     -- prospect | watchman_pending | watchman_active
                                                     -- | watchman_expired | onboarding | active
                                                     -- | paused | churned
    consent_granted INTEGER NOT NULL DEFAULT 0,     -- 0 = Layer 1 only, 1 = Layer 1 + Layer 2
    telegram_chat_id TEXT,                           -- client's Telegram chat for delivery
    contact_name    TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    contact_role    TEXT,                            -- e.g. "Owner", "IT Manager"
    preferred_channel TEXT NOT NULL DEFAULT 'telegram', -- telegram | email | whatsapp
    preferred_language TEXT NOT NULL DEFAULT 'en',  -- en | da
    technical_context TEXT,                           -- self_manages_wordpress | has_developer | hosted_platform | no_technical_resource
    has_developer   INTEGER NOT NULL DEFAULT 0,     -- 1 if client has a developer contact
    developer_contact TEXT,                          -- developer name/email/phone as free text
    scan_schedule   TEXT,                            -- weekly | daily | NULL (derived from plan)
    next_scan_date  TEXT,                            -- ISO-8601 date of next scheduled scan
    notes           TEXT,
    gdpr_sensitive  INTEGER NOT NULL DEFAULT 0,     -- 1 if company handles GDPR-sensitive data (industry + website functionality)
    gdpr_reasons    TEXT NOT NULL DEFAULT '[]',     -- JSON array of reason strings
    -- Onboarding lifecycle (added 2026-04-23 for Sentinel onboarding plan)
    trial_started_at    TEXT,                        -- ISO-8601 UTC; set at Watchman enrollment
    trial_expires_at    TEXT,                        -- trial_started_at + 30 days
    onboarding_stage    TEXT,                        -- upgrade_interest | pending_payment | pending_consent | pending_scope | provisioning | NULL when 'active'
    signup_source       TEXT,                        -- 'email_reply' | 'operator_manual'
    churn_reason        TEXT,
    churn_requested_at  TEXT,                        -- ISO-8601 UTC
    churn_purge_at      TEXT,                        -- scheduled hard-purge date (ISO-8601)
    data_retention_mode TEXT NOT NULL DEFAULT 'standard',
                                                     -- 'standard' | 'anonymised' | 'purge_scheduled' | 'purged'
    created_at      TEXT NOT NULL,                   -- ISO-8601 UTC
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_status
    ON clients(status);

CREATE INDEX IF NOT EXISTS idx_clients_industry
    ON clients(industry_code) WHERE industry_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_clients_gdpr
    ON clients(gdpr_sensitive) WHERE gdpr_sensitive = 1;


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
-- SECTION 4: Findings — normalised into definitions + occurrences
-- =================================================================
--
-- Normalisation rationale (ADR-002):
--
-- The old single `findings` table stored description, risk, cve_id,
-- severity, and plugin_slug per domain per finding. At scale,
-- "Missing HSTS header" appeared on 900 domains with identical text.
-- "Elementor CVE-2022-1329" appeared on 198 domains with identical
-- text. This caused massive row-level duplication of immutable
-- finding metadata.
--
-- The normalised design splits findings into:
--   finding_definitions  — one row per unique finding (keyed by hash)
--   finding_occurrences  — one row per (domain x finding) combination
--
-- Scale estimates (from real data):
--   ~200 unique finding definitions (CVEs + headers + SSL + plugins)
--   14,678 occurrences across 1,169 domains (Phase 0)
--   Phase 2: ~500 definitions, ~150K active occurrences
--   finding_definitions stays tiny; finding_occurrences scales linearly
-- -----------------------------------------------------------------

-- -----------------------------------------------------------------
-- finding_definitions
-- -----------------------------------------------------------------
-- One row per unique finding. The finding_hash is the dedup key,
-- computed as sha256(severity_lower + ":" + normalized_description)[:12].
-- This matches DeltaDetector.generate_finding_id() exactly.
--
-- This table contains NO per-domain data. It is a lookup table for
-- finding metadata that is shared across all domains where the
-- finding appears.

CREATE TABLE IF NOT EXISTS finding_definitions (
    finding_hash    TEXT PRIMARY KEY,               -- sha256(severity + ":" + normalized_desc)[:12]
    severity        TEXT NOT NULL,                   -- critical | high | medium | low | info
    description     TEXT NOT NULL,                   -- human-readable finding description
    risk            TEXT NOT NULL DEFAULT '',        -- risk explanation text
    cve_id          TEXT,                            -- extracted CVE ID (e.g. "CVE-2024-28000"), NULL if not a CVE
    plugin_slug     TEXT,                            -- WP plugin slug (e.g. "litespeed-cache"), NULL if not plugin-related
    provenance      TEXT,                            -- 'confirmed' | 'unconfirmed' | NULL
    category        TEXT,                            -- finding type: cve | outdated_plugin | missing_header | ssl | exposure | info
    first_seen_at   TEXT NOT NULL                    -- ISO-8601 date when first encountered globally
);

-- "All definitions for a specific plugin slug"
CREATE INDEX IF NOT EXISTS idx_finddef_plugin_slug
    ON finding_definitions(plugin_slug) WHERE plugin_slug IS NOT NULL;

-- "All definitions by CVE ID"
CREATE INDEX IF NOT EXISTS idx_finddef_cve_id
    ON finding_definitions(cve_id) WHERE cve_id IS NOT NULL;

-- "All definitions by severity"
CREATE INDEX IF NOT EXISTS idx_finddef_severity
    ON finding_definitions(severity);

-- "All definitions by category"
CREATE INDEX IF NOT EXISTS idx_finddef_category
    ON finding_definitions(category) WHERE category IS NOT NULL;

-- "All unconfirmed definitions"
CREATE INDEX IF NOT EXISTS idx_finddef_provenance
    ON finding_definitions(provenance) WHERE provenance IS NOT NULL AND provenance != '';


-- -----------------------------------------------------------------
-- finding_occurrences
-- -----------------------------------------------------------------
-- One row per (domain x finding) combination. A finding that persists
-- across 50 consecutive scans is still ONE row (with bumped
-- last_seen_at and scan_count), NOT 50 rows.
--
-- Deduplication key: UNIQUE(domain, finding_hash)
--
-- All per-domain lifecycle data lives here: status, first/last seen,
-- scan linkage, follow-up tracking.

CREATE TABLE IF NOT EXISTS finding_occurrences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    domain          TEXT NOT NULL,                   -- e.g. "jellingkro.dk"
    finding_hash    TEXT NOT NULL,                   -- FK to finding_definitions.finding_hash

    -- Confidence classification
    -- "confirmed" = version matched against known affected range
    -- "potential" = plugin detected but version unknown, CVE may or may not apply
    -- NULL = not yet classified (legacy or non-CVE findings)
    confidence      TEXT,                            -- confirmed | potential | NULL

    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'open',    -- open | sent | acknowledged | resolved
    first_seen_at   TEXT NOT NULL,                   -- ISO-8601 date of first detection on THIS domain
    last_seen_at    TEXT NOT NULL,                   -- ISO-8601 date of most recent detection on THIS domain
    resolved_at     TEXT,                            -- ISO-8601 date when status changed to resolved

    -- Scan linkage
    first_scan_id   TEXT,                            -- scan_history.scan_id that first detected this
    last_scan_id    TEXT,                            -- scan_history.scan_id that most recently detected this
    scan_count      INTEGER NOT NULL DEFAULT 1,     -- number of consecutive scans that detected this

    -- Client engagement tracking
    follow_ups_sent INTEGER NOT NULL DEFAULT 0,     -- number of follow-up messages sent about this finding
    last_follow_up  TEXT,                            -- ISO-8601 date of last follow-up

    -- Deduplication constraint
    UNIQUE(domain, finding_hash)
);

-- "All open critical findings" — joins to finding_definitions for severity
-- This covering index lets us find all open occurrences and filter by severity
-- without touching the main table for the status check.
CREATE INDEX IF NOT EXISTS idx_findocc_status
    ON finding_occurrences(status) WHERE status != 'resolved';

-- "All domains with finding X" — given a finding_hash, find all affected domains
CREATE INDEX IF NOT EXISTS idx_findocc_hash
    ON finding_occurrences(finding_hash, status);

-- "New findings since last scan for domain Y" — domain + last_seen_at for recency
CREATE INDEX IF NOT EXISTS idx_findocc_domain_lastseen
    ON finding_occurrences(domain, last_seen_at DESC);

-- "Open findings for domain X" (delta detection hot path)
CREATE INDEX IF NOT EXISTS idx_findocc_domain_status
    ON finding_occurrences(domain, status);

-- "All findings for client (by CVR)"
CREATE INDEX IF NOT EXISTS idx_findocc_cvr
    ON finding_occurrences(cvr) WHERE cvr IS NOT NULL;

-- "All findings from scan X"
CREATE INDEX IF NOT EXISTS idx_findocc_last_scan
    ON finding_occurrences(last_scan_id);

-- "All confirmed/potential findings" — confidence split queries
CREATE INDEX IF NOT EXISTS idx_findocc_confidence
    ON finding_occurrences(confidence) WHERE confidence IS NOT NULL;

-- "Finding trend over time" — first_seen_at for new-findings-per-period queries
CREATE INDEX IF NOT EXISTS idx_findocc_first_seen
    ON finding_occurrences(first_seen_at DESC);


-- -----------------------------------------------------------------
-- finding_status_log
-- -----------------------------------------------------------------
-- Audit trail of status transitions for finding occurrences.
-- The RemediationTracker appends a row on every status change,
-- preserving the full lifecycle (open → sent → acknowledged → resolved)
-- with what triggered each transition.

CREATE TABLE IF NOT EXISTS finding_status_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id   INTEGER NOT NULL,                -- FK to finding_occurrences.id
    from_status     TEXT,                            -- NULL for initial status
    to_status       TEXT NOT NULL,                   -- new status after transition
    source          TEXT NOT NULL,                   -- e.g. "scan:scan-2026-04-02-abc", "client:telegram", "operator:federico"
    created_at      TEXT NOT NULL                    -- ISO-8601 UTC timestamp
);

CREATE INDEX IF NOT EXISTS idx_status_log_occurrence
    ON finding_status_log(occurrence_id, created_at DESC);


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
    has_twin_scan   INTEGER NOT NULL DEFAULT 0,    -- 1 if twin_scan section present
    twin_finding_count INTEGER NOT NULL DEFAULT 0, -- findings where provenance = "unconfirmed"
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
    read_at         TEXT,                            -- when client read the message (from Telegram webhook)
    replied_at      TEXT,                            -- when client replied (from Telegram webhook)
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
-- computes by iterating JSON files. They operate on the normalised
-- finding_definitions + finding_occurrences tables.

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
SELECT b.bucket, COUNT(*) AS domain_count,
       SUM(b.finding_count) AS total_findings,
       SUM(b.critical_count) AS total_critical,
       SUM(COALESCE(c.gdpr_sensitive, 0)) AS gdpr_count
FROM v_current_briefs b
LEFT JOIN clients c ON b.cvr = c.cvr
GROUP BY b.bucket;

-- Severity breakdown across all open finding occurrences
-- Joins to finding_definitions to get severity.
CREATE VIEW IF NOT EXISTS v_severity_breakdown AS
SELECT fd.severity, COUNT(*) AS finding_count
FROM finding_occurrences fo
JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash
WHERE fo.status != 'resolved'
GROUP BY fd.severity;

-- Plugin vulnerability exposure (cross-domain, replaces JSON iteration)
-- Joins occurrences to definitions to get plugin_slug, severity, etc.
CREATE VIEW IF NOT EXISTS v_plugin_exposure AS
SELECT fd.plugin_slug,
       COUNT(DISTINCT fo.domain) AS affected_domains,
       COUNT(*) AS total_cves,
       SUM(CASE WHEN fd.severity = 'critical' THEN 1 ELSE 0 END) AS critical_cves,
       SUM(CASE WHEN fd.severity = 'high' THEN 1 ELSE 0 END) AS high_cves,
       SUM(CASE WHEN fo.confidence = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
       SUM(CASE WHEN fo.confidence = 'potential' THEN 1 ELSE 0 END) AS potential
FROM finding_occurrences fo
JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash
WHERE fd.plugin_slug IS NOT NULL AND fo.status != 'resolved'
GROUP BY fd.plugin_slug
ORDER BY critical_cves DESC, affected_domains DESC;

-- Top prospects: Bucket A + GDPR + most findings
CREATE VIEW IF NOT EXISTS v_top_prospects AS
SELECT b.domain, b.company_name, b.finding_count, b.critical_count, b.high_count,
       b.plugin_count, b.ssl_days_remaining, b.cms, c.gdpr_reasons
FROM v_current_briefs b
INNER JOIN clients c ON b.cvr = c.cvr
WHERE b.bucket = 'A' AND c.gdpr_sensitive = 1
ORDER BY b.critical_count DESC, b.finding_count DESC;

-- CVE cross-reference: which domains are affected by a given CVE
-- Joins occurrences to definitions for cve_id, plugin_slug, severity.
CREATE VIEW IF NOT EXISTS v_cve_domains AS
SELECT fd.cve_id, fd.plugin_slug, fd.severity, fo.confidence,
       COUNT(DISTINCT fo.domain) AS affected_domains,
       GROUP_CONCAT(DISTINCT fo.domain) AS domain_list
FROM finding_occurrences fo
JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash
WHERE fd.cve_id IS NOT NULL AND fo.status != 'resolved'
GROUP BY fd.cve_id
ORDER BY affected_domains DESC;

-- Finding trend: new findings per pipeline run
CREATE VIEW IF NOT EXISTS v_finding_trend AS
SELECT pr.run_id, pr.run_date, pr.domain_count,
       pr.finding_count, pr.critical_count, pr.high_count
FROM pipeline_runs pr
WHERE pr.status = 'completed'
ORDER BY pr.run_date DESC;

-- Denormalised finding view: joins definitions + occurrences for
-- queries that need the full picture (e.g. "all findings for domain X
-- with severity and description"). This replaces the old `findings`
-- table interface — consumers that previously queried `findings`
-- can query `v_findings` with the same column names.
CREATE VIEW IF NOT EXISTS v_findings AS
SELECT fo.id,
       fo.finding_hash,
       fo.domain,
       fo.cvr,
       fd.severity,
       fd.description,
       fd.risk,
       fd.cve_id,
       fd.plugin_slug,
       fo.confidence,
       fd.provenance,
       fd.category,
       fo.status,
       fo.first_seen_at,
       fo.last_seen_at,
       fo.resolved_at,
       fo.scan_count,
       fo.follow_ups_sent,
       fo.last_follow_up,
       fo.first_scan_id,
       fo.last_scan_id
FROM finding_occurrences fo
JOIN finding_definitions fd ON fo.finding_hash = fd.finding_hash;


-- =================================================================
-- SECTION 8: Prospects — outreach pipeline
-- =================================================================

-- -----------------------------------------------------------------
-- prospects
-- -----------------------------------------------------------------
-- One row per domain selected from the prospecting pipeline for
-- outreach. Tracks the lifecycle from pipeline output through
-- outreach to conversion (or decline).
--
-- Campaign format: MMYY-industry (e.g. "0426-restaurants").
-- The promote step writes all qualifying prospects (loose filter).
-- The interpret step filters to Critical/High at runtime via flags.

CREATE TABLE IF NOT EXISTS prospects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT NOT NULL,
    cvr             TEXT,
    company_name    TEXT,
    campaign        TEXT NOT NULL,
    bucket          TEXT,
    industry_code   TEXT,
    industry_name   TEXT,
    brief_json      TEXT NOT NULL,              -- full brief JSON (self-contained)
    finding_count   INTEGER NOT NULL DEFAULT 0,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    interpreted_json TEXT,                      -- LLM interpretation result
    interpreted_at  TEXT,
    outreach_status TEXT NOT NULL DEFAULT 'new',
    outreach_sent_at TEXT,
    delivery_id     INTEGER,                   -- FK to delivery_log.id
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(domain, campaign)
);

CREATE INDEX IF NOT EXISTS idx_prospects_campaign_status
    ON prospects(campaign, outreach_status);

CREATE INDEX IF NOT EXISTS idx_prospects_campaign_bucket
    ON prospects(campaign, bucket);

CREATE INDEX IF NOT EXISTS idx_prospects_domain
    ON prospects(domain);


-- =================================================================
-- SECTION 9: Delivery retry queue
-- =================================================================

-- -----------------------------------------------------------------
-- delivery_retry
-- -----------------------------------------------------------------
-- Catches failed interpretation/send attempts so they are not
-- permanently lost. When the delivery runner encounters a Claude API
-- or Telegram failure it inserts a row here. A background coroutine
-- polls for rows whose next_retry_at <= now() and re-attempts.
--
-- status values:
--   pending   — waiting for next retry attempt
--   succeeded — delivery succeeded on a retry; row kept for audit
--   exhausted — max attempts exceeded; manual intervention required

CREATE TABLE IF NOT EXISTS delivery_retry (
    id              INTEGER PRIMARY KEY,
    delivery_log_id INTEGER REFERENCES delivery_log(id),
    domain          TEXT NOT NULL,
    brief_path      TEXT NOT NULL,
    attempt         INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TEXT NOT NULL,
    last_error      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_delivery_retry_pending
    ON delivery_retry(status, next_retry_at);


-- =================================================================
-- SECTION 10: Sentinel-tier CT monitoring
-- =================================================================
--
-- Per-client Certificate Transparency monitoring. Polls SSLMate's
-- CertSpotter API for each Sentinel client's domains on a daily
-- schedule, compares new certs against stored snapshots, and emits
-- Telegram alerts for new certs, new SANs, and CA changes.
--
-- Watchman tier: monitoring_enabled = 0 (no polling).
-- Sentinel tier: monitoring_enabled = 1 (daily polling).
--
-- See src/client_memory/ct_monitor.py for the implementation.

-- Monitoring toggle and last-poll timestamp live on the clients row.
-- Added via ALTER TABLE in src/db/migrate.py (idempotent).
--   clients.monitoring_enabled INTEGER NOT NULL DEFAULT 0
--   clients.ct_last_polled_at  TEXT

-- -----------------------------------------------------------------
-- client_cert_snapshots
-- -----------------------------------------------------------------
-- One row per (cvr, domain, cert_sha256). The cert fingerprint dedupes
-- across polls — if the same cert appears in a later poll we UPDATE
-- last_seen_at without inserting a new row. first_seen_at is frozen at
-- initial detection.

CREATE TABLE IF NOT EXISTS client_cert_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    domain          TEXT NOT NULL,                   -- the monitored domain (may be any client_domains row)
    cert_sha256     TEXT NOT NULL,                   -- hex fingerprint, primary dedupe key
    common_name     TEXT,                            -- cert CN
    issuer_name     TEXT,                            -- e.g. "Let's Encrypt", "DigiCert"
    dns_names_json  TEXT NOT NULL DEFAULT '[]',     -- JSON array of SANs
    not_before      TEXT,                            -- ISO-8601 UTC
    not_after       TEXT,                            -- ISO-8601 UTC
    first_seen_at   TEXT NOT NULL,                   -- when we first detected this cert
    last_seen_at    TEXT NOT NULL,                   -- last poll that confirmed this cert
    UNIQUE(cvr, domain, cert_sha256)
);

CREATE INDEX IF NOT EXISTS idx_ccs_cvr_domain
    ON client_cert_snapshots(cvr, domain);


-- -----------------------------------------------------------------
-- client_cert_changes
-- -----------------------------------------------------------------
-- Audit log of detected changes. One row per change event. The
-- delivery runner subscribes to the Redis channel client-cert-change
-- and transitions status pending -> delivered -> acknowledged.
--
-- change_type values:
--   new_cert  — a cert_sha256 we have never seen before for this (cvr, domain)
--   new_san   — the new cert has SANs not present on any prior snapshot
--   ca_change — issuer_name differs from the most-recent prior snapshot
--
-- status values:
--   pending     — detected, not yet delivered
--   delivered   — Telegram message sent
--   acknowledged — client clicked the "Got it" button
--   failed      — delivery exhausted retries

CREATE TABLE IF NOT EXISTS client_cert_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    domain          TEXT NOT NULL,
    change_type     TEXT NOT NULL
        CHECK (change_type IN ('new_cert','new_san','ca_change')),
    details_json    TEXT NOT NULL,                   -- JSON blob with cert fields + diff
    detected_at     TEXT NOT NULL,                   -- when ct_monitor identified the change
    delivered_at    TEXT,                            -- when composer handed to delivery
    acknowledged_at TEXT,                            -- when client clicked Got it
    status          TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_ccc_pending
    ON client_cert_changes(status, detected_at);

CREATE INDEX IF NOT EXISTS idx_ccc_cvr
    ON client_cert_changes(cvr, detected_at);


-- Campaign performance summary
CREATE VIEW IF NOT EXISTS v_campaign_summary AS
SELECT campaign,
       COUNT(*) AS total,
       SUM(CASE WHEN outreach_status = 'new' THEN 1 ELSE 0 END) AS new_count,
       SUM(CASE WHEN outreach_status = 'interpreted' THEN 1 ELSE 0 END) AS interpreted_count,
       SUM(CASE WHEN outreach_status = 'sent' THEN 1 ELSE 0 END) AS sent_count,
       SUM(CASE WHEN outreach_status = 'failed' THEN 1 ELSE 0 END) AS failed_count
FROM prospects
GROUP BY campaign;


-- =================================================================
-- SECTION 9: Onboarding lifecycle (added 2026-04-23)
-- =================================================================
--
-- Supports the Sentinel onboarding plan: Watchman free trial →
-- Sentinel conversion → MitID Erhverv consent → Betalingsservice
-- direct debit → active paid client → offboarding/retention.
--
-- See /Users/fsaf/.claude/plans/i-need-you-to-logical-pebble.md
-- and the 2026-04-23 entry in docs/decisions/log.md.
--
-- Related columns on clients (above): trial_started_at,
-- trial_expires_at, onboarding_stage, signup_source, churn_reason,
-- churn_requested_at, churn_purge_at, data_retention_mode.

-- -----------------------------------------------------------------
-- signup_tokens
-- -----------------------------------------------------------------
-- Magic-link handshake. Issued when a prospect replies with signup
-- intent. The token is single-use, 30-min TTL, and encodes a bind
-- between the email address and the eventual Telegram chat_id on
-- /start <token>.

CREATE TABLE IF NOT EXISTS signup_tokens (
    token           TEXT PRIMARY KEY,                -- URL-safe random token
    cvr             TEXT NOT NULL,                   -- target CVR (pre-matched from prospecting)
    email           TEXT,                            -- optional; the reply-from address
    source          TEXT NOT NULL DEFAULT 'email_reply',
                                                     -- 'email_reply' | 'operator_manual'
    expires_at      TEXT NOT NULL,                   -- ISO-8601 UTC (typically created_at + 30 min)
    consumed_at     TEXT,                            -- NULL = unconsumed; set at Telegram /start
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signup_tokens_cvr
    ON signup_tokens(cvr, expires_at);


-- -----------------------------------------------------------------
-- subscriptions
-- -----------------------------------------------------------------
-- One row per Sentinel subscription. Canonical "current period"
-- source; history preserved (status transitions) rather than mutated.

CREATE TABLE IF NOT EXISTS subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    plan            TEXT NOT NULL,                   -- 'sentinel' (Watchman has no subscription row)
    status          TEXT NOT NULL,
                                                     -- 'pending_payment' | 'active' | 'past_due'
                                                     -- | 'cancelled' | 'refunded'
    started_at      TEXT NOT NULL,                   -- ISO-8601 UTC
    current_period_end TEXT,                         -- ISO-8601 UTC next billing date
    cancelled_at    TEXT,
    invoice_ref     TEXT,                            -- last invoice ref (Bogføringsloven link)
    amount_dkk      INTEGER NOT NULL,                -- periodic amount in øre (to avoid float)
    billing_period  TEXT NOT NULL DEFAULT 'monthly', -- 'monthly' | 'annual'
    mandate_id      TEXT,                            -- Betalingsservice PBS-aftale reference
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_cvr_status
    ON subscriptions(cvr, status);

CREATE INDEX IF NOT EXISTS idx_subscriptions_status_period
    ON subscriptions(status, current_period_end);


-- -----------------------------------------------------------------
-- payment_events
-- -----------------------------------------------------------------
-- Immutable append-only log of every Betalingsservice event. Used
-- both for reconciliation and for dunning (Message 9). Never update
-- or delete — refunds are recorded as new rows.

CREATE TABLE IF NOT EXISTS payment_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    subscription_id INTEGER,                         -- FK to subscriptions.id (nullable for ad-hoc)
    provider        TEXT NOT NULL DEFAULT 'betalingsservice',
                                                     -- Source of the event row. Defaults to
                                                     -- 'betalingsservice' for parity with the
                                                     -- single-provider state in D18; the column
                                                     -- is here so a later provider switch (e.g.
                                                     -- a Stripe fallback) does not break the
                                                     -- (provider, external_id, event_type)
                                                     -- idempotency contract.
    event_type      TEXT NOT NULL,
                                                     -- 'invoice_issued' | 'mandate_registered'
                                                     -- | 'payment_succeeded' | 'payment_failed'
                                                     -- | 'refund' | 'chargeback'
                                                     -- | 'mandate_cancelled'
    amount_dkk      INTEGER NOT NULL,                -- in øre
    external_id     TEXT,                            -- NETS / Betalingsservice reference
    occurred_at     TEXT NOT NULL,                   -- ISO-8601 UTC
    payload_json    TEXT,                            -- raw webhook / reconciliation payload
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payment_events_cvr_time
    ON payment_events(cvr, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_payment_events_subscription
    ON payment_events(subscription_id);

-- The partial UNIQUE index `uq_payment_events_provider_extid_eventtype`
-- on (provider, external_id, event_type) WHERE external_id IS NOT NULL
-- is created in `src/db/migrate.py` AFTER the `provider` column is added
-- to existing databases — placing it inline here would break ordering
-- on legacy DBs whose payment_events table predates the column.
-- Resolves R3 from the 2026-04-25 cloud-hosting plan.


-- -----------------------------------------------------------------
-- conversion_events
-- -----------------------------------------------------------------
-- Every touchpoint on the Watchman → Sentinel funnel. Feeds the
-- funnel dashboard view (V5) and the "stuck on X" operator views.

CREATE TABLE IF NOT EXISTS conversion_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    event_type      TEXT NOT NULL,
                                                     -- 'signup' | 'cta_click' | 'upgrade_reply'
                                                     -- | 'invoice_opened' | 'consent_opened'
                                                     -- | 'consent_signed' | 'payment_intent'
                                                     -- | 'scope_confirmed' | 'abandoned'
                                                     -- | 'cancellation'
    source          TEXT,                            -- e.g. 'email_click', 'telegram_reply', 'signup_form'
    payload_json    TEXT,                            -- optional context
    occurred_at     TEXT NOT NULL,                   -- ISO-8601 UTC
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversion_cvr_time
    ON conversion_events(cvr, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversion_type_time
    ON conversion_events(event_type, occurred_at DESC);


-- -----------------------------------------------------------------
-- onboarding_stage_log
-- -----------------------------------------------------------------
-- Audit trail for clients.onboarding_stage transitions. Mirrors the
-- finding_status_log pattern. Not load-bearing for product logic —
-- operator visibility and post-hoc debugging only.

CREATE TABLE IF NOT EXISTS onboarding_stage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    from_stage      TEXT,                            -- may be NULL (first entry into the funnel)
    to_stage        TEXT,                            -- may be NULL (exit to 'active')
    source          TEXT,                            -- 'webhook' | 'operator' | 'cron' | 'system'
    note            TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_onboarding_log_cvr
    ON onboarding_stage_log(cvr, created_at DESC);


-- -----------------------------------------------------------------
-- retention_jobs
-- -----------------------------------------------------------------
-- GDPR purge scheduler. Tiered retention (D16):
--   Watchman non-converter: anonymise at 90d, purge at 365d.
--   Sentinel cancelled:     anonymise at 30d; invoice records kept
--                           5 years (Bogføringsloven), scan data purged.
-- A cron / scheduler picks up rows where scheduled_for <= now and
-- status = 'pending', executes the action, then marks completed.

CREATE TABLE IF NOT EXISTS retention_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cvr             TEXT NOT NULL,                   -- FK to clients.cvr
    action          TEXT NOT NULL,
                                                     -- 'anonymise' | 'purge' | 'purge_bookkeeping' | 'export'
    scheduled_for   TEXT NOT NULL,                   -- ISO-8601 UTC
    claimed_at      TEXT,                            -- ISO-8601 UTC when runner took the job (status='running')
    executed_at     TEXT,                            -- NULL until run completes (success or failure)
    status          TEXT NOT NULL DEFAULT 'pending',
                                                     -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retention_pending
    ON retention_jobs(scheduled_for) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_retention_cvr
    ON retention_jobs(cvr);


-- -----------------------------------------------------------------
-- Extra indexes on clients for onboarding console views
-- -----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_clients_trial_expires
    ON clients(trial_expires_at) WHERE status = 'watchman_active';

CREATE INDEX IF NOT EXISTS idx_clients_onboarding_stage
    ON clients(onboarding_stage) WHERE onboarding_stage IS NOT NULL;
