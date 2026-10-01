"""Runs scenarios: batch runs in a background worker, single ones watched live over the WebSocket.

One simulation at a time: the agent and the caller share the local GPU, and parallel calls would
distort the latencies the results report.
"""

import asyncio
from collections.abc import Awaitable, Callable

from loguru import logger
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Agent, Scenario, ScenarioResult, ScenarioRun, TestSession, now
from app.flows.schema import FlowGraph
from app.runtime.persistence import event_sink
from app.runtime.providers import AgentSettings
from app.simulation.runner import ScenarioSpec, run_simulation
from app.trace.events import Sink, Tracer

# Created by start_worker: asyncio primitives bind to the event loop that first uses them.
_queue: asyncio.Queue[str] | None = None
_slot: asyncio.Semaphore | None = None
_worker: asyncio.Task | None = None
_cancels: dict[str, asyncio.Event] = {}  # run id or result id -> cancel signal


def spec_of(s: Scenario) -> ScenarioSpec:
    return ScenarioSpec(
        name=s.name,
        persona=s.persona,
        goal=s.goal,
        success_criteria=s.success_criteria,
        expected_outcome=s.expected_outcome or None,
        variables=s.variables or {},
        max_turns=s.max_turns,
    )


async def run_result(
    result_id: str,
    graph: FlowGraph,
    agent_settings: AgentSettings,
    spec: ScenarioSpec,
    *,
    started_by: str | None,
    flow_version: int,
    extra_sinks: list[Sink] = (),
    on_session: Callable[[TestSession], Awaitable[None]] | None = None,
    cancel: asyncio.Event | None = None,
) -> ScenarioResult:
    """Run one scenario into an existing ScenarioResult row and store the verdict."""
    async with SessionLocal() as db:
        result = await db.get(ScenarioResult, result_id)
        session_row = TestSession(
            agent_id=result.agent_id,
            flow_version=flow_version,
            graph=graph.model_dump(),
            mode="simulation",
            started_by=started_by,
        )
        db.add(session_row)
        await db.flush()
        result.session_id, result.status = session_row.id, "running"
        await db.commit()
    if on_session:
        await on_session(session_row)

    tracer = Tracer([event_sink(session_row.id), *extra_sinks])
    async with _slot:
        try:
            outcome = await run_simulation(graph, agent_settings, spec, tracer, cancel=cancel)
            fields = {
                "status": "cancelled"
                if outcome.end_reason == "user_hangup"
                else ("passed" if outcome.verdict.passed else "failed"),
                "outcome": outcome.outcome,
                "end_reason": outcome.end_reason,
                "turns": outcome.turns,
                "duration": outcome.duration,
                "verdict": outcome.verdict.model_dump(),
            }
        except Exception as e:
            logger.exception(f"Scenario '{spec.name}' failed")
            fields = {"status": "error", "verdict": {"passed": False, "checks": [], "error": str(e)}}

    async with SessionLocal() as db:
        result = await db.get(ScenarioResult, result_id)
        for key, value in fields.items():
            setattr(result, key, value)
        await db.commit()
        return result


async def _run_batch(run_id: str) -> None:
    cancel = _cancels.setdefault(run_id, asyncio.Event())
    async with SessionLocal() as db:
        run = await db.get(ScenarioRun, run_id)
        if run is None or run.status == "cancelled":
            return
        run.status = "running"
        agent = await db.get(Agent, run.agent_id)
        agent_settings = AgentSettings.model_validate(agent.settings or {})
        graph = FlowGraph.model_validate(run.graph)
        results = (
            await db.scalars(
                select(ScenarioResult)
                .where(ScenarioResult.run_id == run_id, ScenarioResult.status == "pending")
                .order_by(ScenarioResult.ordinal)
            )
        ).all()
        scenarios = {
            s.id: s
            for s in await db.scalars(
                select(Scenario).where(Scenario.id.in_([r.scenario_id for r in results if r.scenario_id]))
            )
        }
        started_by, version = run.created_by, run.flow_version
        await db.commit()

    for result in results:
        if cancel.is_set():
            break
        scenario = scenarios.get(result.scenario_id)
        if scenario is None:  # deleted while queued
            async with SessionLocal() as db:
                (await db.get(ScenarioResult, result.id)).status = "cancelled"
                await db.commit()
            continue
        await run_result(
            result.id,
            graph,
            agent_settings,
            spec_of(scenario),
            started_by=started_by,
            flow_version=version,
            cancel=cancel,
        )

    async with SessionLocal() as db:
        run = await db.get(ScenarioRun, run_id)
        leftover = await db.scalars(
            select(ScenarioResult).where(ScenarioResult.run_id == run_id, ScenarioResult.status == "pending")
        )
        for r in leftover:
            r.status = "cancelled"
        run.status = "cancelled" if cancel.is_set() else "done"
        run.finished_at = now()
        await db.commit()
    _cancels.pop(run_id, None)


async def _worker_loop() -> None:
    while True:
        run_id = await _queue.get()
        try:
            await _run_batch(run_id)
        except Exception:
            logger.exception(f"Scenario run {run_id} failed")
        finally:
            _queue.task_done()


def enqueue_run(run_id: str) -> None:
    if _queue is None:
        raise RuntimeError("Simulation worker is not running")
    _queue.put_nowait(run_id)


def cancel(key: str) -> None:
    _cancels.setdefault(key, asyncio.Event()).set()


def cancel_signal(key: str) -> asyncio.Event:
    return _cancels.setdefault(key, asyncio.Event())


def release(key: str) -> None:
    _cancels.pop(key, None)


async def start_worker() -> None:
    global _queue, _slot, _worker
    _queue, _slot = asyncio.Queue(), asyncio.Semaphore(1)
    async with SessionLocal() as db:
        # A restart interrupts whatever was running; queued runs start over from pending results.
        for r in await db.scalars(select(ScenarioResult).where(ScenarioResult.status == "running")):
            r.status = "error"
            r.verdict = {"passed": False, "checks": [], "error": "Sunucu yeniden başlatıldı."}
        pending_runs = (
            await db.scalars(
                select(ScenarioRun.id)
                .where(ScenarioRun.status.in_(("queued", "running")))
                .order_by(ScenarioRun.created_at)
            )
        ).all()
        await db.commit()
    for run_id in pending_runs:
        enqueue_run(run_id)
    _worker = asyncio.create_task(_worker_loop())


async def stop_worker() -> None:
    if _worker:
        _worker.cancel()
