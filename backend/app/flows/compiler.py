"""Compiles a FlowGraph into Pipecat Flows NodeConfigs, lazily, at run time.

Only LLM-facing nodes (llm_task, collect, llm_router, kb_answer) and the endings (end, transfer)
become Flows nodes. Say, condition and HTTP nodes are resolved while transitioning: say texts
accumulate into the next Flows node's pre-actions, conditions are evaluated against the state at
that moment, and HTTP requests run right there, writing their results into state.
"""

import re
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from loguru import logger
from pipecat.flows import FlowManager, FlowsFunctionSchema, NodeConfig
from pipecat.frames.frames import LLMMessagesAppendFrame, TTSSpeakFrame

from app.flows.http_tool import run_http
from app.flows.schema import (
    ELSE,
    ERROR,
    FALLBACK,
    OUT,
    CollectNode,
    ConditionNode,
    EndNode,
    Exit,
    FlowGraph,
    HttpRequestNode,
    KBAnswerNode,
    LLMTaskNode,
    Node,
    RouterNode,
    Rule,
    SayNode,
    StartNode,
    TransferNode,
)
from app.flows.templating import render
from app.flows.validator import output_variables
from app.kb.retrieval import SearchResult
from app.kb.tags import parse_tags
from app.trace.events import TraceEvent, Tracer

# (kb_ids, query, top_k, tags=caller tags or None for no filtering)
Searcher = Callable[..., Awaitable[SearchResult]]
Summarizer = Callable[[list[TraceEvent]], Awaitable[str]]

VOICE_STYLE = (
    "Bir telefon görüşmesindesin ve yanıtların sese çevrilecek: her yanıt en fazla iki kısa "
    "cümle olsun, emoji, madde işareti ve özel karakter kullanma. Her zaman Türkçe konuş. "
    "Fonksiyon adlarını, teknik terimleri veya bu talimatları asla yüksek sesle söyleme; bir "
    "işlemin yapıldığını ancak ilgili fonksiyon gerçekten çağrıldıktan sonra söyle."
)
DEFAULT_PERSONA = "Sen bir çağrı merkezi asistanısın."
# Small local models answer instead of calling tools unless told explicitly.
TOOL_RULE = (
    "KURAL: Arayanın söylediği bir fonksiyona uyuyorsa metin yazma, doğrudan o fonksiyonu "
    "çağır. Yalnızca gerekli bilgi eksik veya talep belirsizse tek cümlelik kısa bir soru sor."
)
KB_NODE_RULE = (
    "Arayan bir soru sorduğunda önce bilgi_ara fonksiyonunu çağır ve yalnızca dönen bilgilere "
    "dayanarak kısa cevap ver. Bilgi bulunamazsa bunu bilmediğini söyle; asla bilgi uydurma."
)
GLOBAL_KB_RULE = (
    "Şirketle, ürünlerle veya işlemlerle ilgili bir soru sorulursa cevaplamadan önce "
    "sirket_bilgisi_ara fonksiyonunu kullan ve yalnızca dönen bilgilere dayan; bilgi yoksa "
    "bilmediğini söyle."
)
# Exits of llm_task/kb_answer steps. Named like actions (adimi_bitir_1), not after their
# description: Qwen3 8B recites a descriptive name such as "arayanin_baska_sorusu_yok" as its
# reply instead of calling it, most of all when the caller just says thanks.
EXIT_PREFIX = "adimi_bitir"
EXIT_RULE = (
    "Bu adımı bitirmek için uygun durumda aşağıdaki fonksiyonlardan birini çağır. Fonksiyonu "
    "çağırdığında arayana ne söyleneceğini sistem belirler; sen ayrıca bir şey söyleme:"
)
NOT_FOUND = "Bu konuda bilgi tabanında bilgi bulunamadı."
TRANSFER_TEXT = "Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın."
GLOBAL_TOP_K = 4
MAX_PASSTHROUGH_STEPS = 100
JSON_TYPES = {"string": "string", "number": "number", "boolean": "boolean"}


class FlowCompileError(Exception):
    pass


