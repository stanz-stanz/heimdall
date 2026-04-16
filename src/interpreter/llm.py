"""LLM backend abstraction.

Ships with Anthropic (Claude API). Swap to Ollama by changing the
``backend`` field in ``config/interpreter.json`` — zero code changes
in the interpreter or composer.

Interface: ``complete(prompt, system) → str``
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path

from loguru import logger

from src.core.secrets import get_secret

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "interpreter.json"

# Retry settings for transient failures (429, 500, 503, 529)
_MAX_RETRIES = 3
_RETRY_BACKOFF = [1, 3, 5]  # seconds between retries

# Anthropic client timeout (seconds) — prevents thread pile-up on Pi5
_ANTHROPIC_TIMEOUT = 60


@lru_cache(maxsize=1)
def _load_config() -> dict:
    """Load interpreter config (cached — config is static at runtime)."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def complete(
    prompt: str,
    system: str = "",
    config_override: dict | None = None,
) -> str:
    """Send a prompt to the configured LLM backend and return the response.

    Retries up to 3 times on transient failures (429, 5xx).

    Raises
    ------
    LLMError
        On permanent failure or retries exhausted.
    """
    config = {**_load_config()}  # shallow copy to avoid mutating cache
    if config_override:
        config.update(config_override)

    backend = config.get("backend", "anthropic")

    if backend == "anthropic":
        return _complete_anthropic(prompt, system, config)
    elif backend == "ollama":
        return _complete_ollama(prompt, system, config)
    else:
        raise LLMError(f"Unknown LLM backend: {backend}")


class LLMError(Exception):
    """Raised when the LLM backend fails."""


# Cached Anthropic client (one per API key, reuses connection pool)
_anthropic_client = None
_anthropic_client_key = None


def _get_anthropic_client():
    """Get or create a cached Anthropic client."""
    global _anthropic_client, _anthropic_client_key
    try:
        import anthropic
    except ImportError:
        raise LLMError("anthropic package not installed — pip install anthropic")

    api_key = get_secret("claude_api_key", "CLAUDE_API_KEY")
    if not api_key:
        raise LLMError("CLAUDE_API_KEY not set (secret file or env var)")

    if _anthropic_client is None or _anthropic_client_key != api_key:
        _anthropic_client = anthropic.Anthropic(
            api_key=api_key,
            timeout=_ANTHROPIC_TIMEOUT,
        )
        _anthropic_client_key = api_key

    return _anthropic_client


def _complete_anthropic(prompt: str, system: str, config: dict) -> str:
    """Call Claude API via the Anthropic SDK with retry on transient errors."""
    import anthropic

    client = _get_anthropic_client()
    last_error = None

    for attempt in range(_MAX_RETRIES):
        t0 = time.monotonic()
        try:
            response = client.messages.create(
                model=config.get("model", "claude-sonnet-4-6"),
                max_tokens=config.get("max_output_tokens", 1024),
                temperature=config.get("temperature", 0.3),
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            # Check for truncation
            stop_reason = response.stop_reason
            if stop_reason == "max_tokens":
                logger.bind(context={
                    "model": config.get("model"),
                    "max_tokens": config.get("max_output_tokens"),
                    "output_tokens": response.usage.output_tokens,
                }).warning("llm_truncated")

            logger.bind(context={
                "backend": "anthropic",
                "model": config.get("model"),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "stop_reason": stop_reason,
                "duration_ms": elapsed_ms,
                "attempt": attempt + 1,
            }).info("llm_complete")

            return response.content[0].text

        except anthropic.RateLimitError as exc:
            last_error = exc
            _retry_wait(attempt, "rate_limited", config)
        except anthropic.InternalServerError as exc:
            last_error = exc
            _retry_wait(attempt, "server_error", config)
        except anthropic.APIConnectionError as exc:
            last_error = exc
            _retry_wait(attempt, "connection_error", config)
        except anthropic.APIError as exc:
            # Non-retryable (auth, bad request, etc.)
            raise LLMError(f"Anthropic API error: {exc}") from exc

    raise LLMError(f"Anthropic API failed after {_MAX_RETRIES} retries: {last_error}") from last_error


def _retry_wait(attempt: int, reason: str, config: dict) -> None:
    """Log and sleep before retry."""
    if attempt < len(_RETRY_BACKOFF):
        wait = _RETRY_BACKOFF[attempt]
    else:
        wait = _RETRY_BACKOFF[-1]
    logger.bind(context={
        "reason": reason,
        "attempt": attempt + 1,
        "max_retries": _MAX_RETRIES,
        "wait_seconds": wait,
        "model": config.get("model"),
    }).warning("llm_retry")
    time.sleep(wait)


def _complete_ollama(prompt: str, system: str, config: dict) -> str:
    """Call a local Ollama instance."""
    import requests

    base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = config.get("model", "llama3")

    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": config.get("temperature", 0.3),
                    "num_predict": config.get("max_output_tokens", 1024),
                },
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.bind(context={
            "backend": "ollama",
            "model": model,
            "duration_ms": elapsed_ms,
        }).info("llm_complete")

        return text

    except (requests.RequestException, KeyError, ValueError) as exc:
        raise LLMError(f"Ollama error: {exc}") from exc
