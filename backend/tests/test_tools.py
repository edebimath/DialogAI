"""HTTP Aracı and Temsilciye Aktar cards, and the demo APIs the templates call."""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api import demo
from app.flows.compiler import FlowCompiler
from app.flows.http_tool import lookup, run_http, to_state
from app.flows.schema import FlowGraph, HttpRequestNode
from app.flows.templates import TEMPLATES, template_graph
from app.flows.validator import validate
from app.trace.events import Tracer


@pytest.fixture
def demo_transport():
    app = FastAPI()
    app.include_router(demo.router)
    return httpx.ASGITransport(app=app)


async def no_summary(events):
    raise AssertionError("summary not expected")


def compiler(key: str, transport, summarizer=no_summary) -> tuple[FlowCompiler, Tracer]:
    tracer = Tracer()
    return FlowCompiler(template_graph(key), tracer, summarizer=summarizer, http_transport=transport), tracer


@pytest.mark.parametrize("key", [k for k in TEMPLATES if k != "blank"])
def test_templates_are_valid(key):
    issues = validate(template_graph(key))
    # The FAQ template asks the user to pick a knowledge base after creating it.
    assert not [i for i in issues if i.severity == "error" and i.code != "no_kb"], issues


def test_http_node_validation():
    def codes(**node):
        g = FlowGraph.model_validate(
            {
                "nodes": [{"id": "s", "type": "start"}, {"id": "h", "type": "http_request", **node}],
                "edges": [{"id": "1", "source": "s", "target": "h"}],
            }
        )
        return {i.code for i in validate(g) if i.node_id == "h"}

    assert "empty_url" in codes()
    assert "bad_url" in codes(url="ftp://x")
    assert "bad_url" not in codes(url="{{ adres }}/x")  # the base may come from a variable
    assert "body_on_get" in codes(url="http://x", body='{"a": 1}')
    assert "bad_body" in codes(url="http://x", method="POST", body='{"a": }')
    assert "bad_body" not in codes(url="http://x", method="POST", body='{"a": {{ no }}, "b": "{{ no }}"}')
    assert "bad_output_name" in codes(url="http://x", outputs=[{"variable": "Durum", "path": "d"}])
    # Output variables count as known names for placeholders elsewhere.
    assert "unknown_variable" not in codes(url="http://x/{{ durum }}", outputs=[{"variable": "durum", "path": "d"}])


def test_lookup_and_state_values():
    data = {"a": {"list": [{"t": "09:30"}, {"t": "11:00"}]}, "ok": True}
    assert lookup(data, "a.list.1.t") == "11:00"
    assert to_state(lookup(data, "ok")) == "true"
    assert to_state(["09:30", "11:00"]) == "09:30, 11:00"
    assert to_state({"x": 1}) == '{"x": 1}'


async def test_http_values_are_escaped_and_failures_reset_outputs():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(500, json={"detail": "x"})

    node = HttpRequestNode(
        id="h",
        method="POST",
        url="http://api.test/ara/{{ ad }}",
        headers=[{"name": "Authorization", "value": "Bearer {{ anahtar }}"}],
        body='{"not": "{{ ad }}"}',
        outputs=[{"variable": "sonuc", "path": "sonuc"}],
    )
    state = {"ad": 'Ali "Veli"/&x', "anahtar": "k1", "sonuc": "eski"}
    result = await run_http(node, state, httpx.MockTransport(handler))
    assert not result.ok and result.status == 500
    assert result.values == {"sonuc": ""}
    assert seen["url"] == "http://api.test/ara/Ali%20%22Veli%22/%26x"
    assert seen["body"] == '{"not":"Ali \\"Veli\\"/&x"}'
    assert seen["auth"] == "Bearer k1"
    assert "Authorization" not in str(result.trace())


