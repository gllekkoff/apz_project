#!/usr/bin/env bash
# Shows auth database schema and users without password hashes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_helpers.sh"

require_services auth-db

echo "=== Auth DB: tables ==="
docker compose exec -T auth-db psql -U auth -d auth -c "\dt"

echo
echo "=== Auth DB: users ==="
docker compose exec -T auth-db psql -U auth -d auth -c \
  "SELECT id, username, created_at FROM users ORDER BY id DESC LIMIT 20;"
