#!/usr/bin/env bash
# Compact health overview for the APZ stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_helpers.sh"

echo "=== Docker Compose services ==="
docker compose ps

echo
echo "=== HTTP health checks from inside Compose network ==="
require_services api-gateway auth-service-1 auth-service-2 market-data-service reporting-service
docker compose exec -T api-gateway python - <<'PY'
import urllib.error
import urllib.request

checks = {
    "api-gateway": "http://localhost:8000/health",
    "auth-service-1": "http://auth-service-1:8000/health",
    "auth-service-2": "http://auth-service-2:8000/health",
    "market-data-service": "http://market-data-service:8000/health",
    "reporting-service": "http://reporting-service:8000/health",
}

for name, url in checks.items():
    try:
        with urllib.request.urlopen(url, timeout=5) as res:
            print(f"{name:22} {res.status}")
    except urllib.error.URLError as exc:
        print(f"{name:22} ERROR {exc}")
PY
