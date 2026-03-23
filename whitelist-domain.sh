#!/bin/bash
# Simple script to whitelist a domain and restart necessary services.
# Usage: ./whitelist-domain.sh domain.com

if [ -z "$1" ]; then
    echo "Usage: $0 domain.com"
    exit 1
fi

DOMAIN=$1
WHITELIST="./outbound-proxy/whitelist.txt"

# 1. Add to whitelist if it doesn't exist
if grep -q "^$DOMAIN$" "$WHITELIST" 2>/dev/null; then
    echo "--- [whitelist] Domain '$DOMAIN' is already in whitelist.txt"
else
    echo "$DOMAIN" >> "$WHITELIST"
    echo "+++ [whitelist] Added '$DOMAIN' to whitelist.txt"
fi

# 2. Restart services to apply changes
# This handles both updating the internal state and ensuring dependencies are up.
echo "🔄 [docker] Restarting proxy, dns, and openclaw..."
docker compose restart proxy dns openclaw

echo "✅ Done. Domain '$DOMAIN' is now whitelisted."
