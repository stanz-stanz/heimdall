#!/usr/bin/env bash
# Convenience wrapper: spin up a digital twin from a prospect brief.
# Usage: ./tools/twin/run.sh [brief_filename]
# Example: ./tools/twin/run.sh jellingkro.dk.json

set -euo pipefail
BRIEF="${1:-conrads.dk.json}"
export BRIEF_FILE="/config/$BRIEF"

cd "$(git rev-parse --show-toplevel)"
# Unset the dev/prod-isolation overrides so a sourced .env.dev or exported
# shell var can't redirect this base-compose call to data/dev/* paths.
env -u INPUT_HOST_DIR -u ENRICHED_HOST_DIR -u RESULTS_HOST_DIR -u BRIEFS_HOST_DIR \
	docker compose -f infra/compose/docker-compose.yml --profile twin up --build twin
