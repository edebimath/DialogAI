"""Cleans LLM output meant to be spoken. Small local models ignore "no emoji" instructions."""

import re

from pipecat.frames.frames import Frame, LLMTextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, symbols & pictographs ext.
    "☀-➿"  # misc symbols, dingbats
    "⬀-⯿"  # arrows, stars
    "️‍⃣"  # variation selector, zero-width joiner, keycap
    "]+"
)


# List markers at the start of a line ("- ", "* ", "1. ") in a finished reply.
LIST_MARKER = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")


def speakable(text: str) -> str:
    """Safe on streamed fragments: removes emoji only."""
    return EMOJI.sub("", text)


def clean_reply(text: str) -> str:
    """A whole reply as the transcript shows it. Not for streamed fragments, where a line start
    is just a chunk boundary (it would eat the dash in "08:00 - 22:00")."""
    return LIST_MARKER.sub("", speakable(text)).strip()


class SpokenTextFilter(FrameProcessor):
    """Strips emoji from LLM text before it reaches the context, the TTS and the transcript."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame) and direction == FrameDirection.DOWNSTREAM:
            frame.text = speakable(frame.text)
        await self.push_frame(frame, direction)
