# ADR-001: SQLite schema for findings and brief snapshots

## Status
Proposed

## Context

The current architecture stores scan results and briefs as JSON files:

- `data/results/{client_id}/{domain}/{date}.json` -- scan results
- `data/output/briefs/{domain}.json` -- per-site technology briefs

At scale (1,000 clients x daily scans), this creates ~365K files/year with no way to query across them. Answering "show all domains with critical findings" requires reading every file. Delta detection (`src/client_memory/delta.py`) currently compares in-memory lists loaded from JSON -- it works, but couples finding history to a single client's JSON blob instead of a queryable store.

This ADR adds two tables (`findings` and `brief_snapshots`) to the existing client management schema in `data/clients/clients.db` (which already defines `operators`, `clients`, `client_domains`, `consent_records`, `scan_history`, `delivery_log`).

## Decision

### Table: `findings`

```sql
-- =================================================================
-- findings — every individual finding from every scan
-- =================================================================
-- Design: one row per unique finding per domain. NOT one row per scan
-- occurrence. A finding that persists across 50 scans is still one
-- row with updated last_seen_at and scan_count.  New row only when
-- the dedup key (domain + finding_hash) has no existing open match.
--
-- At 1,179 domains x ~5 unique findings avg = ~6,000 active rows.
-- At 1,000 clients x ~10 domains avg x ~8 findings = ~80,000 active rows.
-- Resolved findings accumulate but are rarely queried hot-path.
-- =================================================================

CREATE TABLE IF NOT EXISTS findings (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_hash    TEXT    NOT NULL,           -- sha256(severity + normalized_description)[:12], matches DeltaDetector.generate_finding_id()
    domain          TEXT    NOT NULL,           -- e.g. "jellingkro.dk"
    client_id       TEXT,                       -- NULL for prospects (pre-onboarding pipeline)

    -- Finding content
    severity        TEXT    NOT NULL,           -- critical | high | medium | low | info
    description     TEXT    NOT NULL,           -- human-readable finding description
    risk            TEXT    NOT NULL DEFAULT '',-- risk explanation
    cve_id          TEXT,                       -- extracted CVE ID if present (e.g. "CVE-2024-28000"), NULL otherwise
    plugin_slug     TEXT,                       -- extracted plugin slug if present (e.g. "litespeed-cache"), NULL otherwise

    -- Provenance
    provenance      TEXT    NOT NULL DEFAULT '',-- "" (Layer 1 direct) | "twin-derived"
    provenance_json TEXT,                       -- full provenance_detail as JSON TEXT, NULL if no provenance

    -- Lifecycle
    status          TEXT    NOT NULL DEFAULT 'open',  -- open | acknowledged | in_progress | completed | verified | resolved
    first_seen_at   TEXT    NOT NULL,           -- ISO-8601 date of first detection
    last_seen_at    TEXT    NOT NULL,           -- ISO-8601 date of most recent detection
    resolved_at     TEXT,                       -- ISO-8601 date when status became "resolved"
    scan_count      INTEGER NOT NULL DEFAULT 1, -- number of scans that detected this finding

    -- Scan linkage
    first_scan_id   TEXT    NOT NULL,           -- scan_history.scan_id that first detected this
    last_scan_id    TEXT    NOT NULL,           -- scan_history.scan_id that most recently detected this

    -- Timestamps
    created_at      TEXT    NOT NULL,           -- row creation timestamp (ISO-8601 UTC)
    updated_at      TEXT    NOT NULL,           -- last modification timestamp

    -- Deduplication constraint: same finding on same domain = same row
    UNIQUE(domain, finding_hash)
);

-- Primary query: "all critical findings across all clients"
CREATE INDEX IF NOT EXISTS idx_findings_severity
    ON findings(severity) WHERE status != 'resolved';

-- "all CVEs for a specific plugin slug"
CREATE INDEX IF NOT EXISTS idx_findings_plugin_slug
    ON findings(plugin_slug) WHERE plugin_slug IS NOT NULL;

-- "all CVEs by CVE ID"
CREATE INDEX IF NOT EXISTS idx_findings_cve_id
    ON findings(cve_id) WHERE cve_id IS NOT NULL;

-- "all findings for domain X over time"
CREATE INDEX IF NOT EXISTS idx_findings_domain
    ON findings(domain, last_seen_at DESC);

-- "new findings since last scan" (delta detection)
CREATE INDEX IF NOT EXISTS idx_findings_domain_status
    ON findings(domain, status);

-- "all findings with provenance=twin-derived"
CREATE INDEX IF NOT EXISTS idx_findings_provenance
    ON findings(provenance) WHERE provenance != '';

-- Client lookup (for onboarded clients)
CREATE INDEX IF NOT EXISTS idx_findings_client
    ON findings(client_id) WHERE client_id IS NOT NULL;

-- Scan linkage for "findings from scan X"
CREATE INDEX IF NOT EXISTS idx_findings_last_scan
    ON findings(last_scan_id);
```

