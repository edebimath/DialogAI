"""Runs an HTTP Aracı node: fills placeholders, sends the request, maps the JSON reply to variables.

Guarded against server-side request forgery, since viewers can run tests with variables of
their choosing: see check_target(). Secrets come from the server environment, not the flow.
"""

import asyncio
import fnmatch
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import settings
from app.flows.schema import HttpRequestNode
from app.flows.templating import render
from app.flows.validator import PLACEHOLDER

SECRET_PREFIX = "secret"
MASK = "GIZLI"  # plain letters: the address is URL-quoted

TRACE_RESPONSE_CHARS = 1500
_MISSING = object()


@dataclass
class HttpResult:
    ok: bool
    method: str
    url: str
    status: int | None = None
    ms: int = 0
    values: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # output paths absent from the reply
    error: str | None = None
    response: str = ""

    def trace(self) -> dict[str, Any]:
        """Event data; request headers are left out since they often carry API keys."""
        return {
            "ok": self.ok,
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "ms": self.ms,
            "values": self.values,
            "missing": self.missing,
            "error": self.error,
            "response": self.response,
        }


def lookup(data: Any, path: str) -> Any:
    """Value at a dotted path such as "data.slots.0.time"; list items by index."""
    current = data
    for part in path.strip().split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and re.fullmatch(r"\d+", part) and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def to_state(value: Any) -> Any:
    """A form prompts and condition rules can use: booleans as true/false, lists as text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) or v is None for v in value):
        return ", ".join(str(to_state(v)) for v in value)
    return json.dumps(value, ensure_ascii=False)


def _json_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


class BlockedTarget(Exception):
    pass


def secret_names(node: HttpRequestNode) -> set[str]:
    """Names used as {{ secret.name }} in the node's address, headers and body."""
    texts = [node.url, node.body, *(h.value for h in node.headers)]
    names = set()
    for text in texts:
        for match in PLACEHOLDER.finditer(text):
            parts = match.group(0).strip("{} \t").split(".")
            if parts[0] == SECRET_PREFIX and len(parts) == 2:
                names.add(parts[1])
    return names


def _endpoint(url: str) -> tuple[str, int] | None:
    parts = urlsplit(url.replace("postgresql+asyncpg://", "postgres://"))
    if not parts.hostname:
        return None
    default = {"https": 443, "http": 80, "postgres": 5432}.get(parts.scheme, 80)
    return parts.hostname.lower(), parts.port or default


