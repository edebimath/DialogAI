"""Static checks on a FlowGraph, reported per node/edge so the canvas can highlight them."""

import json
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from app.flows.schema import (
    IDENTIFIER,
    CollectNode,
    ConditionNode,
    EndNode,
    FlowGraph,
    HttpRequestNode,
    KBAnswerNode,
    LLMTaskNode,
    Node,
    RouterNode,
    SayNode,
    StartNode,
    TransferNode,
    exit_handles,
)

# Same placeholder syntax Pipecat Flows renders from state: {{ key }} or {{ key.sub }}.
PLACEHOLDER = re.compile(r"(?<!\\)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)(?:\.[A-Za-z0-9_.]+)?\s*\}\}")

# {{ secret.name }}: a value from the server environment, only for HTTP nodes (never prompts).
SECRET = "secret"

# Nodes the compiler walks through without an LLM turn; a cycle made only of these never ends.
PASSTHROUGH = (StartNode, SayNode, ConditionNode, HttpRequestNode)
TERMINAL = (EndNode, TransferNode)


class Issue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


def _texts(node: Node) -> list[str]:
    match node:
        case SayNode():
            return [node.text]
        case LLMTaskNode() | KBAnswerNode():
            return [node.prompt, *(e.description for e in node.exits)]
        case CollectNode():
            return [node.prompt]
        case RouterNode():
            return [node.prompt, *(r.description for r in node.routes)]
        case EndNode():
            return [node.text or ""]
        case TransferNode():
            return [node.text or "", node.target]
        case HttpRequestNode():
            return [node.url, node.body, *(h.value for h in node.headers)]
    return []


def _content_problems(node: Node) -> list[tuple[str, str]]:
    """Required content the schema leaves to the validator, so drafts always save."""
    problems: list[tuple[str, str]] = []
    match node:
        case SayNode() if not node.text.strip():
            problems.append(("empty_text", "Söylenecek metin boş."))
        case LLMTaskNode():
            if not node.prompt.strip():
                problems.append(("empty_prompt", "Görev talimatı boş."))
            if any(not e.description.strip() for e in node.exits):
                problems.append(("empty_exit", "Her çıkışın ne zaman seçileceği yazılmalı."))
        case RouterNode():
            if not node.routes:
                problems.append(("no_routes", "Yönlendiricide en az bir seçenek olmalı."))
            if any(not r.description.strip() for r in node.routes):
                problems.append(("empty_exit", "Her seçeneğin açıklaması yazılmalı."))
        case CollectNode():
            names = [f.name for f in node.fields]
            if not names:
                problems.append(("no_fields", "Toplanacak en az bir bilgi tanımlanmalı."))
            if any(not re.match(IDENTIFIER, n) for n in names):
                problems.append(("bad_field_name", "Alan adları küçük harf, rakam ve _ içermeli (ör. musteri_no)."))
            if len(names) != len(set(names)):
                problems.append(("duplicate_field", "Aynı alan adı birden fazla kez kullanılmış."))
            if any(not f.description.strip() for f in node.fields):
                problems.append(("empty_field", "Her alanın açıklaması yazılmalı."))
        case KBAnswerNode():
            if not node.kb_ids:
                problems.append(("no_kb", "En az bir bilgi tabanı seçilmeli."))
            if any(not e.description.strip() for e in node.exits):
                problems.append(("empty_exit", "Her çıkışın ne zaman seçileceği yazılmalı."))
        case HttpRequestNode():
            problems.extend(_http_problems(node))
        case ConditionNode():
            if not node.rules:
                problems.append(("no_rules", "Koşulda en az bir kural olmalı."))
            if any(not r.variable.strip() for r in node.rules):
                problems.append(("empty_rule", "Her kuralın bir değişkeni olmalı."))
    return problems


