# Valdi Scan-Type Validation -- Batch Hash Refresh

- **Timestamp:** 2026-04-05T14:00:00Z
- **Verdict:** APPROVED (all six scan types)
- **Triggered by:** Federico (manual request, stale hashes from prior commits)
- **Review type:** Re-validation after non-security code changes (loguru migration, subfinder parameter adjustments)

## Scope

Six Level 0, Layer 1 scan types whose `function_hash` values became stale due to prior commits (loguru structured logging migration, subfinder flag changes). No security-relevant behavioral changes in any function. Existing approval tokens retained; only `function_hash` and `approved_at` updated.

## Scan Types Reviewed

| # | scan_type_id | Function | Layer | Level | New Hash |
|---|---|---|---|---|---|
| 1 | `httpx_tech_fingerprint` | `_run_httpx` | 1 | 0 | `sha256:a699a70f...9d92ccbc` |
| 2 | `webanalyze_cms_detection` | `_run_webanalyze` | 1 | 0 | `sha256:1c07aae5...b13ea4aa` |
| 3 | `subdomain_enumeration_passive` | `_run_subfinder` | 1 | 0 | `sha256:97290...b420223b` |
| 4 | `dns_enrichment` | `_run_dnsx` | 1 | 0 | `sha256:97b6f5fc...dfe0c748` |
| 5 | `certificate_transparency_query` | `_query_crt_sh` | 1 | 0 | `sha256:09865688...2c839abb` |
| 6 | `cloud_storage_index_query` | `_query_grayhatwarfare` | 1 | 0 | `sha256:a41b9b76...c95f92b0` |

## Per-Function Analysis

### 1. `_run_httpx` (scanner.py lines 276-321)

- **Tool:** httpx (Layer 1 -- SCANNING_RULES.md Layer 1 table)
- **CLI flags:** `-json`, `-tech-detect`, `-server`, `-status-code`, `-title`, `-follow-redirects`, `-silent`
- **URLs/paths requested:** Public homepage of each domain (no specific paths)
- **HTTP methods:** GET (via httpx default)
- **Layer 2 activity:** None
- **Changes from prior version:** `logger.warning("httpx execution failed: {}", e)` -- loguru structured logging format only. No new network requests, no new flags, no new targets.
- **Verdict:** APPROVED. Reads what the server voluntarily sends to any visitor. Passes the Decision Test.

### 2. `_run_webanalyze` (scanner.py lines 324-370)

- **Tool:** webanalyze (Layer 1 -- SCANNING_RULES.md Layer 1 table)
- **CLI flags:** `-hosts`, `-output json`, `-silent`, `-crawl 0`
- **URLs/paths requested:** `https://{domain}` -- public homepage only. `-crawl 0` prevents crawling beyond the initial page.
- **HTTP methods:** GET (via webanalyze default)
- **Layer 2 activity:** None
- **Changes from prior version:** `logger.warning("webanalyze execution failed: {}", e)` -- loguru structured logging format only.
- **Verdict:** APPROVED. Technology fingerprinting from public page responses.

### 3. `_run_subfinder` (scanner.py lines 428-479)

- **Tool:** subfinder (Layer 1 -- SCANNING_RULES.md Layer 1 table)
- **CLI flags:** `-dL`, `-json`, `-silent`, `-t {threads}`, `-max-time {max_enum_time}`
- **URLs/paths requested:** None on target infrastructure. Queries passive sources (CT logs, DNS datasets).
- **HTTP methods:** N/A (passive source queries)
- **Layer 2 activity:** None
- **Changes from prior version:** Logger calls migrated to loguru format (`logger.info("subfinder: found {} subdomains...", ...)`, `logger.warning("subfinder execution failed: {}", e)`). Subfinder parameter adjustments (`-t`, `-max-time` from config). No new data sources, no direct target queries.
- **Verdict:** APPROVED. Passive subdomain enumeration via third-party data sources.

### 4. `_run_dnsx` (scanner.py lines 482-527)

