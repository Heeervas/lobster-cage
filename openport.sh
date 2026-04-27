#!/usr/bin/env bash
# openport.sh — Expose a Hermes container port through Caddy reverse proxy.
# Usage: ./openport.sh <port>
# Example: ./openport.sh 8787
#
# What it does:
#   1. Adds a Caddy block to caddy/Caddyfile for the given port
#   2. Adds the port mapping to docker-compose.yml
#   3. Restarts Caddy to apply changes
#
# After running, access the app at: https://<LAN_IP>:<port>
# (Protected by the same basic auth as other Caddy endpoints)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CADDYFILE="$SCRIPT_DIR/caddy/Caddyfile"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

if [[ ! -f "$CADDYFILE" || ! -f "$COMPOSE_FILE" ]]; then
    echo "Error: Expected Caddyfile or compose file is missing."
    exit 1
fi

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
    echo "Port $PORT already configured in caddy/Caddyfile — skipping Caddy config."
else
    echo "Adding port $PORT to caddy/Caddyfile..."
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
if grep -qE "\"${PORT}:${PORT}\"" "$COMPOSE_FILE"; then
    echo "Port $PORT already mapped in docker-compose.yml — skipping."
else
    echo "Adding port mapping $PORT:$PORT to docker-compose.yml..."
    tmp_file="$(mktemp)"
    awk -v port_line="      - \"${PORT}:${PORT}\"" '
        BEGIN {
            in_caddy = 0
            in_ports = 0
            inserted = 0
        }

        /^  caddy:$/ {
            in_caddy = 1
        }

        in_caddy && in_ports && $0 !~ /^      - "/ {
            print port_line
            inserted = 1
            in_ports = 0
        }

        in_caddy && /^    ports:$/ {
            in_ports = 1
            print
            next
        }

        in_caddy && $0 ~ /^  [^ ]/ && $0 != "  caddy:" {
            in_caddy = 0
        }

        {
            print
        }

        END {
            if (in_ports && !inserted) {
                print port_line
                inserted = 1
            }

            if (!inserted) {
                exit 1
            }
        }
    ' "$COMPOSE_FILE" > "$tmp_file" || {
        rm -f "$tmp_file"
        echo "Error: Failed to insert port mapping under the caddy service."
        exit 1
    }
    mv "$tmp_file" "$COMPOSE_FILE"
    echo "  ✓ Port mapping added."
fi

echo ""
echo "Restarting Caddy to apply changes..."
cd "$SCRIPT_DIR"
docker compose up -d caddy
echo ""
echo "✅ Port $PORT is now accessible at https://<your-LAN-IP>:$PORT"
echo "   (Protected by basic auth — same credentials as other endpoints)"
