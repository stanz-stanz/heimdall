"""CVR enrichment: fetch Reklamebeskyttelse from datacvr.virk.dk for confirmed prospects."""

from __future__ import annotations

import csv
import logging
import random
import re
import time
from pathlib import Path

from pipeline.config import CVR_BASE_URL, CVR_SCRAPE_DELAY, DATA_DIR

log = logging.getLogger(__name__)


def _extract_reklamebeskyttelse(html: str) -> str | None:
    """Extract Reklamebeskyttelse value (Ja/Nej) from page HTML."""
    match = re.search(
        r'Reklamebeskyttelse</strong></div>\s*<div[^>]*>(\w+)</div>',
        html,
    )
    if match:
        return match.group(1).strip()
    return None


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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
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
                    if value:
                        row["reklamebeskyttelse"] = value
                        success += 1
                    else:
                        row["reklamebeskyttelse"] = "unknown"
                        log.warning("CVR %s: Reklamebeskyttelse field not found in page", cvr)
                        failed += 1
                else:
                    status = resp.status if resp else "no response"
                    row["reklamebeskyttelse"] = "error"
                    log.warning("CVR %s: HTTP %s", cvr, status)
                    failed += 1
            except Exception as e:
                row["reklamebeskyttelse"] = "error"
                log.warning("CVR %s: %s", cvr, e)
                failed += 1

            if i % 25 == 0:
                log.info("Enriched %d/%d (success: %d, failed: %d)", i, len(confirmed), success, failed)

            delay = random.uniform(*CVR_SCRAPE_DELAY)
            time.sleep(delay)

        browser.close()

    log.info("CVR enrichment complete: %d success, %d failed out of %d", success, failed, len(confirmed))

    # Write enriched CSV
    if output_csv is None:
        output_csv = input_csv.parent / input_csv.name.replace(".csv", "-enriched.csv")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info("Wrote enriched CSV to %s", output_csv)
    return output_csv


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "prospect-list-2026-03-22.csv"
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    enrich_from_cvr(input_path)
