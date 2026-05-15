#!/usr/bin/env bash

require_services() {
  local missing=()
  local running
  running="$(docker compose ps --status running --services 2>/dev/null || true)"

  for service in "$@"; do
    if ! grep -qx "$service" <<<"$running"; then
      missing+=("$service")
    fi
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    echo "Missing running service(s): ${missing[*]}" >&2
    echo "Start them with:" >&2
    echo "  docker compose up -d ${missing[*]}" >&2
    exit 1
  fi
}

