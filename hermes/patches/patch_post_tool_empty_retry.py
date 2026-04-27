#!/usr/bin/env python3
"""Runtime patcher: avoid blind identical retries after post-tool empty nudges.

Hermes currently handles an empty response after tool execution by appending a
single user nudge. If the model returns empty again, the generic empty-response
retry loop resubmits that exact same post-tool prompt three more times.

In the live Codex incidents this produced byte-identical request payloads with
no new model state, burning time and tokens without improving recovery.

This patch adds one stronger post-tool continuation prompt and skips the blind
generic retry loop for those post-tool nudge prompts. After the stronger nudge,
Hermes falls through to its existing fallback-or-empty handling instead of
replaying the same payload again.

Designed to be idempotent and to fail loudly if the upstream anchor changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/hermes/run_agent.py")

MARKER = "_post_tool_escalation_prompt = ("

OLD_BLOCK = '''                        _truly_empty = not self._strip_think_blocks(
                            final_response
                        ).strip()
                        _prefill_exhausted = (
                            _has_structured
                            and self._thinking_prefill_retries >= 2
                        )
                        if _truly_empty and (not _has_structured or _prefill_exhausted) and self._empty_content_retries < 3:
                            self._empty_content_retries += 1
                            logger.warning(
                                "Empty response (no content or reasoning) — "
                                "retry %d/3 (model=%s)",
                                self._empty_content_retries, self.model,
                            )
                            self._emit_status(
                                f"⚠️ Empty response from model — retrying "
                                f"({self._empty_content_retries}/3)"
                            )
                            continue
'''

NEW_BLOCK = '''                        _truly_empty = not self._strip_think_blocks(
                            final_response
                        ).strip()
                        _prefill_exhausted = (
                            _has_structured
                            and self._thinking_prefill_retries >= 2
                        )
                        _post_tool_continue_prompt = (
                            "You just executed tool calls but returned an "
                            "empty response. Please process the tool "
                            "results above and continue with the task."
                        )
                        _post_tool_escalation_prompt = (
                            "Your previous continuation after tool results "
                            "was still empty. Using the tool results already "
                            "above, do one of these now: (1) call the next "
                            "tool you need, or (2) return the final answer. "
                            "Do not return an empty response."
                        )
                        _last_user_content = ""
                        for _msg in reversed(messages[-4:]):
                            if not isinstance(_msg, dict):
                                continue
                            if _msg.get("role") != "user":
                                continue
                            _msg_content = _msg.get("content")
                            if isinstance(_msg_content, str):
                                _last_user_content = _msg_content.strip()
                                break

                        if (
                            _truly_empty
                            and _prior_was_tool
                            and _last_user_content == _post_tool_continue_prompt
                        ):
                            logger.warning(
                                "Empty response after post-tool nudge — "
                                "escalating continuation prompt (model=%s)",
                                self.model,
                            )
                            self._emit_status(
                                "⚠️ Still empty after tool-call nudge — "
                                "escalating continuation prompt"
                            )
                            _retry_msg = self._build_assistant_message(
                                assistant_message, finish_reason
                            )
                            _retry_msg["content"] = "(empty)"
                            messages.append(_retry_msg)
                            messages.append({
                                "role": "user",
                                "content": _post_tool_escalation_prompt,
                            })
                            self._session_messages = messages
                            self._save_session_log(messages)
                            continue

                        _skip_generic_empty_retry = (
                            _prior_was_tool
                            and _last_user_content in (
                                _post_tool_continue_prompt,
                                _post_tool_escalation_prompt,
                            )
                        )
                        if (
                            _truly_empty
                            and (not _has_structured or _prefill_exhausted)
                            and self._empty_content_retries < 3
                            and not _skip_generic_empty_retry
                        ):
                            self._empty_content_retries += 1
                            logger.warning(
                                "Empty response (no content or reasoning) — "
                                "retry %d/3 (model=%s)",
                                self._empty_content_retries, self.model,
                            )
                            self._emit_status(
                                f"⚠️ Empty response from model — retrying "
                                f"({self._empty_content_retries}/3)"
                            )
                            continue
'''


def main() -> None:
    if not TARGET.exists():
        print(f"FATAL: {TARGET} not found", file=sys.stderr)
        sys.exit(1)

    source = TARGET.read_text(encoding="utf-8")

    if MARKER in source:
        print(f"Already patched: {TARGET}")
        return

    if OLD_BLOCK not in source:
        print(f"FATAL: anchor block not found in {TARGET}", file=sys.stderr)
        sys.exit(1)

    TARGET.write_text(source.replace(OLD_BLOCK, NEW_BLOCK, 1), encoding="utf-8")
    print(f"Patched: {TARGET} — post-tool empty retries now escalate once before fallback")


if __name__ == "__main__":
    main()