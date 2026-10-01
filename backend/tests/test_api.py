import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email="admin@test.local", password="secret123") -> dict:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", data={"username": "admin@test.local", "password": "nope"})
    assert r.status_code == 401


def test_agent_flow_lifecycle(client):
    h = login(client)
    agent = client.post("/api/agents", json={"name": "Destek", "template": "ariza_fatura"}, headers=h)
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]
    assert agent.json()["settings"]["llm"]["provider"] == "ollama"

    flow = client.get(f"/api/agents/{agent_id}/flow", headers=h).json()
    assert flow["issues"] == []
    assert "global" in flow["graph"]

    # Saving a broken draft is allowed, publishing it is not.
    broken = flow["graph"] | {"edges": flow["graph"]["edges"][:-1]}
    saved = client.put(f"/api/agents/{agent_id}/flow", json={"graph": broken}, headers=h).json()
    assert any(i["code"] == "unconnected_exit" for i in saved["issues"])
    assert client.post(f"/api/agents/{agent_id}/publish", json={}, headers=h).status_code == 400

    client.put(f"/api/agents/{agent_id}/flow", json={"graph": flow["graph"]}, headers=h)
    published = client.post(f"/api/agents/{agent_id}/publish", json={"note": "ilk"}, headers=h)
    assert published.json()["version"] == 1
    assert client.get(f"/api/agents/{agent_id}", headers=h).json()["published_version"] == 1


def test_viewer_cannot_edit(client):
    h = login(client)
    r = client.post(
        "/api/users",
        json={"email": "izleyici@test.local", "password": "secret123", "role": "viewer"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    viewer = login(client, "izleyici@test.local")
    assert client.get("/api/agents", headers=viewer).status_code == 200
    assert client.post("/api/agents", json={"name": "x"}, headers=viewer).status_code == 403
    assert client.get("/api/users", headers=viewer).status_code == 403


def test_session_ws_rejects_invalid_flow(client):
    h = login(client)
    agent_id = client.post("/api/agents", json={"name": "Boş"}, headers=h).json()["id"]
    token = h["Authorization"].split()[1]
    with client.websocket_connect("/api/sessions/ws") as ws:
        ws.send_json({"type": "start", "token": token, "agent_id": agent_id})
        message = ws.receive_json()
    assert message["type"] == "error"
    assert message["issues"]


def test_datetimes_are_returned_with_timezone(client):
    h = login(client)
    agent = client.post("/api/agents", json={"name": "Saat"}, headers=h).json()
    assert agent["updated_at"].endswith(("Z", "+00:00")), agent["updated_at"]
