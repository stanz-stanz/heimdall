# ADR-001: SQLite schema for client management database

## Status
Accepted (revised 2026-04-01: CVR natural key, industry normalisation, operator removal, consent simplification; findings section superseded by ADR-002)

## Context

The initial architecture stored scan results and briefs as JSON files:

- `data/results/{client_id}/{domain}/{date}.json` -- scan results
- `data/output/briefs/{domain}.json` -- per-site technology briefs

At scale (1,000 clients x daily scans), this creates ~365K files/year with no way to query across them. A real pipeline run of 1,179 domains (14,678 findings, 12.6 avg/domain) confirmed these problems:

1. **File sprawl.** 1,169 result files + 1,169 brief files per run. `analyze_pipeline.py` reads every JSON file to produce stats.
2. **No cross-domain queries.** Answering "which domains have CVE-2024-28000?" requires reading all files and scanning every finding.
3. **No confidence classification.** Twin-derived findings have `confidence: "high-inference"` or `"medium-inference"` in their provenance, but no structured column to filter on.
4. **No pipeline run tracking.** No first-class record of "run X scanned Y domains in Z seconds."
5. **Identity tables undefined.** The original schema only defined `findings` and `brief_snapshots`, referencing "existing tables defined elsewhere" that had no authoritative SQL definition.

This revision promotes the SQL schema file to the single authoritative definition of the entire client management database.

## Decision

### Complete schema in one file

`docs/architecture/client-db-schema.sql` defines ALL tables:

| Section | Tables | Purpose |
|---------|--------|---------|
| 1. Identity | `industries`, `clients`, `client_domains` | Industry lookup, clients (keyed by CVR), domain mapping |
| 2. Consent | `consent_records` | Audit trail for consent events |
| 3. Scanning | `pipeline_runs`, `scan_history` | Run-level and domain-level scan tracking |
| 4. Findings | `finding_definitions`, `finding_occurrences` | Normalised finding definitions + per-domain occurrence tracking (see ADR-002) |
| 5. Briefs | `brief_snapshots` | Versioned brief archive with extracted summary columns |
| 6. Delivery | `delivery_log` | Message delivery tracking |
| 7. Views | `v_current_briefs`, `v_bucket_distribution`, etc. | Pre-built analytics views |

### Key changes from initial proposal

**1. `pipeline_runs` table (new)**

One row per pipeline execution. Stores aggregate counts (domains, findings, severity breakdown, bucket distribution, timing) so that `analyze_pipeline.py` can produce its full report from a single row instead of iterating files.

**2. `scan_history` gains `result_json` column**

The DB is the primary storage. The full scan result JSON (including `raw_httpx`, `dns_records`, `ct_certificates`, etc.) is stored in `scan_history.result_json`. JSON files become a transitional artifact during migration, not the source of truth.

**3. `findings` gains `confidence` column**

```
confidence TEXT  -- confirmed | potential | NULL
```

- **confirmed**: the installed version is within the CVE's affected range (version-matched).
- **potential**: the plugin is detected but version is unknown, or the version could not be matched against the affected range.
- **NULL**: not yet classified, or not a CVE finding (e.g., missing-header findings).

The confidence split is already present in the pipeline data as `provenance_detail.confidence` (`"high-inference"` / `"medium-inference"`). The mapping is: `high-inference` -> `confirmed`, `medium-inference` -> `potential`.

A compound index `idx_findings_plugin_severity_confidence` supports the high-value query: "confirmed critical findings for plugin X across all domains."

**4. `findings` gains engagement tracking columns**

```
follow_ups_sent  INTEGER NOT NULL DEFAULT 0
last_follow_up   TEXT
```

These match the existing `FindingRecord` dataclass fields that were missing from the original schema.

**5. `brief_snapshots` expanded with more extracted columns**

Added columns extracted from real brief data that `analyze_pipeline.py` currently computes by parsing JSON:

