#!/usr/bin/env bash
# setup.sh – Initial setup for openclaw-secure
# Generates TLS certificates and hashes the Caddy password.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

# ── 1. Create .env from template if it doesn't exist ──
if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env created from .env.example – please edit it with your API keys!"
    echo ""
else
    info ".env already exists"
fi

# ── 2. Source .env to get LAN_IP ──
set -a
source .env
set +a

LAN_IP="${LAN_IP:-192.168.1.100}"

# ── 3. Generate self-signed TLS certificate ──
CERT_DIR="./certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    info "TLS certificates already exist in $CERT_DIR/"
else
    info "Generating self-signed TLS certificate for $LAN_IP ..."
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" \
        -days 3650 \
        -subj "/CN=$LAN_IP" \
        -addext "subjectAltName=IP:$LAN_IP" \
        2>/dev/null
    info "Certificate generated: $CERT_DIR/cert.pem"
fi

# ── 4. Hash Caddy password (bcrypt) ──
CADDY_AUTH_PASSWORD="${CADDY_AUTH_PASSWORD:-changeme}"
if [ "$CADDY_AUTH_PASSWORD" = "changeme" ] || [ "$CADDY_AUTH_PASSWORD" = "change-me-please" ]; then
    warn "CADDY_AUTH_PASSWORD is still the default – please change it in .env!"
fi

# Generate bcrypt hash using Docker (caddy image has the hash-password command)
info "Generating bcrypt hash for Caddy basic auth..."
BCRYPT_HASH=$(docker run --rm caddy:alpine caddy hash-password --plaintext "$CADDY_AUTH_PASSWORD" 2>/dev/null)

if [ -n "$BCRYPT_HASH" ]; then
    # Write hash to caddy/caddy.env (escape $ as $$ for Docker Compose)
    ESCAPED_HASH=$(echo "$BCRYPT_HASH" | sed 's/\$/\$\$/g')
    mkdir -p caddy
    echo "CADDY_AUTH_HASH=$ESCAPED_HASH" > caddy/caddy.env
    info "Bcrypt hash generated and saved to caddy/caddy.env"
else
    error "Failed to generate bcrypt hash. Make sure Docker is running."
    exit 1
fi

# ── 5. Create workspace directory ──
WORKSPACE="${OPENCLAW_WORKSPACE_PATH:-./workspace}"
if [ ! -d "$WORKSPACE" ]; then
    mkdir -p "$WORKSPACE"
    info "Created workspace directory: $WORKSPACE"
else
    info "Workspace directory exists: $WORKSPACE"
fi

# ── 6. Create data directory ──
if [ ! -d "./data" ]; then
    mkdir -p ./data
    info "Created data directory"
else
    info "Data directory exists"
fi

# ── Done ──
echo ""
info "Setup complete! Next steps:"
echo "  1. Edit .env with your API keys (at minimum one AI model provider)"
echo "  2. Optionally add your LAN IP to outbound-proxy/whitelist.txt"
echo "  3. Run: docker compose up -d"
echo ""
OPENCLAW_PORT="${OPENCLAW_PORT:-18789}"
echo "  Web UI will be at: https://${LAN_IP}:${OPENCLAW_PORT}"
echo ""
