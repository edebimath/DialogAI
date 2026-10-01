"""Test sessions: a WebSocket per simulated call, plus history for replay.

WebSocket protocol (JSON messages):
  client -> {"type": "start", "token": str, "agent_id": str, "version": int = 0, "variables": {},
             "mode": "text" | "voice" | "simulation", "scenario_id": str (simulation)}
            voice only, right after start:
            {"type": "webrtc_offer", "sdp": str, "sdp_type": "offer"}
            {"type": "user_text", "text": str}          (text and voice calls)
            {"type": "hangup"}
  server -> {"type": "session", "session": SessionOut}
            voice only: {"type": "webrtc_answer", "sdp": str, "sdp_type": "answer"}
            {"type": "event", "event": TraceEvent}
            simulation only, at the end: {"type": "simulation_result", "result": ResultOut}
            {"type": "error", "message": str, "issues": [Issue]?}

The token travels in the first message, not the URL, so it never lands in access logs.

Audio itself flows over WebRTC (Pipecat SmallWebRTC, aiortc); the answer carries all ICE
candidates, so the WebSocket is the only signalling channel needed. In simulation mode an LLM
plays the caller (app.simulation) and the client only watches.
"""

import asyncio
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.agents import get_agent, get_version
from app.api.deps import DB, CurrentUser, user_from_token
from app.api.knowledge import kb_ids
from app.api.schemas import ResultOut, SessionDetail, SessionOut
from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models import Agent, Scenario, ScenarioResult, TestSession, User
from app.flows.schema import FlowGraph
from app.flows.validator import has_errors, validate
from app.runtime.persistence import event_sink, recording_path
from app.runtime.providers import AgentSettings, ProviderError
from app.runtime.session import CallSession
from app.simulation import service
from app.trace.events import TraceEvent, Tracer

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

MAX_SESSION_SECS = 15 * 60
OFFER_TIMEOUT_SECS = 15
START_TIMEOUT_SECS = 10
MAX_VARIABLE_CHARS = 500
_active = 0


class StartMessage(BaseModel):
    type: str = "start"
    token: str = ""
    agent_id: str
    version: int = 0
    variables: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["text", "voice", "simulation"] = "text"
    scenario_id: str | None = None


class OfferMessage(BaseModel):
    type: Literal["webrtc_offer"]
    sdp: str
    sdp_type: str = "offer"


def call_variables(graph: FlowGraph, given: dict[str, Any]) -> dict[str, str]:
    """Only the flow's declared variables may be set for a test call, as short text; the rest
    of the state (collected fields, HTTP results) comes from the call itself."""
    declared = {v.name for v in graph.variables}
    return {k: str(v)[:MAX_VARIABLE_CHARS] for k, v in given.items() if k in declared and v is not None}