async def _addresses(host: str, port: int) -> set[str]:
    """Resolved IPs; loopback addresses all count as one ("loopback")."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise BlockedTarget(f"Sunucu adı çözülemedi: {host}") from e
    out = set()
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        out.add("loopback" if ip.is_loopback else str(ip))
    return out


async def check_target(url: str) -> None:
    """Raises BlockedTarget for addresses an HTTP node must never reach.

    Always blocked: link-local (cloud metadata at 169.254.169.254), multicast, unspecified and
    reserved addresses, and this system's own infrastructure (database, Ollama). With
    HTTP_TOOL_ALLOWED_HOSTS set, only those hosts are allowed at all.
    """
    host, port = _endpoint(url) or ("", 0)
    if not host:
        raise BlockedTarget("Adreste sunucu adı yok.")
    allowed = [h.strip().lower() for h in settings.http_tool_allowed_hosts if h.strip()]
    if allowed and not any(fnmatch.fnmatch(host, pattern) for pattern in allowed):
        raise BlockedTarget(f"{host} izinli sunucular listesinde değil (HTTP_TOOL_ALLOWED_HOSTS).")
    addresses = await _addresses(host, port)
    for address in addresses - {"loopback"}:
        ip = ipaddress.ip_address(address)
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise BlockedTarget(f"{host} ({address}) adresine istek atılamaz.")
    for infra in (settings.ollama_url, settings.database_url):
        endpoint = _endpoint(infra)
        if endpoint and endpoint[1] == port and addresses & await _addresses(*endpoint):
            raise BlockedTarget("Sistemin kendi altyapı servislerine (veritabanı, model sunucusu) istek atılamaz.")


async def run_http(
    node: HttpRequestNode,
    state: dict[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> HttpResult:
    """Never raises: failures come back as ok=False so the flow can take the "error" exit.

    Output variables are reset on failure too, so a retry loop never acts on a stale reply.
    """
    names = secret_names(node)
    secrets = {name: settings.secret(name) for name in names}
    url_quote = lambda v: quote(v, safe=":/")  # noqa: E731
    # The trace shows the address with secrets masked; the request uses the real values.
    shown_url = render(node.url.strip(), {**state, SECRET_PREFIX: dict.fromkeys(names, MASK)}, escape=url_quote)
    result = HttpResult(ok=False, method=node.method, url=shown_url)
    empty = {o.variable: "" for o in node.outputs}

    def fail(message: str) -> HttpResult:
        result.error = message
        result.values = empty
        return result

    missing = sorted(name for name, value in secrets.items() if not value)
    if missing:
        return fail("Sunucuda tanımlı olmayan gizli değer: " + ", ".join(f"SECRET_{n.upper()}" for n in missing))
    filled = {**state, SECRET_PREFIX: secrets}
    url = render(node.url.strip(), filled, escape=url_quote)
    if not re.match(r"^https?://", url):
        return fail(f"Geçersiz adres: {shown_url or '(boş)'}")
    payload = None
    if node.body.strip() and node.method != "GET":
        try:
            payload = json.loads(render(node.body, filled, escape=_json_escape))
        except ValueError:
            return fail("Gövde, değişkenler doldurulduktan sonra geçerli bir JSON değil.")
    headers = {h.name.strip(): render(h.value, filled) for h in node.headers if h.name.strip()}

    started = time.monotonic()
    try:
        if transport is None:  # tests pass a transport and never reach the network
            await check_target(url)
        # Redirects are not followed: each hop would need the same checks.
        async with httpx.AsyncClient(timeout=node.timeout, transport=transport, follow_redirects=False) as client:
            async with client.stream(node.method, url, headers=headers, json=payload) as reply:
                body = await _read_limited(reply)
    except BlockedTarget as e:
        return fail(str(e))
    except _TooLarge:
        result.ms = round((time.monotonic() - started) * 1000)
        return fail(f"Cevap {settings.http_tool_max_response_bytes // 1024} KB sınırını aşıyor.")
    except httpx.TimeoutException:
        result.ms = round((time.monotonic() - started) * 1000)
        return fail(f"İstek {node.timeout:g} sn içinde cevap vermedi.")
    except httpx.HTTPError as e:
        result.ms = round((time.monotonic() - started) * 1000)
        return fail(f"İstek gönderilemedi: {type(e).__name__}")
    result.ms = round((time.monotonic() - started) * 1000)
    result.status = reply.status_code
    text = body.decode(reply.encoding or "utf-8", errors="replace")
    result.response = text[:TRACE_RESPONSE_CHARS]

    if reply.is_redirect:
        return fail(f"Sunucu {reply.status_code} ile başka adrese yönlendirdi; yönlendirmeler izlenmez, son adresi yazın.")
    if not reply.is_success:
        return fail(f"Sunucu {reply.status_code} döndürdü.")
    if not node.outputs:
        result.ok = True
        return result
    try:
        data = json.loads(text)
    except ValueError:
        return fail("Cevap JSON değil, değişkenlere yazılamadı.")

    for output in node.outputs:
        value = lookup(data, output.path)
        if value is _MISSING:
            result.missing.append(output.path)
            value = None
        result.values[output.variable] = to_state(value)
    result.ok = True
    return result


class _TooLarge(Exception):
    pass


async def _read_limited(reply: httpx.Response) -> bytes:
    limit = settings.http_tool_max_response_bytes
    chunks, size = [], 0
    async for chunk in reply.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise _TooLarge
        chunks.append(chunk)
    return b"".join(chunks)