### Table: `brief_snapshots`

```sql
-- =================================================================
-- brief_snapshots — versioned brief storage, one row per domain per scan
-- =================================================================
-- The full brief JSON is stored as TEXT for archive/replay. Key fields
-- are extracted into indexed columns for cross-domain querying.
--
-- At 1,179 domains x 1 run/day = ~1,179 rows/day = ~430K rows/year.
-- Brief JSON averages ~5-15KB. At 430K rows x 10KB avg = ~4.3GB/year.
-- Consider a retention policy (e.g., keep 90 days detail, archive older).
-- =================================================================

CREATE TABLE IF NOT EXISTS brief_snapshots (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT    NOT NULL,           -- e.g. "jellingkro.dk"
    scan_date       TEXT    NOT NULL,           -- ISO-8601 date (YYYY-MM-DD)
    scan_id         TEXT,                       -- FK to scan_history.scan_id (NULL for prospect pipeline runs)

    -- Extracted summary fields (indexed for queries)
    bucket          TEXT,                       -- A | B | C | D | E | NULL
    cms             TEXT,                       -- "WordPress" | "Joomla" | etc. | NULL
    finding_count   INTEGER NOT NULL DEFAULT 0, -- len(findings[])
    critical_count  INTEGER NOT NULL DEFAULT 0, -- findings where severity = "critical"
    high_count      INTEGER NOT NULL DEFAULT 0, -- findings where severity = "high"
    medium_count    INTEGER NOT NULL DEFAULT 0, -- findings where severity = "medium"
    plugin_count    INTEGER NOT NULL DEFAULT 0, -- len(technology.detected_plugins[])
    gdpr_sensitive  INTEGER NOT NULL DEFAULT 0, -- 1 if gdpr_sensitive = true
    has_twin_scan   INTEGER NOT NULL DEFAULT 0, -- 1 if twin_scan section present
    ssl_days_remaining INTEGER,                 -- technology.ssl.days_remaining, NULL if no SSL data

    -- Full brief archive
    brief_json      TEXT    NOT NULL,           -- complete brief JSON (not indexed)

    -- Timestamps
    created_at      TEXT    NOT NULL,           -- row creation timestamp (ISO-8601 UTC)

    -- One snapshot per domain per scan date
    UNIQUE(domain, scan_date)
);

-- "all Bucket A sites with >10 findings"
CREATE INDEX IF NOT EXISTS idx_briefs_bucket_findings
    ON brief_snapshots(bucket, finding_count DESC);

-- "brief history for jellingkro.dk"
CREATE INDEX IF NOT EXISTS idx_briefs_domain_date
    ON brief_snapshots(domain, scan_date DESC);

-- "sites where finding count changed" — compare consecutive rows by domain
CREATE INDEX IF NOT EXISTS idx_briefs_scan_date
    ON brief_snapshots(scan_date DESC);

-- CMS distribution queries
CREATE INDEX IF NOT EXISTS idx_briefs_cms
    ON brief_snapshots(cms) WHERE cms IS NOT NULL;

-- SSL expiry monitoring
CREATE INDEX IF NOT EXISTS idx_briefs_ssl_expiry
    ON brief_snapshots(ssl_days_remaining) WHERE ssl_days_remaining IS NOT NULL AND ssl_days_remaining < 30;
```

### Finding deduplication strategy

A finding is "the same" if it appears on the same domain with the same `finding_hash`. The hash is `sha256(severity_lower + ":" + normalized_description)[:12]`, which is exactly what `DeltaDetector.generate_finding_id()` already computes.

