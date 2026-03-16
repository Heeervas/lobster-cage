#!/usr/bin/env bash
# swap-ollama-model.sh — delete an Ollama model and pull a new one
#
# Usage:
#   ./swap-ollama-model.sh <new-model>              # just pull
#   ./swap-ollama-model.sh <old-model> <new-model>  # delete old, then pull new

set -euo pipefail

CONTAINER="openclaw_ollama"

# The Ollama container has http_proxy set for model downloads, but the ollama CLI
# connects to the local daemon (127.0.0.1:11434). Go's http client does not always
# honour NO_PROXY for loopback addresses when proxy env vars are present — clear
# them for all CLI exec calls, keep them only for the actual pull (which downloads
# from registry.ollama.ai through Tinyproxy).
OLLAMA_EXEC=(docker exec
    -e http_proxy="" -e https_proxy="" -e HTTP_PROXY="" -e HTTPS_PROXY=""
    "$CONTAINER" ollama)

echo "→ Refreshing network whitelist (restarting proxy and dns)..."
docker compose restart proxy dns >/dev/null 2>&1 || true
# Wait for proxy to be healthy before attempting pulls — Docker's embedded DNS
# returns SERVFAIL for restarting container names during the brief window.
echo "→ Waiting for proxy to become healthy..."
for i in $(seq 1 30); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "${CONTAINER%_ollama}_proxy" 2>/dev/null || echo unknown)
    if [[ "$STATUS" == "healthy" ]]; then break; fi
    sleep 1
done

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 [old-model] <new-model>"
    echo "  Example: $0 granite4:350m"
    echo ""
    echo "Currently installed models:"
    "${OLLAMA_EXEC[@]}" list || echo "Ollama service not responding."
    exit 1
fi

if [[ $# -eq 1 ]]; then
    OLD_MODEL=""
    NEW_MODEL="$1"
elif [[ $# -eq 2 ]]; then
    OLD_MODEL="$1"
    NEW_MODEL="$2"
else
    echo "Error: Too many arguments."
    exit 1
fi

if [[ -n "$OLD_MODEL" ]]; then
    echo "→ Checking if $OLD_MODEL exists..."
    if "${OLLAMA_EXEC[@]}" list | grep -q "$OLD_MODEL"; then
        echo "→ Deleting $OLD_MODEL from $CONTAINER..."
        "${OLLAMA_EXEC[@]}" rm "$OLD_MODEL"
        echo "  Deleted."
    else
        echo "  Notice: $OLD_MODEL not found, skipping deletion."
    fi
fi

echo "→ Pulling $NEW_MODEL into $CONTAINER..."
"${OLLAMA_EXEC[@]}" pull "$NEW_MODEL"
echo "  Done."

# Bake num_ctx=16384 into the model's Modelfile.
# Ollama's OpenAI-compat API ignores OLLAMA_NUM_CTX and request-body options;
# the only reliable way to set context window is via the model's own Modelfile.
echo "→ Setting num_ctx=16384 in Modelfile for $NEW_MODEL..."
docker exec \
    -e http_proxy="" -e https_proxy="" -e HTTP_PROXY="" -e HTTPS_PROXY="" \
    "$CONTAINER" \
    sh -c "printf 'FROM ${NEW_MODEL}\\nPARAMETER num_ctx 16384\\n' > /tmp/Modelfile && ollama create '${NEW_MODEL}' -f /tmp/Modelfile"
echo "  num_ctx=16384 baked in."

echo ""
echo "Installed models:"
"${OLLAMA_EXEC[@]}" list