def test_demo_day_and_time_parsing():
    monday = date(2026, 9, 28)
    assert demo.parse_day("Salı'ya olsun", monday) == "Salı"
    assert demo.parse_day("pazartesi günü", monday) == "Pazartesi"
    assert demo.parse_day("cumartesi", monday) == "Cumartesi"
    assert demo.parse_day("yarın", monday) == "Salı"
    assert demo.parse_day("bilmem", monday) is None
    assert demo.parse_time("14.30") == "14:30"
    assert demo.parse_time("saat 2") == "14:00"


async def test_randevu_template_books_through_the_demo_api(demo_transport):
    c, tracer = compiler("randevu", demo_transport)
    state = c.initial_state({"ad_soyad": "Fatma Demir", "gun": "salı"})

    node = await c.resolve("musait", state)
    assert node["name"] == "saat"
    assert state["musait"] == "true" and state["gun_adi"] == "Salı"
    assert state["saatler"] == "09:30, 11:00, 14:00, 16:30"
    http = next(e for e in tracer.events if e.type == "http_request")
    assert http.data["ok"] and http.data["status"] == 200

    state["saat"] = "saat 2"
    node = await c.resolve("olustur", state)
    assert node["name"] == "onay"
    assert state["saat"] == "14:00" and state["randevu_no"].startswith("R")
    assert tracer.outcome == "appointment_booked"

    # A time that isn't on the list takes the error exit back to choosing a time.
    state["saat"] = "18:00"
    node = await c.resolve("olustur", state)
    assert node["name"] == "saat"
    assert state["randevu_no"] == ""

    state["gun"] = "pazar"
    node = await c.resolve("musait", state)
    assert node["name"] == "gun"  # through "Başka gün iste"
    assert [a["node_id"] for a in node["pre_actions"]] == ["baska_gun"]
    assert state["musait_mesaj"] == "Pazar günleri kapalıyız."


async def test_kargo_unknown_number_transfers_with_summary(demo_transport):
    async def summarizer(events):
        return "Arayan 999888 numaralı gönderiyi sordu, bulunamadı."

    c, tracer = compiler("kargo", demo_transport, summarizer)
    state = c.initial_state({"takip_no": "999888"})
    node = await c.resolve("sorgu", state)
    assert node["name"] == "bulunamadi"
    assert [a["type"] for a in node["pre_actions"]] == ["say", "transfer", "end_conversation"]
    assert tracer.outcome == "transferred"

    transfer = node["pre_actions"][1]
    await transfer["handler"](transfer, SimpleNamespace(state=state))
    event = tracer.events[-1]
    assert event.type == "transfer" and event.node_id == "bulunamadi"
    assert event.data["target"] == "Müşteri hizmetleri"
    # What the caller gave, not configuration still at its default.
    assert event.data["variables"] == {"takip_no": "999888"}
    assert event.data["summary"].startswith("Arayan 999888")


async def test_transfer_without_summary_still_transfers(demo_transport):
    async def broken(events):
        raise RuntimeError("model yok")

    c, tracer = compiler("kargo", demo_transport, broken)
    node = await c.resolve("numarasiz", c.initial_state())
    transfer = node["pre_actions"][1]
    await transfer["handler"](transfer, SimpleNamespace(state={}))
    assert tracer.events[-1].data["summary"] is None
    assert tracer.events[-1].data["summary_error"]


async def test_step_exits_are_named_as_actions_and_listed(demo_transport):
    c, tracer = compiler("kargo", demo_transport)
    node = await c.resolve("yardim", c.initial_state())
    assert [f.name for f in node["functions"]] == ["adimi_bitir_1", "adimi_bitir_2"]
    task = node["task_messages"][0]["content"]
    assert "- adimi_bitir_1: Arayanın başka sorusu veya isteği yok" in task
    await node["functions"][0].handler({}, SimpleNamespace(state={}))
    call = next(e for e in tracer.events if e.type == "function_call")
    assert call.data["label"] == "Arayanın başka sorusu veya isteği yok"
    # Router routes keep descriptive names; they help the model classify.
    router = await FlowCompiler(template_graph("ariza_fatura"), Tracer()).resolve("yonlendir", {})
    assert "fatura_ucret_veya_odeme_sorusu" in {f.name for f in router["functions"]}