- `hosting`, `server` -- infrastructure detection
- `low_count`, `info_count` -- full severity breakdown (was missing low + info)
- `theme_count`, `subdomain_count` -- additional brief fields
- `gdpr_reasons` (JSON array) -- specific GDPR trigger reasons
- `twin_finding_count` -- count of unconfirmed findings (was only has_twin_scan boolean)
- `ssl_valid`, `ssl_issuer` -- full SSL status (was only days_remaining)
- `meta_author`, `footer_credit` -- agency detection fields
- `company_name`, `cvr` -- company reference
- `run_id` -- link to pipeline run

The `brief_json` column retention policy is explicit: after 90 days, set to NULL. Summary columns remain queryable indefinitely.

**6. Identity and consent tables defined**

`industries`, `clients`, `client_domains`, `consent_records`, `delivery_log` are now fully defined with columns, indexes, and constraints. No more "defined elsewhere" references.

**7. Analytics views**

Seven views replace the Python loops in `analyze_pipeline.py`:

- `v_latest_run` -- most recent completed pipeline run
- `v_current_briefs` -- latest brief for every domain
- `v_bucket_distribution` -- bucket counts with finding/GDPR aggregates
- `v_severity_breakdown` -- finding severity counts
- `v_plugin_exposure` -- plugin vulnerability cross-domain analysis
- `v_top_prospects` -- Bucket A + GDPR sorted by severity
- `v_cve_domains` -- which domains share a given CVE
- `v_finding_trend` -- findings per pipeline run over time

### Revision: 2026-04-01 — Schema normalisation

Four structural corrections applied after review:

**R1. CVR as natural primary key**

Removed the synthetic `client_id TEXT PRIMARY KEY` from `clients`. CVR (Danish company registration number) is unique per company and is now the primary key: `cvr TEXT PRIMARY KEY`. All foreign keys across `client_domains`, `consent_records`, `scan_history`, `findings`, and `delivery_log` now reference `cvr` instead of `client_id`. The separate `idx_clients_cvr` index was dropped (redundant with PK). Index `idx_scan_history_client` renamed to `idx_scan_history_cvr`; `idx_findings_client` renamed to `idx_findings_cvr`; `idx_delivery_client` renamed to `idx_delivery_cvr`.

**R2. Industry data normalised**

Removed `industry_name` from `clients`. Added an `industries` table (`code TEXT PRIMARY KEY`, `name_da TEXT`, `name_en TEXT`) populated from `config/industry_codes.json`. The `clients.industry_code` column serves as a foreign key reference. Added `idx_clients_industry` partial index.

**R3. Operators table removed**

