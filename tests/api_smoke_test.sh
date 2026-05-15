#!/usr/bin/env bash
# Full API smoke test through the api-gateway.
# Tests auth flow, market data, and reports with a fresh user account.
# Run after `docker compose up -d` and data has had time to populate.
#
# Usage:
#   bash tests/api_smoke_test.sh
#   GATEWAY=http://localhost:8080 bash tests/api_smoke_test.sh

set -u

GATEWAY="${GATEWAY:-http://localhost:8080}"
TS=$(date +%s)
USERNAME="apitest_${TS}"
PASSWORD="apitest123"
TOKEN=""

pass=0
fail=0

check() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    printf "  %-60s " "$label"
    if [[ "$actual" == "$expected" ]]; then
        echo "PASS ($actual)"
        pass=$((pass + 1))
    else
        echo "FAIL  expected=$expected  got=$actual"
        fail=$((fail + 1))
    fi
}

check_ne() {
    local label="$1"
    local actual="$2"
    local bad="$3"
    printf "  %-60s " "$label"
    if [[ "$actual" != "$bad" ]]; then
        echo "PASS ($actual)"
        pass=$((pass + 1))
    else
        echo "FAIL  should not be=$bad"
        fail=$((fail + 1))
    fi
}

http_code() {
    local method="$1" path="$2" token="${3:-}" body="${4:-}"
    local args=(-s -o /dev/null -w "%{http_code}" -X "$method" "${GATEWAY}${path}")
    [[ -n "$body"  ]] && args+=(-H "Content-Type: application/json" -d "$body")
    [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
    curl "${args[@]}"
}

http_body() {
    local method="$1" path="$2" token="${3:-}" body="${4:-}"
    local args=(-s -X "$method" "${GATEWAY}${path}")
    [[ -n "$body"  ]] && args+=(-H "Content-Type: application/json" -d "$body")
    [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
    curl "${args[@]}"
}

echo
echo "=== Gateway reachability ==="
echo "  Gateway: $GATEWAY"
check "GET /health returns 200" \
    "$(http_code GET /health)" "200"

echo
echo "=== Unauthenticated requests are rejected ==="
check "GET /auth/me without token → 401" \
    "$(http_code GET /auth/me)" "401"
check "GET /market/trades without token → 401" \
    "$(http_code GET /market/trades?symbol=XBTUSD)" "401"
check "GET /market/momentum/XBTUSD without token → 401" \
    "$(http_code GET /market/momentum/XBTUSD)" "401"
check "GET /market/alerts/whale/XBTUSD without token → 401" \
    "$(http_code GET /market/alerts/whale/XBTUSD)" "401"
check "GET /reports/hourly without token → 401" \
    "$(http_code GET /reports/hourly?symbol=XBTUSD)" "401"

echo
echo "=== Registration ==="
REG_CODE=$(http_code POST /auth/register "" "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")
check "POST /auth/register → 201" "$REG_CODE" "201"

DUP_CODE=$(http_code POST /auth/register "" "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")
check "POST /auth/register duplicate → 409" "$DUP_CODE" "409"

echo
echo "=== Login ==="
LOGIN_BODY=$(http_body POST /auth/login "" "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")
TOKEN=$(echo "$LOGIN_BODY" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
check_ne "POST /auth/login returns token" "$TOKEN" ""

BAD_LOGIN=$(http_code POST /auth/login "" "{\"username\":\"$USERNAME\",\"password\":\"wrongpassword\"}")
check "POST /auth/login bad password → 401" "$BAD_LOGIN" "401"

echo
echo "=== Authenticated user endpoints ==="
check "GET /auth/me with valid token → 200" \
    "$(http_code GET /auth/me "$TOKEN")" "200"
check "POST /auth/validate with valid token → 200" \
    "$(http_code POST /auth/validate "$TOKEN")" "200"
check "GET /auth/me with bad token → 401" \
    "$(http_code GET /auth/me "not-a-real-token")" "401"

echo
echo "=== Market data endpoints (authenticated) ==="
TRADES_CODE=$(http_code GET "/market/trades?symbol=XBTUSD&limit=10" "$TOKEN")
check_ne "GET /market/trades → not 401" "$TRADES_CODE" "401"

MOMENTUM_CODE=$(http_code GET "/market/momentum/XBTUSD?minutes=30" "$TOKEN")
check_ne "GET /market/momentum/XBTUSD → not 401" "$MOMENTUM_CODE" "401"

WHALE_CODE=$(http_code GET "/market/alerts/whale/XBTUSD?limit=10" "$TOKEN")
check_ne "GET /market/alerts/whale/XBTUSD → not 401" "$WHALE_CODE" "401"

VOL_CODE=$(http_code GET "/market/alerts/volatility/XBTUSD?limit=10" "$TOKEN")
check_ne "GET /market/alerts/volatility/XBTUSD → not 401" "$VOL_CODE" "401"

ETHUSD_CODE=$(http_code GET "/market/trades?symbol=ETHUSD&limit=5" "$TOKEN")
check_ne "GET /market/trades ETHUSD → not 401" "$ETHUSD_CODE" "401"

echo
echo "=== Reporting endpoints (authenticated) ==="
HOURLY_CODE=$(http_code GET "/reports/hourly?symbol=XBTUSD&hours=6" "$TOKEN")
check_ne "GET /reports/hourly → not 401" "$HOURLY_CODE" "401"

echo
echo "=== Logout ==="
check "POST /auth/logout → 204" \
    "$(http_code POST /auth/logout "$TOKEN")" "204"
check "GET /auth/me after logout → 401" \
    "$(http_code GET /auth/me "$TOKEN")" "401"
check "GET /market/trades after logout → 401" \
    "$(http_code GET /market/trades?symbol=XBTUSD "$TOKEN")" "401"

echo
echo "=== Frontend ==="
FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null || echo "000")
check_ne "Frontend at :3000 reachable" "$FRONTEND_CODE" "000"
check_ne "Frontend at :3000 not 404" "$FRONTEND_CODE" "404"

echo
echo "Summary: ${pass} passed, ${fail} failed"
echo
exit $fail
