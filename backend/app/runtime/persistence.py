"""Stores test-session events as they happen, and where call recordings live."""

from pathlib import Path

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models import SessionEvent, TestSession, now
from app.trace.events import TraceEvent


def recording_path(session_id: str) -> Path:
    return settings.data_dir / "recordings" / f"{session_id}.wav"


async def persist_event(session_id: str, event: TraceEvent) -> None:
    async with SessionLocal() as db:
        db.add(
            SessionEvent(
                session_id=session_id,
                seq=event.seq,
                ts=event.ts,
                type=event.type,
                node_id=event.node_id,
                data=event.data,
            )
        )
        if event.type == "session_ended":
            row = await db.get(TestSession, session_id)
            row.ended_at = now()
            row.outcome = event.data.get("outcome")
            row.end_reason = event.data.get("reason")
        await db.commit()


def event_sink(session_id: str):
    async def sink(event: TraceEvent) -> None:
        await persist_event(session_id, event)

    return sink
