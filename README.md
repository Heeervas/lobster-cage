# 🦞 Lobster Cage

**A Dockerized security cage for [OpenClaw](https://openclaw.io) AI agents.**

Your AI agent needs internet access to be useful — web search, APIs, reading pages. But that same access lets it exfiltrate your data. Lobster Cage solves this with **two layers of defense**:

1. **Structural** — an isolated Docker network with zero internet access, where every outbound request is routed through controlled, audited channels
2. **Behavioral** — security rules baked into the agent's SOUL.md that teach it to never leak sensitive data

Six containers. One whitelist file. The agent gets everything it needs; you keep control. An optional `SOUL.md.example` template adds behavioral security rules on top.

```bash
git clone https://github.com/YOUR_USERNAME/lobster-cage.git && cd lobster-cage
./setup.sh && nano .env && docker compose up -d
```

---

## What you get — and where the limits are

Lobster Cage defends in two layers: **structural barriers** that are physically impossible to bypass, and **security rules in the agent's SOUL.md** that address the remaining residual risks behaviorally.

### ✅ Blocked — structurally impossible, regardless of how clever the agent is

| Attack | How it's blocked |
|--------|-----------------|
| Agent connects to the internet | Internal-only Docker network — **no route exists** |
| Agent connects to arbitrary IPs | Network topology prevents it, not just firewall rules |
| Agent resolves unknown domains | DNS relay only resolves whitelisted domains → everything else **REFUSED** |
| Agent sends POST/PUT/DELETE to random sites | Non-whitelisted URLs → GET-only reader proxy, write methods rejected |
| Agent accesses your LAN | Reader blocks RFC 1918, link-local, loopback IPs |
| Agent accesses cloud metadata (169.254.x) | Reader blocks metadata endpoints |
| Agent opens a reverse shell | No DNS + no TCP out + no route = nowhere to connect |
| Agent does DNS tunneling | DNS relay only forwards whitelisted domains; can't encode data in queries to unknown domains |
| Agent uses raw sockets / ICMP tunnel | All Linux capabilities dropped (`cap_drop: ALL`) |
| Agent escalates privileges (setuid) | `no-new-privileges` security option active |
| Agent modifies proxy-bootstrap.js | File mounted read-only from host (`:ro`) |
| Agent bypasses proxy via subprocess | `http_proxy` / `https_proxy` env vars → all HTTP goes through Tinyproxy |
| Someone uses the proxy from outside | Tinyproxy only allows `172.28.0.0/24` (Docker internal subnet) |
| Agent changes its own DNS server | Docker `dns:` config is read-only; even if changed, no route to external DNS |

### ⚠️ Residual risk — mitigated by SOUL.md security rules + audit logging

These vectors are inherent to *any* system that gives an AI agent internet access. The cage can't block them structurally — but the security rules in **SOUL.md** teach the agent to avoid them, and **audit logging** makes every attempt visible.

| Attack | Why it can't be blocked structurally | SOUL.md mitigation | Audit log |
|--------|--------------------------------------|-------------------|----------|
| Data exfil via search queries | Agent searches "my-secret-key" — SearXNG forwards to Google | Never put real secrets in search queries — search for the pattern, not the instance | `[proxy-audit] SEARCH q="..."` |
| Data exfil via GET parameters | Agent fetches `evil.com/log?d=secret` via reader | Never put sensitive data in URLs | `[reader-audit] FETCH https://...` |
| Data exfil via whitelisted APIs | Agent POSTs secrets to Telegram or OpenAI | Only send data the user explicitly asked to send; never print full API keys | `[proxy-audit] WHITELIST POST ...` |
| Data exfil via curl/subprocess | curl uses proxy env vars → Tinyproxy → whitelisted domain | Same rules apply to subprocesses; check commands before running | Tinyproxy access log |
| Accidental secret exposure | Agent prints API key in chat or writes it to a file | Check keys with `[ -n "$VAR" ]`, never `echo $VAR`; reference env vars, don't hardcode | — |
| Agent ignores security context | Agent doesn't know it's in a cage, makes wrong assumptions | SOUL.md describes network topology, proxy routing — agent can troubleshoot instead of guessing | — |

> **SOUL.md rules are instructions, not enforcement.** A jailbroken agent could ignore them. The structural cage remains the hard boundary. The SOUL.md is the second line of defense — it reduces the *probability* of data leaks, the cage reduces the *possibility*.

### ❌ Not addressed — and why that's acceptable

| Attack | Why it's not covered | Practical risk | Could be reduced by |
|--------|---------------------|---------------|---------------------|
| Timing side channels | Would need kernel-level isolation | Extremely low bandwidth — impractical | Not feasible in Docker |
| Container escape (kernel exploit) | Standard Docker + `cap_drop: ALL` + `no-new-privileges` | Very hard without capabilities | Run Docker in rootless mode; use gVisor/Kata Containers |
| Supply chain attack on OpenClaw image | We trust `ghcr.io/openclaw/openclaw:latest` | Upstream compromise — out of scope | Pin image to specific digest (`@sha256:...`) instead of `:latest` |
| Credential theft inside container | API keys are env vars; compromised container reads them | Inherent to any Docker app that needs API keys | Use Docker secrets or an external vault (HashiCorp Vault, SOPS) |

### The bottom line

> **Lobster Cage makes it structurally impossible for the agent to establish arbitrary outbound connections.** The remaining vectors — search queries, GET parameters, whitelisted API calls — are inherent to giving *any* AI internet access. They're addressed with a combination of **SOUL.md security rules** (behavioral) and **audit logging** (visibility). Two layers: the cage makes exfiltration *structurally hard*, the SOUL.md makes it *behaviorally unlikely*.

---

## Architecture

### The big picture

```
                        You ──HTTPS──▶ :18789
                                │
                         ┌──────┴──────┐
                         │    Caddy    │  TLS + Basic Auth
                         └──────┬──────┘
                                │
════════════════════════════════╪══════════════════════════════ internal network ═══
                                │
                         ┌──────┴──────┐
                         │   OpenClaw  │  AI Agent
                         │    :18789   │
                         └──┬──┬──┬──┬─┘
                            │  │  │  │
              ┌─────────────┘  │  │  └──────────────┐
              │       ┌────────┘  └─────────┐       │
              ▼       ▼                     ▼       ▼
        ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
        │  SearXNG  │ │ Outbound  │ │  Reader   │ │    DNS    │
        │   :8080   │ │   Proxy   │ │   :3000   │ │   Relay   │
        │           │ │   :8888   │ │           │ │    :53    │
        └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
              │             │             │             │
══════════════╪═════════════╪═════════════╪═════════════╪═════ external network ═══
              ▼             ▼             ▼             ▼
           Search        APIs         Websites       DNS servers
           engines     (POST OK,     (GET only,     (whitelisted
                      whitelisted)   text only)     domains only)
```

### The four channels

| # | Channel | What it does | Methods | How it works |
|---|---------|-------------|---------|--------------|
| 1 | **SearXNG** | Self-hosted meta search engine (Google, Bing, DDG, Wikipedia) | GET | `proxy-bootstrap.js` intercepts Brave API calls → redirects to SearXNG |
| 2 | **Outbound Proxy** | Tinyproxy — forwards to whitelisted domains only | All | Agent calls APIs (OpenAI, Telegram, GitHub, …). Non-whitelisted → denied |
| 3 | **Reader** | Python GET-only web page reader, returns plain text | GET only | Non-whitelisted URLs → Reader fetches, strips HTML, blocks private IPs |
| 4 | **DNS Relay** | dnsmasq — resolves whitelisted domains only | DNS | Everything not in `whitelist.txt` → REFUSED |

### How `proxy-bootstrap.js` routes traffic

This is the heart of the system. A Node.js preload script that patches `globalThis.fetch()` — every HTTP request the agent makes passes through it:

```
Agent calls fetch(url)
       │
       ▼
┌─ Is it api.search.brave.com? ──────────── YES ──▶ SearXNG (search)
│       │ NO
│       ▼
├─ Is it an internal service? ───────────── YES ──▶ Direct (Docker network)
│  (searxng, reader, proxy, caddy)                  ⚠ direct SearXNG access logged
│       │ NO
│       ▼
├─ Is the domain in whitelist.txt? ──────── YES ──▶ Outbound Proxy (full HTTP)
│       │ NO
│       ▼
└─ Everything else ──────────────────────────────▶ Reader Proxy (GET only, text)
```

The agent doesn't know it's being proxied. OpenClaw thinks it's talking to the Brave Search API; it's actually talking to your local SearXNG.

### Network isolation

| Network | Internet | Who's on it |
|---------|:--------:|-------------|
| `openclaw_internal` | ❌ No | All 6 services — agent can reach internal services only |
| `openclaw_external` | ✅ Yes | Proxy, SearXNG, Reader, Caddy, DNS — these need internet |

The agent is **only** on `openclaw_internal` (`internal: true`). Docker creates no default route to the host. The agent cannot open a TCP connection to any IP outside 172.28.0.0/24.

### Single source of truth

`outbound-proxy/whitelist.txt` feeds three systems simultaneously:

```
whitelist.txt ──▶ Tinyproxy (which domains can be reached via HTTP)
             ──▶ dnsmasq (which domains can be resolved via DNS)
             ──▶ proxy-bootstrap.js (which domains go through proxy vs. reader)
```

Add a domain once, restart, done.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/lobster-cage.git
cd lobster-cage

./setup.sh          # generates TLS cert + hashes password
nano .env           # add at least one API key
cp SOUL.md.example workspace/SOUL.md   # security-hardened agent identity
docker compose up -d
```

Open `https://<YOUR_LAN_IP>:18789` in your browser.

### What `setup.sh` does

1. Creates `.env` from `.env.example` if it doesn't exist
2. Generates a self-signed TLS certificate for your `LAN_IP`
3. Bcrypt-hashes your `CADDY_AUTH_PASSWORD` into `caddy/caddy.env`

---

## Services

| Service | Container | Image | What it does |
|---------|-----------|-------|-------------|
| **Caddy** | `openclaw_caddy` | `caddy:alpine` | HTTPS reverse proxy + basic auth — your entry point |
| **OpenClaw** | `openclaw_agent` | `ghcr.io/openclaw/openclaw:latest` + custom Dockerfile | AI agent + gateway runtime |
| **SearXNG** | `openclaw_searxng` | `searxng/searxng:latest` | Meta search engine (Google, Bing, DDG, Wikipedia) |
| **Reader** | `openclaw_reader` | Python 3.12 slim (custom) | GET-only web reader — fetches any URL, returns text |
| **Outbound Proxy** | `openclaw_proxy` | `docker-tinyproxy:latest` | HTTP proxy — whitelist-only, deny by default |
| **DNS Relay** | `openclaw_dns` | Alpine 3.19 + dnsmasq | DNS resolver — whitelist-only, REFUSED by default |

---

## Configuration

### .env

Copy `.env.example` to `.env` and fill in your values. You need **at least one** model provider.

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ≥1 needed | OpenAI API key |
| `OPENROUTER_API_KEY` | ≥1 needed | OpenRouter key (200+ models) |
| `GEMINI_API_KEY` | ≥1 needed | Google Gemini key |
| `COPILOT_GITHUB_TOKEN` | ≥1 needed | GitHub Copilot token |
| `NVIDIA_API_KEY` | ≥1 needed | NVIDIA API key |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot (enables chat via Telegram) |
| `CADDY_AUTH_PASSWORD` | Yes | Password for the web UI |
| `LAN_IP` | Yes | Your machine's LAN IP |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | Shared secret for device pairing |

See `.env.example` for the full list with URLs to get each key.

### Whitelisted domains

Edit `outbound-proxy/whitelist.txt` to control which APIs the agent can reach. Included out of the box:

GitHub/Copilot · Google/Gemini · NVIDIA · OpenAI · OpenRouter · Telegram · OpenClaw · Hugging Face · PyPI · npm · Debian APT · wttr.in

---

## Usage

```bash
docker compose up -d              # Start
docker compose down               # Stop
docker compose ps                 # Status
docker compose logs -f            # All logs
docker logs -f openclaw_agent     # Agent logs only
```

### OpenClaw CLI

```bash
docker exec -it openclaw_agent openclaw --help
docker exec -it openclaw_agent openclaw status
docker exec -it openclaw_agent openclaw tui
docker exec -it openclaw_agent openclaw channels status
```

### Updating

```bash
docker compose build --pull --no-cache openclaw reader
docker compose up -d
```

### Audit logs

Every outbound request is logged:

```bash
docker logs -f openclaw_agent 2>&1 | grep "proxy-audit"    # Proxy routing decisions
docker logs -f openclaw_reader 2>&1 | grep "reader-audit"  # Reader fetches
docker logs -f openclaw_dns                                 # DNS queries
docker logs -f openclaw_proxy                               # Tinyproxy access
```

---

## Personalization

Your personal config lives in two gitignored files:

| File | What it's for |
|------|---------------|
| `.env` | API keys, passwords, LAN IP |
| `docker-compose.override.yml` | Extra mounts, optional integrations |
| `workspace/SOUL.md` | Agent identity + security rules (from `SOUL.md.example`) |

```bash
cp .env.example .env
cp docker-compose.override.example.yml docker-compose.override.yml
nano .env                        # fill in your API keys
nano docker-compose.override.yml # uncomment what you need
```

### Optional: Nextcloud CalDAV

Gives the agent calendar access (read + write events).

1. Uncomment the `NC_CALDAV_*` block in `docker-compose.override.yml`
2. Fill in `NC_CALDAV_URL`, `NC_CALDAV_USER`, `NC_CALDAV_APP_PASSWORD` in `.env`
3. Add your Nextcloud IP to `outbound-proxy/whitelist.txt`
4. Set `TLS_SKIP_VERIFY_HOSTS=your-nextcloud-ip` in `.env` (if self-signed cert)
5. `docker compose restart proxy dns openclaw`

### Optional: Home Assistant

Gives the agent smart home control via the HA REST API.

1. Uncomment the `HA_*` block in `docker-compose.override.yml`
2. Create a long-lived access token in HA (Profile → Security → Long-Lived Access Tokens)
3. Fill in `HA_URL` and `HA_TOKEN` in `.env`
4. Add your HA IP to `outbound-proxy/whitelist.txt`
5. `docker compose restart proxy dns openclaw`

### Adding other LAN services

1. Add the IP/hostname to `outbound-proxy/whitelist.txt`
2. If self-signed TLS: add to `TLS_SKIP_VERIFY_HOSTS` in `.env`
3. Pass any credentials via env vars in `docker-compose.override.yml`
4. `docker compose restart proxy dns openclaw`

---

## Extending the cage

### How to add a new whitelisted API

```bash
echo "api.example.com" >> outbound-proxy/whitelist.txt
docker compose restart proxy dns openclaw
```

Tinyproxy, dnsmasq, and proxy-bootstrap.js all read the same file.

### How to add a new container

```yaml
# In docker-compose.override.yml (not tracked by git)
services:
  my-service:
    image: whatever:latest
    container_name: openclaw_myservice
    networks:
      - openclaw_internal        # Agent can reach it
      # - openclaw_external      # Only if it needs internet
```

### What's safe to add

| Extension | Security impact |
|-----------|----------------|
| Calendar (CalDAV), Note API, Weather | Just whitelist the domain — same as any API |
| Local LLM (Ollama), Database, Vector DB | Container on `internal` only — zero internet, zero risk |
| Home Assistant, Nextcloud | Whitelist LAN IP — audited like any other API |
| Email **reading** (IMAP bridge) | Read-only bridge on `internal` — agent reads, can't send |

### What weakens the cage (think twice)

| Extension | Why it's risky |
|-----------|----------------|
| Arbitrary HTTP POST on reader | Opens exfiltration to any website |
| Full browser with cookies | Can login, exfiltrate via authenticated sessions |
| SSH to external hosts | Full shell access to another machine |
| Agent on `external` network | Defeats the entire cage |

---

## SOUL.md — Optional security rules for additional protection

The structural cage already blocks exfiltration at the network level — **it works without any SOUL.md configuration.** The included `SOUL.md.example` is an optional template that adds a second layer of defense: behavioral rules that teach the agent to handle the remaining open channels (search, web fetch, whitelisted APIs) responsibly.

If you want this extra protection, copy the template into your workspace:

```bash
cp SOUL.md.example workspace/SOUL.md
nano workspace/SOUL.md          # personalize tone, language, mission
```

### What the SOUL.md template covers

| Section | Addresses | What it teaches the agent |
|---------|-----------|---------------------------|
| **Security principles** | Exfil via search/URLs/APIs | Never put real secrets in queries — search for the pattern, not the instance. Never encode private data in URLs. Scrub configs before sharing. Never send memory files externally. |
| **Credential handling** | Credential leaks | Check if keys are set without printing them (`[ -n "$VAR" ]`). Reference env vars instead of hardcoding. Don't write secrets to workspace files. |
| **Audit awareness** | Evasion attempts | The agent knows every request is logged and acts accordingly. Can help the user review audit logs. Won't try to obfuscate requests. |
| **Cage awareness** | Misunderstandings / errors | The agent understands the network topology, proxy routing, and DNS whitelisting. Can self-diagnose connectivity issues instead of guessing. |

### How defense layers map to the threat model

```
✅ Structural barriers ──────────────── block 14 attack vectors (impossible to bypass)
⚠️ SOUL.md rules + audit logging ───── reduce 6 residual risks (behavioral + visibility)
❌ Out of scope ─────────────────────── 4 edge cases (kernel exploits, supply chain, etc.)
```

### Why SOUL.md and not separate skill files?

OpenClaw loads `SOUL.md` **on every session startup** — it's the agent's core identity. Security rules baked into the SOUL are always active, can't be missed, and don't need routing or discovery. Separate skill files would only be loaded if the agent happens to look at them.

> **Important:** SOUL.md rules are instructions, not enforcement. A jailbroken agent could ignore them. The structural cage remains the hard security boundary. The SOUL.md is the second line of defense — it makes data leaks *behaviorally unlikely*, while the cage makes arbitrary exfiltration *structurally impossible*.

---

## File Structure

```
lobster-cage/
├── docker-compose.yml                  # All 6 services + 2 networks
├── docker-compose.override.example.yml # Template for personal overrides
├── setup.sh                            # One-time setup (TLS + password hash)
├── .env.example                        # Template for secrets
├── agent/
│   ├── Dockerfile                      # Extends official OpenClaw image
│   └── proxy-bootstrap.js              # Transparent fetch() router + audit log
├── caddy/
│   └── Caddyfile                       # HTTPS reverse proxy config
├── dns/
│   └── entrypoint.sh                   # DNS whitelisting (reads whitelist.txt)
├── outbound-proxy/
│   ├── tinyproxy.conf                  # Proxy settings
│   └── whitelist.txt                   # THE whitelist (proxy + DNS + bootstrap)
├── searxng/
│   ├── settings.yml                    # Search engine config
│   └── limiter.toml                    # SearXNG rate limiter (disabled)
├── reader/
│   ├── Dockerfile                      # Python 3.12 slim
│   └── server.py                       # GET-only web reader + audit log
├── SOUL.md.example                     # Security-hardened SOUL template → copy to workspace/
└── tools/
    └── oauth-catcher.py                # OAuth callback helper
```

Files **not** in the repo (gitignored, personal):

```
.env                            # Your API keys and passwords
docker-compose.override.yml     # Your personal mounts and integrations
caddy/caddy.env                 # Bcrypt hash (generated by setup.sh)
certs/                          # TLS certificates (generated by setup.sh)
data/                           # Agent state, memories, configs
workspace/                      # Agent workspace (incl. your SOUL.md)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| API call hangs | Domain not in `whitelist.txt` | Add domain, `docker compose restart proxy dns openclaw` |
| `403` from proxy | Same | Same |
| Empty search results | SearXNG can't reach search engines | `docker logs openclaw_searxng` |
| Reader returns `502` | Target site is down or blocking | `docker logs openclaw_reader` |
| DNS errors | Domain not whitelisted | Check `whitelist.txt`, `docker compose restart dns` |
| TLS errors to LAN host | Self-signed cert not trusted | Add hostname to `TLS_SKIP_VERIFY_HOSTS` |
| `web_search` returns nothing | SearXNG API format changed | Check SearXNG version, `docker compose pull searxng` |
| Agent can't install packages | `pypi.org` or `deb.debian.org` blocked | Should be in whitelist by default — check DNS |

---

## License

MIT