Removed the `operators` table entirely. Operator configuration (Federico's Telegram chat ID for approval routing) belongs in environment/config, not in the database. Removed `operator_id` from `clients` and its index `idx_clients_operator`. In `delivery_log`, replaced `operator_id` FK with `approved_by TEXT NOT NULL DEFAULT ''` -- a simple text field recording who approved the message, with no foreign key constraint.

**R4. Consent simplified — binary model**

Removed `layers_permitted TEXT` from `consent_records`. Only Layer 2 requires consent; Layer 1 is always permitted (passive, publicly available information). Consent is therefore binary. Added `consent_granted INTEGER NOT NULL DEFAULT 0` to the `clients` table for the fast boolean check at scan time. The `consent_records` table remains as the audit trail (who granted consent, when, under which document, domain scope, expiry, revocation).

### Finding deduplication strategy (unchanged)

A finding is "the same" if it appears on the same domain with the same `finding_hash`. The hash is `sha256(severity_lower + ":" + normalized_description)[:12]`, which is exactly what `DeltaDetector.generate_finding_id()` already computes.

The `UNIQUE(domain, finding_hash)` constraint enforces this at the database level. The upsert pattern:

```sql
INSERT INTO findings (
    finding_hash, domain, cvr,
    severity, description, risk, cve_id, plugin_slug,
    confidence, provenance, provenance_json,
    status, first_seen_at, last_seen_at,
    first_scan_id, last_scan_id, scan_count,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(domain, finding_hash) DO UPDATE SET
    last_seen_at  = excluded.last_seen_at,
    last_scan_id  = excluded.last_scan_id,
    scan_count    = scan_count + 1,
    updated_at    = excluded.updated_at,
    -- Preserve status (may have been acknowledged/in_progress)
    -- Preserve first_seen_at and first_scan_id
    -- Update risk/description if they changed (version text may update)
    risk          = excluded.risk,
    description   = excluded.description,
    -- Update confidence if the new value is more specific
    confidence    = COALESCE(excluded.confidence, findings.confidence);
```

**CVE cross-domain efficiency:** With 1,252 Elementor CVE findings across 200 domains, the same CVE (e.g., CVE-2024-28000) appears as separate rows in `findings` (one per domain). Cross-domain queries use the `idx_findings_cve_id` index:

```sql
-- "Which domains are affected by CVE-2024-28000?"
SELECT domain, confidence, severity FROM findings
WHERE cve_id = 'CVE-2024-28000' AND status != 'resolved';
-- Uses idx_findings_cve_id, returns ~N rows (one per affected domain)
```

This is efficient because the index is partial (only rows where `cve_id IS NOT NULL`), keeping it small relative to total findings.

### Delta detection against `findings` table (unchanged)

The algorithm remains the same as the original ADR: compute set differences using the `idx_findings_domain_status` index. See the schema SQL file for the complete index set.

### Operational events decision

Federico's concern #5: whether the DB needs an `operational_events` table for loguru migration. **Decision: no.** Operational logs (scan started, tool invoked, error encountered) belong in structured log files, not in the client management database. Reasons:

1. Log volume is orders of magnitude higher than finding volume. A single scan produces ~50 log lines but ~12 findings. Mixing them inflates the DB.
2. Loguru writes to files with rotation built in. No benefit to duplicating in SQLite.
3. The `pipeline_runs` table captures the aggregate operational data (timing, counts, errors) that is actually queried. Individual log lines are for debugging, not analytics.

If a future need arises for queryable operational events (e.g., "which scans hit rate limits this week"), a separate `data/logs/events.db` is the right approach -- not a table in the client management DB.

## Consequences

**Benefits:**
- Single authoritative SQL file for the entire client management schema
- Cross-domain queries are SQL (no file iteration): plugin exposure, CVE cross-reference, severity breakdown, bucket distribution
- Confidence classification is a first-class indexed column, ready for the confirmed/potential split
- Pipeline runs are tracked as structured data, replacing JSON file aggregation
- `scan_history.result_json` makes the DB the primary storage, not an index alongside files
- Analytics views replace custom Python aggregation code in `analyze_pipeline.py`
- Delta detection performance unchanged: O(1) indexed query per domain

**Trade-offs:**
- `scan_history.result_json` stores 5-20 KB per domain per scan. At 1,169 domains/day = ~15 MB/day = ~5.5 GB/year. Combined with `brief_snapshots.brief_json` (~4.3 GB/year), total is ~10 GB/year. Retention policy (90 days for `brief_json`, configurable for `result_json`) keeps the hot DB under 3 GB.
- Seven analytics views add schema complexity. They are read-only and zero-cost until queried (SQLite views are not materialized).
- Migration path: both JSON and SQLite paths must coexist until all consumers (pipeline, API, console) are updated.
- The `provenance_json` column stores denormalized JSON -- intentional, as the structure varies by scan tool.
- CVR as PK means non-Danish companies cannot be stored. This is acceptable: Heimdall exclusively targets Danish companies (all have a CVR).
- Removing `operators` means multi-operator routing must be handled in config/environment if needed later. Current scale (single operator) does not require a DB table.

**Index budget (Pi5 RAM consideration):**
- `findings`: 10 indexes, many partial. At 150K active rows + 500K resolved rows/year, estimated index overhead: ~80 MB at 1M total rows.
- `brief_snapshots`: 8 indexes. At 427K rows/year, estimated: ~40 MB at 500K rows.
- `scan_history`: 4 indexes. At 427K rows/year, estimated: ~30 MB.
- `pipeline_runs`: 1 index. Negligible (365 rows/year).
- Total additional SQLite overhead: ~150 MB at steady state (1 year). Within the 8GB Pi5 budget.
