"""Request/response bodies of the REST API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Role
from app.flows.schema import FlowGraph
from app.flows.validator import Issue
from app.runtime.providers import AgentSettings


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: str
    email: str
    name: str
    role: Role
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = ""
    password: str = Field(min_length=8, max_length=128)
    role: Role = "editor"


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    template: str = "blank"


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    settings: AgentSettings | None = None


class AgentOut(ORM):
    id: str
    name: str
    description: str
    settings: AgentSettings
    created_at: datetime
    updated_at: datetime
    published_version: int | None = None


class FlowOut(BaseModel):
    version: int
    graph: FlowGraph
    issues: list[Issue]
    updated_at: datetime | None = None


class FlowSave(BaseModel):
    graph: FlowGraph


class PublishIn(BaseModel):
    note: str = Field(default="", max_length=255)


class VersionOut(ORM):
    version: int
    note: str
    created_at: datetime


class SessionOut(ORM):
    id: str
    agent_id: str
    flow_version: int
    mode: str
    started_at: datetime
    ended_at: datetime | None
    outcome: str | None
    end_reason: str | None


class EventOut(ORM):
    seq: int
    ts: float
    type: str
    node_id: str | None
    data: dict[str, Any]


class SessionDetail(SessionOut):
    graph: dict[str, Any]
    events: list[EventOut]
    has_recording: bool = False


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class KBUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class KBOut(ORM):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    ready_count: int = 0
    chunk_count: int = 0


class DocumentOut(ORM):
    """An entry: an uploaded file (kind "file") or a question-answer pair (kind "qa")."""

    id: str
    kind: str
    filename: str
    question: str | None = None
    answer: str | None = None
    tags: list[str] = []
    size: int
    status: str
    error: str | None
    chunk_count: int
    edited_chunks: int = 0
    created_at: datetime
    updated_at: datetime | None = None


class KBDetail(KBOut):
    documents: list[DocumentOut]


TagColor = Literal["violet", "indigo", "sky", "teal", "emerald", "amber", "orange", "rose", "slate"]


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    color: TagColor = "violet"


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    color: TagColor | None = None


class TagOut(ORM):
    id: str
    name: str
    description: str
    color: str
    created_at: datetime
    entry_count: int = 0


class QAIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    tags: list[str] = []


class EntryUpdate(BaseModel):
    """question/answer only apply to question-answer entries."""

    tags: list[str] | None = None
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)


class ChunkOut(ORM):
    id: int
    ordinal: int
    page: int | None
    text: str
    edited: bool


class ChunkUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class SearchIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)
    # The caller's tags to try the search as; None searches everything.
    tags: list[str] | None = None


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    persona: str = ""
    goal: str = ""
    success_criteria: str = ""
    expected_outcome: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    max_turns: int = Field(default=12, ge=1, le=40)


class ResultOut(ORM):
    id: str
    run_id: str | None
    scenario_id: str | None
    scenario_name: str
    ordinal: int
    session_id: str | None
    status: str
    outcome: str | None
    end_reason: str | None
    turns: int
    duration: float | None
    verdict: dict[str, Any]
    created_at: datetime


class ScenarioOut(ORM):
    id: str
    agent_id: str
    name: str
    persona: str
    goal: str
    success_criteria: str
    expected_outcome: str | None
    variables: dict[str, Any]
    max_turns: int
    created_at: datetime
    updated_at: datetime
    last_result: ResultOut | None = None


class RunCreate(BaseModel):
    version: int = 0
    scenario_ids: list[str] | None = None  # None: every scenario of the agent


class RunOut(ORM):
    id: str
    agent_id: str
    flow_version: int
    status: str
    created_at: datetime
    finished_at: datetime | None
    total: int = 0
    passed: int = 0
    failed: int = 0
    pending: int = 0


class RunDetail(RunOut):
    results: list[ResultOut]
