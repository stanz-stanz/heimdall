#!/usr/bin/env python3
"""PreToolUse hook — block commands that would print secrets to stdout.

Sourcing .env, cat .env, bare env/printenv, and echo of *_KEY/*_TOKEN/etc
are all ways credentials leak into the conversation transcript.
"""
import json
import re
import sys

SECRET_PATTERNS = [
    (r"(^|\s|;|&&|\|\|)source\s+\S*\.env\b", "sourcing .env can surface values in trace output"),
    (r"(^|\s|;|&&|\|\|)\.\s+\S*\.env\b", "sourcing .env can surface values in trace output"),
    (r"\bcat\s+[^|]*\.env\b", "cat .env prints secrets to stdout"),
    (r"(^|;|&&|\|\|)\s*env\s*$", "bare 'env' prints all environment variables"),
    (r"(^|;|&&|\|\|)\s*printenv\s*$", "bare 'printenv' prints all environment variables"),
    (
        r"\becho\s+[^\n]*\$\{?[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD)\}?",
        "echoing a secret env var to stdout",
    ),
]


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    for pattern, reason in SECRET_PATTERNS:
        if re.search(pattern, command):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Secret exposure risk: {reason}. "
                        f"Read credentials via explicit single-var reads instead."
                    ),
                }
            }
            print(json.dumps(output))
            sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
