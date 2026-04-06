# Docker Disk Cleanup Guide

Guía de referencia para limpiar el espacio en disco ocupado por Docker cuando el disco se llena.

## Contexto del problema

`docker compose pull` **no actualiza** los servicios que usan `build:` (como `openclaw`, `reader`, `dns`, `clawroute`). Solo actualiza servicios con `image:` directo (proxy, searxng, caddy, browserless). Para actualizar openclaw hay que hacer `docker pull` de la imagen base y luego `docker compose build --no-cache openclaw`.

El proceso de rebuild puede llenar el disco si hay imágenes acumuladas. Esta guía detalla cómo limpiar de forma segura.

---

## ¿Qué es seguro borrar?

**Seguro borrar (Docker interno):**
- Imágenes sin usar (dangling + no referenciadas)
- Contenedores parados
- Networks no usadas
- Build cache
- Volúmenes Docker *no usados* — en este compose **no hay volúmenes Docker nombrados**, todo son bind mounts en disco

**NO tocar (datos persistentes en disco del host):**
- `lobster-cage/data/` → memorias y configuración de OpenClaw (`/home/node/.openclaw`)
- `lobster-cage/gogcli/` → credenciales de gogcli
- `lobster-cage/clawroute_data/` → datos de ClawRoute
- `~/.codex/auth.json` → token OAuth de Codex

---

## Pasos para limpiar y reconstruir

### 1. Bajar el stack

```bash
cd lobster-cage/

# Si docker compose down falla (cwd incorrecto o archivo vacío):
docker stop openclaw_agent openclaw_browserless openclaw_clawroute \
             openclaw_searxng openclaw_proxy openclaw_dns openclaw_reader openclaw_caddy
docker rm   openclaw_agent openclaw_browserless openclaw_clawroute \
             openclaw_searxng openclaw_proxy openclaw_dns openclaw_reader openclaw_caddy
```

### 2. Ver cuánto espacio ocupa Docker

```bash
docker system df
df -h /
```

### 3. Limpiar TODO lo que Docker no está usando

```bash
# Elimina: imágenes sin usar, contenedores parados, networks huérfanas, build cache
docker system prune -a -f

# Elimina volúmenes Docker no usados (aquí son solo internos, los datos reales son bind mounts)
docker volume prune -f
```

Esto libera entre 10-15 GB en un sistema con historial de builds acumulado.

### 4. Verificar espacio liberado

```bash
df -h /
docker system df
```

### 5. Pull de la imagen base de OpenClaw

```bash
docker pull ghcr.io/openclaw/openclaw:latest
```

### 6. Rebuild del compose completo desde cero

```bash
cd lobster-cage/
docker compose build --no-cache
```

### 7. Levantar el stack

```bash
docker compose up -d
```

### 8. Verificar que todo está healthy

```bash
docker compose ps
docker compose logs openclaw --tail=20
```

---

## Cambio realizado en docker-compose.yml (2026-04-06)

Se añadieron los flags `--disable-crash-reporter --no-crashpad` al `DEFAULT_LAUNCH_ARGS` de browserless. La imagen `ghcr.io/browserless/chromium:latest` actualizada requería estos flags o Chromium fallaba al arrancar con el error:

```
chrome_crashpad_handler: --database is required
```

```yaml
# Antes:
- DEFAULT_LAUNCH_ARGS=--proxy-server=http://proxy:8888

# Después:
- DEFAULT_LAUNCH_ARGS=--proxy-server=http://proxy:8888 --disable-crash-reporter --no-crashpad
```

---

## Comandos de referencia rápida

```bash
# Ver uso de disco Docker
docker system df

# Limpeza segura (solo dangling images y contenedores parados)
docker system prune -f

# Limpieza agresiva (todas las imágenes no activas + build cache)
docker system prune -a -f && docker volume prune -f

# Rebuild solo openclaw
docker pull ghcr.io/openclaw/openclaw:latest
docker compose build --no-cache openclaw
docker compose up -d openclaw

# Ver logs en tiempo real
docker compose logs openclaw -f
```
