#!/usr/bin/env bash
# Heimdall health check — runs via cron every 5 minutes.
# Checks container health and restart counts. Alerts operator via Telegram.
#
# Cron setup: */5 * * * * /path/to/heimdall/scripts/healthcheck.sh
#
# Required env vars (set in crontab or .env):
#   TELEGRAM_BOT_TOKEN, TELEGRAM_OPERATOR_CHAT_ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${TELEGRAM_OPERATOR_CHAT_ID:-}"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_OPERATOR_CHAT_ID must be set" >&2
    exit 1
fi

send_alert() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d chat_id="$CHAT_ID" \
        -d text="$message" \
        -d parse_mode="HTML" > /dev/null 2>&1
}

COMPOSE_DIR="$PROJECT_DIR/infra/compose"
ALERTS=""

# Check each service's health status
for service in redis worker api delivery scheduler ct-collector; do
    container=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps -q "$service" 2>/dev/null | head -1)
    [ -z "$container" ] && continue

    health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no-healthcheck")
    restarts=$(docker inspect --format='{{.RestartCount}}' "$container" 2>/dev/null || echo "0")

    if [ "$health" = "unhealthy" ]; then
        ALERTS="${ALERTS}\n- ${service}: UNHEALTHY"
    fi
    if [ "$restarts" -gt 2 ]; then
        ALERTS="${ALERTS}\n- ${service}: ${restarts} restarts"
    fi
done

if [ -n "$ALERTS" ]; then
    send_alert "<b>Heimdall Alert</b>${ALERTS}"
fi
