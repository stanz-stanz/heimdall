# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:02:00Z
- **Scan type:** Technology fingerprinting via httpx CLI
- **Scan type ID:** httpx_tech_fingerprint
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 69c956db-2ad1-4606-b9b4-f85bc309be4e
- **Function hash:** sha256:9f5fb3f1ed4cd20611a661046b729d4e573bb2235e0a26a3505a51d2c2e0ddfe
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def _run_httpx(domains: list[str]) -> dict[str, dict]:
    """Run httpx CLI tool against a list of domains. Returns dict keyed by domain."""
    if not shutil.which("httpx"):
        log.warning("httpx not found in PATH — skipping httpx scan")
        return {}

    # Write domains to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            [
                "httpx",
                "-l", input_file,
                "-json",
                "-tech-detect",
                "-server",
                "-status-code",
                "-title",
                "-follow-redirects",
                "-silent",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        results = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("input", data.get("host", "")).lower()
                if host:
                    results[host] = data
            except json.JSONDecodeError:
                continue
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("httpx execution failed: %s", e)
        return {}
    finally:
        import os
        os.unlink(input_file)
```

**File:** `pipeline/scanner.py` (lines 111-157)

## Tools Invoked

- **httpx** (permitted at Level 0 per SCANNING_RULES.md)

### httpx flags analysed

| Flag | Purpose | Compliance |
|------|---------|------------|
| `-l` | Input file of domains | N/A (input method) |
| `-json` | JSON output format | N/A (output format) |
| `-tech-detect` | Technology detection from response | Layer 1 — reads publicly served data |
| `-server` | Extract server header | Layer 1 — reads publicly served header |
| `-status-code` | Record HTTP status code | Layer 1 — reads publicly served response |
| `-title` | Extract page title | Layer 1 — reads publicly served HTML |
| `-follow-redirects` | Follow HTTP redirects | Layer 1 — standard browser behaviour |
| `-silent` | Suppress banner output | N/A (display option) |

No flags that trigger active probing, path discovery, vulnerability scanning, or port scanning.

## URLs/Paths Requested

- Homepage (`/`) of each domain — httpx with default settings requests the root path
- httpx does NOT probe hidden paths, admin panels, or non-public endpoints with these flags

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) designed to be called from the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level.

**Condition:** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance.

## Reasoning

httpx is explicitly listed as an allowed Level 0 tool in SCANNING_RULES.md: "httpx — HTTP probing of public pages, tech fingerprinting from response data."

The function invokes httpx with flags that only read publicly served data: technology detection (`-tech-detect`), server headers (`-server`), status codes (`-status-code`), and page titles (`-title`). All of these read information the server voluntarily sends to any visitor.

The function:
1. Only accesses the homepage/root path of each domain
2. Does NOT use path probing, fuzzing, or vulnerability detection flags
3. Does NOT use port scanning flags
4. Does NOT send crafted requests
5. Uses only an explicitly permitted Level 0 tool

All activity is within Layer 1. No Layer 2 or Layer 3 activity present.

## Violations

None.
