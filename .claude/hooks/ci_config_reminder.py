#!/usr/bin/env python3
"""PostToolUse hook — remind about CI verification after editing config files.

Fires after Edit/Write to GitHub Actions workflows, pre-commit config,
pyproject.toml, or requirements.txt. Injects a reminder that local
pytest does not validate CI and new tools must be added to dep metadata.
"""
import json
import re
import sys

CI_CONFIG_PATTERNS = [
    r"\.github/workflows/.*\.ya?ml$",
    r"\.pre-commit-config\.yaml$",
    r"pyproject\.toml$",
    r"requirements\.txt$",
]

REMINDER = """CI/BUILD CONFIG MODIFIED: {file}

Local pytest does NOT validate CI. You must push and watch the run:
  git push && gh run watch $(gh run list --branch <branch> --limit 1 --json databaseId -q '.[0].databaseId')

If you added a tool (ruff, mypy, etc.), confirm it's in the project's dep
management — CI will fail otherwise:
  - Runtime deps → requirements.txt
  - Dev deps → [dependency-groups].dev in pyproject.toml
  - Or explicit pip install in the workflow itself

Past failure: ruff added to CI but not to requirements → every push failed
until the fix was shipped."""


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    if not any(re.search(p, file_path) for p in CI_CONFIG_PATTERNS):
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": REMINDER.format(file=file_path),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
