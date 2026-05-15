#!/usr/bin/env bash
# Runs all database/storage checks used in the demo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/check_auth_db.sh"
echo
"$SCRIPT_DIR/check_redis_sessions.sh"
echo
"$SCRIPT_DIR/check_warehouse_db.sh"
echo
"$SCRIPT_DIR/check_cassandra.sh"

