#!/usr/bin/env bash
set -euo pipefail

MARKET_API="${MARKET_API:-http://localhost:8100}"
SYMBOL="${SYMBOL:-XBTUSD}"

status_code() {
    curl -s -o /dev/null -w "%{http_code}" "$1"
}

expect_ok() {
    local label="$1"
    local url="$2"
    local code
    code=$(status_code "$url")
    if [[ "$code" != "200" ]]; then
        echo "FAIL ${label}: expected 200, got ${code}"
        exit 1
    fi
    echo "PASS ${label}: ${code}"
}

echo "Checking market-data-service before failover..."
expect_ok "health before" "$MARKET_API/health"
expect_ok "trade lookup before" "$MARKET_API/market/trades?symbol=$SYMBOL&limit=1"

echo
echo "Stopping cassandra primary node..."
docker compose stop cassandra

cleanup() {
    echo
    echo "Starting cassandra primary node again..."
    docker compose start cassandra >/dev/null
}
trap cleanup EXIT

echo "Waiting for driver/node failover..."
sleep 15

expect_ok "health after primary stop" "$MARKET_API/health"
expect_ok "trade lookup after primary stop" "$MARKET_API/market/trades?symbol=$SYMBOL&limit=1"

echo
echo "Cassandra failover demo passed."
