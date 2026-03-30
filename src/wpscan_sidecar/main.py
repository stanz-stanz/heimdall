"""WPScan sidecar — BRPOP loop that runs wpscan CLI and returns results via Redis.

Consumes jobs from ``queue:wpscan``, runs the wpscan binary, and pushes
structured results back to a per-job response key. Caches results to avoid
re-scanning the same domain within the TTL window.

Run as::

    python -m src.wpscan_sidecar [--redis-url redis://localhost:6379/0]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import time
from typing import Optional

import redis as redis_lib

log = logging.getLogger(__name__)

# Scan settings
WPSCAN_TIMEOUT = 120  # seconds per domain
WPSCAN_USER_AGENT = "Heimdall-EASM/1.0 (authorised-scan)"
CACHE_TTL = 86400  # 24h
RESPONSE_KEY_TTL = 600  # 10 min — auto-cleanup for abandoned responses

_shutdown_requested: bool = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    sig_name = signal.Signals(signum).name
    log.info("Received %s — shutting down after current job", sig_name)


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heimdall WPScan sidecar")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
    )
    return parser.parse_args(argv)


def _run_wpscan(domain: str) -> dict:
    """Run wpscan CLI and return structured result.

    Returns a dict with keys: status, domain, wpscan (parsed output),
    exit_code, duration_ms.
    """
    # Support both plain domains (https://) and explicit URLs (http://host:port)
    if domain.startswith("http://") or domain.startswith("https://"):
        url = domain if domain.endswith("/") else f"{domain}/"
    else:
        url = f"https://{domain}/"
    cmd = [
        "wpscan",
        "--url", url,
        "--format", "json",
        "--no-banner",
        "--enumerate", "vp,vt",
        "--force",  # Scan even if WordPress detection is inconclusive
        "--disable-tls-checks",  # Accept self-signed certs (twin, staging)
        "--user-agent", WPSCAN_USER_AGENT,
    ]
    api_token = os.environ.get("WPSCAN_API_TOKEN", "")
    if api_token:
        cmd.extend(["--api-token", api_token])

    t0 = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=WPSCAN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.warning("wpscan timed out after %ds for %s", WPSCAN_TIMEOUT, domain)
        return {"status": "timeout", "domain": domain, "wpscan": {}}
    except FileNotFoundError:
        log.error("wpscan binary not found")
        return {"status": "error", "domain": domain, "wpscan": {}, "error": "binary not found"}

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Exit code 4 = not WordPress (should not happen with --force)
    if result.returncode == 4:
        log.warning(
            "wpscan: %s exit 4 despite --force — stderr: %s — stdout: %s",
            domain, result.stderr[:500], result.stdout[:500],
        )
        return {
            "status": "not_wordpress",
            "domain": domain,
            "wpscan": {},
            "exit_code": 4,
            "duration_ms": elapsed_ms,
        }

    # Exit codes 0 (clean) and 5 (vulns found) are valid
    if result.returncode not in (0, 5):
        log.warning(
            "wpscan exited with code %d for %s: %s",
            result.returncode, domain, result.stderr[:500],
        )
        return {
            "status": "error",
            "domain": domain,
            "wpscan": {},
            "exit_code": result.returncode,
            "duration_ms": elapsed_ms,
        }

    # Parse JSON output
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log.warning("wpscan produced invalid JSON for %s", domain)
        return {
            "status": "error",
            "domain": domain,
            "wpscan": {},
            "exit_code": result.returncode,
            "duration_ms": elapsed_ms,
            "error": "invalid JSON output",
        }

    # Extract structured results
    wp_version = data.get("version", {})
    plugins = data.get("plugins", {})
    main_theme = data.get("main_theme", {})
    vulns = []

    # Core vulnerabilities
    if isinstance(wp_version, dict):
        for v in wp_version.get("vulnerabilities", []):
            vulns.append({
                "title": v.get("title", ""),
                "type": "wordpress_core",
                "fixed_in": v.get("fixed_in", ""),
            })

    # Plugin vulnerabilities
    for plugin_name, plugin_data in plugins.items():
        if not isinstance(plugin_data, dict):
            continue
        for v in plugin_data.get("vulnerabilities", []):
            vulns.append({
                "title": v.get("title", ""),
                "type": "plugin",
                "plugin": plugin_name,
                "fixed_in": v.get("fixed_in", ""),
            })

    # Theme vulnerabilities (main_theme + any additional themes)
    if isinstance(main_theme, dict):
        for v in main_theme.get("vulnerabilities", []):
            vulns.append({
                "title": v.get("title", ""),
                "type": "theme",
                "fixed_in": v.get("fixed_in", ""),
            })
    for theme_name, theme_data in data.get("themes", {}).items():
        if not isinstance(theme_data, dict):
            continue
        for v in theme_data.get("vulnerabilities", []):
            vulns.append({
                "title": v.get("title", ""),
                "type": "theme",
                "theme": theme_name,
                "fixed_in": v.get("fixed_in", ""),
            })

    parsed = {
        "vulnerabilities": vulns,
        "wordpress": {
            "version": wp_version.get("number", "") if isinstance(wp_version, dict) else "",
            "status": wp_version.get("status", "") if isinstance(wp_version, dict) else "",
        },
        "plugins": [
            {
                "name": name,
                "version": pd.get("version", {}).get("number", "") if isinstance(pd.get("version"), dict) else "",
                "outdated": pd.get("outdated", False),
                "vuln_count": len(pd.get("vulnerabilities", [])),
            }
            for name, pd in plugins.items()
            if isinstance(pd, dict)
        ],
    }

    log.info("wpscan_complete", extra={"context": {
        "domain": domain,
        "exit_code": result.returncode,
        "vuln_count": len(vulns),
        "plugin_count": len(plugins),
        "duration_ms": elapsed_ms,
    }})

    return {
        "status": "completed",
        "domain": domain,
        "wpscan": parsed,
        "exit_code": result.returncode,
        "duration_ms": elapsed_ms,
    }


def _process_job(job: dict, conn: redis_lib.Redis) -> None:
    """Process a single WPScan job."""
    job_id = job.get("job_id", "")
    domain = job.get("domain", "")

    if not domain:
        log.warning("wpscan job missing domain — skipping")
        return

    response_key = f"wpscan:result:{job_id}"
    cache_key = f"cache:wpscan:{domain}"

    # Check cache first
    cached = conn.get(cache_key)
    if cached is not None:
        try:
            cached_result = json.loads(cached)
            result = {
                "job_id": job_id,
                "domain": domain,
                "status": cached_result.get("status", "completed"),
                "wpscan": cached_result.get("wpscan", cached_result),
                "cached": True,
            }
            conn.lpush(response_key, json.dumps(result))
            conn.expire(response_key, RESPONSE_KEY_TTL)
            log.debug("wpscan cache hit for %s", domain)
            return
        except (json.JSONDecodeError, TypeError):
            pass  # Cache corrupt — run fresh scan

    # Run WPScan
    log.info("wpscan_running", extra={"context": {"job_id": job_id, "domain": domain}})
    scan_result = _run_wpscan(domain)
    log.info("wpscan_finished", extra={"context": {
        "job_id": job_id, "domain": domain,
        "status": scan_result.get("status", "unknown"),
        "exit_code": scan_result.get("exit_code", ""),
        "duration_ms": scan_result.get("duration_ms", ""),
        "error": scan_result.get("error", ""),
    }})

    # Build response
    result = {
        "job_id": job_id,
        "domain": domain,
        **scan_result,
    }

    # Push response to worker
    conn.lpush(response_key, json.dumps(result))
    conn.expire(response_key, RESPONSE_KEY_TTL)

    # Cache successful results
    if scan_result["status"] in ("completed", "not_wordpress"):
        conn.setex(cache_key, CACHE_TTL, json.dumps(scan_result))


def main(argv: Optional[list] = None) -> None:
    """Sidecar main loop: connect to Redis, BRPOP for WPScan jobs."""
    args = _parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    log.info("WPScan sidecar starting")

    # Connect to Redis
    try:
        conn = redis_lib.Redis.from_url(
            args.redis_url,
            decode_responses=True,
            socket_connect_timeout=10,
        )
        conn.ping()
    except (redis_lib.ConnectionError, redis_lib.TimeoutError, OSError) as exc:
        log.error("Cannot connect to Redis at %s: %s", args.redis_url, exc)
        raise SystemExit(1)

    log.info("Connected to Redis at %s", args.redis_url)

    # Signal handlers
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log.info("WPScan sidecar ready — waiting for jobs on queue:wpscan")

    while not _shutdown_requested:
        try:
            item = conn.brpop("queue:wpscan", timeout=30)
        except (redis_lib.ConnectionError, redis_lib.TimeoutError) as exc:
            log.warning("Redis BRPOP error: %s — retrying", exc)
            continue

        if item is None:
            continue

        _queue_name, raw_job = item

        try:
            job = json.loads(raw_job)
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("Malformed WPScan job JSON: %s — skipping", exc)
            continue

        log.info("wpscan_job_received", extra={"context": {
            "job_id": job.get("job_id", ""),
            "domain": job.get("domain", ""),
        }})

        try:
            _process_job(job, conn)
        except Exception:
            log.exception("Unhandled error processing WPScan job for %s", job.get("domain", "unknown"))

    log.info("WPScan sidecar shut down gracefully")
