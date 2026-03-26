# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-22T10:06:00Z
- **Scan type:** CVR registry lookup (Reklamebeskyttelse enrichment)
- **Scan type ID:** cvr_registry_lookup
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** FLAGGED
- **Approval token:** N/A
- **Function hash:** sha256:ea947042ad65b8d6c69fb8e56dac45037e739330c32447565e0e236b1cf261ef
- **Triggered by:** Claude Code (backfill)

## Function Reviewed

```python
def enrich_from_cvr(input_csv: Path, output_csv: Path | None = None) -> Path:
    """Read prospect CSV, query datacvr.virk.dk for each confirmed entry, add Reklamebeskyttelse."""

    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        original_fieldnames = reader.fieldnames

    confirmed = [r for r in rows if r["website"] and not r["discard_reason"]]
    log.info("Enriching %d confirmed prospects from CVR", len(confirmed))

    # Add new field
    fieldnames = list(original_fieldnames)
    if "reklamebeskyttelse" not in fieldnames:
        fieldnames.append("reklamebeskyttelse")

    # Initialize all rows
    for r in rows:
        r.setdefault("reklamebeskyttelse", "")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed — cannot enrich from CVR")
        return input_csv

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...",
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')

        success = 0
        failed = 0

        for i, row in enumerate(confirmed, 1):
            cvr = row["cvr_number"]
            url = f"{CVR_BASE_URL}/{cvr}?enhedstype=virksomhed"

            try:
                resp = page.goto(url, wait_until="networkidle", timeout=20000)
                if resp and resp.status == 200:
                    content = page.content()
                    value = _extract_reklamebeskyttelse(content)
                    ...
            except Exception as e:
                ...

            delay = random.uniform(*CVR_SCRAPE_DELAY)
            time.sleep(delay)

        browser.close()

    # Write enriched CSV
    ...
    return output_csv
```

**File:** `pipeline/cvr_enrich.py` (lines 28-115)

## Tools Invoked

- **Playwright** (headless Chromium browser)

Not a scanning tool in the SCANNING_RULES.md sense. Playwright is used here as a web scraper for a government registry, not for security scanning.

## URLs/Paths Requested

- `https://datacvr.virk.dk/enhed/virksomhed/{cvr}?enhedstype=virksomhed` — Danish government CVR public registry

This function does NOT make requests to target domains. It only queries the government's public company registry.

## robots.txt Handling

**Not checked for datacvr.virk.dk.** The function does not verify whether virk.dk's robots.txt permits automated access before scraping.

## Reasoning

This function occupies a grey zone that requires human review:

**Arguments for approval:**
1. This is NOT a scan of a target's infrastructure. It queries a government-operated public company registry (datacvr.virk.dk) for publicly available business information (Reklamebeskyttelse status).
2. The CVR register is explicitly a public data source — its purpose is to make company information available to the public.
3. The data retrieved (Reklamebeskyttelse flag) is used to determine whether a company may be contacted for marketing — this is actually a compliance-positive action.
4. SCANNING_RULES.md governs scanning of target domains, not queries to third-party data sources.

**Arguments for concern:**
1. The function uses anti-detection measures (`--disable-blink-features=AutomationControlled`, hiding webdriver property) which suggest awareness that the target site may not welcome automated access.
2. The function does NOT check datacvr.virk.dk's robots.txt before scraping.
3. datacvr.virk.dk has a structured API (the ElasticSearch-based CVR API) that is the intended machine-readable interface. Scraping the HTML frontend with anti-detection measures may violate the site's terms of service.
4. Rate limiting is implemented (random 1-3 second delay), which is responsible but also signals awareness that bulk automated requests may be unwelcome.

**Classification uncertainty:**
This function does not fit cleanly into the Layer/Level framework, which was designed for scanning target domains. It is a data enrichment function that queries a government registry. Valdi's mandate covers "scanning activities" — whether CVR registry scraping constitutes a "scanning activity" is a judgement call that falls outside Valdi's stated boundaries.

## Decision

**FLAGGED for human review.** Blocked pending operator decision.

The operator should determine:
1. Whether CVR registry queries fall under the scanning rules (Valdi's recommendation: they do not, but the robots.txt concern is valid regardless)
2. Whether datacvr.virk.dk's robots.txt should be checked and respected (Valdi's recommendation: yes, as a matter of principle)
3. Whether the anti-detection measures are appropriate or should be removed
4. Whether the official CVR API should be used instead of HTML scraping

**This function must NOT execute until the operator has reviewed this log and made a decision.**
