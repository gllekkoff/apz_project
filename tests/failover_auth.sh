#!/usr/bin/env bash
# Verifies auth sessions are shared across auth-service replicas through Redis.
# Run after:
#   docker compose up -d --build auth-db redis auth-service-1 auth-service-2

set -euo pipefail

cleanup() {
    docker compose start auth-service-1 >/dev/null || true
}
trap cleanup EXIT

echo "Creating a session through auth-service-1 and validating it on both replicas"
docker compose exec -T auth-service-2 python - <<'PY'
import json
import time
import urllib.request

service_1 = "http://auth-service-1:8000"
service_2 = "http://localhost:8000"
username = f"failover_{int(time.time())}"
password = "demo123"


def post(base, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as res:
        body = res.read().decode()
        return res.status, json.loads(body) if body else None


post(service_1, "/auth/register", {"username": username, "password": password})
_, login = post(service_1, "/auth/login", {"username": username, "password": password})
token = login["token"]
print(token)
print("validate service 1:", post(service_1, "/auth/validate", token=token)[1])
print("validate service 2:", post(service_2, "/auth/validate", token=token)[1])
PY

TOKEN=$(docker compose exec -T auth-service-2 python - <<'PY'
import json
import time
import urllib.request

service_1 = "http://auth-service-1:8000"
username = f"failover_stop_{int(time.time())}"
password = "demo123"


def post(path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(service_1 + path, data=data, method="POST")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as res:
        body = res.read().decode()
        return json.loads(body) if body else None


post("/auth/register", {"username": username, "password": password})
login = post("/auth/login", {"username": username, "password": password})
print(login["token"])
PY
)

echo "Stopping auth-service-1"
docker compose stop auth-service-1 >/dev/null

echo "Validating the same token through auth-service-2 while auth-service-1 is stopped"
docker compose exec -T -e TOKEN="$TOKEN" auth-service-2 python - <<'PY'
import json
import os
import urllib.error
import urllib.request

token = os.environ["TOKEN"]
base = "http://localhost:8000"


def post(path, token):
    req = urllib.request.Request(base + path, data=b"", method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as res:
        body = res.read().decode()
        return res.status, json.loads(body) if body else None


print("validate after service 1 stopped:", post("/auth/validate", token)[1])
print("logout:", post("/auth/logout", token)[0])
try:
    post("/auth/validate", token)
except urllib.error.HTTPError as exc:
    print("validate after logout:", exc.code)
    if exc.code != 401:
        raise
else:
    raise AssertionError("token should be invalid after logout")
PY

echo "Auth failover test passed"
