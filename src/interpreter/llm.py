"""LLM backend abstraction.

Ships with Anthropic (Claude API). Swap to Ollama by changing the
``backend`` field in ``config/interpreter.json`` — zero code changes
in the interpreter or composer.

Interface: ``complete(prompt, system) → str``
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "interpreter.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def complete(
    prompt: str,
    system: str = "",
    config_override: Optional[dict] = None,
) -> str:
    """Send a prompt to the configured LLM backend and return the response.

    Parameters
    ----------
    prompt : str
        The user message.
    system : str
        System prompt (role, tone, rules).
    config_override : dict, optional
        Override config values (for testing or per-call tuning).

    Returns
    -------
    str
        The LLM response text.

    Raises
    ------
    LLMError
        On any backend failure (network, auth, rate limit, etc.).
    """
    config = _load_config()
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


def _complete_anthropic(prompt: str, system: str, config: dict) -> str:
    """Call Claude API via the Anthropic SDK."""
    try:
        import anthropic
    except ImportError:
        raise LLMError("anthropic package not installed — pip install anthropic")

    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise LLMError("CLAUDE_API_KEY environment variable not set")

    t0 = time.monotonic()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config.get("model", "claude-sonnet-4-6"),
            max_tokens=config.get("max_output_tokens", 1024),
            temperature=config.get("temperature", 0.3),
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        log.info("llm_complete", extra={"context": {
            "backend": "anthropic",
            "model": config.get("model"),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "duration_ms": elapsed_ms,
        }})

        return text

    except anthropic.APIError as exc:
        raise LLMError(f"Anthropic API error: {exc}") from exc


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

        log.info("llm_complete", extra={"context": {
            "backend": "ollama",
            "model": model,
            "duration_ms": elapsed_ms,
        }})

        return text

    except (requests.RequestException, KeyError, ValueError) as exc:
        raise LLMError(f"Ollama error: {exc}") from exc
