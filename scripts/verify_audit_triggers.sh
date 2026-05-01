#!/usr/bin/env bash
# Stage A.5 post-deploy verification. Asserts:
#
#   1. All 12 config_changes triggers are installed in clients.db.
#   2. command_audit and config_changes tables exist in clients.db.
#   3. Every console.db operator has a non-NULL role_hint (without
#      this, the A.5 RBAC decorator would 403 every gated route).
#
# Runs from the Pi5 host (or any host with sqlite3 + the two DB
# files mounted). Emits PASS:/FAIL: lines per check; exits 1 on
# any failure. Idempotent — safe to rerun after every deploy.
#
# Path overrides:
#   CLIENT_DB         — default /var/lib/heimdall/clients/clients.db
#   CONSOLE_DB        — default /var/lib/heimdall/console/console.db
#   SQLITE3           — default sqlite3 (must be on PATH)
#
# Usage (Pi5):
#   sudo bash scripts/verify_audit_triggers.sh
#
# Usage (Mac dev):
#   CLIENT_DB=data/clients/clients.db CONSOLE_DB=data/console/console.db \
#     bash scripts/verify_audit_triggers.sh

set -euo pipefail

CLIENT_DB="${CLIENT_DB:-/var/lib/heimdall/clients/clients.db}"
CONSOLE_DB="${CONSOLE_DB:-/var/lib/heimdall/console/console.db}"
SQLITE3="${SQLITE3:-sqlite3}"

EXPECTED_TRIGGERS=(
  trg_client_domains_audit_delete
  trg_client_domains_audit_update
  trg_clients_audit_delete
  trg_clients_audit_update
  trg_consent_records_audit_delete
  trg_consent_records_audit_update
  trg_retention_jobs_audit_delete
  trg_retention_jobs_audit_update
  trg_signup_tokens_audit_delete
  trg_signup_tokens_audit_update
  trg_subscriptions_audit_delete
  trg_subscriptions_audit_update
)

EXPECTED_TABLES=(
  command_audit
  config_changes
)

failures=0

fail() {
  echo "FAIL: $*"
  failures=$((failures + 1))
}

pass() {
  echo "PASS: $*"
}

# ---------------------------------------------------------------------
# 1. Tier-1 audit tables exist
# ---------------------------------------------------------------------
if [[ ! -f "$CLIENT_DB" ]]; then
  fail "clients DB not found at $CLIENT_DB"
else
  for t in "${EXPECTED_TABLES[@]}"; do
    if "$SQLITE3" "$CLIENT_DB" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='$t'" \
        | grep -q 1; then
      pass "table $t present in clients.db"
    else
      fail "table $t MISSING from clients.db"
    fi
  done

  # ----------------------------------------------------------------
  # 2. All 12 triggers installed
  # ----------------------------------------------------------------
  installed=$("$SQLITE3" "$CLIENT_DB" \
    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_%' ORDER BY name")
  for t in "${EXPECTED_TRIGGERS[@]}"; do
    if grep -qx "$t" <<<"$installed"; then
      pass "trigger $t installed"
    else
      fail "trigger $t MISSING"
    fi
  done

  # Count via SQLite directly. `wc -l <<<""` returns 1 (heredoc adds a
  # newline to empty input), which would mis-report a broken deploy
  # with zero triggers as "found 1".
  trigger_count=$("$SQLITE3" "$CLIENT_DB" \
    "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_%'")
  if [[ "$trigger_count" -ne 12 ]]; then
    fail "expected 12 trg_* triggers, found $trigger_count"
  fi
fi

# ---------------------------------------------------------------------
# 3. Every operator has a role_hint set (RBAC decorator dependency)
# ---------------------------------------------------------------------
if [[ ! -f "$CONSOLE_DB" ]]; then
  fail "console DB not found at $CONSOLE_DB"
else
  null_count=$("$SQLITE3" "$CONSOLE_DB" \
    "SELECT COUNT(*) FROM operators WHERE role_hint IS NULL")
  if [[ "$null_count" -eq 0 ]]; then
    pass "every operator has role_hint populated"
  else
    fail "$null_count operator(s) have NULL role_hint — RBAC decorator will 403 them"
  fi
fi

# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------
echo
if [[ "$failures" -eq 0 ]]; then
  echo "ALL CHECKS PASSED"
  exit 0
fi

echo "VERIFICATION FAILED ($failures check(s) failed)"
exit 1
