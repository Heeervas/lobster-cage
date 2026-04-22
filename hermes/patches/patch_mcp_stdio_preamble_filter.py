#!/usr/bin/env python3
"""Build-time patcher: ignore known stdio startup preambles before JSON-RPC.

Some stdio MCP servers emit human-readable startup lines before the first
JSON-RPC frame. Hermes' vendored MCP SDK currently treats every such line as a
parse failure. This patch keeps the behavior strict while allowing blank lines
and a small allowlist of known startup prefixes until the first valid JSON-RPC
message is seen.

Designed to be idempotent and to fail loudly if the anchor changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/hermes/.venv/lib/python3.13/site-packages/mcp/client/stdio/__init__.py")

MARKER = "# Lobster Cage patch: ignore known stdio startup preambles before the first JSON-RPC frame"

INSERT_ANCHOR = '''# Timeout for process termination before falling back to force kill
PROCESS_TERMINATION_TIMEOUT = 2.0


def get_default_environment() -> dict[str, str]:'''

INSERT_BLOCK = '''# Timeout for process termination before falling back to force kill
PROCESS_TERMINATION_TIMEOUT = 2.0

# Lobster Cage patch: ignore known stdio startup preambles before the first JSON-RPC frame
_DEFAULT_STARTUP_PREAMBLE_PREFIXES = (
    "chrome-devtools-mcp exposes content of the browser instance",
    "Avoid sharing sensitive or personal information",
    "Performance tools may send trace URLs",
    "debug, and modify any data in the browser or DevTools.",
)
_STARTUP_PREAMBLE_PREFIXES_ENV = "HERMES_MCP_STDIO_PREAMBLE_PREFIXES"


def _get_startup_preamble_prefixes() -> tuple[str, ...]:
    raw = os.environ.get(_STARTUP_PREAMBLE_PREFIXES_ENV, "")
    if not raw:
        return _DEFAULT_STARTUP_PREAMBLE_PREFIXES

    extra = tuple(prefix.strip() for prefix in raw.split(",") if prefix.strip())
    if not extra:
        return _DEFAULT_STARTUP_PREAMBLE_PREFIXES

    return _DEFAULT_STARTUP_PREAMBLE_PREFIXES + extra


def get_default_environment() -> dict[str, str]:'''

BUFFER_ANCHOR = '''                buffer = ""
                async for chunk in TextReceiveStream('''

BUFFER_REPLACEMENT = '''                buffer = ""
                preamble_prefixes = _get_startup_preamble_prefixes()
                startup_complete = False
                async for chunk in TextReceiveStream('''

LINE_LOOP_ANCHOR = '''                    for line in lines:
                        try:
                            message = types.JSONRPCMessage.model_validate_json(line)'''

LINE_LOOP_REPLACEMENT = '''                    for line in lines:
                        if not startup_complete:
                            stripped_line = line.strip()
                            if not stripped_line:
                                continue
                            if any(
                                stripped_line.startswith(prefix)
                                for prefix in preamble_prefixes
                            ):
                                logger.debug(
                                    "Ignoring stdio MCP startup preamble line: %s",
                                    stripped_line,
                                )
                                continue
                        try:
                            message = types.JSONRPCMessage.model_validate_json(line)
                            startup_complete = True'''

NEW_LOOP = '''                buffer = ""
                preamble_prefixes = _get_startup_preamble_prefixes()
                startup_complete = False
                async for chunk in TextReceiveStream(
                    process.stdout,
                    encoding=server.encoding,
                    errors=server.encoding_error_handler,
                ):
                    lines = (buffer + chunk).split("\n")
                    buffer = lines.pop()

                    for line in lines:
                        if not startup_complete:
                            stripped_line = line.strip()
                            if not stripped_line:
                                continue
                            if any(
                                stripped_line.startswith(prefix)
                                for prefix in preamble_prefixes
                            ):
                                logger.debug(
                                    "Ignoring stdio MCP startup preamble line: %s",
                                    stripped_line,
                                )
                                continue
                        try:
                            message = types.JSONRPCMessage.model_validate_json(line)
                            startup_complete = True
                        except Exception as exc:  # pragma: no cover
                            logger.exception("Failed to parse JSONRPC message from server")
                            await read_stream_writer.send(exc)
                            continue

                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)'''


def main() -> None:
    if not TARGET.exists():
        print(f"FATAL: {TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = TARGET.read_text(encoding="utf-8")

    if MARKER in source or "HERMES_MCP_STDIO_PREAMBLE_PREFIXES" in source:
        print(f"Already patched: {TARGET}")
        return

    if INSERT_ANCHOR not in source:
        print(f"FATAL: helper anchor not found in {TARGET}", file=sys.stderr)
        sys.exit(1)
    if BUFFER_ANCHOR not in source:
        print(f"FATAL: stdout reader buffer anchor not found in {TARGET}", file=sys.stderr)
        sys.exit(1)
    if LINE_LOOP_ANCHOR not in source:
        print(f"FATAL: stdout reader line-loop anchor not found in {TARGET}", file=sys.stderr)
        sys.exit(1)

    patched = source.replace(INSERT_ANCHOR, INSERT_BLOCK, 1)
    patched = patched.replace(BUFFER_ANCHOR, BUFFER_REPLACEMENT, 1)
    patched = patched.replace(LINE_LOOP_ANCHOR, LINE_LOOP_REPLACEMENT, 1)
    TARGET.write_text(patched, encoding="utf-8")
    print(f"Patched: {TARGET} — startup preamble filter enabled for stdio MCP")


if __name__ == "__main__":
    main()