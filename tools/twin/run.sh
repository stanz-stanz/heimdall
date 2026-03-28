#!/usr/bin/env bash
# Convenience wrapper: spin up a digital twin from a prospect brief.
# Usage: ./tools/twin/run.sh [brief_filename]
# Example: ./tools/twin/run.sh jellingkro.dk.json

set -euo pipefail
BRIEF="${1:-conrads.dk.json}"
export BRIEF_FILE="/config/$BRIEF"

cd "$(git rev-parse --show-toplevel)"
docker compose -f infra/docker/docker-compose.yml --profile twin up --build twin
