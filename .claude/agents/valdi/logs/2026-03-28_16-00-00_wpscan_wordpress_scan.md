# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-28T16:00:00Z
- **Scan type:** WordPress vulnerability scanning via WPScan sidecar container
- **Scan type ID:** wpscan_wordpress_scan
- **Declared Layer:** 2 (Active probing)
- **Declared Level:** 1 (Written consent required)
- **Verdict:** APPROVED
- **Approval token:** df32303b-6291-4eea-a3a3-a53ba93d3350
- **Function hash:** sha256:8a3ae86aab66d4722c24be5ce0de5209af7523a3df9aabd38098e8ec71be4874
- **Triggered by:** Claude Code (Sprint 3.2 — WPScan sidecar)

## Architecture

WPScan runs in a **separate Docker container** (sidecar), not in the worker process. The worker delegates via Redis request-response:

1. Worker detects WordPress CMS from Level 0 scan results
2. Worker LPUSHes a job to `queue:wpscan`
3. Worker BRPOPs on `wpscan:result:{job_id}` (300s timeout)
4. Sidecar picks up the job, runs `wpscan` CLI, returns result via Redis

The approval covers the **delegation function** (`_request_wpscan` in `scan_job.py`).

## Function Reviewed

`_request_wpscan(redis_conn, domain, job_id) -> dict | None`

**File:** `src/worker/scan_job.py`

## Security-Reviewed CLI Constraints (sidecar)

- `--enumerate vp,vt` only — no user enumeration
- Fixed UA: `Heimdall-EASM/1.0 (authorised-scan)` — no `--random-user-agent`
- No `--disable-tls-checks` — preserves forensic chain
- No `--api-token` on CLI — token via `WPSCAN_API_TOKEN` env var

## Enforcement Chain

1. `execute_scan_job` Level 1 gate — `job_level >= 1`
2. CMS detection — only triggers for `scan.cms == "WordPress"`
3. `redis_conn is not None` — sidecar must be reachable
4. Worker Gate 2 — `check_consent()` blocks without valid consent
5. Sidecar isolation — separate container, own resource limits

## Violations

None.
