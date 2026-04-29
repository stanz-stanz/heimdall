#!/bin/bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/ci/build_service_image.sh <service> [platform]

Build a Heimdall service image locally using the same Dockerfile layout as CI.
Defaults to linux/amd64 for fast PR-style smoke coverage.

Services: api, delivery, scheduler, worker, twin
EOF
}

if [ "${1:-}" = "" ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 1
fi

SERVICE="$1"
PLATFORM="${2:-linux/amd64}"

case "$SERVICE" in
    api|delivery|scheduler|worker|twin) ;;
    *)
        echo "error: unknown service '$SERVICE'" >&2
        usage
        exit 1
        ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="$REPO_ROOT/infra/compose/Dockerfile.$SERVICE"
IMAGE_TAG="heimdall-smoke-$SERVICE:local"

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is required" >&2
    exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
    echo "error: docker buildx is required" >&2
    exit 1
fi

echo "==> building $SERVICE for $PLATFORM"
docker buildx build \
    --platform "$PLATFORM" \
    --file "$DOCKERFILE" \
    --tag "$IMAGE_TAG" \
    --progress plain \
    "$REPO_ROOT"

echo "==> build complete: $IMAGE_TAG"
