#!/usr/bin/env bash
# Heimdall SQLite backup — daily cron job.
# Uses sqlite3 .backup for WAL-safe atomic copies.
# Runs integrity check on each backup. 30-day retention.
#
# Cron: 0 3 * * * /path/to/heimdall/scripts/backup.sh
#
# Restore:
#   1. Stop the service that uses the DB
#   2. cp backups/YYYY-MM-DD-HHMMSS/clients.db data/clients/clients.db
#   3. Restart the service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups/$(date +%Y-%m-%d-%H%M%S)"
LOG_FILE="$PROJECT_DIR/backups/backup.log"
RETENTION_DAYS=30

DATABASES=(
    "data/clients/clients.db"
    "data/enriched/companies.db"
)

mkdir -p "$BACKUP_DIR"

log() { echo "$(date -Iseconds) $1" >> "$LOG_FILE"; }

FAILURES=0

for db_rel in "${DATABASES[@]}"; do
    db_path="$PROJECT_DIR/$db_rel"
    db_name=$(basename "$db_rel")
    backup_path="$BACKUP_DIR/$db_name"

    if [ ! -f "$db_path" ]; then
        log "SKIP: $db_rel not found"
        continue
    fi

    # Atomic WAL-safe backup
    if sqlite3 "$db_path" ".backup '$backup_path'" 2>> "$LOG_FILE"; then
        # Integrity check on the backup copy
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

# Cleanup old backups
find "$PROJECT_DIR/backups" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

if [ $FAILURES -gt 0 ]; then
    log "COMPLETED WITH $FAILURES FAILURES"
    exit 1
else
    log "COMPLETED SUCCESSFULLY"
fi