- **Tool:** dnsx (Layer 1 -- SCANNING_RULES.md Layer 1 table)
- **CLI flags:** `-l`, `-json`, `-a`, `-aaaa`, `-cname`, `-mx`, `-ns`, `-txt`, `-silent`
- **URLs/paths requested:** Standard DNS queries to public resolvers for record types A, AAAA, CNAME, MX, NS, TXT.
- **HTTP methods:** N/A (DNS protocol)
- **Layer 2 activity:** None. DNS records are public by design.
- **Changes from prior version:** Logger calls migrated to loguru format.
- **Verdict:** APPROVED. Standard DNS resolution and enrichment.

### 5. `_query_crt_sh` (scanner.py lines 530-585)

- **Tool:** crt.sh API (Layer 1 -- SCANNING_RULES.md Layer 1 table)
- **URLs/paths requested:** `{CRT_SH_API_URL}/?q=%.{domain}&output=json` -- third-party public API. No requests to target infrastructure.
- **HTTP methods:** GET to crt.sh API
- **Layer 2 activity:** None. Queries a public Certificate Transparency log index.
- **Changes from prior version:** Logger calls migrated to loguru format (`logger.debug`, `logger.info`).
- **Verdict:** APPROVED. Third-party public index query, no target interaction.

### 6. `_query_grayhatwarfare` (scanner.py lines 588-628)

- **Tool:** GrayHatWarfare API (Layer 1 -- classified in SCANNING_RULES.md Valdi Classification Notes, 2026-03-26)
- **URLs/paths requested:** `https://buckets.grayhatwarfare.com/api/v2/files?keywords={domain}` -- third-party public index. No requests to target infrastructure.
- **HTTP methods:** GET to GrayHatWarfare API
- **Layer 2 activity:** None. Queries a public index of exposed cloud storage.
- **Changes from prior version:** Logger calls migrated to loguru format.
- **Verdict:** APPROVED. Third-party public index query, functionally equivalent to a search engine query.

## robots.txt Handling

These functions are called by the scan orchestrator (`scan_domains`), which performs robots.txt checks via `_check_robots_txt` before invoking any scan function. Domains that deny automated access are skipped before these functions execute. This is the correct architecture -- the gate is at the orchestrator level, not duplicated in each tool function.

## Decision Test Applied

For each function: "Does this request go to a URL that a normal person would reach by clicking links on the public website, or does it go to a URL that is being guessed or probed for?"

- `_run_httpx`: Homepage -- publicly served. PASS.
- `_run_webanalyze`: Homepage -- publicly served, no crawling. PASS.
- `_run_subfinder`: No target URLs -- passive source queries. PASS.
- `_run_dnsx`: DNS queries -- public by design. PASS.
- `_query_crt_sh`: Third-party API -- no target requests. PASS.
- `_query_grayhatwarfare`: Third-party API -- no target requests. PASS.

## Nature of Changes

All changes across the six functions are non-security-relevant:

1. **Loguru migration:** `logger.warning("message %s", var)` changed to `logger.warning("message {}", var)` -- format string syntax only.
2. **Subfinder parameters:** `-t` (threads) and `-max-time` (max enumeration time) now read from config constants. These are performance tuning parameters that do not change what data is collected or how.
3. No new network requests added to any function.
4. No new URLs, paths, or endpoints targeted.
5. No new tools invoked.
6. No Layer changes.

## Approval Tokens

Existing tokens retained (no security-relevant changes warrant new tokens):

| scan_type_id | Token (unchanged) |
|---|---|
| `httpx_tech_fingerprint` | `69c956db-2ad1-4606-b9b4-f85bc309be4e` |
| `webanalyze_cms_detection` | `474b98c0-4d33-4703-80ca-0a65ba77e467` |
| `subdomain_enumeration_passive` | `a1b2c3d4-1111-4aaa-bbbb-subfinder00001` |
| `dns_enrichment` | `a1b2c3d4-2222-4aaa-bbbb-dnsx000000001` |
| `certificate_transparency_query` | `a1b2c3d4-3333-4aaa-bbbb-crtsh00000001` |
| `cloud_storage_index_query` | `a1b2c3d4-4444-4aaa-bbbb-ghw0000000001` |

## Violations

None.
