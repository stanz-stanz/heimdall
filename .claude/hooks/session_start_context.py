#!/usr/bin/env python3
"""SessionStart hook — inject current git state and priority rules.

Runs once at session start (or resume). Gathers branch, status, recent
commits, and the latest decision log headline. Adds a reminder of the
top priority rules the other hooks enforce.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

TOP_RULES = [
    ("DEAL BREAKER", "You present alternatives; Federico decides. Never make product, architecture, or technical decisions autonomously."),
    ("Infra danger zone", "Before editing .gitignore, docker-compose, Dockerfile, .env, workflows, or pyproject.toml: read docs/decisions/log.md. (A hook injects it automatically, but the reminder matters.)"),
    ("Destructive git", "git reset --hard, git checkout --, git restore ., git clean -f are all blocked by hook — never try to route around them."),
]


def run(cmd, cwd):
    try:
        return subprocess.check_output(
            cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], project_dir) or "unknown"
    status = run(["git", "status", "--short"], project_dir)
    recent = run(["git", "log", "--oneline", "-5"], project_dir)

    log_path = Path(project_dir) / "docs" / "decisions" / "log.md"
    log_headline = ""
    log_age_note = ""
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.startswith("## 20"):
                    log_headline = line[3:].strip()[:120]
                    break
        except OSError:
            pass
        try:
            mtime = log_path.stat().st_mtime
            age_days = (time.time() - mtime) / 86400
            if age_days > 10:
                log_age_note = f" (last updated {int(age_days)} days ago — verify anything you recall)"
        except OSError:
            pass

    parts = ["SESSION CONTEXT (auto-injected)", "", f"Branch: {branch}"]

    status_lines = [ln for ln in status.split("\n") if ln.strip()][:5]
    if status_lines:
        parts.append("Working tree:")
        for line in status_lines:
            parts.append(f"  {line}")

    if recent:
        parts.append("Recent commits:")
        for line in recent.split("\n"):
            parts.append(f"  {line}")

    if log_headline:
        parts.append(f"Last decision log entry: {log_headline}{log_age_note}")

    parts.append("")
    parts.append("TOP PRIORITY RULES (most are hook-enforced, but stay aware):")
    for tag, rule in TOP_RULES:
        parts.append(f"  [{tag}] {rule}")

    context = "\n".join(parts)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
