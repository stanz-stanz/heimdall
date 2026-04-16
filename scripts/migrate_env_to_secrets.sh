#!/usr/bin/env bash
# Split Heimdall credentials out of a .env file into individual
# files compatible with Docker Compose `secrets:` blocks.
#
# Idempotent: re-running is safe. If a target secret file already exists
# on disk, that secret is skipped entirely (no overwrite, no source removal).
#
# Usage:
#   scripts/migrate_env_to_secrets.sh --env <path-to-env> --out <secrets-dir>
#
# Examples:
#   Pi5:  scripts/migrate_env_to_secrets.sh --env infra/compose/.env     --out infra/compose/secrets
#   Mac:  scripts/migrate_env_to_secrets.sh --env infra/compose/.env.dev --out infra/compose/secrets.dev
#
# What it does, per credential:
#   1. Extract VALUE from KEY=VALUE line in the env file (supports quoted values)
#   2. If the target file does not exist yet: write it with chmod 600
#   3. Remove the KEY=... line from the env file (backup: <env>.pre-secrets)
#
# Credentials migrated (keep in sync with docker-compose.yml secrets: block):
#   TELEGRAM_BOT_TOKEN     -> telegram_bot_token
#   CLAUDE_API_KEY         -> claude_api_key
#   CONSOLE_PASSWORD       -> console_password
#   CERTSPOTTER_API_KEY    -> certspotter_api_key
#   GRAYHATWARFARE_API_KEY -> grayhatwarfare_api_key
#
# Not migrated (identifiers / config, stay as env vars):
#   CONSOLE_USER, TELEGRAM_OPERATOR_CHAT_ID, HEIMDALL_BACKUP_DIR,
#   SERPER_API_KEY (CLI-only, not a container secret), TAILSCALE_AUTH_KEY
#   (shell-level, not used by any container).

set -euo pipefail

ENV_PATH=""
OUT_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --env)  ENV_PATH="$2"; shift 2 ;;
        --out)  OUT_DIR="$2";  shift 2 ;;
        -h|--help)
            sed -n '2,29p' "$0"
            exit 0
            ;;
        *) echo "unknown arg: $1"; exit 2 ;;
    esac
done

[ -z "$ENV_PATH" ] && { echo "error: --env required"; exit 2; }
[ -z "$OUT_DIR" ]  && { echo "error: --out required"; exit 2; }
[ -f "$ENV_PATH" ] || { echo "error: env file not found: $ENV_PATH"; exit 1; }

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"

# KEY:filename pairs — add new credentials here only.
PAIRS=(
    "TELEGRAM_BOT_TOKEN:telegram_bot_token"
    "CLAUDE_API_KEY:claude_api_key"
    "CONSOLE_PASSWORD:console_password"
    "CERTSPOTTER_API_KEY:certspotter_api_key"
    "GRAYHATWARFARE_API_KEY:grayhatwarfare_api_key"
)

# Back up env file once; leave in place for rollback.
BACKUP="${ENV_PATH}.pre-secrets"
if [ ! -f "$BACKUP" ]; then
    cp "$ENV_PATH" "$BACKUP"
    echo "backed up env to: $BACKUP"
fi

migrated=0
skipped=0
missing=0

for pair in "${PAIRS[@]}"; do
    key="${pair%%:*}"
    fname="${pair##*:}"
    target="$OUT_DIR/$fname"

    if [ -f "$target" ]; then
        echo "skip  $key -> $target (exists)"
        skipped=$((skipped + 1))
        continue
    fi

    # Extract value. Supports KEY=value, KEY="value", KEY='value'.
    # Ignores comment lines. Keeps the first non-empty match.
    value=$(grep -E "^${key}=" "$ENV_PATH" \
            | head -n 1 \
            | sed -E "s/^${key}=//; s/^['\"]//; s/['\"]$//")

    if [ -z "$value" ]; then
        echo "miss  $key (not set in $ENV_PATH, skipping)"
        missing=$((missing + 1))
        continue
    fi

    # Write without trailing newline; helper will .strip() anyway.
    printf '%s' "$value" > "$target"
    chmod 600 "$target"

    # Remove line from env file (macOS + GNU sed compat via portable -i '').
    # Delete ALL lines beginning with KEY= (not just the first) to avoid
    # leaving stale duplicates.
    if sed --version >/dev/null 2>&1; then
        sed -i -E "/^${key}=.*/d" "$ENV_PATH"
    else
        sed -i '' -E "/^${key}=.*/d" "$ENV_PATH"
    fi

    echo "move  $key -> $target"
    migrated=$((migrated + 1))
done

echo
echo "migrated: $migrated  skipped: $skipped  missing: $missing"
echo "env file: $ENV_PATH"
echo "secrets:  $OUT_DIR"
if [ "$migrated" -gt 0 ]; then
    echo "backup:   $BACKUP (keep until next successful deploy)"
fi
