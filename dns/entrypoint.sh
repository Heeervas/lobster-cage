#!/bin/sh
# DNS Relay with domain whitelisting
# Only resolves domains listed in /etc/dns-whitelist.txt (= outbound-proxy/whitelist.txt).
# All other queries return REFUSED → blocks DNS exfiltration.

set -e

WHITELIST="/etc/dns-whitelist.txt"
CONF="/tmp/dnsmasq-whitelist.conf"

# Base config
cat > "$CONF" <<EOF
# Auto-generated from whitelist – do not edit
keep-in-foreground
listen-address=0.0.0.0
bind-interfaces
no-resolv
no-hosts
log-queries
log-facility=-
# Cache DNS results (reduces upstream queries)
cache-size=500
EOF

# Read whitelisted domains and add server= entries
count=0
if [ -f "$WHITELIST" ]; then
  while IFS= read -r line; do
    # Strip comments and whitespace
    domain=$(echo "$line" | sed 's/#.*//' | tr -d '[:space:]')
    [ -z "$domain" ] && continue

    # Forward this domain to public DNS
    echo "server=/${domain}/1.1.1.1" >> "$CONF"
    echo "server=/${domain}/8.8.8.8" >> "$CONF"
    count=$((count + 1))
  done < "$WHITELIST"
fi

# Also allow resolving search engine domains (SearXNG needs these from the
# agent's perspective for display, though SearXNG itself has its own DNS.)
# These are not in the outbound whitelist because the agent never talks to
# them directly – but we include them so DNS doesn't leak info about blocked queries.

echo ""
echo "[dns-relay] Loaded ${count} whitelisted domains"
echo "[dns-relay] All other DNS queries will be REFUSED"
echo ""

exec dnsmasq --conf-file="$CONF"
