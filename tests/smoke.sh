#!/usr/bin/env bash
# Smoke test — verifies all services are up and data is flowing.
# Run after `docker compose up -d`. Designed to be re-runnable.
#
# Exit code = number of failed checks.

set -u

pass=0
fail=0

check() {
    local name="$1"
    local cmd="$2"
    printf "  %-60s " "$name"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "PASS"
        pass=$((pass + 1))
    else
        echo "FAIL"
        fail=$((fail + 1))
    fi
}

echo
echo "=== Infrastructure health ==="
check "Kafka broker reachable" \
    "docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list"
check "Kafka topic trades-raw exists" \
    "docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic trades-raw"
check "Kafka topic whale-alerts exists" \
    "docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic whale-alerts"
check "Kafka topic volatility-alerts exists" \
    "docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic volatility-alerts"
check "Cassandra reachable" \
    "docker compose exec -T cassandra cqlsh -e 'DESCRIBE KEYSPACES'"
check "Cassandra keyspace 'crypto' exists" \
    "docker compose exec -T cassandra cqlsh -e \"USE crypto; DESCRIBE TABLES\""
check "Postgres reachable" \
    "docker compose exec -T postgres psql -U crypto -d crypto -c 'SELECT 1'"
check "Postgres trades table exists" \
    "docker compose exec -T postgres psql -U crypto -d crypto -c '\\d trades'"

echo
echo "=== Service health endpoints ==="
check "auth-service-1 /health" \
    "curl -fsS http://localhost:8101/health | grep -q ok"
check "auth-service-2 /health" \
    "curl -fsS http://localhost:8102/health | grep -q ok"
check "market-data-service /health" \
    "curl -fsS http://localhost:8100/health | grep -q ok"
check "reporting-service /health" \
    "curl -fsS http://localhost:8200/health | grep -q ok"
check "api-gateway /health" \
    "curl -fsS http://localhost:8080/health | grep -q ok"
check "frontend reachable" \
    "curl -fsS http://localhost:3000/ | grep -qi 'crypto'"

echo
echo "=== Gateway auth flow ==="
TS=$(date +%s)
USERNAME="smoke_${TS}"
PASSWORD="smoke123"

check "POST /auth/register via gateway" \
    "curl -fsS -X POST http://localhost:8080/auth/register \
      -H 'Content-Type: application/json' \
      -d '{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}' | grep -q username"

LOGIN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null)
TOKEN=$(echo "$LOGIN" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)

if [ -n "$TOKEN" ]; then
    echo "  login token obtained                                         PASS"
    pass=$((pass + 1))
else
    echo "  login token obtained                                         FAIL"
    fail=$((fail + 1))
fi

check "GET /auth/me with token" \
    "curl -fsS http://localhost:8080/auth/me -H 'Authorization: Bearer ${TOKEN}' | grep -q username"
check "GET /market/trades unauthenticated returns 401" \
    "[ \"\$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/market/trades?symbol=XBTUSD)\" = '401' ]"
check "GET /market/trades with token (any 2xx or 4xx != 401)" \
    "[ \"\$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/market/trades?symbol=XBTUSD -H 'Authorization: Bearer ${TOKEN}')\" != '401' ]"
check "GET /reports/hourly with token (any 2xx or 4xx != 401)" \
    "[ \"\$(curl -s -o /dev/null -w '%{http_code}' 'http://localhost:8080/reports/hourly?symbol=XBTUSD' -H 'Authorization: Bearer ${TOKEN}')\" != '401' ]"
check "POST /auth/logout" \
    "[ \"\$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080/auth/logout -H 'Authorization: Bearer ${TOKEN}')\" = '204' ]"
check "GET /auth/me after logout returns 401" \
    "[ \"\$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/auth/me -H 'Authorization: Bearer ${TOKEN}')\" = '401' ]"

echo
echo "=== Data flow ==="
check "Cassandra trades has rows" \
    "docker compose exec -T cassandra cqlsh -e 'SELECT count(*) FROM crypto.trades;' | grep -Eq '\\s+[1-9][0-9]*'"
check "Postgres trades has rows" \
    "docker compose exec -T postgres psql -U crypto -d crypto -tA -c 'SELECT count(*) > 0 FROM trades' | grep -q t"
check "market_momentum has rows (wait 1+ min after start)" \
    "docker compose exec -T cassandra cqlsh -e 'SELECT count(*) FROM crypto.market_momentum;' | grep -Eq '\\s+[1-9][0-9]*'"
check "hourly_reports has rows (wait for batch run)" \
    "docker compose exec -T postgres psql -U crypto -d crypto -tA -c 'SELECT count(*) > 0 FROM hourly_reports' | grep -q t"

echo
echo "Summary: ${pass} passed, ${fail} failed"
echo
exit $fail
