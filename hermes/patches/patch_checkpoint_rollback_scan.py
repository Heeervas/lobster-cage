#!/usr/bin/env python3
"""Build-time patcher: fix /rollback to scan all checkpoint repos.

The /rollback command resolves the working directory via
``os.getenv("MESSAGING_CWD", str(Path.home()))`` which in Docker evaluates
to /opt/data (HERMES_HOME).  However, the checkpoint manager creates shadow
repos keyed by the *project root* (found by walking up from the file being
modified), e.g. /opt/data/workspace/brain/obsidian-openclaw.

This mismatch means /rollback always reports "No checkpoints found" because
no checkpoints were ever created for /opt/data itself.

Fix: when ``list_checkpoints(cwd)`` returns empty, scan all shadow repos
in CHECKPOINT_BASE, read their HERMES_WORKDIR, and aggregate results from
repos that have actual commits.  The /rollback command then shows checkpoints
grouped by working directory and allows restore by global index.

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
CM_MARKER = "# --- Checkpoint scan: list_all_checkpoints (lobster-cage patch) ---"

CM_PATCH = '''

# --- Checkpoint scan: list_all_checkpoints (lobster-cage patch) ---
def list_all_checkpoint_dirs() -> list:
    """Scan all shadow repos and return [(workdir, checkpoints_list), ...].

    Only returns directories whose shadow repo has at least one commit.
    Most recent checkpoints first within each directory.
    """
    results = []
    if not CHECKPOINT_BASE.exists():
        return results
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
        # Check if the repo has any commits
        mgr = CheckpointManager(enabled=True)
        cps = mgr.list_checkpoints(workdir)
        if cps:
            results.append((workdir, cps))
    return results


def format_all_checkpoints_list(all_dirs: list) -> str:
    """Format checkpoint list from multiple directories."""
    if not all_dirs:
        return "No checkpoints found in any directory."

    lines = []
    global_idx = 0
    for workdir, cps in all_dirs:
        lines.append(f"\\n📸 Checkpoints for {workdir}:")
        for cp in cps:
            global_idx += 1
            ts = cp["timestamp"]
            if "T" in ts:
                ts_time = ts.split("T")[1].split("+")[0].split("-")[0][:5]
                date = ts.split("T")[0]
                ts = f"{date} {ts_time}"
            files = cp.get("files_changed", 0)
            ins = cp.get("insertions", 0)
            dele = cp.get("deletions", 0)
            stat = f"  ({files} file{'s' if files != 1 else ''}, +{ins}/-{dele})" if files else ""
            lines.append(f"  {global_idx}. {cp['short_hash']}  {ts}  {cp['reason']}{stat}")

    lines.append("\\n  /rollback <N>             restore to checkpoint N")
    lines.append("  /rollback diff <N>        preview changes since checkpoint N")
    lines.append("  /rollback <N> <file>      restore a single file from checkpoint N")
    return "\\n".join(lines)
'''

# ---------------------------------------------------------------------------
# Patch 2: Modify gateway _handle_rollback_command to use scan fallback
# ---------------------------------------------------------------------------

GW_TARGET = Path("/opt/hermes/gateway/run.py")

# The anchor: the original line that resolves cwd and lists checkpoints.
# We replace the entire _handle_rollback_command method body after the
# CheckpointManager instantiation.

GW_MARKER = "# --- Checkpoint rollback scan fallback (lobster-cage patch) ---"

# We find the original block and replace it with a version that falls back
# to scanning all repos.
GW_OLD = '''        cwd = os.getenv("MESSAGING_CWD", str(Path.home()))
        arg = event.get_command_args().strip()

        if not arg:
            checkpoints = mgr.list_checkpoints(cwd)
            return format_checkpoint_list(checkpoints, cwd)

        # Restore by number or hash
        checkpoints = mgr.list_checkpoints(cwd)
        if not checkpoints:
            return f"No checkpoints found for {cwd}"

        target_hash = None
        try:
            idx = int(arg) - 1
            if 0 <= idx < len(checkpoints):
                target_hash = checkpoints[idx]["hash"]
            else:
                return f"Invalid checkpoint number. Use 1-{len(checkpoints)}."
        except ValueError:
            target_hash = arg

        result = mgr.restore(cwd, target_hash)
        if result["success"]:
            return (
                f"✅ Restored to checkpoint {result['restored_to']}: {result['reason']}\\n"
                f"A pre-rollback snapshot was saved automatically."
            )
        return f"❌ {result['error']}"'''

GW_NEW = '''        # --- Checkpoint rollback scan fallback (lobster-cage patch) ---
        from tools.checkpoint_manager import list_all_checkpoint_dirs, format_all_checkpoints_list

        cwd = os.getenv("MESSAGING_CWD", str(Path.home()))
        arg = event.get_command_args().strip()

        # Try primary CWD first; if empty, scan all checkpoint repos
        checkpoints = mgr.list_checkpoints(cwd)
        active_cwd = cwd
        all_dirs = None
        if not checkpoints:
            all_dirs = list_all_checkpoint_dirs()
            if all_dirs and len(all_dirs) == 1:
                # Single project — use it directly
                active_cwd, checkpoints = all_dirs[0]
                all_dirs = None
            elif all_dirs and len(all_dirs) > 1:
                # Multiple projects — flatten for index-based access
                checkpoints = []
                for wd, cps in all_dirs:
                    for cp in cps:
                        cp["_workdir"] = wd
                        checkpoints.append(cp)

        if not arg:
            if all_dirs and len(all_dirs) > 1:
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
            if not checkpoints:
                return f"No checkpoints found"
            target_hash = None
            diff_cwd = active_cwd
            try:
                idx = int(diff_arg) - 1
                if 0 <= idx < len(checkpoints):
                    target_hash = checkpoints[idx]["hash"]
                    diff_cwd = checkpoints[idx].get("_workdir", active_cwd)
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
                restore_cwd = checkpoints[idx].get("_workdir", active_cwd)
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

CLI_MARKER = "# --- Checkpoint CLI standalone manager (lobster-cage patch) ---"

# The old block that requires self.agent for the checkpoint manager
CLI_OLD = '''        from tools.checkpoint_manager import format_checkpoint_list

        if not hasattr(self, 'agent') or not self.agent:
            print("  No active agent session.")
            return

        mgr = self.agent._checkpoint_mgr
        if not mgr.enabled:
            print("  Checkpoints are not enabled.")
            print("  Enable with: hermes --checkpoints")
            print("  Or in config.yaml: checkpoints: { enabled: true }")
            return

        cwd = os.getenv("TERMINAL_CWD", os.getcwd())
        parts = command.split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            # List checkpoints
            checkpoints = mgr.list_checkpoints(cwd)
            print(format_checkpoint_list(checkpoints, cwd))
            return

        # Handle /rollback diff <N>
        if args[0].lower() == "diff":
            if len(args) < 2:
                print("  Usage: /rollback diff <N>")
                return
            checkpoints = mgr.list_checkpoints(cwd)
            if not checkpoints:
                print(f"  No checkpoints found for {cwd}")
                return
            target_hash = self._resolve_checkpoint_ref(args[1], checkpoints)
            if not target_hash:
                return
            result = mgr.diff(cwd, target_hash)
            if result["success"]:
                stat = result.get("stat", "")
                diff = result.get("diff", "")
                if not stat and not diff:
                    print("  No changes since this checkpoint.")
                else:
                    if stat:
                        print(f"\\n{stat}")
                    if diff:
                        # Limit diff output to avoid terminal flood
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
        checkpoints = mgr.list_checkpoints(cwd)
        if not checkpoints:
            print(f"  No checkpoints found for {cwd}")
            return

        target_hash = self._resolve_checkpoint_ref(args[0], checkpoints)
        if not target_hash:
            return

        # Check for file-level restore: /rollback <N> <file>
        file_path = args[1] if len(args) > 1 else None

        result = mgr.restore(cwd, target_hash, file_path=file_path)
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

CLI_NEW = '''        # --- Checkpoint CLI standalone manager (lobster-cage patch) ---
        from tools.checkpoint_manager import CheckpointManager, format_checkpoint_list
        from tools.checkpoint_manager import list_all_checkpoint_dirs, format_all_checkpoints_list

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

        cwd = os.getenv("TERMINAL_CWD", os.getcwd())
        parts = command.split()
        args = parts[1:] if len(parts) > 1 else []

        # Try primary CWD first; if empty, scan all checkpoint repos
        checkpoints = mgr.list_checkpoints(cwd)
        active_cwd = cwd
        all_dirs = None
        if not checkpoints:
            all_dirs = list_all_checkpoint_dirs()
            if all_dirs and len(all_dirs) == 1:
                active_cwd, checkpoints = all_dirs[0]
                all_dirs = None
            elif all_dirs and len(all_dirs) > 1:
                checkpoints = []
                for wd, cps in all_dirs:
                    for cp in cps:
                        cp["_workdir"] = wd
                        checkpoints.append(cp)

        if not args:
            if all_dirs and len(all_dirs) > 1:
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
            if not checkpoints:
                print(f"  No checkpoints found")
                return
            diff_cwd = active_cwd
            target_hash = self._resolve_checkpoint_ref(args[1], checkpoints)
            if not target_hash:
                return
            # Find the working dir for this checkpoint (multi-project support)
            try:
                idx = int(args[1]) - 1
                if 0 <= idx < len(checkpoints):
                    diff_cwd = checkpoints[idx].get("_workdir", active_cwd)
            except ValueError:
                pass
            result = mgr.diff(diff_cwd, target_hash)
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
        if not checkpoints:
            print(f"  No checkpoints found")
            return

        target_hash = self._resolve_checkpoint_ref(args[0], checkpoints)
        if not target_hash:
            return

        # Find the working dir for this checkpoint (multi-project support)
        restore_cwd = active_cwd
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(checkpoints):
                restore_cwd = checkpoints[idx].get("_workdir", active_cwd)
        except ValueError:
            pass

        # Check for file-level restore: /rollback <N> <file>
        file_path = args[1] if len(args) > 1 else None

        result = mgr.restore(restore_cwd, target_hash, file_path=file_path)
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

    if GW_OLD not in source:
        print(
            f"FATAL: anchor block not found in {GW_TARGET}:\n"
            "The upstream _handle_rollback_command likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    patched = source.replace(GW_OLD, GW_NEW, 1)
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

    if CLI_OLD not in source:
        print(
            f"FATAL: anchor block not found in {CLI_TARGET}:\n"
            "The upstream _handle_rollback_command in cli.py likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    patched = source.replace(CLI_OLD, CLI_NEW, 1)
    CLI_TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: CLI rollback standalone + scan fallback applied to {CLI_TARGET}")


def main() -> None:
    patch_checkpoint_manager()
    patch_gateway()
    patch_cli()


if __name__ == "__main__":
    main()
