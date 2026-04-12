# Valdí Scan-Type Revalidation — Post-Refactor Rehash

- **Timestamp:** 2026-04-12T08:33:07Z
- **Event:** Phase 1 (ruff auto-fixes) + Phase 2 (scanner decomposition) invalidated all approval tokens
- **Trigger:** Function source hash changes detected
- **Verdict:** APPROVED (mechanical rehash — no substantive review)
- **Triggered by:** Federico (operator) + Claude Code (acting as Valdí)

## Context

Phase 1 Task 2 auto-fixed 502 ruff violations across the codebase, including formatting changes in the scanner module. Phase 2 Tasks 2-5 then decomposed `src/prospecting/scanner.py` (1,353 lines) into `src/prospecting/scanners/*` — 14 new modules, 18 files total. Every registered scan function was moved to a new module and (usually) renamed to drop its underscore prefix.

Because Valdí approval tokens are SHA-256 hashes of `inspect.getsource(fn)`, and `inspect.getsource` includes the `def` line (which contains the function name), every function's hash changed — even if the body was byte-identical. The validator's next run correctly reported hash mismatches for every token.

## Behavioural Equivalence

No scan function's behaviour changed during the refactor. Specifically:

- No new tools were added
- No new URLs or paths are requested
- No new HTTP methods are used
- No new subprocess arguments
- No change in how robots.txt denial is handled
- No change in consent gating

This is verified by 959 passing tests, including the full `tests/test_scanner.py` suite and `tests/test_level1_scanners.py` (which exercises every Level 0 and Level 1 scan function against mocked subprocesses and HTTP responses).

The one deselected test — `test_level0_ignores_missing_level1_tokens` — was deselected BECAUSE the approval tokens were stale after Phase 1, not because the underlying logic broke. After this rehash, that test must pass again and the `--deselect` flag will be removed from CI.

## Rehashed Scan Functions

| Scan Type ID | New Module | New Function | Level | Layer | Old Hash | New Hash | New Token |
|---|---|---|---|---|---|---|---|
| ssl_certificate_check | src.prospecting.scanners.tls | check_ssl | 0 | 1 | e7d48a879161... | 9c91fedaf22c... | 21be1f07... |
| homepage_meta_extraction | src.prospecting.scanners.wordpress | extract_page_meta | 0 | 1 | 874bc6dad146... | 89e67f7c9889... | 2872e847... |
| httpx_tech_fingerprint | src.prospecting.scanners.httpx_scan | run_httpx | 0 | 1 | a699a70f4e1c... | 7f93d9c7a993... | 8a441dd3... |
| webanalyze_cms_detection | src.prospecting.scanners.webanalyze | run_webanalyze | 0 | 1 | 1c07aae58eee... | 9d4330928f39... | a895838f... |
| response_header_check | src.prospecting.scanners.headers | get_response_headers | 0 | 1 | ce079b27dac4... | 1511f1b8e392... | 8040b850... |
| robots_txt_check | src.prospecting.scanners.robots | check_robots_txt | 0 | 1 | 4177e71d888b... | c2aa0987399f... | 41a0bbe4... |
| passive_domain_scan_orchestrator | src.prospecting.scanners.runner | scan_domains | 0 | 1 | 8372ece33951... | bdffaaef88f2... | 2a81ce5d... |
| subdomain_enumeration_passive | src.prospecting.scanners.subfinder | run_subfinder | 0 | 1 | 972901b2a859... | abbdb8996210... | e840c4aa... |
| dns_enrichment | src.prospecting.scanners.dnsx | run_dnsx | 0 | 1 | 97b6f5fccf3f... | 0db46c56a958... | 912941c2... |
| certificate_transparency_query | src.prospecting.scanners.ct | query_crt_sh | 0 | 1 | 09865688643f... | 3b463d8cdbb7... | 2c0929c7... |
| cloud_storage_index_query | src.prospecting.scanners.grayhat | query_grayhatwarfare | 0 | 1 | a41b9b769f4c... | 430a1d4ed712... | a361e4f3... |
| nuclei_vulnerability_scan | src.prospecting.scanners.nuclei | run_nuclei | 1 | 2 | 4addb4f2a725... | ddcbfb04f2ee... | 675006a0... |
| cmseek_cms_deep_scan | src.prospecting.scanners.cmseek | run_cmseek | 1 | 2 | f4ae289a1b39... | f45789fd297a... | 98fc4f1b... |
| nmap_port_scan | src.prospecting.scanners.nmap | run_nmap | 1 | 2 | e154f0a8877d... | 6c2158f84ec4... | 587349a6... |

## Helper Functions

- `homepage_meta_extraction` uses helper `extract_rest_api_plugins` — new hash `3d31b533ae85...`
- `nmap_port_scan` uses helper `parse_nmap_xml` — new hash `21a68b78c521...`

## Dropped as Obsolete

- `wpscan_wordpress_scan` — WPScan was removed in Sprint 4 (see `docs/decisions/log.md` 2026-04-04). Replaced by the WPVulnerability API lookup, which operates against cached data and does not make outbound requests to target systems. No replacement approval token is needed.

## Unexpected Drops

- (none)

## Reasoning

Every function in the spec list above was inspected in its new location. Each implements exactly the same outbound behaviour as the version that was previously approved. The move from `src/prospecting/scanner.py` to `src/prospecting/scanners/*.py` is a pure structural refactor: code was relocated, reformatted, and renamed, but not rewritten.

Per the Valdí SKILL.md Gate 1 workflow, a new approval is required because the function hash changed. Because the refactor was mechanical and behaviour is preserved, the new verdict matches the old verdict (APPROVED) for every function. The forensic record is this single batch log rather than 14 individual reviews, reflecting that this was one event (the Phase 1/2 refactor) affecting all functions simultaneously.

## Verification

After applying this rehash:

1. `_validate_approval_tokens(max_level=0)` returns the approvals dict (not None)
2. `_validate_approval_tokens(max_level=1)` returns the approvals dict (not None)
3. `tests/test_level1_scanners.py::test_level0_ignores_missing_level1_tokens` passes
4. The `--deselect` is removed from `.github/workflows/ci.yml`
5. CI run on main is green with the full test suite (no deselect)

## Operator Sign-Off

Federico reviewed this log and the accompanying diff to `approvals.json` before the rehash was committed. No substantive concerns raised.
