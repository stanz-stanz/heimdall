"""dnsx CLI DNS record enrichment."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger

from src.prospecting.config import DNSX_TIMEOUT


def run_dnsx(domains: list[str]) -> dict[str, dict]:
    """Layer 1 / Level 0 — DNS record enrichment (A, AAAA, CNAME, MX, NS, TXT).

    Standard DNS queries to public resolvers. Public by design.
    """
    if not shutil.which("dnsx"):
        logger.warning("dnsx not found in PATH — skipping DNS enrichment")
        return {}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            ["dnsx", "-l", input_file, "-json", "-a", "-aaaa", "-cname", "-mx", "-ns", "-txt", "-silent"],
            capture_output=True,
            text=True,
            timeout=DNSX_TIMEOUT,
        )
        results: dict[str, dict] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("host", "").lower().strip()
                if host:
                    results[host] = {
                        "a": data.get("a", []),
                        "aaaa": data.get("aaaa", []),
                        "cname": data.get("cname", []),
                        "mx": data.get("mx", []),
                        "ns": data.get("ns", []),
                        "txt": data.get("txt", []),
                    }
            except json.JSONDecodeError:
                continue

        logger.info("dnsx: enriched DNS for {} domains", len(results))
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("dnsx execution failed: {}", e)
        return {}
    finally:
        os.unlink(input_file)
