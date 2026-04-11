"""httpx CLI tech fingerprinting."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger


def run_httpx(domains: list[str]) -> dict[str, dict]:
    """Run httpx CLI tool against a list of domains. Returns dict keyed by domain."""
    if not shutil.which("httpx"):
        logger.warning("httpx not found in PATH — skipping httpx scan")
        return {}

    # Write domains to temp file
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
        logger.warning("httpx execution failed: {}", e)
        return {}
    finally:

        os.unlink(input_file)
