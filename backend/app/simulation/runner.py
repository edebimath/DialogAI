"""Runs one simulated call: the agent's flow in a text session, a simulated caller on the other end.

The caller speaks when the agent's turn is over: the agent said something, the LLM is idle, and
nothing else happened for a short moment (a tool call or a node change means more is coming).
"""

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass, field

from app.flows.schema import FlowGraph
from app.runtime.providers import AgentSettings
from app.runtime.session import CallSession
from app.simulation.caller import SimulatedCaller
from app.simulation.judge import Verdict, evaluate
from app.trace.events import TraceEvent, Tracer

QUIET_SECS = 0.9  # agent silent this long after speaking -> its turn is over
AGENT_SILENCE_SECS = 30  # no reply at all (even after the empty-reply retry) -> give up
MAX_CALL_SECS = 6 * 60
LOOP_REPEATS = 3  # the caller saying the same thing this many times in a row = stuck
HANGUP_GRACE_SECS = 20  # the agent answering the caller's last words before the line drops
ENDING_SECS = 10  # an ending may still write a handoff summary after its text
BOT_OUTPUT = {"say", "bot_message"}
# Latency metrics arrive around replies but say nothing about whose turn it is.
IGNORED = {"llm_ttfb", "stt_time", "tts_ttfb", "voice_latency"}


@dataclass
class ScenarioSpec:
    name: str
    persona: str
    goal: str
    success_criteria: str = ""
    expected_outcome: str | None = None
    variables: dict = field(default_factory=dict)
    max_turns: int = 12


@dataclass
class SimulationResult:
    verdict: Verdict
    outcome: str | None
    end_reason: str | None
    turns: int
    duration: float


class _TurnWatch:
    """Tracer sink that knows when the agent has finished its turn."""

    def __init__(self):
        self.agent_said: list[str] = []
        self.last_kind: str | None = None
        self.last_at = time.monotonic()
        self.ended = asyncio.Event()
        self.events: list[TraceEvent] = []

    async def __call__(self, event: TraceEvent) -> None:
        self.events.append(event)
        if event.type in IGNORED:
            return
        self.last_kind, self.last_at = event.type, time.monotonic()
        if event.type in BOT_OUTPUT and event.data.get("text"):
            self.agent_said.append(event.data["text"])
        if event.type == "session_ended":
            self.ended.set()

    def agent_done(self, tracer: Tracer) -> bool:
        return (
            bool(self.agent_said)
            and self.last_kind in BOT_OUTPUT
            and not tracer.llm_busy
            and time.monotonic() - self.last_at >= QUIET_SECS
        )


async def _let_agent_answer(watch: _TurnWatch, tracer: Tracer) -> None:
    """Wait for the agent's reply to the caller's last words, or for the call to end."""
    deadline = time.monotonic() + HANGUP_GRACE_SECS
    while time.monotonic() < deadline and not watch.ended.is_set() and not watch.agent_done(tracer):
        await asyncio.sleep(0.15)
    if watch.agent_said:
        # The goodbye may be followed by the ending's own text and session end; give it a moment.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(watch.ended.wait(), timeout=ENDING_SECS)


async def run_simulation(
    graph: FlowGraph,
    agent_settings: AgentSettings,
    scenario: ScenarioSpec,
    tracer: Tracer,
    *,
    cancel: asyncio.Event | None = None,
) -> SimulationResult:
    watch = _TurnWatch()
    tracer.add_sink(watch)
    caller = SimulatedCaller(scenario.persona, scenario.goal)
    session = CallSession(graph, agent_settings, tracer, variables=scenario.variables, mode="text")
    started = time.monotonic()
    turns = 0
    caller_view: dict | None = None
    stop_reason: str | None = None
    caller_lines: list[str] = []

    await session.start()
    try:
        while not watch.ended.is_set():
            if cancel is not None and cancel.is_set():
                stop_reason = "user_hangup"
                break
            if time.monotonic() - started > MAX_CALL_SECS:
                stop_reason = "timeout"
                break
            if not watch.agent_done(tracer):
                if time.monotonic() - watch.last_at > AGENT_SILENCE_SECS:
                    stop_reason = "silence"
                    break
                await asyncio.sleep(0.15)
                continue

            said = " ".join(watch.agent_said)
            watch.agent_said.clear()
            if turns >= scenario.max_turns:
                stop_reason = "max_turns"
                break
            turn = await caller.respond(said)
            turns += 1
            caller_lines.append(re.sub(r"\W+", " ", (turn.text or "").casefold()).strip())
            if len(caller_lines) >= LOOP_REPEATS and len(set(caller_lines[-LOOP_REPEATS:])) == 1:
                stop_reason = "loop"
                break
            if turn.text and not watch.ended.is_set():
                await session.send_user_text(turn.text, source="simulated")
            if turn.hangup:
                caller_view = turn.hangup
                if turn.text:
                    # "Thanks, bye" gets an answer before the line drops, as on a real call;
                    # a goodbye usually takes the flow to its ending, which records the outcome.
                    await _let_agent_answer(watch, tracer)
                if not watch.ended.is_set():
                    await tracer.emit("caller_hangup", **turn.hangup)
                    stop_reason = "caller_hangup"
                break
            if not turn.text:  # nothing to say and no hang-up: don't spin
                stop_reason = "silence"
                break
    finally:
        if stop_reason:
            await session.stop(stop_reason)
        await session.wait()

    duration = round(time.monotonic() - started, 1)  # the call itself, not the judging
    verdict = await evaluate(
        watch.events,
        outcome=tracer.outcome,
        end_reason=session.end_reason,
        expected_outcome=scenario.expected_outcome,
        success_criteria=scenario.success_criteria,
        caller=caller_view,
    )
    return SimulationResult(
        verdict=verdict,
        outcome=tracer.outcome,
        end_reason=session.end_reason,
        turns=turns,
        duration=duration,
    )
