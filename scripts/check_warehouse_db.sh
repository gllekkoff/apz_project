#!/usr/bin/env bash
# Shows warehouse Postgres tables and row counts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_helpers.sh"

require_services postgres

echo "=== Warehouse DB: tables ==="
docker compose exec -T postgres psql -U crypto -d crypto -c "\dt"

echo
echo "=== Warehouse DB: row counts ==="
docker compose exec -T postgres psql -U crypto -d crypto -c "
SELECT 'trades' AS table_name, count(*) FROM trades
UNION ALL SELECT 'quotes', count(*) FROM quotes
UNION ALL SELECT 'hourly_reports', count(*) FROM hourly_reports
UNION ALL SELECT 'trading_patterns', count(*) FROM trading_patterns
ORDER BY table_name;
"
