#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose up --build --detach --wait
bash scripts/repair-codespaces-network.sh
