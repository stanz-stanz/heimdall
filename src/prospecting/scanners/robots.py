"""robots.txt compliance check."""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

import requests

from src.core.config import REQUEST_TIMEOUT, USER_AGENT


def check_robots_txt(domain: str) -> bool:
    """Layer 1 / Level 0 — Check if robots.txt allows automated access.

    Returns True if access is allowed, False if denied.
    Fetching robots.txt is permitted at all Layers — it is an explicitly published file.
    """
    try:
        resp = requests.get(
            f"https://{domain}/robots.txt",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return True  # No robots.txt — no restriction expressed
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch("*", "/")
    except requests.RequestException:
        return True  # Cannot fetch robots.txt — no restriction determinable
