import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.simulation import judge, service
from app.simulation.llm import ChatReply, SimulationLLMError
from app.trace.events import TraceEvent


def ev(seq, type, **data):
    return TraceEvent(seq=seq, ts=seq, type=type, node_id=None, data=data)


CALL = [
    ev(1, "say", text="Hoş geldiniz, size nasıl yardımcı olabilirim?"),
    ev(2, "user_message", text="İnternetim kopuyor.", source="simulated"),
    ev(3, "function_call", name="bilgileri_kaydet", args={"musteri_no": "552190"}),
    ev(4, "say", text="552190 numaralı kaydınız açıldı."),
    ev(5, "session_ended", outcome="ticket_created", reason="flow_ended"),
]


async def test_verdict_combines_rules_and_judge(monkeypatch):
    seen = {}

    async def fake_chat(messages, **kwargs):
        seen["prompt"] = messages[-1]["content"]
        return ChatReply(content=json.dumps({"gerekce": "Kayıt 552190 ile açıldı.", "karsilandi": True}))

    monkeypatch.setattr(judge, "chat", fake_chat)
    v = await judge.evaluate(
        CALL, outcome="ticket_created", end_reason="flow_ended", expected_outcome="ticket_created",
        success_criteria="Kayıt 552190 ile açıldı.", caller=None,
    )
    assert v.passed and v.judge.passed
    assert "Arayan: İnternetim kopuyor." in seen["prompt"]
    assert "bilgileri_kaydet" in seen["prompt"]

    v = await judge.evaluate(
        CALL, outcome="transferred", end_reason="max_turns", expected_outcome="ticket_created",
        success_criteria="", caller=None,
    )
    assert not v.passed
    failed = {c.name for c in v.checks if not c.passed}
    assert failed == {"Çağrı düzgün bitti", "Beklenen sonuç"}


async def test_judge_retries_without_thinking_when_it_runs_long(monkeypatch):
    calls = []

    async def fake_chat(messages, *, think=False, **kwargs):
        calls.append(think)
        if think:
            raise SimulationLLMError("60 sn içinde cevap vermedi")
        return ChatReply(content=json.dumps({"gerekce": "Tamam.", "karsilandi": True}))

    monkeypatch.setattr(judge, "chat", fake_chat)
    verdict = await judge.judge_criterion(CALL, "Kayıt açıldı.")
    assert verdict.passed and calls == [True, False]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_template_scenarios_and_runs(client, monkeypatch):
    queued = []
    monkeypatch.setattr(service, "enqueue_run", queued.append)  # don't simulate in unit tests
    h = {"Authorization": "Bearer " + client.post(
        "/api/auth/login", data={"username": "admin@test.local", "password": "secret123"}
    ).json()["access_token"]}

    agent = client.post("/api/agents", json={"name": "Sim", "template": "ariza_fatura"}, headers=h).json()
    scenarios = client.get(f"/api/agents/{agent['id']}/scenarios", headers=h).json()
    assert len(scenarios) == 3 and scenarios[0]["expected_outcome"] == "ticket_created"

    created = client.post(
        f"/api/agents/{agent['id']}/scenarios",
        json={"name": "Kısa", "persona": "p", "goal": "g", "max_turns": 4}, headers=h,
    )
    assert created.status_code == 201

    run = client.post(
        f"/api/agents/{agent['id']}/scenario-runs", json={"scenario_ids": [scenarios[0]["id"]]}, headers=h
    ).json()
    assert run["total"] == 1 and run["pending"] == 1 and queued == [run["id"]]

    cancelled = client.post(f"/api/scenario-runs/{run['id']}/cancel", headers=h).json()
    assert cancelled["status"] == "cancelled"
    detail = client.get(f"/api/scenario-runs/{run['id']}", headers=h).json()
    assert detail["results"][0]["status"] == "cancelled"