The `UNIQUE(domain, finding_hash)` constraint enforces this at the database level. When a scan produces findings:

1. For each finding, compute `finding_hash` using the existing `DeltaDetector.generate_finding_id()`.
2. Attempt `INSERT OR IGNORE` -- if the row already exists (same domain + hash), the insert is a no-op.
3. For existing findings, run an `UPDATE` to bump `last_seen_at`, `last_scan_id`, and `scan_count`.
4. This is expressed as a single **upsert** using SQLite's `INSERT ... ON CONFLICT` syntax:

```sql
INSERT INTO findings (
    finding_hash, domain, client_id,
    severity, description, risk, cve_id, plugin_slug,
    provenance, provenance_json,
    status, first_seen_at, last_seen_at,
    first_scan_id, last_scan_id, scan_count,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(domain, finding_hash) DO UPDATE SET
    last_seen_at  = excluded.last_seen_at,
    last_scan_id  = excluded.last_scan_id,
    scan_count    = scan_count + 1,
    updated_at    = excluded.updated_at,
    -- Do NOT overwrite status (may have been acknowledged/in_progress)
    -- Do NOT overwrite first_seen_at or first_scan_id
    -- DO overwrite risk/description if they changed (version text may update)
    risk          = excluded.risk,
    description   = excluded.description;
```

**CVE ID extraction:** Findings with a CVE reference contain it in the description (e.g., `"... (CVE-2024-28000)"`) or in `provenance_detail.template_id`. The ingestion code extracts it with a regex: `r'(CVE-\d{4}-\d{4,7})'`.

**Plugin slug extraction:** For twin-derived findings, `provenance_detail.twin_scan_tool` is `"wpvulnerability"` and the description contains the slug in brackets: `"LiteSpeed Cache [litespeed-cache] < 6.4"`. Extract with: `r'\[([a-z0-9-]+)\]'`.

### Delta detection against `findings` table

The existing `DeltaDetector.detect_delta()` takes two lists (previous `FindingRecord` objects, current finding dicts) and returns a `DeltaResult` with `new`, `recurring`, `resolved` lists. With the database, delta detection becomes a set of SQL queries instead of in-memory list comparison.

**Algorithm (per domain, per scan):**

```
1. Compute finding_hash for each finding in the current scan.

2. NEW findings:
   SELECT from current scan hashes WHERE NOT EXISTS in findings table
   for this domain with status != 'resolved'.

   SQL:
   -- Given a list of current hashes, find which are not in the DB
   SELECT ? AS finding_hash
   WHERE ? NOT IN (
       SELECT finding_hash FROM findings
       WHERE domain = ? AND status != 'resolved'
   )

   Practically: query all open finding_hashes for the domain into a set,
   then compute set difference in Python. The DB query is:

   SELECT finding_hash FROM findings
   WHERE domain = :domain AND status != 'resolved';

   new_hashes = current_hashes - existing_hashes

3. RECURRING findings:
   recurring_hashes = current_hashes & existing_hashes

   For these, run the upsert (bump last_seen_at, scan_count).

4. RESOLVED findings:
   resolved_hashes = existing_hashes - current_hashes

   For these:
   UPDATE findings
   SET status = 'resolved', resolved_at = :now, updated_at = :now
   WHERE domain = :domain AND finding_hash IN (:resolved_hashes)
     AND status != 'resolved';

5. Fuzzy matching:
   The existing DeltaDetector has a fuzzy fallback (SequenceMatcher,
   threshold 0.85) for findings whose description changed slightly
   between scans (e.g., version number updated). This still runs in
   Python after step 2 -- any hash in new_hashes that fuzzy-matches
   an existing finding gets reclassified as recurring and the existing
   row is updated (possibly with a new description/risk).
```

**Performance:** For a single domain, step 2 loads ~5-20 hashes (the open findings set). This is a single indexed query on `(domain, status)`. The entire delta detection per domain touches at most ~50 rows. At 1,179 domains per pipeline run, that is ~60,000 row reads -- well within SQLite's capability in a single transaction.

**Migration from JSON-based history:**

The existing `ClientHistory.record_scan()` writes to `{client_id}/history.json`. The migration path:

