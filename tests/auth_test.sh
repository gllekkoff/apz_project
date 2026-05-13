#!/usr/bin/env bash
# Auth service integration check.
# Run after:
#   docker compose up -d --build auth-db redis auth-service-1 auth-service-2

set -euo pipefail

docker compose exec -T auth-service-1 python - <<'PY'
import json
import time
import urllib.error
import urllib.request

base = "http://localhost:8000"
username = f"auth_test_{int(time.time())}"
password = "demo123"


def request(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as res:
        body = res.read().decode()
        return res.status, json.loads(body) if body else None


def expect_http_error(method, path, expected, token=None):
    try:
        request(method, path, token=token)
    except urllib.error.HTTPError as exc:
        print(f"{method} {path}: {exc.code}")
        if exc.code != expected:
            raise
    else:
        raise AssertionError(f"{method} {path} should have returned {expected}")


print("health:", request("GET", "/health")[1])
print("register:", request("POST", "/auth/register", {"username": username, "password": password})[0])
status, login = request("POST", "/auth/login", {"username": username, "password": password})
print("login:", status, login["instance"])
token = login["token"]
print("me:", request("GET", "/auth/me", token=token)[1])
print("validate:", request("POST", "/auth/validate", token=token)[1])
expect_http_error("GET", "/auth/me", 401)
print("logout:", request("POST", "/auth/logout", token=token)[0])
expect_http_error("POST", "/auth/validate", 401, token=token)
print("Auth test passed")
PY
