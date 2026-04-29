#!/bin/bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/ci/check_docker_contexts.sh [service...]

Run local Docker smoke builds for the requested services. When no services are
provided, all 5 CI-published services are built:
  api delivery scheduler worker twin
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

SERVICES=("$@")
if [ "${#SERVICES[@]}" -eq 0 ]; then
    SERVICES=(api delivery scheduler worker twin)
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_SCRIPT="$REPO_ROOT/scripts/ci/build_service_image.sh"

failures=0
for service in "${SERVICES[@]}"; do
    echo ""
    echo "=== docker context smoke: $service ==="
    if ! "$BUILD_SCRIPT" "$service" linux/amd64; then
        failures=$((failures + 1))
    fi
done

if [ "$failures" -ne 0 ]; then
    echo ""
    echo "docker context smoke failed for $failures service(s)"
    exit 1
fi

echo ""
echo "docker context smoke: OK"
