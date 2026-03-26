# Worker Module

Scan job worker for the Heimdall Docker architecture. Pulls domain scan jobs from Redis, executes Layer 1 scan types, stores results.

## Module structure (to be implemented)

```
src/worker/
├── __init__.py
├── main.py          # Worker entry point: connect to Redis, BRPOP loop
├── scan_job.py      # Execute a single domain scan job
├── cache.py         # Redis cache check/store helpers
└── README.md        # This file
```

## How it maps to existing code

The worker reuses scan functions from `src/prospecting/scanner.py`. No rewrite needed — the functions are already per-domain.

| Worker function | Calls | From |
|----------------|-------|------|
| `execute_scan_job()` | Orchestrates all scan types for one domain | `src/worker/scan_job.py` |
| `check_cache()` | Checks Redis for fresh cached result | `src/worker/cache.py` |
| `store_cache()` | Stores result in Redis with TTL | `src/worker/cache.py` |
| SSL check | `_check_ssl(domain)` | `src/prospecting/scanner.py` |
| Response headers | `_get_response_headers(domain)` | `src/prospecting/scanner.py` |
| Page meta | `_extract_page_meta(domain)` | `src/prospecting/scanner.py` |
| httpx | `_run_httpx([domain])` | `src/prospecting/scanner.py` |
| webanalyze | `_run_webanalyze([domain])` | `src/prospecting/scanner.py` |
| subfinder | `_run_subfinder([domain])` | `src/prospecting/scanner.py` |
| dnsx | `_run_dnsx([domain])` | `src/prospecting/scanner.py` |
| crt.sh | `_query_crt_sh_single(domain)` | `src/prospecting/scanner.py` |
| GrayHatWarfare | Per-domain query (needs extraction from loop) | `src/prospecting/scanner.py` |
| Brief generation | `generate_brief(company, scan, bucket)` | `src/prospecting/brief_generator.py` |
| GDPR determination | `_determine_gdpr_sensitivity(company, scan)` | `src/prospecting/brief_generator.py` |
| Valdí validation | `_validate_approval_tokens()` | `src/prospecting/scanner.py` |

## Worker lifecycle

```
startup:
    validate Valdí approval tokens (fail-fast if invalid)
    connect to Redis

loop:
    job = BRPOP("queue:scan", timeout=30)
    if job is None: continue  # no jobs, keep waiting

    domain = job["domain"]
    check robots.txt → skip if denied

    for each scan_type:
        cached = redis.get(f"cache:{scan_type}:{domain}")
        if cached and not expired:
            use cached result
        else:
            run scan function
            redis.setex(f"cache:{scan_type}:{domain}", ttl, result)

    assemble ScanResult from all results
    generate findings + GDPR determination
    write JSON to /data/results/{client_id}/{domain}/{date}.json
    redis.publish("scan-complete", job_id)
```

## Dependencies

- `redis` Python package (redis-py)
- All Go CLI tools: httpx, webanalyze, subfinder, dnsx (installed in Docker image)
- All scan functions from `src/prospecting/scanner.py`
