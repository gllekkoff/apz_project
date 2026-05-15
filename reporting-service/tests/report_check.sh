#!/usr/bin/env bash
set -euo pipefail
base=${1:-http://localhost:8200}
echo "Checking reporting service at $base"
curl -fsS $base/health | jq .
curl -fsS "$base/reports/hourly?symbol=XBTUSD&hours=12" | jq .
curl -fsS "$base/analytics/trading-patterns?symbol=XBTUSD" | jq . || true
curl -fsS "$base/analytics/whale-impact?period=24h" | jq . || true
echo "OK"
