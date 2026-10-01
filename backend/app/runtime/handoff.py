"""Handoff note for the human agent who takes over a transferred call."""

from app.simulation.llm import chat
from app.trace.events import TraceEvent
from app.trace.transcript import transcript

HANDOFF_INSTRUCTION = """\
Bir çağrı merkezi asistanısın. Aşağıdaki görüşme bir müşteri temsilcisine aktarılıyor. \
Temsilcinin arayana hiçbir şeyi yeniden sormadan devam edebilmesi için en fazla üç cümlelik \
Türkçe bir özet yaz: arayanın talebi, verdiği bilgiler, şimdiye kadar yapılanlar ve aktarılma \
nedeni. Dökümde olmayan hiçbir bilgiyi ekleme. Yalnızca özeti yaz."""


async def summarize(events: list[TraceEvent]) -> str:
    """Raises SimulationLLMError when the local model can't be reached."""
    reply = await chat(
        [
            {"role": "system", "content": HANDOFF_INSTRUCTION},
            {"role": "user", "content": transcript(events)},
        ],
        temperature=0.2,
    )
    return reply.content
