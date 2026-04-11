"""webanalyze CLI CMS/tech detection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from loguru import logger


def run_webanalyze(domains: list[str]) -> dict[str, list[str]]:
    """Run webanalyze CLI tool against a list of domains. Returns tech stack per domain."""
    if not shutil.which("webanalyze"):
        logger.warning("webanalyze not found in PATH — skipping webanalyze scan")
        return {}

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
            # webanalyze may output line-by-line JSON
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
        logger.warning("webanalyze execution failed: {}", e)
        return {}
    finally:

        os.unlink(input_file)
