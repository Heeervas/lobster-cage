#!/bin/bash

# OpenClaw Permissions Fixer
# This script aligns ownership and permissions for the OpenClaw data directory
# so the agent (UID 1000) can read/write files manually added on the host.

DATA_DIR="/home/mbpro/.custom_claw/data"
UID_GID="1000:1000"

echo "🔧 Adjusting permissions for OpenClaw data at: $DATA_DIR"

if [ ! -d "$DATA_DIR" ]; then
    echo "❌ Error: Directory $DATA_DIR does not exist."
    exit 1
fi

# Set ownership to UID 1000 (node user in container / mbpro on host)
sudo chown -R $UID_GID "$DATA_DIR"

# Fix directory permissions (755: rwxr-xr-x) - needs to be traversable
find "$DATA_DIR" -type d -exec chmod 755 {} +

# Fix file permissions (644: rw-r--r--) - standard readable/writable
find "$DATA_DIR" -type f -exec chmod 644 {} +

# Secure sensitive credentials (recursive match for credentials/ or .json files containing keys)
# Defaulting to 600 (rw-------) for known sensitive paths
if [ -d "$DATA_DIR/credentials" ]; then
    chmod 700 "$DATA_DIR/credentials"
    find "$DATA_DIR/credentials" -type f -exec chmod 600 {} +
fi

if [ -f "$DATA_DIR/openclaw.json" ]; then
    chmod 600 "$DATA_DIR/openclaw.json"
fi

echo "✅ Permissions updated successfully."
