#!/usr/bin/env python3
"""PreToolUse hook — soft-block pushes to main when they contain src/ Python changes.

Per feedback_git_branching_rule: features go via branch + PR. Only bug
fixes commit directly to main. If a push to main contains new src/**/*.py
diffs, prompt the user to confirm.
"""
import json
import os
import re
import subprocess
import sys

PUSH_MAIN_RE = re.compile(r"\bgit\s+push\s+(?:-[^\s]+\s+)*origin\s+main(?![\w.-])")


def run(cmd, cwd):
    try:
        return subprocess.check_output(
            cmd, cwd=cwd, stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not PUSH_MAIN_RE.search(command):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], project_dir)
    if branch != "main":
        sys.exit(0)

    diff_files = run(
        ["git", "log", "origin/main..HEAD", "--name-only", "--pretty=format:"],
        project_dir,
    )
    feature_changes = [
        f for f in diff_files.split("\n") if f.startswith("src/") and f.endswith(".py")
    ]

    if not feature_changes:
        sys.exit(0)

    sample = ", ".join(feature_changes[:3])
    more = f" (+{len(feature_changes) - 3} more)" if len(feature_changes) > 3 else ""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"Pushing to main with {len(feature_changes)} src/ Python file(s) changed: "
                f"{sample}{more}. Per feedback_git_branching_rule: features → branch + PR; "
                f"bug fixes → direct. Confirm this is a bug fix."
            ),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
