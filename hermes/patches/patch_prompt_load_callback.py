#!/usr/bin/env python3
"""Build-time patcher: injects `pl:` callback handler into TelegramAdapter.

Inserts a handler for the `pl:<skill-name>` inline-keyboard prefix into
``_handle_callback_query`` so that prompt-load menu buttons are translated
into synthetic ``/prompt_load_select <skill>`` message events that flow
through the normal Hermes pipeline.

Designed to be idempotent and to fail loudly if the insertion anchor changes
in a future upstream release.

Usage (inside Dockerfile, as root):
    RUN python3 /opt/hermes/patches/patch_prompt_load_callback.py
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/hermes/gateway/platforms/telegram.py")

# Unique anchor line that marks the insertion point.
# The new block is inserted *immediately before* this line.
ANCHOR = 'if not data.startswith("update_prompt:"):'

# Marker used for idempotency checks.
MARKER = "# --- Prompt-load callbacks (pl:<skill> → synthetic /prompt_load_select) ---"

# The code block to inject.  It will be indented to match the anchor.
PATCH_BLOCK = '''\
# --- Prompt-load callbacks (pl:<skill> → synthetic /prompt_load_select) ---
if data.startswith("pl:"):
    skill_name = data[3:]
    if not skill_name:
        await query.answer(text="Invalid prompt-load selection.")
        return

    chat = query.message.chat if query.message else None
    user = query.from_user

    if not chat:
        await query.answer(text="Cannot resolve chat context.")
        return

    # Determine chat type (mirrors _build_message_event)
    chat_type = "dm"
    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_type = "group"
    elif chat.type == ChatType.CHANNEL:
        chat_type = "channel"

    thread_id = None
    if query.message and query.message.message_thread_id:
        thread_id = str(query.message.message_thread_id)

    source = self.build_source(
        chat_id=str(chat.id),
        chat_name=chat.title or (chat.full_name if hasattr(chat, "full_name") else None),
        chat_type=chat_type,
        user_id=str(user.id) if user else None,
        user_name=user.full_name if user else None,
        thread_id=thread_id,
    )

    # --- Resolve session context ---
    session_context = ""
    try:
        from gateway.session import build_session_key
        session_key = build_session_key(
            source,
            group_sessions_per_user=self.config.extra.get("group_sessions_per_user", True),
            thread_sessions_per_user=self.config.extra.get("thread_sessions_per_user", False),
        )
        store = getattr(self, "_session_store", None)
        if store:
            store._ensure_loaded()
            entry = store._entries.get(session_key)
            if entry:
                transcript = store.load_transcript(entry.session_id)
                # Extract last user/assistant text turns, skip tool/system noise
                recent = []
                for msg in reversed(transcript):
                    role = msg.get("role", "")
                    if role not in ("user", "assistant"):
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            p.get("text", "") for p in content
                            if isinstance(p, dict) and p.get("type") == "text"
                        ).strip()
                    if not content:
                        continue
                    # Cap each turn to avoid bloat
                    if len(content) > 400:
                        content = content[:400] + "…"
                    recent.append(f"{role}: {content}")
                    if len(recent) >= 10:
                        break
                if recent:
                    recent.reverse()
                    session_context = "\\n\\n[session_context]\\n" + "\\n".join(recent)
            else:
                logger.debug("pl: callback — no session entry for key %s", session_key)
        else:
            logger.debug("pl: callback — session store not available on adapter")
    except Exception as exc:
        logger.warning("pl: callback — could not read session context: %s", exc)

    synth_text = f"/prompt_load_select {skill_name}{session_context}"

    event = MessageEvent(
        text=synth_text,
        message_type=MessageType.COMMAND,
        source=source,
        internal=False,
    )

    await query.answer(text=f"Loading: {skill_name}")
    await self.handle_message(event)
    return

'''


def patch() -> None:
    if not TARGET.exists():
        print(f"FATAL: {TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = TARGET.read_text(encoding="utf-8")

    # Idempotency: skip if already patched.
    if MARKER in source:
        print(f"SKIP: {TARGET.name} already contains prompt-load patch")
        return

    # Locate the anchor line.
    anchor_idx = source.find(ANCHOR)
    if anchor_idx == -1:
        print(
            f"FATAL: anchor line not found in {TARGET}:\n  {ANCHOR!r}\n"
            "The upstream file likely changed. Update the patcher.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Detect indentation of the anchor line.
    line_start = source.rfind("\n", 0, anchor_idx) + 1
    indent = ""
    for ch in source[line_start:anchor_idx]:
        if ch in (" ", "\t"):
            indent += ch
        else:
            break

    # Indent the patch block to match.
    indented_block = "".join(
        (indent + line + "\n") if line.strip() else "\n"
        for line in PATCH_BLOCK.splitlines()
    )

    # Insert the block right before the anchor.
    patched = source[:line_start] + indented_block + source[line_start:]

    TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: prompt-load callback patch applied to {TARGET}")


if __name__ == "__main__":
    patch()
