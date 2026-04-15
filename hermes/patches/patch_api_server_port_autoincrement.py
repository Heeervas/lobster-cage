#!/usr/bin/env python3
"""Build-time patcher: auto-find a free port when the default is occupied.

Replaces the hard-fail port conflict detection in ``api_server.py`` with
a loop that increments the port (up to 10 attempts) until a free one is
found.  This avoids the "Port 8642 already in use" error when another
gateway instance is already running.

Designed to be idempotent and to fail loudly if the anchor changes
in a future upstream release.

Usage (inside Dockerfile, as root):
    RUN python3 /opt/hermes/patches/patch_api_server_port_autoincrement.py
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/hermes/gateway/platforms/api_server.py")

# The exact block we want to replace (port conflict detection that fails fast).
OLD_BLOCK = """\
            # Port conflict detection — fail fast if port is already in use
            try:
                with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
                    _s.settimeout(1)
                    _s.connect(('127.0.0.1', self._port))
                logger.error('[%s] Port %d already in use. Set a different port in config.yaml: platforms.api_server.port', self.name, self._port)
                return False
            except (ConnectionRefusedError, OSError):
                pass  # port is free"""

# Replacement: try up to 10 ports starting from the configured one.
NEW_BLOCK = """\
            # Port conflict detection — auto-increment to find a free port
            _original_port = self._port
            for _attempt in range(10):
                try:
                    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
                        _s.settimeout(1)
                        _s.connect(('127.0.0.1', self._port))
                    # Port is in use — try the next one
                    self._port += 1
                except (ConnectionRefusedError, OSError):
                    break  # port is free
            else:
                logger.error('[%s] Ports %d-%d all in use. Set a different port in config.yaml: platforms.api_server.port', self.name, _original_port, self._port)
                return False
            if self._port != _original_port:
                logger.info('[%s] Port %d in use, using %d instead', self.name, _original_port, self._port)"""

MARKER = "# Port conflict detection — auto-increment to find a free port"


def main() -> None:
    if not TARGET.exists():
        print(f"FATAL: {TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = TARGET.read_text()

    # Idempotency: already patched?
    if MARKER in source:
        print(f"Already patched: {TARGET}")
        return

    if OLD_BLOCK not in source:
        print(f"FATAL: anchor block not found in {TARGET} — upstream may have changed", file=sys.stderr)
        sys.exit(1)

    patched = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
    TARGET.write_text(patched)
    print(f"Patched: {TARGET} — port auto-increment enabled")


if __name__ == "__main__":
    main()
