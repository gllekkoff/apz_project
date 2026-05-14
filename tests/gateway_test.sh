#!/usr/bin/env bash
set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8080}"
TS=$(date +%s)
USERNAME="gw_test_${TS}"
PASSWORD="demo123"

http_code() {
    local method="$1"
    local path="$2"
    local token="${3:-}"
    local body="${4:-}"
    local args=(-s -o /dev/null -w "%{http_code}" -X "$method" "$GATEWAY$path")
    if [[ -n "$body" ]]; then
        args+=(-H "Content-Type: application/json" -d "$body")
    fi
    if [[ -n "$token" ]]; then
        args+=(-H "Authorization: Bearer $token")
    fi
    curl "${args[@]}"
}

http_body() {
    local method="$1"
    local path="$2"
    local token="${3:-}"
    local body="${4:-}"
    local args=(-s -X "$method" "$GATEWAY$path")
    if [[ -n "$body" ]]; then
        args+=(-H "Content-Type: application/json" -d "$body")
    fi
    if [[ -n "$token" ]]; then
        args+=(-H "Authorization: Bearer $token")
    fi
    curl "${args[@]}"
}

expect() {
    local label="$1"
    local actual="$2"
    local expected="$3"
    if [[ "$actual" == "$expected" ]]; then
        echo "  PASS  ${label}  →  ${actual}"
    else
        echo "  FAIL  ${label}  →  expected ${expected}, got ${actual}"
        exit 1
    fi
}

expect_one_of() {
    local label="$1"
    local actual="$2"
    shift 2
    for expected in "$@"; do
        if [[ "$actual" == "$expected" ]]; then
            echo "  PASS  ${label}  →  ${actual}"
            return 0
        fi
    done
    echo "  FAIL  ${label}  →  expected one of $*, got ${actual}"
    exit 1
}

echo
echo "=== Gateway health ==="
expect "GET /health"                 "$(http_code GET /health)"                  "200"

echo
echo "=== Unauthenticated protected routes return 401 ==="
expect "GET /auth/me (no token)"     "$(http_code GET /auth/me)"                 "401"
expect "POST /auth/validate (no token)" "$(http_code POST /auth/validate)"       "401"
expect "GET /market/anything (no token)" "$(http_code GET /market/anything)"     "401"
expect "GET /reports/anything (no token)" "$(http_code GET /reports/anything)"   "401"

echo
echo "=== Public auth flow through gateway ==="
expect "POST /auth/register"         "$(http_code POST /auth/register '' "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}")" "201"

LOGIN_BODY=$(http_body POST /auth/login '' "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}")
TOKEN=$(echo "$LOGIN_BODY" | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
if [[ -z "$TOKEN" ]]; then
    echo "  FAIL  login did not return a token: $LOGIN_BODY"
    exit 1
fi
echo "  PASS  POST /auth/login  →  token issued"

echo
echo "=== Protected auth routes with valid token ==="
expect "GET /auth/me (valid token)"  "$(http_code GET /auth/me "$TOKEN")"        "200"
expect "POST /auth/validate (valid)" "$(http_code POST /auth/validate "$TOKEN")" "200"

echo
echo "=== Tampered token is rejected ==="
expect "GET /auth/me (bad token)"    "$(http_code GET /auth/me "not-a-real-token")" "401"

echo
echo "=== Protected market/reports routes accept tokens (gateway forwards) ==="
mkt_code=$(http_code GET "/market/api/trades?symbol=XBTUSD&limit=1" "$TOKEN")
rep_code=$(http_code GET "/reports/api/reports/hourly?symbol=XBTUSD&hours=1" "$TOKEN")
if [[ "$mkt_code" == "401" ]]; then echo "  FAIL  /market with token should not be 401"; exit 1; fi
if [[ "$rep_code" == "401" ]]; then echo "  FAIL  /reports with token should not be 401"; exit 1; fi
echo "  PASS  GET /market/...  →  ${mkt_code} (gateway forwarded)"
echo "  PASS  GET /reports/... →  ${rep_code} (gateway forwarded)"

echo
echo "=== Logout invalidates the token ==="
expect "POST /auth/logout"           "$(http_code POST /auth/logout "$TOKEN")"   "204"
expect "POST /auth/validate (after logout)" "$(http_code POST /auth/validate "$TOKEN")" "401"
expect "GET /market/anything (after logout)" "$(http_code GET /market/anything "$TOKEN")" "401"

echo
echo "Gateway test passed."