1. Add a `ClientHistoryDB` class in `src/client_memory/` that implements the same interface but writes to SQLite.
2. The constructor accepts a `sqlite3.Connection` instead of an `AtomicFileStore`.
3. `record_scan()` runs the upsert logic above instead of JSON read-modify-write.
4. `get_open_findings()` becomes `SELECT * FROM findings WHERE domain = ? AND status != 'resolved'`.
5. `get_stale_findings()` becomes `SELECT * FROM findings WHERE domain = ? AND status != 'resolved' AND first_seen_at < date('now', '-14 days')`.
6. The existing `DeltaDetector` class is kept for its `generate_finding_id()` and fuzzy matching logic. Only the storage layer changes.
7. The `AtomicFileStore`-based `ClientHistory` remains available for fallback/migration period.

**Cross-domain queries that were impossible with JSON files:**

```sql
-- All critical findings across all clients (dashboard)
SELECT f.domain, f.description, f.cve_id, f.first_seen_at
FROM findings f
WHERE f.severity = 'critical' AND f.status != 'resolved'
ORDER BY f.first_seen_at DESC;

-- All CVEs affecting a specific plugin (e.g., after a new CVE drops)
SELECT DISTINCT f.domain, f.description, f.cve_id
FROM findings f
WHERE f.plugin_slug = 'litespeed-cache' AND f.status != 'resolved';

-- Domains with the most unresolved findings (prioritization)
SELECT domain, COUNT(*) as open_count,
       SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical,
       SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high
FROM findings
WHERE status != 'resolved'
GROUP BY domain
ORDER BY critical DESC, high DESC, open_count DESC;

-- Finding trend: new findings per week
SELECT strftime('%Y-W%W', first_seen_at) as week,
       COUNT(*) as new_findings
FROM findings
GROUP BY week
ORDER BY week DESC;

-- Brief comparison: sites where finding count increased
SELECT curr.domain, curr.finding_count, prev.finding_count,
       (curr.finding_count - prev.finding_count) as delta
FROM brief_snapshots curr
JOIN brief_snapshots prev
    ON curr.domain = prev.domain
    AND prev.scan_date = (
        SELECT MAX(scan_date) FROM brief_snapshots
        WHERE domain = curr.domain AND scan_date < curr.scan_date
    )
WHERE curr.scan_date = :today
    AND curr.finding_count > prev.finding_count
ORDER BY delta DESC;

-- All Bucket A sites with >10 findings
SELECT domain, finding_count, critical_count, high_count
FROM brief_snapshots
WHERE bucket = 'A' AND finding_count > 10
    AND scan_date = :today
ORDER BY critical_count DESC, finding_count DESC;
```

## Consequences

**Benefits:**
- Cross-domain queries become trivial (currently impossible without reading every JSON file)
- Delta detection is O(1) per domain instead of O(n) file reads
- Finding deduplication is enforced at the database level, not just in Python logic
- Brief history is queryable without loading 15KB JSON blobs
- Pipeline analytics (finding trends, bucket distribution over time) become SQL queries
- Single WAL-mode SQLite file is simpler to back up than thousands of JSON files

**Trade-offs:**
- Brief JSON storage grows ~4.3GB/year at full scale -- needs a retention policy (e.g., keep 90 days of full JSON, then drop `brief_json` column for older rows or archive to a separate cold-storage DB)
- The `findings` table updates on every scan (upserts), adding write load. WAL mode handles concurrent reads well, but the pipeline should batch upserts in a single transaction per domain
- Fuzzy matching still requires Python (SequenceMatcher) -- cannot be pushed to SQL
- Migration period: both JSON and SQLite paths must coexist until all consumers are updated
- The `provenance_json` column stores denormalized JSON -- this is intentional (the structure varies by scan tool, and we never need to query inside it)

**Index budget (Pi5 RAM consideration):**
- `findings`: 8 indexes on a table that grows to ~80K active rows + ~1.7M resolved rows/year. Partial indexes (WHERE clauses) keep the hot set small. Estimated index overhead: ~50MB at 1M rows.
- `brief_snapshots`: 5 indexes on a table that grows ~430K rows/year. The `brief_json` column is not indexed. Estimated index overhead: ~30MB at 500K rows.
- Total additional SQLite overhead: ~80MB at steady state. Well within the 8GB Pi5 budget (current SQLite DBs for enrichment + vulndb + CT use ~200MB combined).
