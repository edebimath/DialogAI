"""Security guards: logins, tokens, test-call input, HTTP Aracı targets and secrets, settings."""

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.sessions import call_variables
from app.core import ratelimit
from app.core.config import Settings
from app.flows.http_tool import BlockedTarget, check_target, run_http
from app.flows.schema import FlowGraph, HttpRequestNode
from app.flows.validator import validate
from app.main import app, check_settings
from app.runtime.providers import AgentSettings


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_lockouts():
    ratelimit._failures.clear()
    yield
    ratelimit._failures.clear()


def login(client, email="admin@test.local", password="secret123"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_repeated_failed_logins_lock_temporarily(client):
    for _ in range(5):
        assert login(client, password="yanlis").status_code == 401
    r = login(client)  # even the right password waits out the lock
    assert r.status_code == 429 and "Retry-After" in r.headers
    # Unknown e-mails get the same answer as wrong passwords.
    ratelimit._failures.clear()
    assert login(client, email="yok@test.local").json()["detail"] == login(client, password="x").json()["detail"]


def test_password_change_revokes_tokens(client):
    admin = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    user = client.post(
        "/api/users", json={"email": "degisen@test.local", "password": "ilksifre1", "role": "viewer"}, headers=admin
    ).json()
    old = {"Authorization": f"Bearer {login(client, 'degisen@test.local', 'ilksifre1').json()['access_token']}"}
    assert client.get("/api/auth/me", headers=old).status_code == 200
    client.patch(f"/api/users/{user['id']}", json={"password": "yenisifre2"}, headers=admin)
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert login(client, "degisen@test.local", "yenisifre2").status_code == 200
    # Short passwords are refused.
    r = client.post("/api/users", json={"email": "kisa@test.local", "password": "1234567"}, headers=admin)
    assert r.status_code == 422


def test_session_socket_takes_the_token_from_the_message_not_the_url(client):
    token = login(client).json()["access_token"]
    with client.websocket_connect(f"/api/sessions/ws?token={token}") as ws:
        ws.send_json({"type": "start", "agent_id": "x"})
        assert ws.receive_json()["message"].startswith("Oturum geçersiz")


def test_recording_ids_are_checked(client):
    h = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    assert client.get("/api/sessions/..%5C..%5Cx/recording", headers=h).status_code == 404
    assert client.get("/api/sessions/not-a-session/recording", headers=h).status_code == 404


def test_test_calls_only_set_declared_variables():
    graph = FlowGraph.model_validate({"variables": [{"name": "arayan_no"}]})
    given = {"arayan_no": "0532" + "9" * 1000, "musteri_tipi": "vip", "api_adresi": "http://169.254.169.254"}
    assert call_variables(graph, given) == {"arayan_no": ("0532" + "9" * 1000)[:500]}


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[fe80::1]/",
        "http://0.0.0.0:8000/",
        "http://127.0.0.1:11434/api/tags",  # this system's Ollama
        "http://localhost:5432/",  # this system's database
    ],
)
async def test_http_tool_blocks_dangerous_targets(url):
    with pytest.raises(BlockedTarget):
        await check_target(url)


async def test_http_tool_allows_internal_services_and_honours_the_allowlist(monkeypatch):
    await check_target("http://127.0.0.1:8000/api/demo/musteri")  # an internal API on another port
    monkeypatch.setattr("app.flows.http_tool.settings.http_tool_allowed_hosts", ["*.sirket.local"])
    with pytest.raises(BlockedTarget, match="izinli"):
        await check_target("http://127.0.0.1:8000/api/demo/musteri")


async def test_http_tool_secrets_redirects_and_size(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        if request.url.path == "/yonlendir":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        if request.url.path == "/buyuk":
            return httpx.Response(200, content=b"x" * (2 * 1024 * 1024))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    node = HttpRequestNode(
        id="h",
        url="http://crm.test/musteri?anahtar={{ secret.crm_token }}",
        headers=[{"name": "Authorization", "value": "Bearer {{ secret.crm_token }}"}],
        outputs=[{"variable": "ok", "path": "ok"}],
    )
    result = await run_http(node, {}, transport)
    assert not result.ok and "SECRET_CRM_TOKEN" in result.error  # not set on the server yet

    monkeypatch.setenv("SECRET_CRM_TOKEN", "gercek-anahtar")
    result = await run_http(node, {}, transport)
    assert result.ok and seen["auth"] == "Bearer gercek-anahtar"
    assert "gercek-anahtar" not in str(result.trace()) and "GIZLI" in result.url

    redirect = node.model_copy(update={"url": "http://crm.test/yonlendir"})
    result = await run_http(redirect, {}, transport)
    assert not result.ok and "yönlendir" in result.error

    big = node.model_copy(update={"url": "http://crm.test/buyuk"})
    result = await run_http(big, {}, transport)
    assert not result.ok and "sınırını aşıyor" in result.error


def test_secrets_stay_out_of_prompts_and_the_name_is_reserved():
    graph = FlowGraph.model_validate(
        {
            "variables": [{"name": "secret"}],
            "nodes": [{"id": "s", "type": "start"}, {"id": "a", "type": "say", "text": "Anahtar {{ secret.crm_token }}"}],
            "edges": [{"id": "1", "source": "s", "target": "a"}],
        }
    )
    codes = {i.code for i in validate(graph)}
    assert {"secret_outside_http", "reserved_name"} <= codes


def test_agent_settings_only_accept_listed_voice_models():
    with pytest.raises(ValidationError):
        AgentSettings.model_validate({"stt": {"model": "C:/Windows/System32"}})
    with pytest.raises(ValidationError):
        AgentSettings.model_validate({"tts": {"voice": "../../etc/passwd"}})
    with pytest.raises(ValidationError):
        AgentSettings.model_validate({"llm": {"model": "qwen3:8b; rm -rf /"}})


def test_production_refuses_default_secrets(monkeypatch):
    unsafe = Settings(app_env="production", jwt_secret="kisa", bootstrap_admin_password="admin123")
    assert len(unsafe.production_problems()) >= 2 and not unsafe.demo_api_enabled
    monkeypatch.setattr("app.main.settings", unsafe)
    with pytest.raises(RuntimeError, match="Üretim ayarları güvenli değil"):
        check_settings()
    safe = Settings(
        app_env="production",
        jwt_secret="x" * 40,
        bootstrap_admin_password="uzun-ve-guclu-bir-sifre",
        database_url="postgresql+asyncpg://dialogai:guclu@db:5432/dialogai",
    )
    assert safe.production_problems() == []


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
