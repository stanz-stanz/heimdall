"""Finding interpreter — transforms raw scan briefs into client-ready reports.

Takes a scan brief dict (from the worker), calls the configured LLM backend,
and returns a structured interpretation suitable for message composition.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from loguru import logger

from .llm import LLMError, _load_config, complete
from .prompts import build_system_prompt, build_user_prompt


def interpret_brief(
    brief: dict,
    tone: Optional[str] = None,
    language: Optional[str] = None,
    delta_context: Optional[dict] = None,
) -> dict:
    """Interpret a scan brief into a client-ready report.

    Parameters
    ----------
    brief : dict
        The scan brief as produced by ``brief_generator.generate_brief``.
    tone : str, optional
        Override the tone from config ("concise", "balanced", "detailed").
    language : str, optional
        Override the language from config ("da", "en").

    Returns
    -------
    dict
        Interpreted report with keys: ``good_news``, ``findings``,
        ``summary``, ``domain``, ``company_name``, ``scan_date``,
        ``meta`` (timing, tokens, model).

    Raises
    ------
    InterpreterError
        If the LLM call fails or the response cannot be parsed.
    """
    config = _load_config()
    tone = tone or config.get("tone", "balanced")
    language = language or config.get("language", "da")

    tone_descriptions = config.get("tone_descriptions", {})
    tone_description = tone_descriptions.get(tone, tone_descriptions.get("balanced", ""))

    system = build_system_prompt(
        industry=brief.get("industry", ""),
        tone=tone,
        tone_description=tone_description,
        language=language,
    )
    user = build_user_prompt(brief, delta_context=delta_context)

    t0 = time.monotonic()
    try:
        raw_response = complete(user, system=system)
    except LLMError as exc:
        raise InterpreterError(f"LLM call failed: {exc}") from exc
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Parse the JSON response
    try:
        interpreted = _parse_response(raw_response)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.bind(context={
            "domain": brief.get("domain"),
            "error": str(exc),
            "raw_response": raw_response[:500],
        }).warning("interpret_parse_error")
        raise InterpreterError(f"Failed to parse LLM response: {exc}") from exc

    # Attach metadata
    interpreted["domain"] = brief.get("domain", "")
    interpreted["company_name"] = brief.get("company_name", "")
    interpreted["scan_date"] = brief.get("scan_date", "")
    interpreted["meta"] = {
        "tone": tone,
        "language": language,
        "model": config.get("model", "unknown"),
        "duration_ms": elapsed_ms,
    }

    logger.bind(context={
        "domain": brief.get("domain"),
        "findings_in": len(brief.get("findings", [])),
        "findings_out": len(interpreted.get("findings", [])),
        "duration_ms": elapsed_ms,
        "tone": tone,
    }).info("brief_interpreted")

    return interpreted


def _parse_response(raw: str) -> dict:
    """Parse the LLM JSON response, extracting JSON robustly.

    Finds the first ``{`` and last ``}`` in the response to handle
    preamble text, markdown fences, and trailing commentary.
    """
    text = raw.strip()

    # Find the JSON object boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        raise ValueError(f"No JSON object found in response (len={len(text)})")

    json_str = text[first_brace:last_brace + 1]
    parsed = json.loads(json_str)

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected dict, got {type(parsed).__name__}")

    if "findings" not in parsed:
        raise ValueError("Response missing 'findings' key")

    if not isinstance(parsed["findings"], list):
        raise ValueError("'findings' must be a list")

    parsed.setdefault("good_news", [])
    parsed.setdefault("summary", "")

    return parsed


class InterpreterError(Exception):
    """Raised when interpretation fails."""
