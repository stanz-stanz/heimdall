#!/usr/bin/env python3
"""PreToolUse hook — block commands that would print secrets to stdout.

Uses shlex tokenization so dangerous patterns inside quoted arguments
(e.g. commit messages, echo strings) don't false-match.
"""
import json
import shlex
import sys

SECRET_SUFFIXES = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD")


def is_env_path(token: str) -> bool:
    """True if token looks like a path to an .env file."""
    if token == ".env":
        return True
    if token.endswith("/.env"):
        return True
    if token.startswith(".env.") or "/.env." in token:
        return True
    # Matches things like infra/docker/.env
    parts = token.split("/")
    return parts[-1].startswith(".env")


def check(tokens: list) -> str | None:
    """Return a reason string if command would expose secrets."""
    if not tokens:
        return None

    # Check for `source <path>.env` or `. <path>.env` at a command boundary.
    # Command boundaries are: start of tokens, after ;, &&, ||, |.
    separators = {";", "&&", "||", "|"}
    i = 0
    while i < len(tokens):
        # Find the start of a command segment
        if i > 0 and tokens[i - 1] not in separators:
            # Skip ahead to next separator
            while i < len(tokens) and tokens[i] not in separators:
                i += 1
            i += 1
            continue

        if i >= len(tokens):
            break

        first = tokens[i]
        rest = tokens[i + 1 :]

        # source <env> or . <env>
        if first in ("source", ".") and rest and is_env_path(rest[0]):
            return "sourcing .env can surface values in trace output"

        # cat <env>
        if first == "cat" and any(is_env_path(t) for t in rest):
            return "cat .env prints secrets to stdout"

        # bare env / printenv (no args = print all)
        if first in ("env", "printenv") and not rest:
            return f"bare '{first}' prints all environment variables"

        # echo of a secret variable reference
        if first == "echo":
            for t in rest:
                # $FOO_KEY, ${FOO_KEY}, "$FOO_KEY" forms
                stripped = t.strip('"').strip("'")
                if stripped.startswith("$"):
                    varname = stripped.lstrip("${").rstrip("}")
                    if any(varname.endswith(suffix) for suffix in SECRET_SUFFIXES):
                        return "echoing a secret env var to stdout"

        # Advance to next command segment
        while i < len(tokens) and tokens[i] not in separators:
            i += 1
        i += 1

    return None


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

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        sys.exit(0)

    reason = check(tokens)
    if reason is None:
        sys.exit(0)

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


if __name__ == "__main__":
    main()
