# Hermes: Nuke & Start Fresh

How to completely wipe Hermes and start from scratch.

**Your OpenClaw data is NOT affected** — it lives at the path set by `OPENCLAW_DATA_PATH` in `.env` (default: `./data`). Hermes and OpenClaw use completely separate data directories.

---

## Quick Nuke (keep the image, wipe data only)

```bash
cd lobster-cage

# 1. Stop Hermes
docker compose -f docker-compose.yml -f docker-compose.hermes.yml stop hermes

# 2. Remove the container
docker compose -f docker-compose.yml -f docker-compose.hermes.yml rm -f hermes

# 3. Delete all Hermes data (memories, sessions, plugins, config)
#    Default path: ./hermes-data — check HERMES_DATA_PATH in .env
sudo rm -rf ./hermes-data

# 4. Recreate the data directory
mkdir ./hermes-data

# 5. Start fresh
docker compose -f docker-compose.yml -f docker-compose.hermes.yml up -d hermes
```

## Full Nuke (wipe data + rebuild image from scratch)

```bash
cd lobster-cage

# 1. Stop and remove Hermes container
docker compose -f docker-compose.yml -f docker-compose.hermes.yml down --remove-orphans

# 2. Remove the Hermes image
docker rmi $(docker images -q lobster-cage-hermes) 2>/dev/null

# 3. Delete all Hermes data
sudo rm -rf ./hermes-data
mkdir ./hermes-data

# 4. Rebuild from scratch and start
docker compose -f docker-compose.yml -f docker-compose.hermes.yml build hermes --no-cache
docker compose -f docker-compose.yml -f docker-compose.hermes.yml up -d
```

## Go Back to OpenClaw (remove Hermes entirely)

```bash
cd lobster-cage

# 1. Stop Hermes stack
docker compose -f docker-compose.yml -f docker-compose.hermes.yml down --remove-orphans

# 2. Remove Hermes image and data
docker rmi $(docker images -q lobster-cage-hermes) 2>/dev/null
sudo rm -rf ./hermes-data

# 3. Start with base compose only (OpenClaw)
docker compose up -d
```

## What Lives Where

| Data | Path | Controlled by |
|------|------|--------------|
| OpenClaw | `OPENCLAW_DATA_PATH` in `.env` | `docker-compose.yml` |
| Hermes | `HERMES_DATA_PATH` in `.env` (default: `~/.custom_claw/hermes`) | `docker-compose.hermes.yml` |
| gogcli (OpenClaw) | `./gogcli` | `docker-compose.yml` |
| gogcli (Hermes) | `/home/hermes/.config/gogcli` inside container | `docker-compose.hermes.yml` |

The two agents share **no data volumes**. Nuking one never affects the other.
