#!/usr/bin/env bash
# Shows active auth sessions stored in Redis.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_helpers.sh"

require_services redis

echo "=== Redis: active auth session keys ==="
docker compose exec -T redis redis-cli --scan --pattern 'auth:session:*'

echo
echo "=== Redis: key count ==="
docker compose exec -T redis redis-cli DBSIZE
