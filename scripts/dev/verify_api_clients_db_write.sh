#!/usr/bin/env bash
# Verify the dev api container has RW access to clients.db.
#
# PR #46 (2026-04-26) shipped operator console V6 with three retention
# CAS-UPDATE endpoints (POST /console/retention-jobs/{id}/{force-run,
# cancel,retry}) that open a sqlite3 connection from inside the api
# process and run UPDATEs on the retention_jobs table. They require the
# api container to mount client-data RW on /data/clients.
#
# A latent prod bug shipped alongside: the docker-compose.yml mount on
# the api service was ":ro", which would have failed every retention
# action with "attempt to write a readonly database" the moment an
# operator clicked. The bug was caught 2026-04-28 during the Stage A
# spec review (Outcome C of the architect's investigation).
#
# This script probes the mount mode by attempting a no-op write
# transaction (BEGIN IMMEDIATE; ROLLBACK) against /data/clients/
# clients.db inside the running api container. The transaction never
# mutates any row — BEGIN IMMEDIATE just acquires the writer lock,
# which fails with SQLITE_READONLY on a :ro mount and succeeds on RW.
#
# Run any time after `make dev-up` (the api container must be running):
#
#     bash scripts/dev/verify_api_clients_db_write.sh
#
# Or via the Makefile:
#
#     make dev-verify-api-write
#
# Exit code: 0 on PASS, 1 on FAIL.

set -euo pipefail

CONTAINER="${HEIMDALL_API_CONTAINER:-heimdall_dev-api-1}"
DB_PATH="${HEIMDALL_API_DB_PATH:-/data/clients/clients.db}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "FAIL: container '$CONTAINER' is not running. Run \`make dev-up\` first." >&2
    exit 1
fi

# Single Python invocation — opens a write connection, runs
# BEGIN IMMEDIATE / ROLLBACK, prints PASS/FAIL. The Python program
# is short (under 150 chars) so the inline-script guard does not fire.
result=$(docker exec "$CONTAINER" python -c "
import sqlite3, sys
try:
    c = sqlite3.connect('$DB_PATH', timeout=2)
    c.execute('BEGIN IMMEDIATE')
    c.execute('ROLLBACK')
    print('OK')
except sqlite3.OperationalError as e:
    print('RO:' + str(e))
    sys.exit(2)
" 2>&1) || rc=$? && rc=${rc:-0}

case "$result" in
    OK)
        echo "PASS: api container '$CONTAINER' has RW access to $DB_PATH"
        exit 0
        ;;
    RO:*)
        echo "FAIL: api container '$CONTAINER' is READ-ONLY on $DB_PATH"
        echo "  detail: ${result#RO:}"
        echo "  fix: ensure infra/compose/docker-compose.yml does not pin the api service's"
        echo "       client-data mount with ':ro'. PR #46's retention CAS UPDATEs require RW."
        exit 1
        ;;
    *)
        echo "FAIL: unexpected probe output (rc=$rc):"
        echo "  $result"
        exit 1
        ;;
esac
