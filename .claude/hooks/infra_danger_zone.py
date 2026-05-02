#!/usr/bin/env python3
"""PreToolUse hook — inject decision log context when editing infrastructure files.

Triggers on Edit/Write to files that have deployment or configuration impact.
Greps docs/decisions/log.md for relevant keywords and injects any matches
as additionalContext so the model sees the historical decisions before
making a change.

Exits 0 (allow through) — this is a context injector, not a blocker.
"""
import json
import os
import re
import sys
from pathlib import Path

DANGER_PATTERNS = [
    r"(^|/)\.gitignore$",
    r"(^|/)\.env(\.[^/]+)?$",
    r"(^|/)docker-compose.*\.ya?ml$",
    r"(^|/)Dockerfile(\..+)?$",
    r"(^|/)infra/",
    r"(^|/)\.github/workflows/",
    r"(^|/)pyproject\.toml$",
    r"(^|/)requirements\.txt$",
    r"(^|/)SCANNING_RULES\.md$",
    r"(^|/)CLAUDE\.md$",
    r"(^|/)\.pre-commit-config\.yaml$",
    r"(^|/)scripts/.*\.sh$",
]

KEYWORDS_BY_TYPE = {
    "gitignore": ["git commit", "track", "deploy", ".db", "sync"],
    "env": ["env var", "secret", "API key", "config"],
    "docker-compose": ["volume", "bind mount", "named volume", "container", "healthcheck"],
    "Dockerfile": ["build", "base image", "multi-stage", "ARM", "Pi5"],
    "workflows": ["CI", "GitHub Actions", "pytest", "ruff", "workflow"],
    "pyproject": ["dependency", "dev group", "ruff", "pytest", "uv"],
    "requirements": ["dependency", "pin", "version", "pip"],
    "SCANNING_RULES": ["layer", "consent", "robots", "Valdi"],
    "CLAUDE": ["CLAUDE.md", "instructions"],
    "scripts": ["alias", "heimdall-", "Pi5", "deploy"],
}


def file_type_key(file_path: str) -> str:
    name = os.path.basename(file_path).lower()
    if name == ".gitignore":
        return "gitignore"
    if name.startswith(".env"):
        return "env"
    if "docker-compose" in name:
        return "docker-compose"
    if name.startswith("dockerfile"):
        return "Dockerfile"
    if "/workflows/" in file_path.lower():
        return "workflows"
    if name == "pyproject.toml":
        return "pyproject"
    if name == "requirements.txt":
        return "requirements"
    if name == "scanning_rules.md":
        return "SCANNING_RULES"
    if name == "claude.md":
        return "CLAUDE"
    if file_path.endswith(".sh") and "scripts/" in file_path:
        return "scripts"
    return "generic"


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    if not any(re.search(p, file_path) for p in DANGER_PATTERNS):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    log_path = Path(project_dir) / "docs" / "decisions" / "log.md"
    if not log_path.exists():
        sys.exit(0)

    ftype = file_type_key(file_path)
    keywords = KEYWORDS_BY_TYPE.get(ftype, [])

    try:
        content = log_path.read_text(encoding="utf-8")
    except OSError:
        sys.exit(0)

    lines = content.split("\n")
    hits = []  # list of (keyword, [matching lines with context])
    # Walk bottom-up so the first matches we collect are the most recent
    # decisions (entries are appended chronologically to the log). Cap at
    # the 2 most recent matches per keyword: measured 24% byte reduction
    # vs the prior cap=3 oldest-first scheme on a representative
    # `.gitignore` injection, with significantly higher relevance because
    # months-old context is no longer surfaced ahead of current work.
    for kw in keywords:
        kw_lower = kw.lower()
        matches = []
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            if kw_lower in line.lower():
                start = max(0, i - 1)
                end = min(len(lines), i + 2)
                snippet = " | ".join(ln.strip()[:120] for ln in lines[start:end] if ln.strip())
                matches.append(snippet)
                if len(matches) >= 2:
                    break
        if matches:
            hits.append((kw, matches))

    if hits:
        parts = [f"DECISION LOG CONTEXT for {file_path}:"]
        for kw, matches in hits:
            parts.append(f"\n[keyword: {kw}]")
            for m in matches:
                parts.append(f"  {m}")
        parts.append(
            "\nIf your change conflicts with any of the above, STOP and reconsider."
        )
        context = "\n".join(parts)
    else:
        context = (
            f"NOTICE: editing {file_path} (infrastructure file). "
            f"No relevant entries in docs/decisions/log.md for keywords: {', '.join(keywords)}. "
            f"If your change affects deployment or git tracking, add a decision log entry."
        )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
