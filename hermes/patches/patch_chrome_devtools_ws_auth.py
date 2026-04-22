#!/usr/bin/env python3
"""Runtime migrator: stop chrome_devtools from relying on query auth discovery."""

from __future__ import annotations

import os
from pathlib import Path

WS_ENDPOINT_ARG = (
    "- --wsEndpoint=ws://browserless:3000/chromium?"
    "stealth=true&launch=%7B%22headless%22%3Afalse%7D"
)
WS_HEADERS_ARG = '- \'--wsHeaders={"Authorization":"Bearer ${BROWSERLESS_TOKEN}"}\''
WS_HEADERS_MARKER = '--wsHeaders={"Authorization":"Bearer ${BROWSERLESS_TOKEN}"}'
LEGACY_BROWSER_URL_ARGS = {
    "- --browserUrl=http://browserless:3000",
    "- --browserUrl=http://browserless:3000?token=${BROWSERLESS_TOKEN}",
}


def get_targets() -> list[Path]:
    home = Path(os.environ.get("HERMES_HOME", "/opt/data"))
    targets = [home / "config.yaml"]
    profiles_dir = home / "profiles"
    if profiles_dir.exists():
        targets.extend(sorted(profiles_dir.glob("*/config.yaml")))
    return targets


def patch_lines(lines: list[str]) -> tuple[list[str], bool]:
    patched: list[str] = []
    changed = False
    for line in lines:
        stripped = line.strip()
        if stripped not in LEGACY_BROWSER_URL_ARGS:
            patched.append(line)
            continue

        indent = line[: len(line) - len(line.lstrip())]
        patched.append(f"{indent}{WS_ENDPOINT_ARG}")
        patched.append(f"{indent}{WS_HEADERS_ARG}")
        changed = True
    return patched, changed


def patch_file(path: Path) -> str:
    if not path.exists():
        return f"Skip: {path} missing"

    source = path.read_text(encoding="utf-8")
    if "chrome_devtools:" not in source:
        return f"Skip: {path} has no chrome_devtools config"
    if WS_HEADERS_MARKER in source:
        return f"Already patched: {path}"

    trailing_newline = source.endswith("\n")
    patched_lines, changed = patch_lines(source.splitlines())
    if not changed:
        return f"Skip: {path} has no legacy browserUrl arg"

    updated = "\n".join(patched_lines)
    if trailing_newline:
        updated += "\n"
    path.write_text(updated, encoding="utf-8")
    return f"Patched: {path} — chrome_devtools now uses wsEndpoint + wsHeaders"


def main() -> None:
    for target in get_targets():
        print(patch_file(target))


if __name__ == "__main__":
    main()