"""subfinder CLI passive subdomain enumeration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger

from src.prospecting.config import (
    SUBFINDER_MAX_ENUM_TIME,
    SUBFINDER_THREADS,
    SUBFINDER_TIMEOUT,
)


def run_subfinder(domains: list[str]) -> dict[str, list[str]]:
    """Layer 1 / Level 0 — Subdomain enumeration via passive sources (CT logs, DNS datasets).

    Uses subfinder CLI. No direct queries to the target's infrastructure beyond DNS.
    """
    if not shutil.which("subfinder"):
        logger.warning("subfinder not found in PATH — skipping subdomain enumeration")
        return {}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            [
                "subfinder", "-dL", input_file, "-json", "-silent",
                "-t", str(SUBFINDER_THREADS),
                "-max-time", str(SUBFINDER_MAX_ENUM_TIME),
            ],
            capture_output=True,
            text=True,
            timeout=SUBFINDER_TIMEOUT,
        )
        results: dict[str, list[str]] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("host", "").lower().strip()
                # Determine which parent domain this subdomain belongs to
                if host:
                    for domain in domains:
                        if host.endswith(f".{domain}") or host == domain:
                            results.setdefault(domain, []).append(host)
                            break
            except json.JSONDecodeError:
                continue

        # Deduplicate per domain
        for domain in results:
            results[domain] = list(dict.fromkeys(results[domain]))

        logger.info("subfinder: found {} subdomains across {} domains",
                    sum(len(v) for v in results.values()), len(results))
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("subfinder execution failed: {}", e)
        return {}
    finally:
        os.unlink(input_file)
