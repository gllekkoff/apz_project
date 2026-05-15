#!/usr/bin/env bash
set -euo pipefail

MARKET_API="${MARKET_API:-http://localhost:8100}"
SYMBOL="${SYMBOL:-XBTUSD}"
HEAD_BYTES="${HEAD_BYTES:-500}"

hit() {
    local title="$1"
    local url="$2"
    echo
    echo "------ ${title} ------"
    echo "GET ${url}"
    local body
    body=$(curl -sS -w '\n[HTTP %{http_code}]' "$url" 2>&1)
    echo "$body" | head -c "$HEAD_BYTES"
    echo
    if ! echo "$body" | tail -n 1 | grep -Eq '\[HTTP (200|404)\]'; then
        echo "Unexpected response for ${title}"
        exit 1
    fi
}

echo "Market API: $MARKET_API"
echo "Symbol    : $SYMBOL"

hit "Health check" "$MARKET_API/health"
hit "Trades" "$MARKET_API/market/trades?symbol=$SYMBOL&limit=3"
hit "Trades legacy API path" "$MARKET_API/api/trades?symbol=$SYMBOL&limit=3"
hit "Momentum" "$MARKET_API/market/momentum/$SYMBOL?minutes=10"
hit "Whale alerts" "$MARKET_API/market/alerts/whale/$SYMBOL?limit=5"
hit "Volatility alerts" "$MARKET_API/market/alerts/volatility/$SYMBOL?limit=5"

echo
echo "Market data test finished."
