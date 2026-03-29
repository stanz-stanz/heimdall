#!/bin/bash
# Docker smoke test — verify worker image is correctly assembled.
# Run inside the worker container or via:
#   docker compose run --rm --entrypoint bash worker scripts/docker-smoke.sh
set -e

PASS=0
FAIL=0

check() {
    if eval "$2" > /dev/null 2>&1; then
        echo "  [OK] $1"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $1"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== HEIMDALL DOCKER SMOKE TEST ==="

echo ""
echo "  Go Binaries"
for bin in httpx webanalyze subfinder dnsx nuclei; do
    check "$bin exists at /opt/go-tools/" "test -f /opt/go-tools/$bin"
    check "$bin is >1MB (not pip wrapper)" "test $(stat -f%z /opt/go-tools/$bin 2>/dev/null || stat -c%s /opt/go-tools/$bin 2>/dev/null) -gt 1000000"
done
check "PATH starts with /opt/go-tools" "echo \$PATH | grep -q '^/opt/go-tools'"

echo ""
echo "  Nuclei Templates"
TEMPLATE_COUNT=$(find /opt/nuclei-templates -name '*.yaml' 2>/dev/null | wc -l)
check "Templates >= 1000 (found: $TEMPLATE_COUNT)" "test $TEMPLATE_COUNT -ge 1000"

echo ""
echo "  CMSeek"
check "cmseek.py exists" "test -f /opt/cmseek/cmseek.py"

echo ""
echo "  Application Code"
check "src/worker/scan_job.py exists" "test -f /app/src/worker/scan_job.py"
check "tools/twin/slug_map.json exists" "test -f /app/tools/twin/slug_map.json"
check ".claude/agents/valdi/approvals.json exists" "test -f /app/.claude/agents/valdi/approvals.json"
check "config/remediation_states.json exists" "test -f /app/config/remediation_states.json"
check "scan_job importable" "python -c 'from src.worker.scan_job import execute_scan_job'"
check "twin module importable" "python -c 'from tools.twin.templates import load_slug_map'"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ $FAIL -gt 0 ]; then
    echo "SMOKE TEST FAILED — do not run pipeline"
    exit 1
fi
