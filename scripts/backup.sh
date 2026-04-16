#!/usr/bin/env bash
# Heimdall SQLite backup — daily cron job.
# Uses sqlite3 .backup for WAL-safe atomic copies.
# Runs integrity check on each backup. 30-day retention.
#
# Cron: 0 3 * * * /path/to/heimdall/scripts/backup.sh
#
# Backup destination:
#   Defaults to $PROJECT_DIR/backups (same filesystem — laptop dev).
#   On Pi5, set HEIMDALL_BACKUP_DIR to a separate physical medium for
#   protection against NVMe SSD failure:
#     export HEIMDALL_BACKUP_DIR=/mnt/sdbackup/heimdall
#   (Pi5 has a dormant microSD boot fallback that can be mounted here.)
#
# What gets backed up:
#   - data/enriched/companies.db (host bind mount, tracked in git)
#   - clients.db from Docker volume 'docker_client-data' (via docker exec)
#
# The clients.db backup uses a running container (api or worker) to read
# from the Docker volume — no sudo required. If no container is running,
# the clients.db backup is SKIPPED with a warning (the compose stack is
# probably down, which is itself a reason to alert).
#
# Restore:
#   1. Stop the service that uses the DB
#   2. cp $BACKUP_ROOT/YYYY-MM-DD-HHMMSS/clients.db /var/lib/docker/volumes/docker_client-data/_data/clients.db
#      (or use a temporary container to write it back into the volume)
#   3. Restart the service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/infra/compose/docker-compose.yml"
BACKUP_ROOT="${HEIMDALL_BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y-%m-%d-%H%M%S)"
LOG_FILE="$BACKUP_ROOT/backup.log"
RETENTION_DAYS=30

# Host-path databases (project-relative, backed up via direct sqlite3)
HOST_DATABASES=(
    "data/enriched/companies.db"
)

# Container that has client-data volume mounted (read is sufficient)
# api is preferred (always up, has healthcheck); worker is fallback.
CONTAINER_PREFERENCES=("api" "worker")

mkdir -p "$BACKUP_ROOT" "$BACKUP_DIR"

log() { echo "$(date -Iseconds) $1" >> "$LOG_FILE"; }

FAILURES=0

# --- Host-path backups ---
for db_rel in "${HOST_DATABASES[@]}"; do
    db_path="$PROJECT_DIR/$db_rel"
    db_name=$(basename "$db_rel")
    backup_path="$BACKUP_DIR/$db_name"

    if [ ! -f "$db_path" ]; then
        log "SKIP: $db_rel not found"
        continue
    fi

    if sqlite3 "$db_path" ".backup '$backup_path'" 2>> "$LOG_FILE"; then
        result=$(sqlite3 "$backup_path" "PRAGMA integrity_check" 2>&1)
        if [ "$result" = "ok" ]; then
            log "OK: $db_name backed up and verified"
        else
            log "WARN: $db_name backup integrity check failed: $result"
            FAILURES=$((FAILURES + 1))
        fi
    else
        log "ERROR: $db_name backup failed"
        FAILURES=$((FAILURES + 1))
    fi
done

# --- Docker-volume backups (clients.db) ---
backup_clients_db() {
    if ! command -v docker >/dev/null 2>&1; then
        log "SKIP: clients.db — docker CLI not available"
        return 1
    fi
    if [ ! -f "$COMPOSE_FILE" ]; then
        log "SKIP: clients.db — compose file not found at $COMPOSE_FILE"
        return 1
    fi

    local container_id=""
    local container_name=""
    for name in "${CONTAINER_PREFERENCES[@]}"; do
        container_id=$(docker compose -p docker -f "$COMPOSE_FILE" ps -q "$name" 2>/dev/null | head -1 || true)
        if [ -n "$container_id" ]; then
            container_name="$name"
            break
        fi
    done

    if [ -z "$container_id" ]; then
        log "SKIP: clients.db — no running container with client-data volume (tried: ${CONTAINER_PREFERENCES[*]})"
        return 1
    fi

    local backup_path="$BACKUP_DIR/clients.db"
    local tmp_path_in_container="/tmp/clients-backup-$$.db"

    # Use Python sqlite3 backup API inside the container (WAL-safe).
    # Python is guaranteed present since all Heimdall containers run Python.
    if ! docker exec -i "$container_id" python -c "
import sqlite3
src = sqlite3.connect('/data/clients/clients.db')
dst = sqlite3.connect('$tmp_path_in_container')
src.backup(dst)
dst.close()
src.close()
" 2>> "$LOG_FILE"; then
        log "ERROR: clients.db backup failed in container $container_name"
        docker exec "$container_id" rm -f "$tmp_path_in_container" 2>/dev/null || true
        return 1
    fi

    # Copy backup file out of container to host
    if ! docker cp "$container_id:$tmp_path_in_container" "$backup_path" 2>> "$LOG_FILE"; then
        log "ERROR: clients.db docker cp failed from container $container_name"
        docker exec "$container_id" rm -f "$tmp_path_in_container" 2>/dev/null || true
        return 1
    fi

    # Clean up temp file inside container
    docker exec "$container_id" rm -f "$tmp_path_in_container" 2>/dev/null || true

    # Integrity check on the host copy
    local result
    result=$(sqlite3 "$backup_path" "PRAGMA integrity_check" 2>&1)
    if [ "$result" = "ok" ]; then
        log "OK: clients.db backed up and verified (via $container_name container)"
        return 0
    else
        log "WARN: clients.db backup integrity check failed: $result"
        return 1
    fi
}

if ! backup_clients_db; then
    FAILURES=$((FAILURES + 1))
fi

# Cleanup old backups
find "$BACKUP_ROOT" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

if [ $FAILURES -gt 0 ]; then
    log "COMPLETED WITH $FAILURES FAILURES"
    exit 1
else
    log "COMPLETED SUCCESSFULLY"
fi
