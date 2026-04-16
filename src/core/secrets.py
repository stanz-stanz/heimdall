"""Read secrets from Docker Compose `secrets:` mounts with env-var fallback.

In production, Docker mounts each declared secret at `/run/secrets/<name>`.
In tests and local runs outside a container, fall back to `os.environ`.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

_SECRETS_DIR = Path("/run/secrets")
_env_fallback_warned: set[str] = set()


def get_secret(file_name: str, env_name: str, default: str = "") -> str:
    """Return the secret value or `default` if unset.

    Lookup order: /run/secrets/<file_name>, then os.environ[<env_name>].
    Trailing whitespace is stripped from file contents.

    Logs a one-shot WARNING per secret when the env fallback is used
    while the secrets dir exists — that pattern signals a misconfigured
    container (secret not mounted) rather than a legitimate local run.
    """
    secret_path = _SECRETS_DIR / file_name
    if secret_path.is_file():
        return secret_path.read_text().strip()

    value = os.environ.get(env_name, default)
    if value and _SECRETS_DIR.is_dir() and env_name not in _env_fallback_warned:
        _env_fallback_warned.add(env_name)
        logger.warning(
            "secret {} read from env fallback; expected /run/secrets/{}",
            env_name,
            file_name,
        )
    return value
