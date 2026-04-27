FROM nousresearch/hermes-agent:v2026.4.23

USER root

# Make venv available to all processes (docker exec, cron, etc.)
ENV PATH="/opt/hermes/.venv/bin:$PATH"

# Ensure venv PATH survives login shells (bash -l, su -, SSH, sh)
# /etc/profile.d/ is sourced by both bash and sh login shells
RUN echo 'export PATH="/opt/hermes/.venv/bin:$PATH"' > /etc/profile.d/hermes-venv.sh

# CLI-Toolbox: Network, System, Dev, Data Processing, Media
# (matches OpenClaw's toolbox minus packages the base image already includes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # --- Network ---
    curl \
    wget \
    iputils-ping \
    dnsutils \
    netcat-openbsd \
    traceroute \
    nmap \
    whois \
    openssh-client \
    rsync \
    # --- System (procps already in base image since v0.8.0) ---
    htop \
    less \
    file \
    tree \
    zip \
    unzip \
    # --- Editors ---
    nano \
    vim-tiny \
    # --- Dev (git already in base image since v0.9.0) ---
    gh \
    make \
    g++ \
    pkg-config \
    # --- Data Processing ---
    jq \
    bc \
    xmlstarlet \
    # --- Documents ---
    poppler-utils \
    pandoc \
    # --- Media ---
    imagemagick \
    # --- Archives ---
    p7zip-full \
    xz-utils \
    # --- Diagnostics ---
    lsof \
    # --- TLS / Certs ---
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Persist APT proxy so runtime builds inside the container use the outbound proxy
RUN echo 'Acquire::http::Proxy "http://proxy:8888";' > /etc/apt/apt.conf.d/99proxy \
    && echo 'Acquire::https::Proxy "http://proxy:8888";' >> /etc/apt/apt.conf.d/99proxy

# Pre-installed Python packages into the upstream venv (v0.9.0+ uses .venv, not system Python)
RUN uv pip install --python /opt/hermes/.venv/bin/python \
    python-docx \
    pymupdf \
    numpy \
    pandas \
    matplotlib \
    requests \
    "yt-dlp[default]" \
    curl-cffi \
    PySocks \
    google-api-python-client \
    google-auth-oauthlib \
    google-auth-httplib2 \
    obsidiantools

# hermes-web-search-plus plugin (SearXNG support)
# Cloned to /opt/hermes-plugins/ at build time;
# entrypoint-wrapper copies to $HERMES_HOME/plugins/ on first boot
RUN git clone --depth 1 https://github.com/robbyczgw-cla/hermes-web-search-plus.git \
    /opt/hermes-plugins/web-search-plus

# Proxy bootstrap Python (audit + Brave→SearXNG interception)
# Loaded via PYTHONPATH=/opt/hermes/bootstrap → sitecustomize.py
COPY proxy-bootstrap.py /opt/hermes/bootstrap/sitecustomize.py

# CDP patch: rewrites browserless 0.0.0.0 WebSocket URLs → Docker hostname
# Loaded via NODE_OPTIONS=--require=/opt/hermes/bootstrap/cdp-patch.js
COPY cdp-patch.js /opt/hermes/bootstrap/cdp-patch.js

# Install gogcli (Google CLI — Gmail, Calendar, Drive, Docs, Sheets, etc.)
# https://github.com/steipete/gogcli
RUN set -eux; \
    GOGCLI_VERSION="0.12.0"; \
    ARCH="$(dpkg --print-architecture)"; \
    curl -fsSL "https://github.com/steipete/gogcli/releases/download/v${GOGCLI_VERSION}/gogcli_${GOGCLI_VERSION}_linux_${ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin gog; \
    chmod +x /usr/local/bin/gog

# Install Deno (JS runtime required by yt-dlp EJS challenge solver)
RUN set -eux; \
    DENO_VERSION="2.2.3"; \
    ARCH="$(dpkg --print-architecture)"; \
    case "${ARCH}" in \
        amd64) DENO_ARCH="x86_64-unknown-linux-gnu" ;; \
        arm64) DENO_ARCH="aarch64-unknown-linux-gnu" ;; \
        *) echo "Unsupported arch: ${ARCH}" && exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${DENO_ARCH}.zip" \
        -o /tmp/deno.zip; \
    unzip /tmp/deno.zip -d /usr/local/bin; \
    rm /tmp/deno.zip; \
    chmod +x /usr/local/bin/deno

# Build dashboard frontend (SPA → hermes_cli/web_dist/)
# Pre-built at image time so the dashboard is instantly available on first boot.
# Remove web/package.json after build so the runtime `hermes dashboard` command
# skips the npm install/build step (which would fail behind the outbound proxy).
RUN cd /opt/hermes/web && npm ci --prefer-offline && npm run build && rm -rf node_modules .cache package.json

# UID remapping: the base entrypoint (v0.9.0+) handles this at runtime via gosu.
# Set HERMES_UID/HERMES_GID in docker-compose to match host volume ownership.
# No build-time usermod/chown needed — avoids a 3-minute find/chown over 5GB.

# Persist pip/uv proxy config (created as root; gosu drops to hermes at runtime)
RUN mkdir -p /opt/data/.config/pip \
    && printf '[global]\nproxy = http://proxy:8888\n' > /opt/data/.config/pip/pip.conf

# Entrypoint wrapper: copies plugins, re-applies patches, drops privileges via gosu,
# starts the web dashboard in background, then execs the gateway.
COPY entrypoint-wrapper.sh /opt/hermes/entrypoint-wrapper.sh
RUN chmod +x /opt/hermes/entrypoint-wrapper.sh

# Build-time patches for upstream Hermes files (survive base image updates)
COPY patches/ /opt/hermes/patches/
RUN python3 /opt/hermes/patches/patch_prompt_load_callback.py
RUN python3 /opt/hermes/patches/patch_api_server_port_autoincrement.py
RUN python3 /opt/hermes/patches/patch_checkpoint_rollback_scan.py
RUN python3 /opt/hermes/patches/patch_mcp_proxy_env.py
RUN python3 /opt/hermes/patches/patch_mcp_stdio_preamble_filter.py

# NOTE: No USER directive — the container starts as root so the base entrypoint
# can remap UID/GID via HERMES_UID/HERMES_GID and chown the data volume,
# then gosu drops to hermes. For docker exec, use: docker exec -u hermes ...

ENTRYPOINT ["/opt/hermes/entrypoint-wrapper.sh"]
