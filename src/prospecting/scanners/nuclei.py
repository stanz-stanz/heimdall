"""Nuclei template-based vulnerability scanning (Level 1 — requires consent)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger

# Pi5 constraints: limit concurrency and rate to stay within 1 GB memory budget
NUCLEI_RATE_LIMIT = 50
NUCLEI_CONCURRENCY = 5
NUCLEI_TIMEOUT = 300  # seconds


def run_nuclei(domains: list[str]) -> dict[str, dict]:
    """Layer 2 / Level 1 — Template-based vulnerability scanning via Nuclei.

    Sends crafted requests to test for specific vulnerabilities. Requires
    written consent (Level 1) before execution.

    Returns ``{domain: {"findings": [...], "template_count": N}}``.
    """
    if not shutil.which("nuclei"):
        logger.warning("nuclei not found in PATH — skipping vulnerability scan")
        return {}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    # Template directory: baked into Docker image at build time
    templates_dir = os.environ.get("NUCLEI_TEMPLATES_DIR", "/opt/nuclei-templates")

    try:
        result = subprocess.run(
            [
                "nuclei",
                "-l", input_file,
                "-jsonl",
                "-silent",
                "-rate-limit", str(NUCLEI_RATE_LIMIT),
                "-c", str(NUCLEI_CONCURRENCY),
                "-severity", "low,medium,high,critical",
                "-no-update-check",
                "-ud", templates_dir,
                "-no-interactsh",
                "-disable-redirects",
                "-exclude-tags", "rce,exploit,intrusive,dos",
            ],
            capture_output=True,
            text=True,
            timeout=NUCLEI_TIMEOUT,
        )

        if result.returncode != 0 and result.stderr:
            logger.warning("nuclei exited with code {}: {}", result.returncode, result.stderr[:500])

        results: dict[str, dict] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("host", "").lower().strip()
                # Normalize host: strip protocol and trailing slash/path
                if "://" in host:
                    host = host.split("://", 1)[1]
                host = host.split("/")[0].split(":")[0]

                if not host:
                    logger.warning("nuclei finding dropped — unparseable host: {} (template: {})",
                                   data.get("host", ""), data.get("template-id", "unknown"))
                    continue

                if host not in results:
                    results[host] = {"findings": [], "finding_count": 0}

                results[host]["findings"].append({
                    "template_id": data.get("template-id", data.get("templateID", "")),
                    "severity": data.get("info", {}).get("severity", "unknown"),
                    "name": data.get("info", {}).get("name", ""),
                    "matched_at": data.get("matched-at", data.get("matched_at", "")),
                    "type": data.get("type", ""),
                })
                results[host]["finding_count"] += 1
            except json.JSONDecodeError:
                continue

        logger.info(
            "nuclei: scanned {} domains, found {} total findings",
            len(domains),
            sum(r["finding_count"] for r in results.values()),
        )
        return results

    except subprocess.TimeoutExpired:
        logger.warning("nuclei timed out after {}s", NUCLEI_TIMEOUT)
        return {}
    except FileNotFoundError:
        logger.warning("nuclei binary not found")
        return {}
    finally:
        os.unlink(input_file)
