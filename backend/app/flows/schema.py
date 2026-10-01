"""Canvas flow schema: the versioned JSON contract between the editor and the runtime.

The editor saves a FlowGraph; the compiler turns it into Pipecat Flows NodeConfigs at run time.
Handles: nodes with a single exit use the "out" handle; branching nodes use the id of the exit
(route, rule, or task exit), condition nodes also have an "else" handle, and HTTP nodes have
"out" and "error".
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1
OUT = "out"
ELSE = "else"
FALLBACK = "fallback"
ERROR = "error"

# Names referenced from prompts as {{ name }}; checked by the validator, not here, so a
# half-edited draft can still be saved.
IDENTIFIER = r"^[a-z_][a-z0-9_]*$"


class Position(BaseModel):
    x: float = 0
    y: float = 0


class _NodeBase(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str | None = None
    position: Position = Field(default_factory=Position)


class Exit(BaseModel):
    """A branch an LLM node can take; the description tells the LLM when to take it."""

    id: str = Field(min_length=1, max_length=64)
    description: str = ""


class StartNode(_NodeBase):
    type: Literal["start"] = "start"


class SayNode(_NodeBase):
    """Speaks fixed text, then moves on without an LLM turn."""

    type: Literal["say"] = "say"
    text: str = ""


class LLMTaskNode(_NodeBase):
    """Free-form LLM step; leaves through one of its exits when the LLM decides it's done."""

    type: Literal["llm_task"] = "llm_task"
    prompt: str = ""
    exits: list[Exit] = Field(default_factory=list)


class CollectField(BaseModel):
    name: str
    description: str = ""
    type: Literal["string", "number", "boolean"] = "string"
    required: bool = True


class CollectNode(_NodeBase):
    """Collects variables from the caller, stores them in state, then moves on."""

    type: Literal["collect"] = "collect"
    prompt: str = ""
    fields: list[CollectField] = Field(default_factory=list)
    # Adds a FALLBACK exit for callers who can't or won't give the information.
    fallback: bool = False


class RouterNode(_NodeBase):
    """LLM classifies the caller's intent into one of its routes."""

    type: Literal["llm_router"] = "llm_router"
    prompt: str = ""
    routes: list[Exit] = Field(default_factory=list)


Operator = Literal["eq", "neq", "contains", "gt", "lt", "exists", "not_exists"]


class Rule(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    variable: str = ""
    operator: Operator = "eq"
    value: str = ""


class ConditionNode(_NodeBase):
    """Deterministic branch on state; first matching rule wins, otherwise "else"."""

    type: Literal["condition"] = "condition"
    rules: list[Rule] = Field(default_factory=list)


class KBAnswerNode(_NodeBase):
    """Answers the caller's questions from knowledge bases; leaves through an exit when done."""

    type: Literal["kb_answer"] = "kb_answer"
    prompt: str = ""
    kb_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=4, ge=1, le=10)
    exits: list[Exit] = Field(default_factory=list)


class Header(BaseModel):
    name: str = ""
    value: str = ""


class HttpOutput(BaseModel):
    """Stores one value of the JSON response in a variable; path is dotted, e.g. "data.slots.0"."""

    variable: str = ""
    path: str = ""


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class HttpRequestNode(_NodeBase):
    """Calls an external API without an LLM turn; leaves through "out" or, on failure, "error"."""

    type: Literal["http_request"] = "http_request"
    method: HttpMethod = "GET"
    url: str = ""
    headers: list[Header] = Field(default_factory=list)
    # JSON text; placeholders are filled with JSON-escaped values.
    body: str = ""
    timeout: float = Field(default=10, ge=1, le=30)
    outputs: list[HttpOutput] = Field(default_factory=list)


class TransferNode(_NodeBase):
    """Ends the call by handing it to a human; optionally writes a handoff summary for them."""

    type: Literal["transfer"] = "transfer"
    target: str = ""
    text: str | None = None
    summary: bool = True


class EndNode(_NodeBase):
    """Ends the call. With text, says it verbatim; without, the LLM says goodbye."""

    type: Literal["end"] = "end"
    text: str | None = None
    outcome: str = "completed"


Node = Annotated[
    StartNode
    | SayNode
    | LLMTaskNode
    | CollectNode
    | RouterNode
    | ConditionNode
    | KBAnswerNode
    | HttpRequestNode
    | TransferNode
    | EndNode,
    Field(discriminator="type"),
]


class Edge(BaseModel):
    id: str = Field(min_length=1)
    source: str
    target: str
    source_handle: str = OUT


class Variable(BaseModel):
    name: str
    description: str = ""
    default: str | None = None


class GlobalSettings(BaseModel):
    persona: str = ""
    rules: str = ""
    # Searchable from every step through a global tool.
    kb_ids: list[str] = Field(default_factory=list)
    # The caller's tags for knowledge-base searches, comma-separated, usually a variable filled
    # by a caller lookup ("{{ musteri_tipi }}"). Empty = no filtering: every entry is used.
    caller_tags: str = ""


class FlowGraph(BaseModel):
    schema_version: int = SCHEMA_VERSION
    global_: GlobalSettings = Field(default_factory=GlobalSettings, alias="global")
    variables: list[Variable] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


def exit_handles(node: Node) -> list[str]:
    """The source handles a node exposes, in display order."""
    match node:
        case CollectNode():
            return [OUT, FALLBACK] if node.fallback else [OUT]
        case StartNode() | SayNode():
            return [OUT]
        case HttpRequestNode():
            return [OUT, ERROR]
        case LLMTaskNode() | KBAnswerNode():
            return [e.id for e in node.exits]
        case RouterNode():
            return [r.id for r in node.routes]
        case ConditionNode():
            return [r.id for r in node.rules] + [ELSE]
        case EndNode() | TransferNode():
            return []
    return []
