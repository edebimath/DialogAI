"""Run one simulated call against a template flow and print the trace and verdict (needs Ollama).

Usage: python scripts/sim_demo.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger  # noqa: E402

from app.flows.templates import template_graph  # noqa: E402
from app.runtime.providers import AgentSettings  # noqa: E402
from app.simulation.runner import ScenarioSpec, run_simulation  # noqa: E402
from app.trace.events import TraceEvent, Tracer  # noqa: E402

SCENARIO = ScenarioSpec(
    name="Modemi kopan müşteri",
    persona="Ayşe, 45 yaşında, sabırlı ama teknolojiden pek anlamayan bir ev hanımı. Müşteri numarası 552190.",
    goal="İki gündür kopan internet için arıza kaydı açtırmak.",
    success_criteria="Ajan arıza kaydını müşterinin verdiği 552190 numarasıyla açtığını söyledi.",
    expected_outcome="ticket_created",
)


async def main():
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    async def show(e: TraceEvent):
        d = e.data
        if e.type in ("say", "bot_message", "user_message"):
            who = "ARAYAN" if e.type == "user_message" else "AJAN  "
            print(f"{e.ts:6.1f}s {who} {d['text']}")
        elif e.type in ("function_call", "caller_hangup", "session_ended", "node_entered"):
            print(f"{e.ts:6.1f}s   [{e.type}] {e.node_id or ''} {d}")

    result = await run_simulation(template_graph("ariza_fatura"), AgentSettings(), SCENARIO, Tracer([show]))
    v = result.verdict
    print(f"\nPASSED={v.passed} turns={result.turns} {result.duration}s end={result.end_reason} outcome={result.outcome}")
    for c in v.checks:
        print(f"  {'✓' if c.passed else '✗'} {c.name}: {c.detail}")
    if v.judge:
        print(f"  {'✓' if v.judge.passed else '✗'} Hakem: {v.judge.reason}")
    print("  arayan:", v.caller)


asyncio.run(main())
