FROM ghcr.io/openclaw/openclaw:latest

USER root

# Passwordless sudo for the node user (agent can install packages at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends sudo \
    && echo 'node ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/node \
    && chmod 0440 /etc/sudoers.d/node

# CLI-Toolbox: Network, System, Dev, Data Processing
RUN apt-get install -y --no-install-recommends \
    # --- Network ---
    curl \
    wget \
    iputils-ping \
    dnsutils \
    netcat-openbsd \
    traceroute \
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
    make \
    python3 \
    python3-pip \
    python3-venv \
    # --- Data Processing ---
    jq \
    bc \
    # --- PDF ---
    poppler-utils \
    # --- TLS / Certs ---
    ca-certificates \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Persist APT proxy so that sudo apt-get inside the agent uses the outbound proxy
RUN echo 'Acquire::http::Proxy "http://proxy:8888";' > /etc/apt/apt.conf.d/99proxy \
    && echo 'Acquire::https::Proxy "http://proxy:8888";' >> /etc/apt/apt.conf.d/99proxy

# Persist pip proxy
RUN mkdir -p /home/node/.config/pip \
    && printf '[global]\nproxy = http://proxy:8888\n' > /home/node/.config/pip/pip.conf \
    && chown -R node:node /home/node/.config

# Pre-installed Python packages (document manipulation + PDF parsing)
RUN pip3 install --break-system-packages python-docx pymupdf

# Make the 'openclaw' CLI command available system-wide
# (the npm package declares bin: { openclaw: openclaw.mjs } but isn't globally linked)
RUN ln -sf /app/openclaw.mjs /usr/local/bin/openclaw

# Global HTTP proxy for Node.js fetch() — loaded via NODE_OPTIONS
COPY proxy-bootstrap.js /proxy-bootstrap.js

USER node
