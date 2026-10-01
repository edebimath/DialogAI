from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, Editor
from app.api.schemas import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    FlowOut,
    FlowSave,
    PublishIn,
    SessionOut,
    VersionOut,
)
from app.db.models import Agent, FlowVersion, Scenario, TestSession, now
from app.flows.schema import FlowGraph
from app.flows.templates import TEMPLATES
from app.flows.validator import has_errors, validate
from app.api.knowledge import kb_ids, tagged_kb_ids
from app.runtime.providers import AgentSettings

router = APIRouter(prefix="/api/agents", tags=["agents"])


async def get_agent(db: AsyncSession, agent_id: str) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ajan bulunamadı.")
    return agent


async def get_version(db: AsyncSession, agent_id: str, version: int) -> FlowVersion:
    row = await db.scalar(
        select(FlowVersion).where(FlowVersion.agent_id == agent_id, FlowVersion.version == version)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Akış sürümü bulunamadı.")
    return row


async def latest_published(db: AsyncSession, agent_id: str) -> int | None:
    return await db.scalar(
        select(func.max(FlowVersion.version)).where(
            FlowVersion.agent_id == agent_id, FlowVersion.version > 0
        )
    )


async def agent_out(db: AsyncSession, agent: Agent) -> AgentOut:
    out = AgentOut.model_validate(agent)
    out.published_version = await latest_published(db, agent.id)
    return out


async def flow_out(db: AsyncSession, row: FlowVersion) -> FlowOut:
    graph = FlowGraph.model_validate(row.graph)
    issues = validate(graph, await kb_ids(db), await tagged_kb_ids(db))
    return FlowOut(version=row.version, graph=graph, issues=issues, updated_at=row.updated_at)


# --- Agents -------------------------------------------------------------------------


@router.get("", response_model=list[AgentOut])
async def list_agents(db: DB, _: CurrentUser):
    agents = (await db.scalars(select(Agent).order_by(Agent.updated_at.desc()))).all()
    return [await agent_out(db, a) for a in agents]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, db: DB, user: Editor):
    if body.template not in TEMPLATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bilinmeyen şablon.")
    agent = Agent(
        name=body.name,
        description=body.description,
        settings=AgentSettings().model_dump(),
        created_by=user.id,
    )
    db.add(agent)
    await db.flush()
    graph = FlowGraph.model_validate(TEMPLATES[body.template]["graph"])
    db.add(FlowVersion(agent_id=agent.id, version=0, graph=graph.model_dump(), created_by=user.id))
    for scenario in TEMPLATES[body.template].get("scenarios", []):
        db.add(Scenario(agent_id=agent.id, **scenario))
    await db.commit()
    return await agent_out(db, agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def read_agent(agent_id: str, db: DB, _: CurrentUser):
    return await agent_out(db, await get_agent(db, agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: str, body: AgentUpdate, db: DB, _: Editor):
    agent = await get_agent(db, agent_id)
    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.settings is not None:
        agent.settings = body.settings.model_dump()
    await db.commit()
    return await agent_out(db, agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, db: DB, _: Editor):
    await db.delete(await get_agent(db, agent_id))
    await db.commit()


# --- Flow draft, validation and versions ----------------------------------------------


@router.get("/{agent_id}/flow", response_model=FlowOut)
async def read_draft(agent_id: str, db: DB, _: CurrentUser):
    return await flow_out(db, await get_version(db, agent_id, 0))


@router.put("/{agent_id}/flow", response_model=FlowOut)
async def save_draft(agent_id: str, body: FlowSave, db: DB, _: Editor):
    """Drafts are saved even with errors; issues come back for the canvas to show."""
    draft = await get_version(db, agent_id, 0)
    draft.graph = body.graph.model_dump()
    (await get_agent(db, agent_id)).updated_at = now()  # list is sorted by last edit
    await db.commit()
    await db.refresh(draft)
    return await flow_out(db, draft)


@router.post("/{agent_id}/flow/validate", response_model=FlowOut)
async def validate_graph(agent_id: str, body: FlowSave, db: DB, _: CurrentUser):
    issues = validate(body.graph, await kb_ids(db), await tagged_kb_ids(db))
    return FlowOut(version=0, graph=body.graph, issues=issues)


@router.post("/{agent_id}/publish", response_model=VersionOut)
async def publish(agent_id: str, body: PublishIn, db: DB, user: Editor):
    draft = await get_version(db, agent_id, 0)
    if has_errors(validate(FlowGraph.model_validate(draft.graph), await kb_ids(db))):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hataları olan bir akış yayınlanamaz.")
    number = (await latest_published(db, agent_id) or 0) + 1
    row = FlowVersion(
        agent_id=agent_id, version=number, graph=draft.graph, note=body.note, created_by=user.id
    )
    db.add(row)
    await db.commit()
    return row


@router.get("/{agent_id}/versions", response_model=list[VersionOut])
async def list_versions(agent_id: str, db: DB, _: CurrentUser):
    rows = await db.scalars(
        select(FlowVersion)
        .where(FlowVersion.agent_id == agent_id, FlowVersion.version > 0)
        .order_by(FlowVersion.version.desc())
    )
    return rows.all()


@router.get("/{agent_id}/versions/{version}", response_model=FlowOut)
async def read_version(agent_id: str, version: int, db: DB, _: CurrentUser):
    return await flow_out(db, await get_version(db, agent_id, version))


@router.post("/{agent_id}/versions/{version}/restore", response_model=FlowOut)
async def restore_version(agent_id: str, version: int, db: DB, _: Editor):
    source = await get_version(db, agent_id, version)
    draft = await get_version(db, agent_id, 0)
    draft.graph = source.graph
    await db.commit()
    await db.refresh(draft)
    return await flow_out(db, draft)


# --- Test session history -------------------------------------------------------------


@router.get("/{agent_id}/sessions", response_model=list[SessionOut])
async def list_sessions(agent_id: str, db: DB, _: CurrentUser):
    rows = await db.scalars(
        select(TestSession)
        .where(TestSession.agent_id == agent_id)
        .order_by(TestSession.started_at.desc())
        .limit(50)
    )
    return rows.all()