def function_name(description: str, taken: set[str], fallback: str) -> str:
    """A readable tool name the LLM can reason about, e.g. 'fatura_sorusu'."""
    folded = unicodedata.normalize("NFKD", description.replace("ı", "i").replace("İ", "I"))
    ascii_text = folded.encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", ascii_text)[:5]
    name = "_".join(words)[:40].strip("_") or fallback
    if not name[0].isalpha():
        name = f"f_{name}"
    base, n = name, 2
    while name in taken:
        name, n = f"{base}_{n}", n + 1
    taken.add(name)
    return name


def rule_matches(rule: Rule, state: dict[str, Any]) -> bool:
    value = state.get(rule.variable)
    present = value not in (None, "")
    if rule.operator == "exists":
        return present
    if rule.operator == "not_exists":
        return not present
    actual, expected = str(value or "").strip().casefold(), rule.value.strip().casefold()
    match rule.operator:
        case "eq":
            return actual == expected
        case "neq":
            return actual != expected
        case "contains":
            return expected in actual
        case "gt" | "lt":
            try:
                a, b = float(actual.replace(",", ".")), float(expected.replace(",", "."))
            except ValueError:
                return False
            return a > b if rule.operator == "gt" else a < b
    return False


class FlowCompiler:
    def __init__(
        self,
        graph: FlowGraph,
        tracer: Tracer,
        *,
        speak: bool = False,
        searcher: Searcher | None = None,
        summarizer: Summarizer | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ):
        """
        Args:
            graph: A graph that passed validation.
            tracer: Receives node, variable, condition, knowledge-base and HTTP events.
            speak: Voice mode: say-texts are synthesized. In text mode they only enter context.
            searcher: Knowledge-base search; defaults to pgvector retrieval.
            summarizer: Writes the handoff note on transfer; defaults to the local LLM.
            http_transport: For tests; HTTP nodes use the network otherwise.
        """
        self.graph = graph
        self.tracer = tracer
        self.speak = speak
        if searcher is None:
            from app.kb.retrieval import search as searcher
        self.searcher = searcher
        if summarizer is None:
            from app.runtime.handoff import summarize as summarizer
        self.summarizer = summarizer
        self.http_transport = http_transport
        self.nodes: dict[str, Node] = {n.id: n for n in graph.nodes}
        self.next: dict[tuple[str, str], str] = {
            (e.source, e.source_handle): e.target for e in graph.edges
        }
        start = [n for n in graph.nodes if isinstance(n, StartNode)]
        if len(start) != 1:
            raise FlowCompileError("Akışta tam olarak bir Başlangıç düğümü olmalı.")
        self.start_id = start[0].id

        persona = graph.global_.persona.strip() or DEFAULT_PERSONA
        parts = [persona, VOICE_STYLE]
        if graph.global_.rules.strip():
            parts.append(graph.global_.rules.strip())
        if graph.global_.kb_ids:
            parts.append(GLOBAL_KB_RULE)
        self.role_message = "\n\n".join(parts)

    def initial_state(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Every name a prompt can reference exists from the start, so rendering never fails."""
        state: dict[str, Any] = {name: "" for name in output_variables(self.graph)}
        for v in self.graph.variables:
            state[v.name] = v.default if v.default is not None else ""
        state.update(overrides or {})
        return state

    async def initial_node(self, state: dict[str, Any]) -> NodeConfig:
        return await self.resolve(self.start_id, state)

    def global_functions(self) -> list[FlowsFunctionSchema]:
        """Tools available at every step: knowledge-base search when global KBs are set."""
        if not self.graph.global_.kb_ids:
            return []
        return [
            self._kb_function(
                "sirket_bilgisi_ara",
                "Şirket bilgi tabanında arama yap.",
                self.graph.global_.kb_ids,
                GLOBAL_TOP_K,
                node_id=None,
            )
        ]

    def caller_tags(self, state: dict[str, Any]) -> list[str] | None:
        """The caller's tags right now; None when the flow doesn't filter by tags."""
        template = self.graph.global_.caller_tags.strip()
        return parse_tags(render(template, state)) if template else None

    # --- Resolution ------------------------------------------------------------------

    async def resolve(self, node_id: str, state: dict[str, Any]) -> NodeConfig:
        """Walk through pass-through nodes from node_id to the next Flows node."""
        says: list[dict] = []
        for _ in range(MAX_PASSTHROUGH_STEPS):
            node = self.nodes[node_id]
            await self.tracer.emit("node_entered", node.id, node_type=node.type, label=node.label)
            match node:
                case StartNode():
                    node_id = self._target(node.id, OUT)
                case SayNode():
                    says.append(self._say_action(node))
                    node_id = self._target(node.id, OUT)
                case ConditionNode():
                    handle = next((r.id for r in node.rules if rule_matches(r, state)), ELSE)
                    await self.tracer.emit(
                        "condition_evaluated",
                        node.id,
                        matched=handle,
                        values={r.variable: state.get(r.variable) for r in node.rules},
                    )
                    node_id = self._target(node.id, handle)
                case HttpRequestNode():
                    result = await run_http(node, state, self.http_transport)
                    state.update(result.values)
                    await self.tracer.emit("http_request", node.id, **result.trace())
                    node_id = self._target(node.id, OUT if result.ok else ERROR)
                case LLMTaskNode():
                    return self._task_node(node, says)
                case RouterNode():
                    return self._router_node(node, says)
                case CollectNode():
                    return self._collect_node(node, says)
                case KBAnswerNode():
                    return self._kb_node(node, says)
                case EndNode():
                    return self._end_node(node, says)
                case TransferNode():
                    return self._transfer_node(node, says)
        raise FlowCompileError("Söylem/Koşul/HTTP düğümlerinde sonsuz döngü.")

    def _target(self, node_id: str, handle: str) -> str:
        try:
            return self.next[(node_id, handle)]
        except KeyError:
            raise FlowCompileError(f"'{node_id}' düğümünün '{handle}' çıkışı bağlı değil.") from None

    # --- Flows nodes -----------------------------------------------------------------

    def _node(self, node: Node, task: str, *, functions=None, pre_actions=None, **extra) -> NodeConfig:
        # A say node on the way in already took the bot's turn, so wait for the caller.
        extra.setdefault("respond_immediately", not pre_actions)
        config = NodeConfig(
            name=node.id,
            role_message=self.role_message,
            # "system", not "developer": OpenAI-compatible services without the developer role
            # (Ollama) have Pipecat rewrite it to "user", and the model then answers its own task.
            task_messages=[{"role": "system", "content": task}] if task else [],
            **extra,
        )
        if functions:
            config["functions"] = functions
        if pre_actions:
            config["pre_actions"] = pre_actions
        return config

    def _exit_functions(
        self, node: Node, exits: list[Exit], *, numbered: bool = False
    ) -> list[FlowsFunctionSchema]:
        """numbered: names like adimi_bitir_1 (step exits); otherwise named after the description
        (router routes, where the name helps the model classify)."""
        taken: set[str] = set()
        functions = []
        for i, exit_ in enumerate(exits, start=1):
            if numbered:
                name = f"{EXIT_PREFIX}_{i}"
            else:
                name = function_name(exit_.description, taken, fallback=f"secenek_{i}")
            functions.append(
                FlowsFunctionSchema(
                    name=name,
                    description=exit_.description,
                    properties={},
                    required=[],
                    handler=self._traced(
                        node.id,
                        name,
                        self._transition_handler(node.id, exit_.id),
                        label=exit_.description,
                    ),
                )
            )
        return functions

    @staticmethod
    def _exit_rule(functions: list[FlowsFunctionSchema]) -> str:
        options = "\n".join(f"- {f.name}: {f.description}" for f in functions)
        return f"\n\n{EXIT_RULE}\n{options}"

    def _transition_handler(self, node_id: str, handle: str):
        async def handler(args: dict, flow_manager: FlowManager):
            return None, await self.resolve(self._target(node_id, handle), flow_manager.state)

        return handler

    def _traced(self, node_id: str, name: str, handler, *, label: str | None = None):
        """Emit the call before the handler transitions, so it is attributed to its own node.

        label: what the call means, for the timeline (exit names alone say little).
        """

        async def wrapper(args: dict, flow_manager: FlowManager):
            extra = {"label": label} if label else {}
            await self.tracer.emit("function_call", node_id, name=name, args=dict(args), **extra)
            return await handler(args, flow_manager)

        return wrapper

    def _task_node(self, node: LLMTaskNode, says: list[dict]) -> NodeConfig:
        functions = self._exit_functions(node, node.exits, numbered=True)
        task = node.prompt
        if functions:
            task += self._exit_rule(functions) + f"\n\n{TOOL_RULE}"
        return self._node(node, task, functions=functions, pre_actions=says)

    def _router_node(self, node: RouterNode, says: list[dict]) -> NodeConfig:
        functions = self._exit_functions(node, node.routes)
        options = "\n".join(f"- {f.name}: {f.description}" for f in functions)
        task = (
            (node.prompt.strip() or "Arayanın ne istediğini anla.")
            + f"\n\nTalep aşağıdakilerden birine uyduğunda ilgili fonksiyonu çağır:\n{options}"
            + f"\n\n{TOOL_RULE}"
        )
        return self._node(node, task, functions=functions, pre_actions=says)

    def _collect_node(self, node: CollectNode, says: list[dict]) -> NodeConfig:
        properties = {
            f.name: {"type": JSON_TYPES[f.type], "description": f.description} for f in node.fields
        }
        required = [f.name for f in node.fields if f.required]
        target = self._target(node.id, OUT)

        async def handler(args: dict, flow_manager: FlowManager):
            values = {k: v for k, v in args.items() if k in properties}
            flow_manager.state.update(values)
            await self.tracer.emit("variables_set", node.id, values=values)
            return {"kaydedildi": values}, await self.resolve(target, flow_manager.state)

        functions = [
            FlowsFunctionSchema(
                name="bilgileri_kaydet",
                description="Arayandan alınan bilgileri kaydet.",
                properties=properties,
                required=required,
                handler=self._traced(node.id, "bilgileri_kaydet", handler),
            )
        ]
        fallback_rule = ""
        if node.fallback:
            functions.append(
                FlowsFunctionSchema(
                    name="bilgi_verilemiyor",
                    description="Arayan istenen bilgiyi bilmiyor, bulamıyor veya vermek istemiyor.",
                    properties={},
                    required=[],
                    handler=self._traced(
                        node.id, "bilgi_verilemiyor", self._transition_handler(node.id, FALLBACK)
                    ),
                )
            )
            fallback_rule = (
                "Arayan bilgiyi bilmediğini, bulamadığını veya vermek istemediğini söylerse ısrar "
                "etme, bilgi_verilemiyor fonksiyonunu çağır.\n\n"
            )

        wanted = "\n".join(f"- {f.name}: {f.description}" for f in node.fields)
        task = (
            (node.prompt.strip() or "Arayandan aşağıdaki bilgileri al.")
            + f"\n\nAlınacak bilgiler:\n{wanted}\n\nArayan bu bilgileri konuşmada zaten "
            "söylediyse tekrar sorma, hemen bilgileri_kaydet fonksiyonunu çağır. Eksik bilgi "
            "varsa yalnızca onu iste.\n\n" + fallback_rule + TOOL_RULE
        )
        return self._node(node, task, functions=functions, pre_actions=says)

    def _kb_node(self, node: KBAnswerNode, says: list[dict]) -> NodeConfig:
        search = self._kb_function(
            "bilgi_ara", "Bilgi tabanında arama yap.", node.kb_ids, node.top_k, node_id=node.id
        )
        exits = self._exit_functions(node, node.exits, numbered=True)
        task = node.prompt.strip() or "Arayanın sorularını bilgi tabanına dayanarak cevapla."
        task += f"\n\n{KB_NODE_RULE}"
        if exits:
            task += self._exit_rule(exits)
        task += f"\n\n{TOOL_RULE}"
        return self._node(node, task, functions=[search, *exits], pre_actions=says)

    def _kb_function(
        self, name: str, description: str, kb_ids: list[str], top_k: int, *, node_id: str | None
    ) -> FlowsFunctionSchema:
        async def handler(args: dict, flow_manager: FlowManager):
            query = str(args.get("soru", "")).strip()
            await self.tracer.emit("function_call", node_id, name=name, args={"soru": query})
            tags = self.caller_tags(flow_manager.state)
            result = await self.searcher(kb_ids, query, top_k, tags=tags)
            await self.tracer.emit(
                "kb_search",
                node_id,
                query=query,
                kb_ids=kb_ids,
                tags=tags,
                ms=result.ms,
                hits=[
                    {"document": h.document, "page": h.page, "score": h.score, "text": h.text[:400]}
                    for h in result.hits
                ],
            )
            if not result.hits:
                return {"sonuc": NOT_FOUND}, None
            found = [
                {"kaynak": h.document + (f", sayfa {h.page}" if h.page else ""), "metin": h.text}
                for h in result.hits
            ]
            # None: stay on this step and let the LLM answer with what was found.
            return {"bulunan_bilgiler": found}, None

        return FlowsFunctionSchema(
            name=name,
            description=description,
            properties={
                "soru": {
                    "type": "string",
                    "description": "Aranacak soru; arayanın sorusunun kısa ve açık hali.",
                }
            },
            required=["soru"],
            handler=handler,
        )

    def _end_node(self, node: EndNode, says: list[dict]) -> NodeConfig:
        self.tracer.outcome = node.outcome
        end = {"type": "end_conversation"}
        if node.text:
            return self._node(
                node,
                "",
                pre_actions=[*says, self._say_action(node, node.text), end],
                respond_immediately=False,
            )
        config = self._node(
            node,
            "Görüşmeyi kısaca toparla ve kibarca vedalaş.",
            pre_actions=says,
        )
        config["post_actions"] = [end]
        return config

    def _transfer_node(self, node: TransferNode, says: list[dict]) -> NodeConfig:
        self.tracer.outcome = "transferred"
        transfer = {
            "type": "transfer",
            "handler": self._transfer,
            "node_id": node.id,
            "target": node.target,
            "summary": node.summary,
        }
        return self._node(
            node,
            "",
            pre_actions=[
                *says,
                self._say_action(node, node.text or TRANSFER_TEXT),
                transfer,
                {"type": "end_conversation"},
            ],
            respond_immediately=False,
        )

    async def _transfer(self, action: dict, flow_manager: FlowManager) -> None:
        """What the human agent receives: where the call goes, what was collected, a summary.

        Runs after the goodbye text is queued, so in voice mode it overlaps with the speech.
        """
        state = flow_manager.state
        # Flow variables still at their default are configuration (company name, API address),
        # not something learned on the call.
        defaults = {v.name: v.default for v in self.graph.variables}
        data: dict[str, Any] = {
            "target": render(action["target"], state),
            "variables": {
                k: v
                for k, v in state.items()
                if v not in (None, "") and not (k in defaults and v == defaults[k])
            },
            "summary": None,
        }
        if action["summary"]:
            try:
                data["summary"] = await self.summarizer(self.tracer.events)
            except Exception as e:  # the call still transfers without a note
                logger.warning(f"Handoff summary failed: {e}")
                data["summary_error"] = "Özet hazırlanamadı."
        await self.tracer.emit("transfer", action["node_id"], **data)

    # --- Say action --------------------------------------------------------------------

    def _say_action(self, node: Node, text: str | None = None) -> dict:
        return {
            "type": "say",
            "handler": self._say,
            "text": text if text is not None else node.text,
            "node_id": node.id,
        }

    async def _say(self, action: dict, flow_manager: FlowManager) -> None:
        """Speak (voice mode) and put fixed text into context as the assistant's words.

        Pipecat's own tts_say only reaches the context through a TTS service, which the text
        mode doesn't have, so the context append is done here for both modes.
        """
        text = render(action["text"], flow_manager.state)
        await self.tracer.emit("say", action["node_id"], text=text)
        if self.speak:
            await flow_manager.worker.queue_frame(TTSSpeakFrame(text=text, append_to_context=False))
        await flow_manager.worker.queue_frame(
            LLMMessagesAppendFrame(messages=[{"role": "assistant", "content": text}], run_llm=False)
        )
