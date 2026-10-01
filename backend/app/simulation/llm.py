"""Chat client for the simulated caller and the judge (Ollama's native API).

Kept apart from the agent's Pipecat LLM: the caller and the judge are plain request/response
calls, and the judge needs JSON-schema output and optional thinking, which the native API has.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings


class SimulationLLMError(Exception):
    pass


@dataclass
class ChatReply:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{"name", "arguments"}]


async def chat(
    messages: list[dict[str, str]],
    *,
    tools: list[dict] | None = None,
    schema: dict | None = None,
    think: bool = False,
    temperature: float = 0.7,
    timeout: float = 180,
) -> ChatReply:
    body: dict[str, Any] = {
        "model": settings.simulation_model,
        "messages": messages,
        "stream": False,
        "think": think,
        "keep_alive": "30m",
        "options": {"temperature": temperature},
    }
    if tools:
        body["tools"] = tools
    if schema:
        body["format"] = schema
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=timeout) as client:
            r = await client.post("/api/chat", json=body)
            r.raise_for_status()
    except httpx.TimeoutException as e:
        raise SimulationLLMError(f"Simülasyon modeli ({settings.simulation_model}) {timeout:g} sn içinde cevap vermedi.") from e
    except httpx.HTTPError as e:
        # Some httpx errors have an empty message; the type still says what happened.
        raise SimulationLLMError(
            f"Simülasyon modeli ({settings.simulation_model}) çalıştırılamadı: {e or type(e).__name__}"
        ) from e
    message = r.json().get("message", {})
    calls = [
        {"name": c["function"]["name"], "arguments": c["function"].get("arguments") or {}}
        for c in message.get("tool_calls") or []
    ]
    return ChatReply(content=(message.get("content") or "").strip(), tool_calls=calls)


def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }
