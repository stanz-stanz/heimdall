"""Domain resolver: check if website exists, respect robots.txt, discard dead domains."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.robotparser import RobotFileParser

import requests

from pipeline.config import REQUEST_TIMEOUT, USER_AGENT
from pipeline.cvr import Company

log = logging.getLogger(__name__)

MAX_WORKERS = 20


def _check_robots_txt(domain: str) -> bool:
    """Return True if robots.txt allows our user agent. Return True if no robots.txt found."""
    rp = RobotFileParser()
    robots_url = f"https://{domain}/robots.txt"
    try:
        resp = requests.get(robots_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            return rp.can_fetch(USER_AGENT, f"https://{domain}/")
    except requests.RequestException:
        pass
    return True


def _check_website(domain: str) -> tuple[bool, str]:
    """Try to reach the domain. Tries HTTPS first, falls back to HTTP."""
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            resp = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            if resp.status_code < 400:
                return True, resp.url
        except requests.RequestException:
            continue
    return False, ""


def _resolve_single(company: Company) -> None:
    """Resolve a single company's domain. Mutates company in place."""
    domain = company.website_domain

    alive, _ = _check_website(domain)
    if not alive:
        company.discard_reason = "no_website"
        return

    if not _check_robots_txt(domain):
        company.discard_reason = "robots_txt_denied"
        return


def resolve_domains(companies: list[Company]) -> list[Company]:
    """Check each company's derived domain for a live website and robots.txt compliance."""
    to_check = [c for c in companies if not c.discarded and c.website_domain]

    # Deduplicate domains — only resolve each domain once
    domain_to_companies: dict[str, list[Company]] = {}
    for c in to_check:
        domain_to_companies.setdefault(c.website_domain, []).append(c)

    unique_domains = list(domain_to_companies.keys())
    log.info("Resolving %d unique domains (%d companies)", len(unique_domains), len(to_check))

    # Use first company per domain as the probe; propagate result to all sharing that domain
    probes = {d: cs[0] for d, cs in domain_to_companies.items()}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_resolve_single, c): d for d, c in probes.items()}
        done = 0
        for future in as_completed(futures):
            done += 1
            domain = futures[future]
            try:
                future.result()
            except Exception as e:
                log.warning("Error resolving %s: %s", domain, e)
                probes[domain].discard_reason = "resolve_error"

            # Propagate result to all companies sharing this domain
            probe = probes[domain]
            if probe.discard_reason:
                for c in domain_to_companies[domain]:
                    if c is not probe:
                        c.discard_reason = probe.discard_reason

            if done % 50 == 0:
                log.info("Resolved %d/%d domains", done, len(unique_domains))

    resolved = sum(1 for c in to_check if not c.discarded)
    log.info("Domain resolution complete: %d alive, %d discarded", resolved, len(to_check) - resolved)
    return companies
