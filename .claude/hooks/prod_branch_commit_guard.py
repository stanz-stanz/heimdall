#!/usr/bin/env python3
"""PreToolUse hook — hard-block (deny) git commits on the prod branch.

Per Federico's directive 2026-05-02: commits to ``prod`` must never
happen by accident. The branching rule is:

    Features → branch + PR (merged to main, then prod fast-forwards)
    Bug fixes → direct to main (then prod fast-forwards)

A direct commit on ``prod`` bypasses the dev → main → prod gate
entirely, putting unreviewed code straight onto the deploy branch.

This hook fires PreToolUse / Bash, detects ``git commit`` on the
``prod`` branch, and DENIES the call (hard block). The previous
``permissionDecision: "ask"`` was silently auto-approved by Federico's
``skipAutoPermissionPrompt: true`` user setting, recreating the
2026-05-02 prod-commit accident on 2026-05-03. ``deny`` cannot be
auto-approved.

Bypass (rare hotfix only — e.g. broken alias on prod that blocks
future deploys, where the fix MUST land on prod first):

    HEIMDALL_PROD_COMMIT=1 git commit -m "..."

The hook does not validate the bypass intent — the friction itself
is the safety net. Federico typing the bypass prefix is a conscious
acknowledgement that he is bypassing the dev gate.
"""

import json
import os
import re
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
BYPASS_RE = re.compile(r"\bHEIMDALL_PROD_COMMIT=1\b")


def _current_branch(project_dir: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_dir,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        return out
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        sys.exit(0)

    if BYPASS_RE.search(command):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    branch = _current_branch(project_dir)
    if branch != "prod":
        sys.exit(0)

    reason = (
        "Refusing to commit on the prod branch. The branching rule is: "
        "features → branch + PR; bug fixes → main; prod only ever "
        "fast-forwards from main. A direct commit on prod bypasses the "
        "dev → main → prod gate. "
        "Switch to main with `git checkout main` and commit there, then "
        "fast-forward prod afterwards. "
        "If this is a deliberate prod-only hotfix (e.g. an alias bug that "
        "blocks future deploys), prefix the command with "
        "`HEIMDALL_PROD_COMMIT=1 git commit ...`."
    )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
