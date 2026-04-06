FROM ghcr.io/openclaw/openclaw:latest

USER root

# CLI-Toolbox: Network, System, Dev, Data Processing, Media
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get install -y --no-install-recommends \
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
    # --- System ---
    procps \
    htop \
    less \
    file \
    tree \
    zip \
    unzip \
    # --- Editors ---
    nano \
    vim-tiny \
    # --- Dev / Scripting ---
    git \
    gh \
    make \
    gcc \
    g++ \
    pkg-config \
    python3 \
    python3-pip \
    python3-venv \
    # --- Data Processing ---
    jq \
    bc \
    xmlstarlet \
    # --- PDF / Documents ---
    poppler-utils \
    pandoc \
    # --- Media ---
    ffmpeg \
    imagemagick \
    # --- Archive ---
    p7zip-full \
    xz-utils \
    # --- Search ---
    ripgrep \
    # --- Diagnostics (lsof needed by openclaw doctor) ---
    lsof \
    # --- TLS / Certs ---
    ca-certificates \
    openssl \
    # --- Browser (headless, no-sandbox mode) ---
    chromium \
    fonts-liberation \
    #Finish and cleanup
    && rm -rf /var/lib/apt/lists/* 
    

# Persist APT proxy so runtime builds inside the container use the outbound proxy
RUN echo 'Acquire::http::Proxy "http://proxy:8888";' > /etc/apt/apt.conf.d/99proxy \
    && echo 'Acquire::https::Proxy "http://proxy:8888";' >> /etc/apt/apt.conf.d/99proxy

# Install gogcli (Google CLI — Gmail, Calendar, Drive, Docs, Sheets, etc.)
# https://github.com/steipete/gogcli
RUN set -eux; \
    GOGCLI_VERSION="0.12.0"; \
    ARCH="$(dpkg --print-architecture)"; \
    curl -fsSL "https://github.com/steipete/gogcli/releases/download/v${GOGCLI_VERSION}/gogcli_${GOGCLI_VERSION}_linux_${ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin gog; \
    chmod +x /usr/local/bin/gog

# Persist pip proxy
RUN mkdir -p /home/node/.config/pip /home/node/.config/gogcli \
    && printf '[global]\nproxy = http://proxy:8888\n' > /home/node/.config/pip/pip.conf \
    && chown -R node:node /home/node/.config

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

# Pre-installed Python packages
RUN pip3 install --break-system-packages \
    python-docx \
    pymupdf \
    numpy \
    pandas \
    matplotlib \
    requests \
    "yt-dlp[default]" \
    curl-cffi

# Make the 'openclaw' CLI command available system-wide
# (the npm package declares bin: { openclaw: openclaw.mjs } but isn't globally linked)
RUN ln -sf /app/openclaw.mjs /usr/local/bin/openclaw \
 && chmod 755 /app/openclaw.mjs

# Install Playwright's Chromium — OpenClaw looks for this first (auto-detected, no browser config needed)
# Must be installed as root and made world-readable so the 'node' user can access it at runtime.
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers
RUN node /app/node_modules/playwright-core/cli.js install chromium \
    && chmod -R a+rx /usr/local/share/playwright-browsers

# Pre-create Node compile cache dir (NODE_COMPILE_CACHE won't auto-create it)
RUN mkdir -p /var/tmp/openclaw-compile-cache && chown node:node /var/tmp/openclaw-compile-cache

# Global HTTP proxy for Node.js fetch() — loaded via NODE_OPTIONS
COPY proxy-bootstrap.js /proxy-bootstrap.js

USER node
