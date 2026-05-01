#!/bin/bash
# Simple script to whitelist a hostname and restart the services that consume it.
# Usage: ./whitelist-domain.sh domain.com

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 domain.com"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHITELIST="$SCRIPT_DIR/outbound-proxy/whitelist.txt"

normalize_host() {
    local value="$1"
    value="${value#http://}"
    value="${value#https://}"
    value="${value%%/*}"
    value="${value%%:*}"
    printf '%s\n' "$value"
}

DOMAIN="$(normalize_host "$1")"

if [ -z "$DOMAIN" ]; then
    echo "!!! [whitelist] Could not extract a hostname from '$1'"
    exit 1
fi

if [ "$DOMAIN" != "$1" ]; then
    echo "~~~ [whitelist] Normalized '$1' -> '$DOMAIN'"
fi

# 1. Add to whitelist if it doesn't exist already.
if grep -Fxq "$DOMAIN" "$WHITELIST" 2>/dev/null; then
    echo "--- [whitelist] Host '$DOMAIN' is already in whitelist.txt"
else
    echo "$DOMAIN" >> "$WHITELIST"
    echo "+++ [whitelist] Added '$DOMAIN' to whitelist.txt"
fi

cd "$SCRIPT_DIR"

# 2. Restart the live services that cache this whitelist.
restart_services=(proxy dns)
running_services="$(docker compose ps --services --status running 2>/dev/null || true)"

for service in hermes openclaw; do
    if printf '%s\n' "$running_services" | grep -Fxq "$service"; then
        restart_services+=("$service")
    fi
done

echo "🔄 [docker] Restarting: ${restart_services[*]}"
docker compose restart "${restart_services[@]}"

echo "✅ Done. Host '$DOMAIN' is now whitelisted."
