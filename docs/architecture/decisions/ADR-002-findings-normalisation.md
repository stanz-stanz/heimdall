# ADR-002: Normalise findings into definitions + occurrences

## Status
Accepted

## Context

The original `findings` table (ADR-001) stored one row per (domain x finding) with the full finding metadata inlined: `description`, `risk`, `cve_id`, `severity`, `plugin_slug`, `provenance`, and `provenance_json`. This worked at low scale but caused massive duplication at real pipeline volumes.

Real data from the lead generation pipeline (1,169 domains, 14,678 findings):

| Finding | Occurrences | Unique definitions |
|---------|------------:|-----------------:|
| "Missing HSTS header" | 900 | 1 |
| "Elementor CVE-2022-1329" | 198 | 1 |
| All CVE + header + SSL + plugin findings | 14,678 | ~200 |

Every occurrence row duplicated 5-7 columns of immutable text. At Phase 2 scale (150K active occurrences), the description and risk columns alone would consume ~50 MB of redundant text storage. Updates to finding metadata (e.g., improved risk explanations) would require updating every occurrence row instead of a single definition.

## Decision

Split the `findings` table into two normalised tables:

### `finding_definitions` -- one row per unique finding

Keyed by `finding_hash` (sha256 of severity + normalized description, matching `DeltaDetector.generate_finding_id()`). Contains all immutable finding metadata:

- `finding_hash TEXT PRIMARY KEY`
- `severity`, `description`, `risk`, `cve_id`, `plugin_slug`
- `provenance` -- 'unconfirmed' or 'confirmed' or NULL
- `category` -- finding type classification: cve, outdated_plugin, missing_header, ssl, exposure, info
- `first_seen_at` -- global first encounter date

No per-domain data. At current scale: ~200 rows. At Phase 2: ~500 rows. This table stays tiny.

### `finding_occurrences` -- one row per (domain x finding)

Contains all per-domain lifecycle data:

- `cvr`, `domain`, `finding_hash` (FK to definitions)
- `confidence` -- confirmed / potential / NULL
- `status`, `first_seen_at`, `last_seen_at`, `resolved_at`
- `first_scan_id`, `last_scan_id`, `scan_count`
- `follow_ups_sent`, `last_follow_up`
- `UNIQUE(domain, finding_hash)` dedup constraint

### Changes from the old `findings` table

1. **Removed from occurrences (moved to definitions):** `severity`, `description`, `risk`, `cve_id`, `plugin_slug`, `provenance`, `provenance_json`
2. **Removed entirely:** `provenance_json` -- the full provenance detail JSON was only needed during brief generation, not for finding lifecycle tracking. If needed, it can be retrieved from `scan_history.result_json`.
3. **Removed from occurrences:** `created_at`, `updated_at` -- these were tracking row mutation timestamps, which are unnecessary with the normalised lifecycle columns (`first_seen_at`, `last_seen_at`, `resolved_at`)
4. **Added to definitions:** `category TEXT` -- finding type classification for filtering without parsing description text
5. **Added to definitions:** `first_seen_at` -- global first encounter (vs. per-domain first encounter in occurrences)

### Backward compatibility: `v_findings` view

A denormalised view `v_findings` joins definitions and occurrences to present the same column interface as the old `findings` table. Consumers that previously queried `findings` can query `v_findings` with minimal changes.

### Index strategy

**`finding_definitions` (5 indexes):**
- `idx_finddef_plugin_slug` -- partial, plugin_slug IS NOT NULL
- `idx_finddef_cve_id` -- partial, cve_id IS NOT NULL
- `idx_finddef_severity` -- for severity-filtered joins
- `idx_finddef_category` -- partial, category IS NOT NULL
- `idx_finddef_provenance` -- partial, unconfirmed only

**`finding_occurrences` (8 indexes):**
- `idx_findocc_status` -- partial, status != 'resolved' (all open findings)
- `idx_findocc_hash` -- (finding_hash, status) for "all domains with finding X"
- `idx_findocc_domain_lastseen` -- (domain, last_seen_at DESC) for recency queries
- `idx_findocc_domain_status` -- (domain, status) for delta detection hot path
- `idx_findocc_cvr` -- partial, cvr IS NOT NULL
- `idx_findocc_last_scan` -- last_scan_id for scan linkage
- `idx_findocc_confidence` -- partial, confidence IS NOT NULL
- `idx_findocc_first_seen` -- first_seen_at DESC for new-findings-per-period

### Upsert pattern

**Definitions:** INSERT OR IGNORE (definitions are immutable once created, except risk text which may be improved):

```sql
INSERT INTO finding_definitions (
    finding_hash, severity, description, risk, cve_id, plugin_slug,
    provenance, category, first_seen_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(finding_hash) DO UPDATE SET
    risk = CASE WHEN length(excluded.risk) > length(finding_definitions.risk)
           THEN excluded.risk ELSE finding_definitions.risk END;
```

**Occurrences:** Upsert on (domain, finding_hash):

```sql
INSERT INTO finding_occurrences (
    cvr, domain, finding_hash, confidence, status,
    first_seen_at, last_seen_at, first_scan_id, last_scan_id, scan_count
) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, 1)
ON CONFLICT(domain, finding_hash) DO UPDATE SET
    last_seen_at  = excluded.last_seen_at,
    last_scan_id  = excluded.last_scan_id,
    scan_count    = scan_count + 1,
    confidence    = COALESCE(excluded.confidence, finding_occurrences.confidence);
```

## Consequences

**Benefits:**
- ~200 definition rows instead of ~14,700 rows carrying duplicated text. At Phase 2 scale, ~500 definitions vs ~150K duplicated metadata sets.
- Updating a finding's risk explanation is a single-row update to `finding_definitions`, not a bulk update across all affected domains.
- `category` column enables filtering by finding type without parsing description text.
- Cross-domain queries ("which domains have CVE-2024-28000?") now join a tiny definitions table with an indexed occurrences table -- faster than scanning a large flat table.
- The `v_findings` view provides backward compatibility for existing query patterns.

**Trade-offs:**
- All queries that need finding metadata (severity, description, cve_id) must now JOIN two tables instead of reading one. The `v_findings` view mitigates this for simple queries, but complex queries must be aware of the join.
- Implementation code (`src/client_memory/`) must be updated to write to two tables instead of one. The upsert pattern is slightly more complex (definition first, then occurrence).
- The old `findings` table's compound index `idx_findings_plugin_severity_confidence` (plugin_slug + severity + confidence in one index) is no longer possible on a single table. The equivalent query requires a join. At the current definitions table size (~200 rows), this join is effectively free.
- Migration from the old schema requires a one-time data transformation: extract unique definitions, then rewrite occurrences with foreign keys.

**Index budget (Pi5 RAM):**
- `finding_definitions`: 5 indexes on ~200-500 rows. Negligible overhead (<1 MB).
- `finding_occurrences`: 8 indexes on 150K active + 500K resolved rows/year. Estimated ~60 MB at 1M total rows. This is a reduction from the old schema's 10 indexes on rows that were wider (more indexed columns per row).
- Net effect: slight reduction in total index size due to narrower occurrence rows.
