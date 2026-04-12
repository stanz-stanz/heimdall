#!/usr/bin/env bash
# Verify the 2026-04-12 CT rebuild deploy.
#
# Runs end-to-end health checks for:
#   1. Stack topology (expected containers up, ct-collector gone)
#   2. Valdí token validation on worker startup
#   3. Scheduler daemon started + CT monitoring timer initialized
#   4. Delivery runner subscribed to client-cert-change channel
#   5. Schema migration applied (new cert tables + clients columns)
#   6. monitoring.json readable inside scheduler
#   7. CERTSPOTTER_API_KEY passthrough to scheduler + delivery
#
# Usage (on the Pi5):
#   bash scripts/verify_ct_rebuild.sh
#
# Exits 0 if all checks pass, 1 if any check fails.
# Idempotent. No writes to the stack. Safe to rerun.

set -uo pipefail

PASS=0
FAIL=0

_pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
_fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
_dump_logs() {
    local container=$1 tail=${2:-30}
    echo "  --- last $tail lines of $container ---"
    docker logs --tail "$tail" "$container" 2>&1 | sed 's/^/  | /'
    echo "  --- end $container ---"
}

_have_container() {
    docker ps --format '{{.Names}}' | grep -q "^$1$"
}

echo "=== 1. Stack topology ==="
for svc in docker-redis-1 docker-api-1 docker-scheduler-1 docker-delivery-1 \
           docker-worker-1 docker-worker-2 docker-worker-3; do
    if _have_container "$svc"; then
        _pass "$svc is up"
    else
        _fail "$svc is NOT running"
    fi
done

if _have_container docker-ct-collector-1; then
    _fail "docker-ct-collector-1 still running — should have been deleted"
else
    _pass "docker-ct-collector-1 is gone"
fi

if docker volume ls --format '{{.Name}}' | grep -q '^docker_ct-data$'; then
    _fail "docker_ct-data volume still exists — should have been removed"
else
    _pass "docker_ct-data volume is gone"
fi


echo
echo "=== 2. Valdí token validation (worker) ==="
if docker logs docker-worker-1 2>&1 | grep -qiE 'valdi.*approval.*(validated|loaded)|approval_tokens_validated'; then
    _pass "worker-1 validated Valdí approval tokens on startup"
else
    _fail "worker-1 did NOT log Valdí approval token validation"
    _dump_logs docker-worker-1
fi


echo
echo "=== 3. Scheduler daemon + CT monitoring timer ==="
sched_logs=$(docker logs docker-scheduler-1 2>&1)
if echo "$sched_logs" | grep -q 'Scheduler daemon started'; then
    _pass "scheduler daemon started"
else
    _fail "scheduler daemon did NOT log 'Scheduler daemon started'"
fi
if echo "$sched_logs" | grep -q 'CT monitoring timer started'; then
    _pass "CT monitoring timer initialized"
else
    _fail "CT monitoring timer did NOT log 'CT monitoring timer started' (check config/monitoring.json mount)"
fi


echo
echo "=== 4. Delivery runner Redis subscription ==="
delivery_logs=$(docker logs docker-delivery-1 2>&1)
if echo "$delivery_logs" | grep -qE 'client-cert-change|redis_subscribed'; then
    _pass "delivery runner subscribed to Redis channels"
else
    _fail "delivery runner did NOT log Redis subscription"
    _dump_logs docker-delivery-1
fi


echo
echo "=== 5. Schema migration applied ==="
schema_check=$(docker exec docker-delivery-1 python -c '
import sqlite3, sys
try:
    c = sqlite3.connect("/data/clients/clients.db")
    tables = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type=\"table\" AND name LIKE \"client_cert%\""
    ).fetchall()}
    cols = {r[1] for r in c.execute("PRAGMA table_info(clients)").fetchall()}
    missing_tables = {"client_cert_snapshots", "client_cert_changes"} - tables
    missing_cols = {"monitoring_enabled", "ct_last_polled_at"} - cols
    if missing_tables or missing_cols:
        print("MISSING tables=" + str(missing_tables) + " cols=" + str(missing_cols))
        sys.exit(1)
    print("OK")
    c.close()
except Exception as e:
    print("ERROR: " + str(e))
    sys.exit(1)
' 2>&1)
if echo "$schema_check" | grep -q '^OK$'; then
    _pass "schema migration applied (client_cert_* tables + clients columns)"
else
    _fail "schema check: ${schema_check:-<empty>}"
fi


echo
echo "=== 6. monitoring.json readable inside scheduler ==="
mon_check=$(docker exec docker-scheduler-1 sh -c 'cat /config/monitoring.json 2>/dev/null || cat config/monitoring.json 2>/dev/null' 2>&1)
if echo "$mon_check" | grep -q 'ct_poll_schedule_hour_utc'; then
    _pass "monitoring.json readable by scheduler"
else
    _fail "monitoring.json NOT readable by scheduler (checked /config/ and ./config/)"
fi


echo
echo "=== 7. CERTSPOTTER_API_KEY passthrough ==="
for svc in docker-scheduler-1 docker-delivery-1; do
    val=$(docker exec "$svc" sh -c 'echo "${CERTSPOTTER_API_KEY:-}"' 2>/dev/null)
    if [ -n "$val" ]; then
        _pass "$svc has CERTSPOTTER_API_KEY set (len=${#val})"
    else
        _fail "$svc has CERTSPOTTER_API_KEY empty or unset"
    fi
done


echo
echo "=== Summary ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
