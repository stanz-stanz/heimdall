#!/bin/bash
# Build worker image and run smoke tests inside it.
# Usage: bash scripts/docker-smoke.sh

set -e

COMPOSE_FILE="infra/docker/docker-compose.yml"

echo "=== Building worker image ==="
docker compose -f "$COMPOSE_FILE" build worker

echo ""
echo "=== Running smoke tests inside container ==="
docker compose -f "$COMPOSE_FILE" run --rm worker python -m pytest tests/test_docker_smoke.py -v

echo ""
echo "=== Smoke test passed ==="
