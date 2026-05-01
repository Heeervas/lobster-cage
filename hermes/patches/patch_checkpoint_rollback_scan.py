#!/usr/bin/env python3
"""Build-time patcher: fix /rollback cwd resolution and fallback scope.

The /rollback command resolves a single working directory from the gateway
environment, which in Docker often falls back to /opt/data (HERMES_HOME).
However, the checkpoint manager creates shadow repos keyed by the *project
root* (found by walking up from the file being modified), e.g.
/opt/data/workspace/brain/obsidian-openclaw.

This mismatch means /rollback always reports "No checkpoints found" because
no checkpoints were ever created for /opt/data itself.

Fix: resolve the canonical working directory from config.yaml when the
gateway/CLI env is unset or still points at a generic container cwd. When
``list_checkpoints(cwd)`` still returns empty, scan all shadow repos in
CHECKPOINT_BASE, but only auto-select a fallback when there is exactly one
unambiguous candidate. If multiple workdirs have checkpoints, show a grouped
listing and refuse cross-workdir numeric restore/diff selection.

Designed to be idempotent and to fail loudly if the insertion anchor changes
in a future upstream release.

Usage (inside Dockerfile, as root):
    RUN python3 /opt/hermes/patches/patch_checkpoint_rollback_scan.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patch 1: Add list_all_checkpoints() to CheckpointManager
# ---------------------------------------------------------------------------

CM_TARGET = Path("/opt/hermes/tools/checkpoint_manager.py")

# Insert after the format_checkpoint_list function (end of file or before
# a known anchor).  We append to the end of the file.
CM_MARKER = "# --- Checkpoint scan helpers (lobster-cage patch) ---"
CM_OLD_MARKER = "# --- Checkpoint scan: list_all_checkpoints (lobster-cage patch) ---"

CM_PATCH = '''

# --- Checkpoint scan helpers (lobster-cage patch) ---
from pathlib import Path


_CHECKPOINT_SYSTEM_DIRS = {
    "/",
    "/opt",
    "/opt/hermes",
    "/tmp",
}


def _resolve_configured_terminal_cwd() -> str | None:
    """Read terminal.cwd from HERMES_HOME/config.yaml when available."""
    import os

    try:
        import yaml
    except Exception:
        return None

    config_path = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))) / "config.yaml"
    if not config_path.exists():
        return None

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None

    terminal = config.get("terminal") if isinstance(config, dict) else None
    if not isinstance(terminal, dict):
        return None

    cwd = terminal.get("cwd")
    if not isinstance(cwd, str):
        return None

    cwd = cwd.strip()
    if cwd in ("", ".", "auto", "cwd"):
        return None

    return str(Path(cwd).expanduser())


def resolve_checkpoint_cwd(default_cwd: str) -> str:
    """Resolve the best cwd for checkpoint lookups."""
    import os

    for candidate in (
        os.getenv("TERMINAL_CWD"),
        os.getenv("MESSAGING_CWD"),
        _resolve_configured_terminal_cwd(),
        default_cwd,
    ):
        if not candidate:
            continue
        candidate = str(Path(candidate).expanduser())
        if candidate not in _CHECKPOINT_SYSTEM_DIRS:
            return candidate
    return default_cwd


def _is_broad_checkpoint_dir(workdir: str) -> bool:
    workdir = str(Path(workdir).expanduser())
    if workdir in _CHECKPOINT_SYSTEM_DIRS:
        return True
    if workdir.startswith("/opt/data"):
        suffix = workdir[len("/opt/data"):].strip("/")
        if suffix in ("", "workspace", "brain", "workspace/projects"):
            return True
    return False


def list_all_checkpoint_dirs() -> list:
    """Scan all shadow repos and return [(workdir, checkpoints_list), ...].

    Only returns directories whose shadow repo has at least one commit.
    Most recent checkpoints first within each directory.
    """
    results = {}
    if not CHECKPOINT_BASE.exists():
        return []
    for shadow in sorted(CHECKPOINT_BASE.iterdir()):
        if not shadow.is_dir():
            continue
        workdir_file = shadow / "HERMES_WORKDIR"
        head_file = shadow / "HEAD"
        if not workdir_file.exists() or not head_file.exists():
            continue
        workdir = workdir_file.read_text(encoding="utf-8").strip()
        if not workdir:
            continue
        if _is_broad_checkpoint_dir(workdir):
            continue
        # Check if the repo has any commits
        mgr = CheckpointManager(enabled=True)
        cps = mgr.list_checkpoints(workdir)
        if cps:
            existing = results.get(workdir)
            if existing is None or len(cps) > len(existing):
                results[workdir] = cps
    return [(workdir, cps) for workdir, cps in results.items()]


def match_checkpoint_dirs(active_cwd: str, all_dirs: list) -> list:
    """Return fallback dirs ordered by closeness to the active cwd."""
    if len(all_dirs) == 1:
        return all_dirs

    active = str(Path(active_cwd).expanduser())
    exact = []
    nested = []
    parents = []
    unrelated = []
    for workdir, cps in all_dirs:
        workdir = str(Path(workdir).expanduser())
        if workdir == active:
            exact.append((workdir, cps))
        elif workdir.startswith(active.rstrip("/") + "/"):
            nested.append((workdir, cps))
        elif active.startswith(workdir.rstrip("/") + "/"):
            parents.append((workdir, cps))
        else:
            unrelated.append((workdir, cps))

    if exact:
        return exact
    if len(nested) == 1:
        return nested
    if len(parents) == 1:
        return parents
    if not active or active in _CHECKPOINT_SYSTEM_DIRS:
        return []
    return []


def format_all_checkpoints_list(all_dirs: list) -> str:
    """Format checkpoint list from multiple directories without global indices."""
    if not all_dirs:
        return "No checkpoints found in any directory."

    lines = []
    for workdir, cps in all_dirs:
        lines.append(f"\\n📸 Checkpoints for {workdir}:")
        for idx, cp in enumerate(cps, start=1):
            ts = cp["timestamp"]
            if "T" in ts:
                ts_time = ts.split("T")[1].split("+")[0].split("-")[0][:5]
                date = ts.split("T")[0]
                ts = f"{date} {ts_time}"
            files = cp.get("files_changed", 0)
            ins = cp.get("insertions", 0)
            dele = cp.get("deletions", 0)
            stat = f"  ({files} file{'s' if files != 1 else ''}, +{ins}/-{dele})" if files else ""
            lines.append(f"  {idx}. {cp['short_hash']}  {ts}  {cp['reason']}{stat}")

    lines.append("\\nAmbiguous rollback scope: multiple workdirs have checkpoints.")
    lines.append("Set terminal.cwd in config.yaml or open the intended project before using /rollback.")
    lines.append("Grouped restore/diff stays disabled until the active cwd is narrowed to one project.")
    return "\\n".join(lines)
'''

# ---------------------------------------------------------------------------
# Patch 2: Modify gateway _handle_rollback_command to use scan fallback
# ---------------------------------------------------------------------------

GW_TARGET = Path("/opt/hermes/gateway/run.py")

# The anchor: the original line that resolves cwd and lists checkpoints.
# We replace the entire _handle_rollback_command method body after the
# CheckpointManager instantiation.

GW_MARKER = "# --- Checkpoint rollback scoped fallback (lobster-cage patch) ---"
GW_OLD_MARKER = "        # --- Checkpoint rollback scan fallback (lobster-cage patch) ---"
GW_START_CANDIDATES = (
    GW_OLD_MARKER,
    '        cwd = os.getenv("TERMINAL_CWD") or os.getenv("MESSAGING_CWD", str(Path.home()))',
    '        cwd = os.getenv("TERMINAL_CWD", str(Path.home()))',
    '        cwd = os.getenv("MESSAGING_CWD", str(Path.home()))',
)
GW_END = '        return f"❌ {result[\'error\']}"'

GW_NEW = '''        # --- Checkpoint rollback scoped fallback (lobster-cage patch) ---
        from tools.checkpoint_manager import (
            format_all_checkpoints_list,
            list_all_checkpoint_dirs,
            match_checkpoint_dirs,
            resolve_checkpoint_cwd,
        )

        cwd = resolve_checkpoint_cwd(str(Path.home()))
        arg = event.get_command_args().strip()

        checkpoints = mgr.list_checkpoints(cwd)
        active_cwd = cwd
        all_dirs = None
        if not checkpoints:
            all_dirs = list_all_checkpoint_dirs()
            matched_dirs = match_checkpoint_dirs(active_cwd, all_dirs)
            if len(matched_dirs) == 1:
                active_cwd, checkpoints = matched_dirs[0]
                all_dirs = None
            elif matched_dirs:
                all_dirs = matched_dirs

        if not arg:
            if all_dirs:
                return format_all_checkpoints_list(all_dirs)
            if not checkpoints:
                return f"No checkpoints found for {active_cwd}"
            return format_checkpoint_list(checkpoints, active_cwd)

        # Handle /rollback diff <N>
        if arg.lower().startswith("diff"):
            diff_parts = arg.split(None, 1)
            if len(diff_parts) < 2:
                return "Usage: /rollback diff <N>"
            diff_arg = diff_parts[1]
            if all_dirs:
                return format_all_checkpoints_list(all_dirs)
            if not checkpoints:
                return f"No checkpoints found"
            target_hash = None
            diff_cwd = active_cwd
            try:
                idx = int(diff_arg) - 1
                if 0 <= idx < len(checkpoints):
                    target_hash = checkpoints[idx]["hash"]
                else:
                    return f"Invalid checkpoint number. Use 1-{len(checkpoints)}."
            except ValueError:
                target_hash = diff_arg
            result = mgr.diff(diff_cwd, target_hash)
            if result["success"]:
                stat = result.get("stat", "")
                diff = result.get("diff", "")
                if not stat and not diff:
                    return "No changes since this checkpoint."
                parts = []
                if stat:
                    parts.append(stat)
                if diff:
                    diff_lines = diff.splitlines()
                    if len(diff_lines) > 80:
                        parts.append("\\n".join(diff_lines[:80]))
                        parts.append(f"\\n... ({len(diff_lines) - 80} more lines)")
                    else:
                        parts.append(diff)
                return "\\n".join(parts)
            return f"❌ {result['error']}"

        # Restore by number or hash
        if all_dirs:
            return format_all_checkpoints_list(all_dirs)
        if not checkpoints:
            return f"No checkpoints found"

        # Parse file-level restore: /rollback <N> <file>
        restore_parts = arg.split(None, 1)
        restore_arg = restore_parts[0]
        file_path = restore_parts[1] if len(restore_parts) > 1 else None

        target_hash = None
        restore_cwd = active_cwd
        try:
            idx = int(restore_arg) - 1
            if 0 <= idx < len(checkpoints):
                target_hash = checkpoints[idx]["hash"]
            else:
                return f"Invalid checkpoint number. Use 1-{len(checkpoints)}."
        except ValueError:
            target_hash = restore_arg

        result = mgr.restore(restore_cwd, target_hash, file_path=file_path)
        if result["success"]:
            msg = f"✅ Restored to checkpoint {result['restored_to']}: {result['reason']}"
            if file_path:
                msg = f"✅ Restored {file_path} from checkpoint {result['restored_to']}: {result['reason']}"
            return msg + "\\nA pre-rollback snapshot was saved automatically."
        return f"❌ {result['error']}"'''

# ---------------------------------------------------------------------------
# Patch 3: Fix CLI _handle_rollback_command to not require self.agent
# ---------------------------------------------------------------------------

CLI_TARGET = Path("/opt/hermes/cli.py")

CLI_MARKER = "# --- Checkpoint CLI scoped manager (lobster-cage patch) ---"
CLI_OLD_MARKER = "        # --- Checkpoint CLI standalone manager (lobster-cage patch) ---"
CLI_START_CANDIDATES = (
    CLI_OLD_MARKER,
    "        from tools.checkpoint_manager import format_checkpoint_list",
)
CLI_END = '            print(f"  ❌ {result[\'error\']}")'

CLI_NEW = '''        # --- Checkpoint CLI scoped manager (lobster-cage patch) ---
        from tools.checkpoint_manager import CheckpointManager, format_checkpoint_list
        from tools.checkpoint_manager import (
            format_all_checkpoints_list,
            list_all_checkpoint_dirs,
            match_checkpoint_dirs,
            resolve_checkpoint_cwd,
        )

        # Try to get manager from agent; fall back to standalone from config
        mgr = None
        if hasattr(self, 'agent') and self.agent and hasattr(self.agent, '_checkpoint_mgr'):
            mgr = self.agent._checkpoint_mgr
        if mgr is None or not mgr.enabled:
            # Create standalone manager from config
            if hasattr(self, 'checkpoints_enabled') and self.checkpoints_enabled:
                mgr = CheckpointManager(
                    enabled=True,
                    max_snapshots=getattr(self, 'checkpoint_max_snapshots', 50),
                )
            else:
                print("  Checkpoints are not enabled.")
                print("  Enable with: hermes --checkpoints")
                print("  Or in config.yaml: checkpoints: { enabled: true }")
                return

        cwd = resolve_checkpoint_cwd(os.getcwd())
        parts = command.split()
        args = parts[1:] if len(parts) > 1 else []

        checkpoints = mgr.list_checkpoints(cwd)
        active_cwd = cwd
        all_dirs = None
        if not checkpoints:
            all_dirs = list_all_checkpoint_dirs()
            matched_dirs = match_checkpoint_dirs(active_cwd, all_dirs)
            if len(matched_dirs) == 1:
                active_cwd, checkpoints = matched_dirs[0]
                all_dirs = None
            elif matched_dirs:
                all_dirs = matched_dirs

        if not args:
            if all_dirs:
                print(format_all_checkpoints_list(all_dirs))
            elif not checkpoints:
                print(f"  No checkpoints found for {active_cwd}")
            else:
                print(format_checkpoint_list(checkpoints, active_cwd))
            return

        # Handle /rollback diff <N>
        if args[0].lower() == "diff":
            if len(args) < 2:
                print("  Usage: /rollback diff <N>")
                return
            if all_dirs:
                print(format_all_checkpoints_list(all_dirs))
                return
            if not checkpoints:
                print(f"  No checkpoints found")
                return
            target_hash = self._resolve_checkpoint_ref(args[1], checkpoints)
            if not target_hash:
                return
            result = mgr.diff(active_cwd, target_hash)
            if result["success"]:
                stat = result.get("stat", "")
                diff = result.get("diff", "")
                if not stat and not diff:
                    print("  No changes since this checkpoint.")
                else:
                    if stat:
                        print(f"\\n{stat}")
                    if diff:
                        diff_lines = diff.splitlines()
                        if len(diff_lines) > 80:
                            print("\\n".join(diff_lines[:80]))
                            print(f"\\n  ... ({len(diff_lines) - 80} more lines, showing first 80)")
                        else:
                            print(f"\\n{diff}")
            else:
                print(f"  ❌ {result['error']}")
            return

        # Resolve checkpoint reference (number or hash)
        if all_dirs:
            print(format_all_checkpoints_list(all_dirs))
            return
        if not checkpoints:
            print(f"  No checkpoints found")
            return

        target_hash = self._resolve_checkpoint_ref(args[0], checkpoints)
        if not target_hash:
            return

        # Check for file-level restore: /rollback <N> <file>
        file_path = args[1] if len(args) > 1 else None

        result = mgr.restore(active_cwd, target_hash, file_path=file_path)
        if result["success"]:
            if file_path:
                print(f"  ✅ Restored {file_path} from checkpoint {result['restored_to']}: {result['reason']}")
            else:
                print(f"  ✅ Restored to checkpoint {result['restored_to']}: {result['reason']}")
            print("  A pre-rollback snapshot was saved automatically.")

            # Also undo the last conversation turn so the agent's context
            # matches the restored filesystem state
            if self.conversation_history:
                self.undo_last()
                print("  Chat turn undone to match restored file state.")
        else:
            print(f"  ❌ {result['error']}")'''


def patch_checkpoint_manager() -> None:
    """Add list_all_checkpoint_dirs() and format_all_checkpoints_list() to checkpoint_manager.py."""
    if not CM_TARGET.exists():
        print(f"FATAL: {CM_TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = CM_TARGET.read_text(encoding="utf-8")

    if CM_MARKER in source:
        print(f"SKIP: {CM_TARGET.name} already contains checkpoint scan patch")
        return

    old_idx = source.find(CM_OLD_MARKER)
    if old_idx != -1:
        patched = source[:old_idx].rstrip() + "\n" + CM_PATCH
        CM_TARGET.write_text(patched, encoding="utf-8")
        print(f"OK: checkpoint scan helpers upgraded in {CM_TARGET}")
        return

    # Append to end of file
    patched = source.rstrip() + "\n" + CM_PATCH
    CM_TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: checkpoint scan functions added to {CM_TARGET}")


def patch_gateway() -> None:
    """Modify _handle_rollback_command in gateway/run.py to scan all repos."""
    if not GW_TARGET.exists():
        print(f"FATAL: {GW_TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = GW_TARGET.read_text(encoding="utf-8")

    if GW_MARKER in source:
        print(f"SKIP: {GW_TARGET.name} already contains rollback scan patch")
        return

    start_idx = -1
    for candidate in GW_START_CANDIDATES:
        start_idx = source.find(candidate)
        if start_idx != -1:
            break

    if start_idx == -1:
        print(
            f"FATAL: anchor block not found in {GW_TARGET}:\n"
            "The upstream _handle_rollback_command likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    end_idx = source.find(GW_END, start_idx)
    if end_idx == -1:
        print(
            f"FATAL: rollback handler end marker not found in {GW_TARGET}:\n"
            "The upstream _handle_rollback_command likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    patched = source[:start_idx] + GW_NEW + source[end_idx + len(GW_END):]
    GW_TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: rollback scan fallback applied to {GW_TARGET}")


def patch_cli() -> None:
    """Fix CLI _handle_rollback_command to not require self.agent and scan all repos."""
    if not CLI_TARGET.exists():
        print(f"FATAL: {CLI_TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = CLI_TARGET.read_text(encoding="utf-8")

    if CLI_MARKER in source:
        print(f"SKIP: {CLI_TARGET.name} already contains CLI checkpoint patch")
        return

    start_idx = -1
    for candidate in CLI_START_CANDIDATES:
        start_idx = source.find(candidate)
        if start_idx != -1:
            break

    if start_idx == -1:
        print(
            f"FATAL: anchor block not found in {CLI_TARGET}:\n"
            "The upstream _handle_rollback_command in cli.py likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    end_idx = source.find(CLI_END, start_idx)
    if end_idx == -1:
        print(
            f"FATAL: rollback handler end marker not found in {CLI_TARGET}:\n"
            "The upstream _handle_rollback_command in cli.py likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    patched = source[:start_idx] + CLI_NEW + source[end_idx + len(CLI_END):]
    CLI_TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: CLI rollback standalone + scan fallback applied to {CLI_TARGET}")


def main() -> None:
    patch_checkpoint_manager()
    patch_gateway()
    patch_cli()


if __name__ == "__main__":
    main()