def _http_problems(node: HttpRequestNode) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    url = node.url.strip()
    if not url:
        problems.append(("empty_url", "İstek adresi (URL) boş."))
    elif not url.startswith("{{") and not re.match(r"^https?://", url):
        problems.append(("bad_url", "Adres http:// veya https:// ile başlamalı."))
    if node.body.strip():
        if node.method == "GET":
            problems.append(("body_on_get", "GET isteğinde gövde gönderilmez; yöntemi POST yapın veya gövdeyi silin."))
        # Placeholders may stand for numbers or sit inside strings; 0 is valid JSON either way.
        elif not _is_json(PLACEHOLDER.sub("0", node.body)):
            problems.append(("bad_body", "Gövde geçerli bir JSON değil."))
    if any(not h.name.strip() for h in node.headers):
        problems.append(("empty_header", "Her başlığın bir adı olmalı."))
    names = [o.variable for o in node.outputs]
    if any(not re.match(IDENTIFIER, n) for n in names):
        problems.append(("bad_output_name", "Değişken adları küçük harf, rakam ve _ içermeli (ör. kargo_durumu)."))
    if len(names) != len(set(names)):
        problems.append(("duplicate_output", "Aynı değişkene birden fazla değer yazılıyor."))
    if any(not o.path.strip() for o in node.outputs):
        problems.append(("empty_output_path", "Her değişken için cevaptaki alanın yolu yazılmalı."))
    return problems


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def output_variables(graph: FlowGraph) -> set[str]:
    """Every name a node writes into state: collect fields and HTTP outputs."""
    names = {f.name for n in graph.nodes if isinstance(n, CollectNode) for f in n.fields}
    names |= {o.variable for n in graph.nodes if isinstance(n, HttpRequestNode) for o in n.outputs}
    return names


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def validate(
    graph: FlowGraph, known_kb_ids: set[str] | None = None, tagged_kb_ids: set[str] | None = None
) -> list[Issue]:
    """known_kb_ids: existing knowledge bases; when given, references to deleted ones are errors.
    tagged_kb_ids: knowledge bases with tagged entries; using one without caller tags is a warning."""
    issues: list[Issue] = []

    def err(code, message, node_id=None, edge_id=None):
        issues.append(Issue(severity="error", code=code, message=message, node_id=node_id, edge_id=edge_id))

    def warn(code, message, node_id=None, edge_id=None):
        issues.append(Issue(severity="warning", code=code, message=message, node_id=node_id, edge_id=edge_id))

    nodes: dict[str, Node] = {}
    for node in graph.nodes:
        if node.id in nodes:
            err("duplicate_node", f"'{node.id}' kimliği birden fazla düğümde kullanılmış.", node.id)
        nodes[node.id] = node

    starts = [n for n in graph.nodes if isinstance(n, StartNode)]
    if not starts:
        err("no_start", "Akışta bir Başlangıç düğümü olmalı.")
    elif len(starts) > 1:
        for n in starts[1:]:
            err("multiple_start", "Akışta yalnızca bir Başlangıç düğümü olabilir.", n.id)

    for node in graph.nodes:
        ids = [h for h in exit_handles(node)]
        if len(ids) != len(set(ids)):
            err("duplicate_exit", "Bu düğümde aynı kimliğe sahip birden fazla çıkış var.", node.id)
        for code, message in _content_problems(node):
            err(code, message, node.id)
        if isinstance(node, (LLMTaskNode, KBAnswerNode)) and not node.exits:
            warn("no_exit", "Bu adımın çıkışı yok; konuşma bu adımda kalır.", node.id)
        if known_kb_ids is not None and isinstance(node, KBAnswerNode):
            if set(node.kb_ids) - known_kb_ids:
                err("missing_kb", "Seçilen bilgi tabanlarından biri silinmiş.", node.id)

    if known_kb_ids is not None and set(graph.global_.kb_ids) - known_kb_ids:
        err("missing_kb", "Genel ayarlarda seçilen bilgi tabanlarından biri silinmiş.")

    used_kbs = set(graph.global_.kb_ids)
    used_kbs |= {k for n in graph.nodes if isinstance(n, KBAnswerNode) for k in n.kb_ids}
    if tagged_kb_ids and used_kbs & tagged_kb_ids and not graph.global_.caller_tags.strip():
        warn(
            "no_caller_tags",
            "Kullanılan bilgi tabanlarında etiketli girdiler var ama Genel ayarlarda 'Arayan "
            "etiketleri' boş; etiketli girdiler de her arayana gösterilir.",
        )

    for v in graph.variables:
        if not re.match(IDENTIFIER, v.name):
            err("bad_variable_name", f"Geçersiz değişken adı: '{v.name}' (küçük harf, rakam, _).")
    if SECRET in output_variables(graph) | {v.name for v in graph.variables}:
        err("reserved_name", f"'{SECRET}' adı gizli değerler için ayrılmış; başka bir değişken adı seçin.")

    # Edges
    outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
    adjacency: dict[str, list[str]] = defaultdict(list)
    seen_edges: set[str] = set()
    for edge in graph.edges:
        if edge.id in seen_edges:
            err("duplicate_edge", f"'{edge.id}' kimliği birden fazla bağlantıda kullanılmış.", edge_id=edge.id)
        seen_edges.add(edge.id)
        source, target = nodes.get(edge.source), nodes.get(edge.target)
        if source is None or target is None:
            err("dangling_edge", "Bağlantı var olmayan bir düğüme işaret ediyor.", edge_id=edge.id)
            continue
        if edge.source_handle not in exit_handles(source):
            err("bad_handle", "Bağlantı düğümün var olmayan bir çıkışından çıkıyor.", source.id, edge.id)
            continue
        if isinstance(target, StartNode):
            err("edge_into_start", "Başlangıç düğümüne bağlantı yapılamaz.", target.id, edge.id)
        outgoing[(edge.source, edge.source_handle)].append(edge.id)
        adjacency[edge.source].append(edge.target)

    for node in graph.nodes:
        for handle in exit_handles(node):
            edges = outgoing.get((node.id, handle), [])
            if len(edges) > 1:
                for edge_id in edges[1:]:
                    err("multiple_edges", "Bir çıkıştan yalnızca bir bağlantı çıkabilir.", node.id, edge_id)
            elif not edges:
                err("unconnected_exit", f"'{handle}' çıkışı bir düğüme bağlanmamış.", node.id)

    # Reachability
    if len(starts) == 1:
        reachable: set[str] = set()
        stack = [starts[0].id]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(adjacency.get(current, []))
        for node in graph.nodes:
            if node.id not in reachable:
                warn("unreachable", "Bu düğüme Başlangıç'tan ulaşılamıyor.", node.id)
        if not any(isinstance(nodes[n], TERMINAL) for n in reachable if n in nodes):
            warn("no_end", "Başlangıç'tan ulaşılabilen bir Bitiş veya Temsilciye Aktar düğümü yok.")

    # A loop made only of say/condition nodes would spin forever without waiting for the caller.
    passthrough = {n.id for n in graph.nodes if isinstance(n, PASSTHROUGH)}
    color: dict[str, int] = {}

    def has_cycle(node_id: str) -> bool:
        color[node_id] = 1
        for nxt in adjacency.get(node_id, []):
            if nxt not in passthrough:
                continue
            if color.get(nxt) == 1 or (color.get(nxt) is None and has_cycle(nxt)):
                return True
        color[node_id] = 2
        return False

    for node_id in passthrough:
        if color.get(node_id) is None and has_cycle(node_id):
            err("passthrough_loop", "Bu düğüm, arayanı hiç beklemeyen sonsuz bir döngünün parçası.", node_id)
            break

    # Placeholders must name something that can be in state by then.
    known = {v.name for v in graph.variables} | output_variables(graph)
    secret_rule = "Gizli değerler ({{ secret.ad }}) yalnızca HTTP Aracı'nın adres, başlık ve gövdesinde kullanılabilir."
    global_texts = (graph.global_.persona, graph.global_.rules, graph.global_.caller_tags)
    for name in set().union(*(placeholders(t) for t in global_texts)):
        if name == SECRET:
            err("secret_outside_http", secret_rule)
        elif name not in known:
            err("unknown_variable", f"Global ayarlarda tanımsız değişken: {{{{ {name} }}}}")
    for node in graph.nodes:
        for text in _texts(node):
            names = placeholders(text)
            if SECRET in names and not isinstance(node, HttpRequestNode):
                err("secret_outside_http", secret_rule, node.id)
            for name in names - known - {SECRET}:
                err("unknown_variable", f"Tanımsız değişken: {{{{ {name} }}}}", node.id)
        if isinstance(node, ConditionNode):
            for rule in node.rules:
                if rule.variable not in known:
                    warn("unknown_variable", f"Koşul tanımsız bir değişkene bakıyor: {rule.variable}", node.id)

    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
