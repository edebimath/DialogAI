from app.flows.compiler import FlowCompiler, function_name, render, rule_matches
from app.flows.schema import FlowGraph, Rule
from app.flows.templates import ARIZA_FATURA, template_graph
from app.flows.validator import has_errors, validate
from app.trace.events import Tracer


def graph(**changes) -> FlowGraph:
    data = {**ARIZA_FATURA, **changes}
    return FlowGraph.model_validate(data)


def codes(g: FlowGraph) -> set[str]:
    return {i.code for i in validate(g)}


def test_template_is_valid():
    issues = validate(template_graph("ariza_fatura"))
    assert not issues, issues


def test_blank_template_cannot_run_until_start_is_connected():
    issues = validate(template_graph("blank"))
    assert has_errors(issues)
    assert {i.code for i in issues if i.severity == "error"} == {"unconnected_exit"}


def test_unconnected_exit_and_unknown_variable():
    g = graph(edges=[e for e in ARIZA_FATURA["edges"] if e["id"] != "e4"])
    assert "unconnected_exit" in codes(g)
    nodes = [dict(n) for n in ARIZA_FATURA["nodes"]]
    nodes[1] = {**nodes[1], "text": "Merhaba {{ bilinmeyen }}"}
    assert "unknown_variable" in codes(graph(nodes=nodes))


def test_passthrough_loop_detected():
    g = FlowGraph.model_validate(
        {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "a", "type": "say", "text": "a"},
                {"id": "b", "type": "say", "text": "b"},
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "a"},
                {"id": "2", "source": "a", "target": "b"},
                {"id": "3", "source": "b", "target": "a"},
            ],
        }
    )
    assert "passthrough_loop" in codes(g)


def test_function_names_are_readable_and_unique():
    taken: set[str] = set()
    assert function_name("Fatura, ücret veya ödeme sorusu", taken, "x") == "fatura_ucret_veya_odeme_sorusu"
    assert function_name("İnternet arızası", taken, "x") == "internet_arizasi"
    assert function_name("İnternet arızası", taken, "x") == "internet_arizasi_2"
    assert function_name("!!!", taken, "secenek_1") == "secenek_1"


def test_render_and_rules():
    assert render("No: {{ musteri_no }}.", {"musteri_no": "42"}) == "No: 42."
    assert render("{{ yok }}", {}) == ""
    state = {"musteri_no": "452618", "tutar": "129,5"}
    assert rule_matches(Rule(id="r", variable="musteri_no", operator="exists"), state)
    assert rule_matches(Rule(id="r", variable="tutar", operator="gt", value="100"), state)
    assert not rule_matches(Rule(id="r", variable="bos", operator="exists"), {"bos": ""})


async def test_resolve_walks_say_into_router_and_condition_into_end():
    tracer = Tracer()
    compiler = FlowCompiler(template_graph("ariza_fatura"), tracer)
    state = compiler.initial_state()

    first = await compiler.initial_node(state)
    assert first["name"] == "yonlendir"
    assert [a["type"] for a in first["pre_actions"]] == ["say"]
    assert {f.name for f in first["functions"]} == {
        "fatura_ucret_veya_odeme_sorusu",
        "internet_modem_veya_hat_arizasi",
    }
    assert "Örnek Telekom" not in first["role_message"]  # Flows renders placeholders itself

    state["musteri_no"] = ""
    assert (await compiler.resolve("numara_var_mi", state))["name"] == "temsilci"
    state["musteri_no"] = "452618"
    end = await compiler.resolve("numara_var_mi", state)
    assert end["name"] == "kayit_acildi"
    assert [a["type"] for a in end["pre_actions"]] == ["say", "end_conversation"]
    assert tracer.outcome == "ticket_created"
    entered = [e.node_id for e in tracer.events if e.type == "node_entered"]
    assert entered[:3] == ["start", "karsilama", "yonlendir"]


def test_empty_content_is_a_validation_error_not_a_schema_error():
    g = FlowGraph.model_validate(
        {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "a", "type": "say"},
                {"id": "c", "type": "collect", "fields": [{"name": "Müşteri No"}]},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "a"},
                {"id": "2", "source": "a", "target": "c"},
                {"id": "3", "source": "c", "target": "e"},
            ],
        }
    )
    assert {"empty_text", "bad_field_name", "empty_field"} <= codes(g)


def test_spoken_text_filter_strips_emoji():
    from app.runtime.filters import speakable

    assert speakable("Tamam! 📡🔧 Kaydettim 😊.") == "Tamam!  Kaydettim ."
    assert speakable("Müşteri no: 452-618 ✓") == "Müşteri no: 452-618 "


def test_clean_reply_drops_list_markers_but_keeps_ranges():
    from app.runtime.filters import clean_reply

    assert clean_reply("- Hasan bey, numaranızı verin.") == "Hasan bey, numaranızı verin."
    assert clean_reply("Saat 08:00 - 22:00 arası.") == "Saat 08:00 - 22:00 arası."


async def test_collect_fallback_exit():
    g = template_graph("ariza_fatura")
    node = await FlowCompiler(g, Tracer()).resolve("musteri_no", {})
    assert {f.name for f in node["functions"]} == {"bilgileri_kaydet", "bilgi_verilemiyor"}
    fallback = next(f for f in node["functions"] if f.name == "bilgi_verilemiyor")
    from types import SimpleNamespace

    _, target = await fallback.handler({}, SimpleNamespace(state={}))
    assert target["name"] == "temsilci"


def test_tidy_messages_turns_stale_tool_calls_into_notes():
    from app.runtime.context_tidy import tidy_messages

    def call(i, name):
        return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": '{"no": "7"}'}}

    step_change = [
        {"role": "user", "content": "Faturam yüksek."},
        {"role": "assistant", "tool_calls": [call(1, "fatura_sorusu")]},
        {"role": "tool", "tool_call_id": "c1", "content": "{}"},
        {"role": "system", "content": "Müşteri numarasını al."},
    ]
    # The call that just changed the step is kept for the step's first answer ...
    assert tidy_messages(step_change, allowed={"bilgileri_kaydet"}) == step_change

    # ... and becomes a note once the conversation has moved on.
    later = step_change + [
        {"role": "assistant", "content": "Numaranız?", "tool_calls": [call(2, "bilgi_ara"), call(3, "eski")]},
        {"role": "tool", "tool_call_id": "c2", "content": "sonuç"},
        {"role": "tool", "tool_call_id": "c3", "content": "{}"},
        {"role": "user", "content": "7"},
    ]
    out = tidy_messages(later, allowed={"bilgi_ara"})
    assert [m["role"] for m in out] == ["user", "system", "system", "assistant", "system", "tool", "user"]
    assert "fatura_sorusu" in out[1]["content"] and '"no": "7"' in out[1]["content"]
    assert [c["function"]["name"] for c in out[3]["tool_calls"]] == ["bilgi_ara"]
    assert out[5]["tool_call_id"] == "c2"
