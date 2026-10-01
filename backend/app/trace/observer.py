"""Turns pipeline frames into trace events: replies, transcripts, latencies, interruptions, errors.

Function calls are traced by the compiler's handlers, which know the node they belong to.
"""

import time
from collections.abc import Awaitable, Callable

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import TTFBMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.services.llm_service import LLMService
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService

from app.runtime.filters import clean_reply
from app.trace.events import Tracer


class TraceObserver(BaseObserver):
    def __init__(self, tracer: Tracer, on_empty_reply: Callable[[int], Awaitable[None]] | None = None):
        """
        Args:
            on_empty_reply: Called with the count of consecutive LLM responses that had neither
                text nor a function call; small models sometimes return nothing, which leaves
                the caller in silence.
        """
        super().__init__(observe_every_push=False)
        self._tracer = tracer
        self._on_empty_reply = on_empty_reply
        self._reply: list[str] | None = None
        self._reply_called = False
        self._empty_streak = 0
        self._user_stopped_at: float | None = None
        self._bot_speaking = False

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        source = data.source
        from_llm = isinstance(source, LLMService)

        if from_llm and isinstance(frame, LLMFullResponseStartFrame):
            self._reply = []
            self._reply_called = False
            self._tracer.llm_busy = True
        elif from_llm and isinstance(frame, FunctionCallsStartedFrame):
            self._reply_called = True
        elif from_llm and isinstance(frame, LLMTextFrame):
            if self._reply is not None:
                self._reply.append(frame.text)
        elif from_llm and isinstance(frame, LLMFullResponseEndFrame):
            # Observed at the LLM's push, before SpokenTextFilter cleans the frames.
            text = clean_reply("".join(self._reply or []))
            self._reply = None
            self._tracer.llm_busy = False
            if text:
                await self._tracer.emit("bot_message", text=text)
            if text or self._reply_called:
                self._empty_streak = 0
            else:
                self._empty_streak += 1
                if self._on_empty_reply:
                    await self._on_empty_reply(self._empty_streak)
        elif isinstance(frame, TranscriptionFrame) and isinstance(source, STTService):
            if frame.text.strip():
                await self._tracer.emit("user_message", text=frame.text.strip(), source="voice")
        elif isinstance(frame, MetricsFrame):
            await self._metrics(frame, source)
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_stopped_at = time.monotonic()
        elif isinstance(frame, BotStartedSpeakingFrame):
            # Broadcast in both directions; the first copy clears the mark, the second is ignored.
            self._bot_speaking = True
            if self._user_stopped_at is not None:
                seconds = time.monotonic() - self._user_stopped_at
                self._user_stopped_at = None
                await self._tracer.emit("voice_latency", seconds=round(seconds, 3))
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif isinstance(frame, InterruptionFrame):
            # Pipecat interrupts at every caller turn; it only matters when the bot was talking.
            # The flag also drops the second copy of the broadcast.
            if self._bot_speaking:
                self._bot_speaking = False
                await self._tracer.emit("interrupted")
        elif isinstance(frame, ErrorFrame):
            await self._tracer.emit("error", message=str(frame.error))

    async def _metrics(self, frame: MetricsFrame, source) -> None:
        for metric in frame.data:
            if isinstance(source, LLMService) and isinstance(metric, TTFBMetricsData):
                if metric.value > 0:
                    await self._tracer.emit("llm_ttfb", seconds=round(metric.value, 3))
            elif isinstance(source, STTService) and isinstance(metric, TTFBMetricsData):
                # Time from the end of speech to the final transcript.
                if metric.value > 0:
                    await self._tracer.emit("stt_time", seconds=round(metric.value, 3))
            elif isinstance(source, TTSService) and isinstance(metric, TTFBMetricsData):
                if metric.value > 0:
                    await self._tracer.emit("tts_ttfb", seconds=round(metric.value, 3))
