"""GrayHatWarfare exposed cloud storage search."""

from __future__ import annotations

import json

import requests
from loguru import logger

from src.prospecting.config import GRAYHATWARFARE_API_KEY


def query_grayhatwarfare(domains: list[str]) -> dict[str, list[dict]]:
    """Layer 1 / Level 0 — Exposed cloud storage search via GrayHatWarfare public index.

    Queries a third-party public index. No requests to the target's infrastructure.
    """
    if not GRAYHATWARFARE_API_KEY:
        logger.warning("GRAYHATWARFARE_API_KEY not set — skipping cloud storage search")
        return {}

    results: dict[str, list[dict]] = {}

    for domain in domains:
        try:
            resp = requests.get(
                "https://buckets.grayhatwarfare.com/api/v2/files",
                params={"keywords": domain},
                headers={"Authorization": f"Bearer {GRAYHATWARFARE_API_KEY}"},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.debug("GrayHatWarfare returned {} for {}", resp.status_code, domain)
                continue

            data = resp.json()
            files = data.get("files", [])
            if files:
                buckets: dict[str, int] = {}
                for f in files:
                    bucket_name = f.get("bucket", "unknown")
                    buckets[bucket_name] = buckets.get(bucket_name, 0) + 1

                results[domain] = [
                    {"bucket_name": name, "file_count": count}
                    for name, count in buckets.items()
                ]

        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.debug("GrayHatWarfare query failed for {}: {}", domain, e)

    logger.info("GrayHatWarfare: found exposed storage for {}/{} domains", len(results), len(domains))
    return results
