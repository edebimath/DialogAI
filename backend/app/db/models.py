import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Always hand out timezone-aware UTC values (a naive value would read as local time in
    the browser)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="editor")  # admin | editor | viewer
    is_active: Mapped[bool] = mapped_column(default=True)
    # In every token; raised on password change so tokens issued before it stop working.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)

    versions: Mapped[list["FlowVersion"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True
    )


class FlowVersion(Base):
    """version 0 is the editable draft; publishing snapshots it as the next version number."""

    __tablename__ = "flow_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)

    agent: Mapped[Agent] = relationship(back_populates="versions")


class TestSession(Base):
    """A simulated call. Keeps its own copy of the graph so the trace stays explainable."""

    __tablename__ = "test_sessions"
    __test__ = False  # not a pytest class

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    flow_version: Mapped[int] = mapped_column(Integer, default=0)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(16), default="text")
    started_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    outcome: Mapped[str | None] = mapped_column(String(64))
    end_reason: Mapped[str | None] = mapped_column(String(64))

    events: Mapped[list["SessionEvent"]] = relationship(
        order_by="SessionEvent.seq", cascade="all, delete-orphan", passive_deletes=True
    )


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("test_sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[float]
    type: Mapped[str] = mapped_column(String(32))
    node_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)

    documents: Mapped[list["KBDocument"]] = relationship(
        back_populates="kb", cascade="all, delete-orphan", passive_deletes=True
    )


class KBTag(Base):
    """A tag defined on the tags screen; entries can only carry defined tags.

    Entries and chunks store tag names (not ids) so searches filter on one array column;
    renaming or deleting a tag rewrites those arrays.
    """

    __tablename__ = "kb_tags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    color: Mapped[str] = mapped_column(String(16), default="violet", server_default="violet")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class KBDocument(Base):
    """An entry of a knowledge base: an uploaded file, or a question-answer pair typed in.

    kind "file": status pending -> processing -> ready | failed, split into chunks by the worker.
    kind "qa": one chunk (question + answer), embedded right away, so always "ready".
    tags: who the entry is for; none = everyone (see app/kb/tags.py).
    """

    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="file", server_default="file")
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, server_default="{}")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=now, onupdate=now)

    kb: Mapped[KnowledgeBase] = relationship(back_populates="documents")


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index(
            "ix_kb_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_kb_chunks_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Denormalized from the document so searches filter on one column.
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))
    # Denormalized from the document, like kb_id, so a search filters without a join.
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list, server_default="{}")
    # Edited by hand; re-processing the file would overwrite it.
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Scenario(Base):
    """A simulated caller: who they are, what they want, and what counts as success."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    persona: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    expected_outcome: Mapped[str | None] = mapped_column(String(64))
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_turns: Mapped[int] = mapped_column(Integer, default=12)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)


class ScenarioRun(Base):
    """A batch of scenarios run against one flow version. status: queued | running | done | cancelled"""

    __tablename__ = "scenario_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    flow_version: Mapped[int] = mapped_column(Integer, default=0)
    # Snapshot taken when the run is queued, so editing the draft mid-run changes nothing.
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    results: Mapped[list["ScenarioResult"]] = relationship(
        order_by="ScenarioResult.ordinal", cascade="all, delete-orphan", passive_deletes=True
    )


class ScenarioResult(Base):
    """One simulated call and its verdict. status: pending | running | passed | failed | error | cancelled

    run_id is empty for a single scenario watched live from the test panel.
    """

    __tablename__ = "scenario_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("scenario_runs.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"))
    scenario_name: Mapped[str] = mapped_column(String(255))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("test_sessions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    outcome: Mapped[str | None] = mapped_column(String(64))
    end_reason: Mapped[str | None] = mapped_column(String(64))
    turns: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float | None]
    # {"checks": [{"name", "passed", "detail"}], "judge": {"passed", "reason"}, "caller": {...}}
    verdict: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
