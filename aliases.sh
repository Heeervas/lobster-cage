#!/bin/bash
# lobster-cage/aliases.sh — Persistent aliases for Hermes / OpenClaw / wger
# Usage: echo 'source /path/to/lobster-cage/aliases.sh' >> ~/.bashrc
# source ~/repos/my-lobster/lobster-cage/aliases.sh

CAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DATA_DIR="${HERMES_DATA_PATH:-$HOME/.custom_claw/hermes}"

# ─── Hermes (default stack) ──────────────────────────────────────
alias hermes-up="cd \"$CAGE_DIR\" && docker compose up -d"
alias hermes-down="cd \"$CAGE_DIR\" && docker compose down"
alias hermes-logs="cd \"$CAGE_DIR\" && docker compose logs -f hermes"
alias hermes-rebuild="cd \"$CAGE_DIR\" && docker compose build hermes && docker image prune -f && docker compose up -d hermes"
alias hermes-shell="docker exec -it -u hermes hermes_agent bash"
alias hermes-update="cd \"$CAGE_DIR\" && docker compose pull hermes && docker compose up -d hermes"
alias hermes-restart="cd \"$CAGE_DIR\" && docker compose restart hermes"
alias hermes-doctor="docker exec -u hermes hermes_agent hermes doctor"
alias hermes-profiles="docker exec -u hermes hermes_agent hermes profile list"
alias hermes-coach-start="docker exec -d -u hermes hermes_agent hermes -p coach gateway run"
alias hermes-coach-stop="docker exec -d -u hermes hermes_agent hermes -p coach gateway stop"
alias hermes-cache-top="du -ah --max-depth=2 \"$HERMES_DATA_DIR/.cache\" \"$HERMES_DATA_DIR/.npm\" 2>/dev/null | sort -hr | head -n 20"
alias hermes-cache-live="docker exec -u hermes hermes_agent sh -lc 'du -ah --max-depth=2 /opt/data/.cache /opt/data/.npm /home/hermes/.cache /home/hermes/.npm 2>/dev/null | sort -hr | head -n 20'"
alias hermes-cache-clean="rm -rf \"$HERMES_DATA_DIR/.cache/huggingface\" \"$HERMES_DATA_DIR/.npm/_cacache\" \"$HERMES_DATA_DIR/.npm/_npx\"; find \"$HERMES_DATA_DIR/.npm/_logs\" -type f -delete 2>/dev/null; du -ah --max-depth=2 \"$HERMES_DATA_DIR/.cache\" \"$HERMES_DATA_DIR/.npm\" 2>/dev/null | sort -hr | head -n 20"
alias hermes-dashboard="echo 'https://localhost:9119'"

# ─── OpenClaw (via override file) ────────────────────────────────
_OPENCLAW_COMPOSE="-f docker-compose.yml -f docker-compose.openclaw.yml"
alias openclaw-up="cd \"$CAGE_DIR\" && docker compose $_OPENCLAW_COMPOSE up -d"
alias openclaw-down="cd \"$CAGE_DIR\" && docker compose $_OPENCLAW_COMPOSE down"
alias openclaw-logs="cd \"$CAGE_DIR\" && docker compose $_OPENCLAW_COMPOSE logs -f openclaw"
alias openclaw-rebuild="cd \"$CAGE_DIR\" && docker compose $_OPENCLAW_COMPOSE build openclaw && docker image prune -f && docker compose $_OPENCLAW_COMPOSE up -d openclaw"
alias openclaw-shell="docker exec -it openclaw_agent bash"
alias openclaw-update="cd \"$CAGE_DIR\" && docker compose $_OPENCLAW_COMPOSE pull openclaw && docker compose $_OPENCLAW_COMPOSE up -d openclaw"

# ─── wger (via override file) ────────────────────────────────────
_WGER_COMPOSE="-f docker-compose.yml -f docker-compose.wger.yml"
alias wger-up="cd \"$CAGE_DIR\" && docker compose $_WGER_COMPOSE up -d"
alias wger-down="cd \"$CAGE_DIR\" && docker compose $_WGER_COMPOSE down"
alias wger-logs="cd \"$CAGE_DIR\" && docker compose $_WGER_COMPOSE logs -f wger_web"
alias wger-rebuild="cd \"$CAGE_DIR\" && docker compose $_WGER_COMPOSE up -d --build wger_web"
alias wger-shell="docker exec -it wger_web bash"
alias wger-manage="docker exec -it wger_web python3 manage.py"
alias wger-status="echo 'http://localhost:8000'"

# ─── Common ──────────────────────────────────────────────────────
alias cage-status="cd \"$CAGE_DIR\" && docker compose ps"
alias cage-logs="cd \"$CAGE_DIR\" && docker compose logs -f"
alias cage-restart="cd \"$CAGE_DIR\" && docker compose restart"
alias cage-cleanup="docker image prune -f && docker builder prune -f"
alias cage-apt-clean="sudo apt clean && sudo apt autoremove -y"
alias cage-snap-clean-disabled="bash -lc 'snap list --all | awk '\''/disabled/{print \$1, \$3}'\'' | while read -r snapname revision; do sudo snap remove \"\$snapname\" --revision=\"\$revision\"; done'"
alias cage-snap-retain-2="sudo snap set system refresh.retain=2 && snap get system refresh.retain"
alias cage-apport-clean="sudo find /var/lib/apport -type f \\( -name '*.crash' -o -name '*.upload' -o -name '*.uploaded' \\) -delete && du -ah --max-depth=2 /var/lib/apport 2>/dev/null | sort -hr | head -n 20"
alias cage-varlib-top="du -ah --max-depth=1 /var/lib 2>/dev/null | sort -hr | head -n 5"
alias cage-disk="docker system df && echo '---' && df -h /home"