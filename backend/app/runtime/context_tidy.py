"""Turns tool calls of earlier steps into notes before every LLM inference.

A small model that sees an earlier step's tool call in the history tends to call that tool again,
where it no longer exists. Ollama drops calls to unknown tools, so the reply comes back empty and
the caller hears silence. Those calls (and their results) are replaced with a one-line note.

The call that just moved the conversation to this step is kept while nothing has been said since:
the model answers its result on the step's first turn, and a context ending in bare system
messages makes Qwen3 return nothing as well.
"""

import json
from typing import Any

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def _note(calls: list[dict]) -> str:
    parts = []
    for call in calls:
        fn = call.get("function", {})
        args = fn.get("arguments") or ""
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        parts.append(f"{fn.get('name')}" + (f" {args}" if args and args != "{}" else ""))
    return "[Önceki adımda yapıldı: " + "; ".join(parts) + "]"


def _is_turn(message: Any) -> bool:
    """Something said in the conversation, as opposed to tool traffic and instructions."""
    if not isinstance(message, dict):
        return False
    role = message.get("role")
    return role == "user" or (role == "assistant" and bool(message.get("content")) and not message.get("tool_calls"))


def tidy_messages(messages: list[Any], allowed: set[str]) -> list[Any]:
    """Messages with calls to tools outside `allowed` (and their results) turned into notes,
    except calls made after the last spoken turn."""
    last_turn = max((i for i, m in enumerate(messages) if _is_turn(m)), default=-1)
    dropped_ids: set[str] = set()
    tidied: list[Any] = []
    for i, message in enumerate(messages):
        if not isinstance(message, dict):  # LLM-specific messages are left alone
            tidied.append(message)
            continue
        if message.get("role") == "assistant" and message.get("tool_calls") and i < last_turn:
            keep = [c for c in message["tool_calls"] if c.get("function", {}).get("name") in allowed]
            stale = [c for c in message["tool_calls"] if c not in keep]
            if stale:
                dropped_ids |= {c.get("id") for c in stale}
                if keep or message.get("content"):
                    tidied.append({**message, "tool_calls": keep} if keep else _without_calls(message))
                tidied.append({"role": "system", "content": _note(stale)})
                continue
        if message.get("role") == "tool" and message.get("tool_call_id") in dropped_ids:
            continue
        tidied.append(message)
    return tidied


def _without_calls(message: dict) -> dict:
    return {k: v for k, v in message.items() if k != "tool_calls"}


def _tool_names(context) -> set[str]:
    tools = getattr(context, "tools", None)
    standard = getattr(tools, "standard_tools", None) or []
    return {getattr(t, "name", None) for t in standard} - {None}


class ContextTidier(FrameProcessor):
    """Sits right before the LLM and tidies each context it is about to run on."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            context = frame.context
            context.set_messages(tidy_messages(context.get_messages(), _tool_names(context)))
        await self.push_frame(frame, direction)
