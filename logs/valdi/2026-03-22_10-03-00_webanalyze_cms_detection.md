# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:03:00Z
- **Scan type:** CMS/technology detection via webanalyze CLI
- **Scan type ID:** webanalyze_cms_detection
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** 474b98c0-4d33-4703-80ca-0a65ba77e467
- **Function hash:** sha256:79058d2d513fcf6d748e0c44d4ec253b7e7bd56eeb9593f394acc4c42af7a06f
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def _run_webanalyze(domains: list[str]) -> dict[str, list[str]]:
    """Run webanalyze CLI tool against a list of domains. Returns tech stack per domain."""
    if not shutil.which("webanalyze"):
        log.warning("webanalyze not found in PATH — skipping webanalyze scan")
        return {}

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for d in domains:
            f.write(f"https://{d}\n")
        input_file = f.name

    try:
        result = subprocess.run(
            ["webanalyze", "-hosts", input_file, "-output", "json", "-silent", "-crawl", "0"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        results = {}
        try:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                for entry in data:
                    host = entry.get("hostname", "").replace("https://", "").replace("http://", "").strip("/").lower()
                    techs = [m.get("app_name", "") or m.get("app", "") for m in entry.get("matches", []) if m]
                    if host and techs:
                        results[host] = [t for t in techs if t]
        except json.JSONDecodeError:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    host = entry.get("hostname", "").replace("https://", "").replace("http://", "").strip("/").lower()
                    techs = [m.get("app_name", "") or m.get("app", "") for m in entry.get("matches", []) if m]
                    if host and techs:
                        results[host] = results.get(host, []) + [t for t in techs if t]
                except json.JSONDecodeError:
                    continue
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("webanalyze execution failed: %s", e)
        return {}
    finally:
        import os
        os.unlink(input_file)
```

**File:** `pipeline/scanner.py` (lines 160-207)

## Tools Invoked

- **webanalyze** (permitted at Level 0 per SCANNING_RULES.md)

### webanalyze flags analysed

| Flag | Purpose | Compliance |
|------|---------|------------|
| `-hosts` | Input file of URLs | N/A (input method) |
| `-output json` | JSON output format | N/A (output format) |
| `-silent` | Suppress banner output | N/A (display option) |
| `-crawl 0` | **Disable crawling** | Compliant — ensures no link-following beyond the initial page |

The `-crawl 0` flag is a positive compliance indicator: it explicitly prevents webanalyze from following links or discovering additional pages beyond the homepage.

## URLs/Paths Requested

- `https://{domain}/` (homepage) for each domain — webanalyze with `-crawl 0` only analyses the initial page response

## robots.txt Handling

The function itself does not check robots.txt. It is a private helper (`_` prefix) designed to be called from the `scan_domains` orchestrator, which is responsible for robots.txt enforcement at the domain level.

**Condition:** This approval is valid only when the function is called from an orchestrator that enforces robots.txt compliance.

## Reasoning

webanalyze is explicitly listed as an allowed Level 0 tool in SCANNING_RULES.md: "webanalyze — CMS/technology detection from public page responses."

The function invokes webanalyze with the `-crawl 0` flag, which explicitly disables crawling. This means webanalyze only analyses the homepage response — it does not discover or request additional pages. The tool performs technology fingerprinting by matching response patterns (headers, HTML content, JavaScript libraries) against its signature database. This is reading what the server already sends to any visitor.

The function:
1. Only accesses the homepage of each domain
2. Explicitly disables crawling (`-crawl 0`)
3. Does NOT probe hidden paths or admin panels
4. Does NOT send crafted requests or vulnerability probes
5. Uses only an explicitly permitted Level 0 tool

All activity is within Layer 1. No Layer 2 or Layer 3 activity present.

## Violations

None.