def check_session_id(session_id: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oturum bulunamadı.")


@router.get("/{session_id}", response_model=SessionDetail)
async def read_session(session_id: str, db: DB, _: CurrentUser):
    check_session_id(session_id)
    row = await db.scalar(
        select(TestSession)
        .where(TestSession.id == session_id)
        .options(selectinload(TestSession.events))
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oturum bulunamadı.")
    detail = SessionDetail.model_validate(row)
    detail.has_recording = recording_path(row.id).exists()
    return detail


@router.get("/{session_id}/recording")
async def read_recording(session_id: str, _: CurrentUser):
    check_session_id(session_id)  # the id becomes part of a file path
    path = recording_path(session_id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bu oturumun ses kaydı yok.")
    return FileResponse(path, media_type="audio/wav", filename=f"cagri-{session_id[:8]}.wav")


async def _accept_offer(ws: WebSocket):
    """Wait for the browser's SDP offer, answer it, and return the connection."""
    from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

    offer = OfferMessage.model_validate(
        await asyncio.wait_for(ws.receive_json(), OFFER_TIMEOUT_SECS)
    )
    connection = SmallWebRTCConnection(ice_servers=[])  # same machine / LAN: no STUN needed
    await connection.initialize(sdp=offer.sdp, type=offer.sdp_type)
    answer = connection.get_answer()
    await ws.send_json({"type": "webrtc_answer", "sdp": answer["sdp"], "sdp_type": answer["type"]})
    return connection


@router.websocket("/ws")
async def session_ws(ws: WebSocket):
    global _active
    await ws.accept()

    async def fail(message: str, **extra) -> None:
        await ws.send_json({"type": "error", "message": message, **extra})
        await ws.close()

    async with SessionLocal() as db:
        try:
            start = StartMessage.model_validate(
                await asyncio.wait_for(ws.receive_json(), START_TIMEOUT_SECS)
            )
        except (WebSocketDisconnect, asyncio.TimeoutError):
            return await ws.close()
        except (ValidationError, ValueError):
            return await fail("Geçersiz başlatma mesajı.")
        user = await user_from_token(db, start.token)
        if user is None:
            return await fail("Oturum geçersiz, lütfen tekrar giriş yapın.")
        try:
            agent = await get_agent(db, start.agent_id)
            version = await get_version(db, agent.id, start.version)
        except HTTPException as e:
            return await fail(e.detail)

        graph = FlowGraph.model_validate(version.graph)
        start.variables = call_variables(graph, start.variables)
        issues = validate(graph, await kb_ids(db))
        if has_errors(issues):
            return await fail(
                "Akışta hatalar var, önce bunları düzeltin.",
                issues=[i.model_dump() for i in issues],
            )
        if _active >= settings.max_concurrent_sessions:
            return await fail("Aynı anda çalışabilecek test oturumu sınırına ulaşıldı.")

        scenario = None
        if start.mode == "simulation":
            scenario = await db.get(Scenario, start.scenario_id or "")
            if scenario is None or scenario.agent_id != agent.id:
                return await fail("Senaryo bulunamadı.")

    _active += 1
    try:
        if scenario is not None:
            await _simulation(ws, agent, version.version, graph, scenario, user)
        else:
            await _call(ws, agent, version.version, version.graph, graph, start, user, fail)
    finally:
        _active -= 1
        try:
            await ws.close()
        except RuntimeError:
            pass  # already closed by the client


async def _call(ws, agent: Agent, version: int, raw_graph, graph, start: StartMessage, user: User, fail):
    """A call where the tester is the caller: typing, or speaking over WebRTC."""
    async with SessionLocal() as db:
        row = TestSession(
            agent_id=agent.id, flow_version=version, graph=raw_graph, mode=start.mode, started_by=user.id
        )
        db.add(row)
        await db.commit()
    agent_settings = AgentSettings.model_validate(agent.settings or {})
    ended = asyncio.Event()
    await ws.send_json({"type": "session", "session": SessionOut.model_validate(row).model_dump(mode="json")})

    async def to_client(event: TraceEvent) -> None:
        if event.type == "session_ended":
            ended.set()
        await ws.send_json({"type": "event", "event": event.model_dump()})

    session: CallSession | None = None
    try:
        connection = None
        if start.mode == "voice":
            try:
                connection = await _accept_offer(ws)
            except (ValidationError, asyncio.TimeoutError):
                return await fail("Tarayıcıdan ses bağlantısı teklifi gelmedi.")

        session = CallSession(
            graph,
            agent_settings,
            Tracer([event_sink(row.id), to_client]),
            variables=start.variables,
            mode=start.mode,
            webrtc_connection=connection,
            recording_path=recording_path(row.id) if connection else None,
        )
        try:
            await session.start()
        except ProviderError as e:
            await ws.send_json({"type": "error", "message": str(e)})
            await session.stop("error")
            return

        async def receive() -> None:
            while True:
                message = await ws.receive_json()
                if message.get("type") == "user_text" and str(message.get("text", "")).strip():
                    await session.send_user_text(str(message["text"]).strip())
                elif message.get("type") == "hangup":
                    await session.stop("user_hangup")
                    return

        receiver = asyncio.create_task(receive())
        waiter = asyncio.create_task(ended.wait())
        done, _ = await asyncio.wait(
            {receiver, waiter}, timeout=MAX_SESSION_SECS, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            await session.stop("timeout")
        elif receiver in done and isinstance(receiver.exception(), WebSocketDisconnect):
            await session.stop("client_disconnected")
        await session.wait()
        for task in (receiver, waiter):
            task.cancel()
    except WebSocketDisconnect:
        if session:
            await session.stop("client_disconnected")
    except Exception:
        logger.exception("Test session failed")
        if session:
            await session.stop("error")


async def _simulation(ws, agent: Agent, version: int, graph, scenario: Scenario, user: User):
    """A simulated caller plays the scenario; the tester watches and may stop it."""
    async with SessionLocal() as db:
        result = ScenarioResult(agent_id=agent.id, scenario_id=scenario.id, scenario_name=scenario.name)
        db.add(result)
        await db.commit()
    stop = service.cancel_signal(result.id)

    async def to_client(event: TraceEvent) -> None:
        await ws.send_json({"type": "event", "event": event.model_dump()})

    async def on_session(row: TestSession) -> None:
        await ws.send_json({"type": "session", "session": SessionOut.model_validate(row).model_dump(mode="json")})

    async def listen() -> None:
        try:
            while True:
                if (await ws.receive_json()).get("type") == "hangup":
                    stop.set()
        except WebSocketDisconnect:
            stop.set()

    listener = asyncio.create_task(listen())
    try:
        finished = await service.run_result(
            result.id,
            graph,
            AgentSettings.model_validate(agent.settings or {}),
            service.spec_of(scenario),
            started_by=user.id,
            flow_version=version,
            extra_sinks=[to_client],
            on_session=on_session,
            cancel=stop,
        )
        await ws.send_json(
            {"type": "simulation_result", "result": ResultOut.model_validate(finished).model_dump(mode="json")}
        )
    except (WebSocketDisconnect, RuntimeError):
        pass  # the tester closed the panel; the result is stored anyway
    finally:
        listener.cancel()
        service.release(result.id)
