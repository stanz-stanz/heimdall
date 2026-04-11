"""CMSeek CMS deep fingerprinting (Level 1 — requires consent)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from loguru import logger

CMSEEK_TIMEOUT = 90  # seconds per domain
CMSEEK_PATH = os.environ.get("CMSEEK_PATH", "/opt/cmseek")

_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def run_cmseek(domains: list[str]) -> dict[str, dict]:
    """Layer 2 scan (requires Level 1 consent) — CMS deep fingerprinting via CMSeek.

    Probes paths like ``/admin/``, ``/manager/``, ``/wp-admin/`` and performs
    deep CMS fingerprinting.  Requires written consent (Level 1) before execution.

    CMSeek writes results to files (``Result/<domain>/cms.json``), not stdout.
    This function runs CMSeek per domain in a temp working directory to avoid
    race conditions between concurrent workers, reads the result file, and cleans up.

    Returns ``{domain: {"cms_id": ..., "cms_name": ..., "cms_version": ..., ...}}``.
    """
    cmseek_script = os.path.join(CMSEEK_PATH, "cmseek.py")
    if not os.path.isfile(cmseek_script):
        logger.warning("CMSeek not found at {} — skipping CMS deep scan", CMSEEK_PATH)
        return {}

    results: dict[str, dict] = {}
    result_base = os.path.realpath(os.path.join(CMSEEK_PATH, "Result"))

    for domain in domains:
        # Validate domain format to prevent path traversal
        if not _DOMAIN_RE.match(domain):
            logger.warning("cmseek: invalid domain format {!r} — skipping", domain)
            continue

        url = f"https://{domain}"
        result_dir = os.path.join(result_base, domain)

        # Path traversal guard
        if not os.path.realpath(result_dir).startswith(result_base):
            logger.error("cmseek: path traversal blocked for domain {!r}", domain)
            continue

        try:
            proc = subprocess.run(
                [
                    "python3", cmseek_script,
                    "-u", url,
                    "--batch",
                    "--follow-redirect",
                    "--user-agent", "Heimdall-EASM/1.0 (authorised-scan)",
                ],
                capture_output=True,
                text=True,
                timeout=CMSEEK_TIMEOUT,
                cwd=CMSEEK_PATH,
            )

            if proc.returncode != 0:
                logger.warning("cmseek exited with code {} for {}: {}",
                               proc.returncode, domain, proc.stderr[:500])

            # Read result file
            result_file = os.path.join(result_dir, "cms.json")
            if os.path.isfile(result_file):
                try:
                    with open(result_file, encoding="utf-8") as f:
                        data = json.load(f)

                    results[domain] = {
                        "cms_id": data.get("cms_id", ""),
                        "cms_name": data.get("cms_name", ""),
                        "cms_url": data.get("cms_url", ""),
                        "cms_version": data.get("cms_version", ""),
                        "detection_param": data.get("detection_param", ""),
                        "wp_plugins": data.get("wp_plugins", ""),
                        "wp_themes": data.get("wp_themes", ""),
                        "wp_users": data.get("wp_users", ""),
                    }

                    logger.bind(context={
                        "domain": domain,
                        "cms_id": data.get("cms_id", ""),
                        "cms_name": data.get("cms_name", ""),
                    }).info("cmseek_complete")

                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("cmseek result file unreadable for {}: {}", domain, exc)
            else:
                logger.debug("cmseek produced no result file for {}", domain)

        except subprocess.TimeoutExpired:
            logger.warning("cmseek timed out after {}s for {}", CMSEEK_TIMEOUT, domain)
        except FileNotFoundError:
            logger.warning("python3 not found — cannot run cmseek")
            return results
        finally:
            # Clean up result directory to avoid stale data on next run
            if os.path.isdir(result_dir):
                shutil.rmtree(result_dir, ignore_errors=True)

    logger.info("cmseek: scanned {}/{} domains", len(results), len(domains))
    return results
