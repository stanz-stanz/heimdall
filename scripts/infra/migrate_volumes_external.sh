#!/usr/bin/env bash
# Pre-flight for the Compose volume external-ization (PR-A of the 2026-04-14
# infra unpark).
#
# Runs on the host where the Heimdall stack is deployed. For Pi5 prod the
# expected prefix is `docker_` (compose project pinned to `-p docker`); for
# Mac dev the prefix is `heimdall_dev_`. Set VOLUME_PREFIX accordingly.
#
# What this does (idempotent, zero writes to volumes):
#   1. Verify all 6 data-bearing volumes exist under the expected prefix.
#   2. Verify SQLite integrity on clients.db (mounted by the api container),
#      refusing if integrity != 'ok'.
#   3. Record du -sb per volume so the PR body can show reuse proof
#      (compare CreatedAt / size pre- and post-flip).
#   4. Trigger scripts/backup.sh as a belt-and-braces snapshot.
#
# Exits non-zero on any failed check. Safe to rerun.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

VOLUME_PREFIX="${VOLUME_PREFIX:-docker_}"
EXPECTED_VOLUMES=(
    "${VOLUME_PREFIX}redis-data"
    "${VOLUME_PREFIX}client-data"
    "${VOLUME_PREFIX}valdi-data"
    "${VOLUME_PREFIX}cache-data"
    "${VOLUME_PREFIX}config-data"
    "${VOLUME_PREFIX}message-data"
)

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RESET=$'\033[0m'

pass() { printf '%sPASS%s  %s\n' "$GREEN" "$RESET" "$1"; }
fail() { printf '%sFAIL%s  %s\n' "$RED" "$RESET" "$1"; }
warn() { printf '%sWARN%s  %s\n' "$YELLOW" "$RESET" "$1"; }

FAILED=0

# --- 1. Volume existence ---
echo "==> Volume existence (prefix=${VOLUME_PREFIX})"
for vol in "${EXPECTED_VOLUMES[@]}"; do
    if docker volume inspect "$vol" >/dev/null 2>&1; then
        pass "$vol"
    else
        fail "$vol — missing"
        FAILED=$((FAILED + 1))
    fi
done

if [ $FAILED -gt 0 ]; then
    echo
    fail "$FAILED volume(s) missing. Refusing to proceed. The external: true"
    echo "       flip in docker-compose.yml will cause Compose to error-out rather"
    echo "       than silently recreate. Investigate before continuing."
    exit 1
fi

# --- 2. SQLite integrity on clients.db ---
echo
echo "==> SQLite integrity (clients.db via api container)"
CLIENT_VOL="${VOLUME_PREFIX}client-data"
# Use a throwaway python:3.11-slim container so we don't depend on the stack
# being up. Mount the volume read-only so a bad check can't corrupt anything.
INTEGRITY=$(docker run --rm \
    -v "${CLIENT_VOL}:/mnt:ro" \
    python:3.11-slim \
    python -c "
import sqlite3, sys
try:
    c = sqlite3.connect('/mnt/clients.db')
    r = c.execute('PRAGMA integrity_check').fetchone()[0]
    print(r)
    sys.exit(0 if r == 'ok' else 1)
except Exception as e:
    print(f'error: {e}')
    sys.exit(2)
" 2>&1 || true)

if [ "$INTEGRITY" = "ok" ]; then
    pass "clients.db integrity_check=ok"
else
    fail "clients.db integrity_check=${INTEGRITY}"
    FAILED=$((FAILED + 1))
fi

# --- 3. Size + mountpoint snapshot ---
echo
echo "==> Volume size snapshot (pre-flip baseline)"
for vol in "${EXPECTED_VOLUMES[@]}"; do
    MP=$(docker volume inspect "$vol" --format '{{.Mountpoint}}' 2>/dev/null || echo "")
    CREATED=$(docker volume inspect "$vol" --format '{{.CreatedAt}}' 2>/dev/null || echo "")
    if [ -n "$MP" ] && [ -d "$MP" ]; then
        SIZE=$(sudo du -sb "$MP" 2>/dev/null | awk '{print $1}' || echo "?")
    else
        SIZE="?"
    fi
    printf '     %-32s bytes=%-12s created=%s\n' "$vol" "$SIZE" "$CREATED"
done

# --- 4. Backup trigger ---
echo
echo "==> Backup trigger (scripts/backup.sh)"
if [ -x "$PROJECT_DIR/scripts/backup.sh" ]; then
    if "$PROJECT_DIR/scripts/backup.sh"; then
        pass "backup.sh exited 0"
    else
        warn "backup.sh exited non-zero. Review backup.log before the flip."
        FAILED=$((FAILED + 1))
    fi
else
    warn "scripts/backup.sh not executable or missing. Skipping."
fi

echo
if [ $FAILED -eq 0 ]; then
    pass "All pre-flight checks green. Safe to deploy the external-volume compose change."
    exit 0
else
    fail "$FAILED check(s) failed. Do not deploy."
    exit 1
fi
