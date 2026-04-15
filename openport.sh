#!/usr/bin/env bash
# openport.sh — Expose a Hermes container port through Caddy reverse proxy.
# Usage: ./openport.sh <port>
# Example: ./openport.sh 8787
#
# What it does:
#   1. Adds a Caddy block to Caddyfile.hermes for the given port
#   2. Adds the port mapping to docker-compose.hermes.yml
#   3. Restarts Caddy to apply changes
#
# After running, access the app at: https://<LAN_IP>:<port>
# (Protected by the same basic auth as other Caddy endpoints)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CADDYFILE="$SCRIPT_DIR/caddy/Caddyfile.hermes"
COMPOSE_HERMES="$SCRIPT_DIR/docker-compose.hermes.yml"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <port>"
    echo "Example: $0 8787"
    exit 1
fi

PORT="$1"

# Validate port is a number
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "Error: Invalid port number '$PORT'. Must be 1-65535."
    exit 1
fi

# Check if port already exists in Caddyfile
if grep -qE "^:${PORT} \{" "$CADDYFILE"; then
    echo "Port $PORT already configured in Caddyfile.hermes — skipping Caddy config."
else
    echo "Adding port $PORT to Caddyfile.hermes..."
    cat >> "$CADDYFILE" << EOF

# Hermes app on port $PORT
:${PORT} {
    tls /certs/cert.pem /certs/key.pem

    basic_auth {
        {\$CADDY_AUTH_USER:admin} {\$CADDY_AUTH_HASH}
    }

    reverse_proxy http://hermes:${PORT}
}
EOF
    echo "  ✓ Caddy block added."
fi

# Check if port mapping already exists in compose override
if grep -qE "\"${PORT}:${PORT}\"" "$COMPOSE_HERMES"; then
    echo "Port $PORT already mapped in docker-compose.hermes.yml — skipping."
else
    echo "Adding port mapping $PORT:$PORT to docker-compose.hermes.yml..."
    # Insert after the existing ports line(s) under caddy service
    if grep -q "ports:" "$COMPOSE_HERMES"; then
        # Add the new port after the last existing port line under caddy
        sed -i "/^      - \"[0-9]*:[0-9]*\"/a\\      - \"${PORT}:${PORT}\"" "$COMPOSE_HERMES"
    else
        # No ports section yet — add it after depends_on block
        sed -i '/depends_on:/,/- hermes/{/- hermes/a\    ports:\n      - "'"${PORT}:${PORT}"'"
}' "$COMPOSE_HERMES"
    fi
    echo "  ✓ Port mapping added."
fi

echo ""
echo "Restarting Caddy to apply changes..."
cd "$SCRIPT_DIR"
docker compose -f docker-compose.yml -f docker-compose.hermes.yml up -d caddy
echo ""
echo "✅ Port $PORT is now accessible at https://<your-LAN-IP>:$PORT"
echo "   (Protected by basic auth — same credentials as other endpoints)"
