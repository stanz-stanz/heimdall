"""Search-based domain discovery: Serper (Google SERP) + Claude reasoning.

Layer 1 / No consent required — queries public search engines for company
website domains. Does not probe target domains directly.

Two-step approach:
1. Serper.dev returns Google search results for "{company} {city}"
2. Claude API picks the correct domain from those results
"""

from __future__ import annotations

import os
import re
import time
from functools import lru_cache

import requests
from loguru import logger

from src.core.secrets import get_secret

_RETRY_BACKOFF = [1, 3, 5]
_MAX_RETRIES = 3
_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

SERPER_URL = "https://google.serper.dev/search"


class SearchError(Exception):
    """Raised when search-based domain discovery fails."""


# ---------------------------------------------------------------------------
# Step 1: Serper Google Search
# ---------------------------------------------------------------------------


def _serper_search(query: str, api_key: str) -> list[dict]:
    """Query Serper.dev Google Search API. Returns list of organic result dicts.

    Each result has: title, link, snippet, position.
    1 credit per search. Free tier: 2,500 credits.
    """
    params = {
        "q": query,
        "gl": "dk",
        "apiKey": api_key,
    }

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(SERPER_URL, params=params, timeout=10)
            if resp.status_code == 429:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.bind(context={
                    "attempt": attempt + 1, "wait": wait,
                }).warning("serper_rate_limited")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "position": item.get("position", 0),
                }
                for item in data.get("organic", [])
            ]
        except requests.RequestException as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.bind(context={
                    "attempt": attempt + 1, "wait": wait, "error": str(exc),
                }).warning("serper_search_retry")
                time.sleep(wait)
            else:
                raise SearchError(f"Serper search failed: {exc}") from exc

    return []


# ---------------------------------------------------------------------------
# Step 2: Claude picks the right domain
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_anthropic_client():
    """Get or create a cached Anthropic client."""
    try:
        import anthropic
    except ImportError:
        raise SearchError("anthropic package not installed — pip install anthropic")

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise SearchError("CLAUDE_API_KEY environment variable not set")

    return anthropic.Anthropic(api_key=api_key, timeout=30)


def _pick_domain_with_claude(
    company_name: str, city: str, search_results: list[dict],
) -> tuple[str, str]:
    """Ask Claude to pick the correct website domain from search results.

    Returns (domain, reasoning).
    """
    import anthropic

    results_text = "\n".join(
        f"{r['position']}. {r['title']}\n   URL: {r['link']}\n   {r['snippet']}"
        for r in search_results
    )

    prompt = (
        f'The Danish company "{company_name}" is located in {city}.\n\n'
        f"Here are Google search results:\n\n{results_text}\n\n"
        f"Which result is the company's own official website? "
        f"Return ONLY the domain (e.g. toscanavejle.dk), nothing else. "
        f"Ignore review sites (TripAdvisor, Trustpilot, Google Maps), social media, "
        f"and directory listings. If none of the results is the company's own website, "
        f"respond with NONE."
    )

    client = _get_anthropic_client()

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=128,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        logger.bind(context={
            "company": company_name,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }).info("claude_pick_complete")

        domain = _extract_domain_from_response(text)
        return domain, f"Claude picked: {text}\n\nFrom results:\n{results_text}"

    except anthropic.APIError as exc:
        raise SearchError(f"Claude API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Domain extraction helper
# ---------------------------------------------------------------------------


def _extract_domain_from_response(text: str) -> str:
    """Parse a domain from Claude's response text.

    Handles responses like:
    - "toscanavejle.dk"
    - "https://toscanavejle.dk"
    - "The website is toscanavejle.dk"
    - "NONE"
    """
    if not text:
        return ""

    text = text.strip()
    if text.upper() == "NONE":
        return ""

    for line in text.split("\n"):
        line = line.strip()
        line = re.sub(r"^https?://", "", line)
        line = re.sub(r"/.*$", "", line)
        line = line.strip().lower()
        if _DOMAIN_RE.match(line):
            return line

    match = re.search(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?\.(?:dk|com|eu|net|org|io))", text.lower())
    if match:
        return match.group(1)

    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_company_domain(
    company_name: str,
    city: str,
    delay: float = 0.5,
) -> tuple[str, str]:
    """Find a company's website domain using Serper (Google) + Claude reasoning.

    Step 1: Serper.dev returns Google results for "{company_name} {city}"
    Step 2: Claude picks the correct domain from the 10 results

    Returns (domain, detail) where domain is the discovered domain (or "")
    and detail is the full audit trail.

    Requires SERPER_API_KEY + CLAUDE_API_KEY (compose secret or env var).
    """
    serper_api_key = get_secret("serper_api_key", "SERPER_API_KEY")

    if not serper_api_key:
        raise SearchError(
            "SERPER_API_KEY not set (secret file or env var). "
            "Sign up at https://serper.dev/"
        )

    # Step 1: Google search via Serper
    query = f"{company_name} {city}"
    results = _serper_search(query, serper_api_key)

    if not results:
        detail = f"Serper returned 0 results for: {query}"
        logger.bind(context={
            "company": company_name, "query": query,
        }).info("serper_no_results")
        return "", detail

    logger.bind(context={
        "company": company_name,
        "query": query,
        "result_count": len(results),
    }).info("serper_search_complete")

    # Step 2: Claude picks the domain
    domain, detail = _pick_domain_with_claude(company_name, city, results)

    if delay > 0:
        time.sleep(delay)

    return domain, detail
