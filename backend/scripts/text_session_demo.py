"""End-to-end check of a text session against the local Ollama model.

Usage: python scripts/text_session_demo.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger  # noqa: E402

from app.flows.templates import template_graph  # noqa: E402
from app.runtime.providers import AgentSettings  # noqa: E402
from app.runtime.session import CallSession  # noqa: E402
from app.trace.events import TraceEvent, Tracer  # noqa: E402

CALLER = ["Merhaba, iki gündür modem sürekli kopuyor.", "Müşteri numaram 452618."]


async def main():
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    bot_turn = asyncio.Event()

    async def show(event: TraceEvent):
        print(f"{event.ts:7.2f}s  {event.type:<20} {event.node_id or '':<14} {event.data}")
        if event.type in ("bot_message", "say", "session_ended"):
            bot_turn.set()

    session = CallSession(template_graph("ariza_fatura"), AgentSettings(), Tracer([show]))
    await session.start()
    for line in CALLER:
        await asyncio.wait_for(bot_turn.wait(), 60)
        await asyncio.sleep(0.5)
        bot_turn.clear()
        await session.send_user_text(line)
    await asyncio.wait_for(session.wait(), 90)
    print("\nend reason:", session.end_reason, "| outcome:", session.tracer.outcome)


asyncio.run(main())
