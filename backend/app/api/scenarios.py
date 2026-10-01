from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.agents import get_agent, get_version
from app.api.deps import DB, CurrentUser, Editor
from app.api.knowledge import kb_ids
from app.api.schemas import ResultOut, RunCreate, RunDetail, RunOut, ScenarioIn, ScenarioOut
from app.db.models import Scenario, ScenarioResult, ScenarioRun
from app.flows.schema import FlowGraph
from app.flows.validator import has_errors, validate
from app.simulation import service

router = APIRouter(tags=["scenarios"])

UNFINISHED = ("pending", "running")


async def get_scenario(db: AsyncSession, scenario_id: str) -> Scenario:
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Senaryo bulunamadı.")
    return scenario


def run_out(run: ScenarioRun, results: list[ScenarioResult]) -> RunOut:
    out = RunOut.model_validate(run)
    out.total = len(results)
    out.passed = sum(r.status == "passed" for r in results)
    out.failed = sum(r.status in ("failed", "error") for r in results)
    out.pending = sum(r.status in UNFINISHED for r in results)
    return out


# --- Scenarios ---------------------------------------------------------------------


@router.get("/api/agents/{agent_id}/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(agent_id: str, db: DB, _: CurrentUser):
    scenarios = (
        await db.scalars(select(Scenario).where(Scenario.agent_id == agent_id).order_by(Scenario.created_at))
    ).all()
    latest = await db.scalars(
        select(ScenarioResult)
        .where(ScenarioResult.agent_id == agent_id, ScenarioResult.scenario_id.is_not(None))
        .order_by(ScenarioResult.created_at.desc())
    )
    last: dict[str, ScenarioResult] = {}
    for r in latest:
        last.setdefault(r.scenario_id, r)
    out = []
    for s in scenarios:
        item = ScenarioOut.model_validate(s)
        if s.id in last:
            item.last_result = ResultOut.model_validate(last[s.id])
        out.append(item)
    return out


@router.post("/api/agents/{agent_id}/scenarios", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
async def create_scenario(agent_id: str, body: ScenarioIn, db: DB, _: Editor):
    await get_agent(db, agent_id)
    scenario = Scenario(agent_id=agent_id, **body.model_dump())
    db.add(scenario)
    await db.commit()
    return scenario


@router.put("/api/scenarios/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(scenario_id: str, body: ScenarioIn, db: DB, _: Editor):
    scenario = await get_scenario(db, scenario_id)
    for key, value in body.model_dump().items():
        setattr(scenario, key, value)
    await db.commit()
    return scenario


@router.delete("/api/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(scenario_id: str, db: DB, _: Editor):
    await db.delete(await get_scenario(db, scenario_id))
    await db.commit()


@router.get("/api/scenarios/{scenario_id}/results", response_model=list[ResultOut])
async def scenario_results(scenario_id: str, db: DB, _: CurrentUser):
    rows = await db.scalars(
        select(ScenarioResult)
        .where(ScenarioResult.scenario_id == scenario_id)
        .order_by(ScenarioResult.created_at.desc())
        .limit(30)
    )
    return rows.all()


# --- Runs --------------------------------------------------------------------------


@router.post("/api/agents/{agent_id}/scenario-runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(agent_id: str, body: RunCreate, db: DB, user: Editor):
    await get_agent(db, agent_id)
    version = await get_version(db, agent_id, body.version)
    graph = FlowGraph.model_validate(version.graph)
    if has_errors(validate(graph, await kb_ids(db))):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Akışta hatalar var, önce bunları düzeltin.")
    query = select(Scenario).where(Scenario.agent_id == agent_id).order_by(Scenario.created_at)
    if body.scenario_ids is not None:
        query = query.where(Scenario.id.in_(body.scenario_ids))
    scenarios = (await db.scalars(query)).all()
    if not scenarios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Çalıştırılacak senaryo yok.")

    run = ScenarioRun(agent_id=agent_id, flow_version=body.version, graph=version.graph, created_by=user.id)
    db.add(run)
    await db.flush()
    results = [
        ScenarioResult(run_id=run.id, agent_id=agent_id, scenario_id=s.id, scenario_name=s.name, ordinal=i)
        for i, s in enumerate(scenarios)
    ]
    db.add_all(results)
    await db.commit()
    service.enqueue_run(run.id)
    return run_out(run, results)


@router.get("/api/agents/{agent_id}/scenario-runs", response_model=list[RunOut])
async def list_runs(agent_id: str, db: DB, _: CurrentUser):
    runs = await db.scalars(
        select(ScenarioRun)
        .where(ScenarioRun.agent_id == agent_id)
        .options(selectinload(ScenarioRun.results))
        .order_by(ScenarioRun.created_at.desc())
        .limit(30)
    )
    return [run_out(run, run.results) for run in runs]


@router.get("/api/scenario-runs/{run_id}", response_model=RunDetail)
async def read_run(run_id: str, db: DB, _: CurrentUser):
    run = await db.scalar(
        select(ScenarioRun).where(ScenarioRun.id == run_id).options(selectinload(ScenarioRun.results))
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Koşu bulunamadı.")
    return RunDetail(
        **run_out(run, run.results).model_dump(),
        results=[ResultOut.model_validate(r) for r in run.results],
    )


@router.post("/api/scenario-runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, db: DB, _: Editor):
    run = await db.scalar(
        select(ScenarioRun).where(ScenarioRun.id == run_id).options(selectinload(ScenarioRun.results))
    )
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Koşu bulunamadı.")
    if run.status == "queued":
        run.status = "cancelled"
        for r in run.results:
            if r.status == "pending":
                r.status = "cancelled"
        await db.commit()
    elif run.status == "running":
        service.cancel(run.id)
    return run_out(run, run.results)
