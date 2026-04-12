"""crt.sh Certificate Transparency log queries."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from loguru import logger

from src.core.config import USER_AGENT
from src.prospecting.config import CRT_SH_API_URL, CRT_SH_DELAY

MAX_WORKERS_API = 5  # rate-limited API queries


def query_crt_sh_single(domain: str) -> tuple:
    """Query crt.sh for a single domain. Returns (domain, certs_list)."""
    try:
        time.sleep(CRT_SH_DELAY)  # rate limit even within thread pool
        resp = requests.get(
            f"{CRT_SH_API_URL}/?q=%.{domain}&output=json",
            timeout=30,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            logger.debug("crt.sh returned {} for {}", resp.status_code, domain)
            return domain, []

        data = resp.json()
        if not isinstance(data, list):
            return domain, []

        seen = set()
        certs = []
        for entry in data:
            cn = entry.get("common_name", "")
            if not cn or cn in seen:
                continue
            seen.add(cn)
            name_value = entry.get("name_value", "") or ""
            sans = sorted({
                n.strip().lower()
                for n in name_value.splitlines()
                if n.strip()
            })
            certs.append({
                "common_name": cn,
                "issuer_name": entry.get("issuer_name", ""),
                "not_before": entry.get("not_before", ""),
                "not_after": entry.get("not_after", ""),
                "sans": sans,
            })
        return domain, certs

    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning("crt.sh query failed for {}: {}", domain, e)
        return domain, []


def query_crt_sh(domains: list[str]) -> dict[str, list[dict]]:
    """Layer 1 / Level 0 — Certificate Transparency log query via crt.sh API.

    Queries a third-party public index. No requests to the target's infrastructure.
    Uses thread pool with rate limiting for concurrent queries.
    """
    results: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_API) as executor:
        futures = {executor.submit(query_crt_sh_single, d): d for d in domains}
        for future in as_completed(futures):
            try:
                domain, certs = future.result()
                if certs:
                    results[domain] = certs
            except Exception as e:
                logger.warning("crt.sh thread error: {}", e)

    logger.info("crt.sh: found certificates for {}/{} domains", len(results), len(domains))
    return results
