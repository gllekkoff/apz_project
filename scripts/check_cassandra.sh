#!/usr/bin/env bash
# Shows Cassandra cluster status, keyspace replication, tables, and rough row counts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_helpers.sh"

require_services cassandra

echo "=== Cassandra: cluster status ==="
docker compose exec -T cassandra nodetool status

echo
echo "=== Cassandra: crypto keyspace ==="
docker compose exec -T cassandra cqlsh -e "DESCRIBE KEYSPACE crypto;"

echo
echo "=== Cassandra: tables ==="
docker compose exec -T cassandra cqlsh -e "USE crypto; DESCRIBE TABLES;"

echo
echo "=== Cassandra: row counts ==="
for table in trades market_momentum whale_alerts volatility_alerts; do
    printf "%-20s " "$table:"
    docker compose exec -T cassandra cqlsh -e "SELECT count(*) FROM crypto.${table};" \
        | grep -v -E "Warnings :|Aggregation query used without partition key"
done
