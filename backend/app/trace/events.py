"""Trace events: everything that happened during a simulated call, in order."""

import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel

EventType = Literal[
    "session_started",
    "node_entered",
    "say",
    "user_message",
    "bot_message",
    "function_call",
    "variables_set",
    "condition_evaluated",
    "kb_search",
    "http_request",  # HTTP Aracı: {"ok", "method", "url", "status", "ms", "values", "error", ...}
    "transfer",  # handed to a human: {"target", "variables", "summary"}
    "llm_ttfb",
    "stt_time",
    "tts_ttfb",
    "voice_latency",  # caller stopped speaking -> bot started speaking
    "interrupted",
    "empty_reply",  # the LLM returned nothing; retried once
    "caller_hangup",  # simulated caller ended the call: {"success", "reason"}
    "error",
    "session_ended",
]


class TraceEvent(BaseModel):
    seq: int
    ts: float  # seconds since session start
    type: EventType
    node_id: str | None = None
    data: dict[str, Any] = {}


Sink = Callable[[TraceEvent], Awaitable[None]]


class Tracer:
    """Collects a session's events and forwards each one to the sinks (WebSocket, DB)."""

    def __init__(self, sinks: list[Sink] | None = None):
        self._sinks = list(sinks or [])
        self._start = time.monotonic()
        self._seq = 0
        self.events: list[TraceEvent] = []
        self.current_node: str | None = None
        # Set by the observer while the LLM is producing a response; not an event.
        self.llm_busy = False
        self.outcome: str | None = None

    def add_sink(self, sink: Sink) -> None:
        self._sinks.append(sink)

    async def emit(self, type: EventType, node_id: str | None = None, **data: Any) -> TraceEvent:
        self._seq += 1
        if type == "node_entered":
            self.current_node = node_id
        event = TraceEvent(
            seq=self._seq,
            ts=round(time.monotonic() - self._start, 3),
            type=type,
            node_id=node_id if node_id is not None else self.current_node,
            data=data,
        )
        self.events.append(event)
        for sink in self._sinks:
            try:
                await sink(event)
            except Exception as e:  # a closed WebSocket must not break the call
                logger.warning(f"Trace sink failed for {event.type}: {e}")
        return event
