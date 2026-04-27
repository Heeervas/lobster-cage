#!/bin/bash
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
INSTALL_DIR="/opt/hermes"

# ─── Copy plugins on first boot ──────────────────────────────────
if [ -d /opt/hermes-plugins ] && [ ! -d "${HERMES_HOME}/plugins/web-search-plus" ]; then
    mkdir -p "${HERMES_HOME}/plugins"
    cp -r /opt/hermes-plugins/* "${HERMES_HOME}/plugins/"
    echo "[entrypoint] Plugins copied to ${HERMES_HOME}/plugins/"
fi

# ─── Re-apply Hermes patches (idempotent) ────────────────────────
# Ensures patches survive even if the agent overwrites files at runtime.
if [ -f "$INSTALL_DIR/patches/patch_prompt_load_callback.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_prompt_load_callback.py" 2>&1 | sed 's/^/[entrypoint] /'
fi
if [ -f "$INSTALL_DIR/patches/patch_checkpoint_rollback_scan.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_checkpoint_rollback_scan.py" 2>&1 | sed 's/^/[entrypoint] /'
fi
if [ -f "$INSTALL_DIR/patches/patch_mcp_proxy_env.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_mcp_proxy_env.py" 2>&1 | sed 's/^/[entrypoint] /'
fi
if [ -f "$INSTALL_DIR/patches/patch_mcp_stdio_preamble_filter.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_mcp_stdio_preamble_filter.py" 2>&1 | sed 's/^/[entrypoint] /'
fi
if [ -f "$INSTALL_DIR/patches/patch_post_tool_empty_retry.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_post_tool_empty_retry.py" 2>&1 | sed 's/^/[entrypoint] /'
fi

# ─── Privilege dropping via gosu (mirrors upstream entrypoint) ───
# We replicate the base entrypoint's gosu logic here so we can start
# the dashboard as a sibling process alongside the gateway.
if [ "$(id -u)" = "0" ]; then
    if [ -n "$HERMES_UID" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
        echo "Changing hermes UID to $HERMES_UID"
        usermod -u "$HERMES_UID" hermes
    fi
    if [ -n "$HERMES_GID" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
        echo "Changing hermes GID to $HERMES_GID"
        groupmod -g "$HERMES_GID" hermes
    fi
    actual_uid=$(id -u hermes)
    if [ "$(stat -c %u "$HERMES_HOME" 2>/dev/null)" != "$actual_uid" ]; then
        echo "$HERMES_HOME is not owned by $actual_uid, fixing"
        chown -R hermes:hermes "$HERMES_HOME"
    fi
    echo "Dropping root privileges"
    exec gosu hermes "$0" "$@"
fi

# ─── Running as hermes from here ─────────────────────────────────
source "${INSTALL_DIR}/.venv/bin/activate"

# Create essential directory structure
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills,skins,plans,workspace,home}

# ─── Ensure venv PATH survives login shells ──────────────────────
# Docker ENV PATH works for non-login shells, but login shells (bash -l,
# su -, SSH, cron, agent terminal tool) reset PATH via /etc/login.defs
# and only read ~/.profile which doesn't know about the venv.
# Idempotently inject the venv activation into .bashrc and .profile.
_venv_marker="# hermes-venv-path"
for _rc in "$HERMES_HOME/.bashrc" "$HERMES_HOME/.profile"; do
    if [ -f "$_rc" ] && ! grep -q "$_venv_marker" "$_rc" 2>/dev/null; then
        printf '\n%s\nexport PATH="/opt/hermes/.venv/bin:$PATH"\n' "$_venv_marker" >> "$_rc"
    fi
done

# Bootstrap config files (first boot only)
[ ! -f "$HERMES_HOME/.env" ] && cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
[ ! -f "$HERMES_HOME/config.yaml" ] && cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
[ ! -f "$HERMES_HOME/SOUL.md" ] && cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"

if [ -f "$INSTALL_DIR/patches/patch_chrome_devtools_ws_auth.py" ]; then
    python3 "$INSTALL_DIR/patches/patch_chrome_devtools_ws_auth.py" 2>&1 | sed 's/^/[entrypoint] /'
fi

# Sync bundled skills (manifest-based, preserves user edits)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

# ─── Start dashboard in background ──────────────────────────────
if [ "${HERMES_DASHBOARD_ENABLED:-true}" = "true" ]; then
    DASHBOARD_PORT="${HERMES_DASHBOARD_PORT:-9119}"
    echo "[entrypoint] Starting dashboard on port ${DASHBOARD_PORT}"
    hermes dashboard --host 0.0.0.0 --port "${DASHBOARD_PORT}" --no-open --insecure 2>&1 | sed 's/^/[dashboard] /' &
fi

# ─── Start profile gateways in background ────────────────────────
# Auto-starts profile gateways listed in HERMES_AUTOSTART_PROFILES (comma-separated).
# Each profile gets a unique API server port: default=8642, profiles get 8643, 8644, ...
# Only profiles with their own bot token should be listed (same token = conflict).
if [[ "$1" == "gateway" ]] && [ -n "${HERMES_AUTOSTART_PROFILES:-}" ]; then
    PROFILE_PORT="${API_SERVER_PORT:-8642}"
    IFS=',' read -ra _profiles <<< "$HERMES_AUTOSTART_PROFILES"
    for profile_name in "${_profiles[@]}"; do
        profile_name="$(echo "$profile_name" | xargs)"  # trim whitespace
        [ -z "$profile_name" ] && continue
        profile_dir="${HERMES_HOME}/profiles/${profile_name}"
        if [ ! -f "${profile_dir}/config.yaml" ]; then
            echo "[entrypoint] Profile '${profile_name}' has no config.yaml — skipping"
            continue
        fi
        PROFILE_PORT=$((PROFILE_PORT + 1))
        echo "[entrypoint] Starting profile '${profile_name}' gateway (API port ${PROFILE_PORT})"
        API_SERVER_PORT="${PROFILE_PORT}" hermes -p "${profile_name}" gateway run \
            2>&1 | sed "s/^/[profile:${profile_name}] /" &
    done
fi

# ─── Start main command ─────────────────────────────────────────
exec hermes "$@"
