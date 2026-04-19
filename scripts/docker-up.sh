#!/usr/bin/env bash
# Run the stack in Docker (Compose v2). From repo root: ./scripts/docker-up.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  echo "No .env — copying .env.example (add your API keys inside)."
  cp .env.example .env
fi
exec docker compose up --build "$@"
