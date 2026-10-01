"""Print the exact chat-completion params sent to the LLM on the first caller turn."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger  # noqa: E402
from pipecat.services.openai.base_llm import BaseOpenAILLMService  # noqa: E402

from app.flows.templates import template_graph  # noqa: E402
from app.runtime.providers import AgentSettings  # noqa: E402
from app.runtime.session import CallSession  # noqa: E402
from app.trace.events import Tracer  # noqa: E402

original = BaseOpenAILLMService.build_chat_completion_params


def spy(self, params_from_context):
    params = original(self, params_from_context)
    view = {
        "messages": params.get("messages"),
        "tools": [t["function"]["name"] for t in (params.get("tools") or [])]
        if isinstance(params.get("tools"), list)
        else str(params.get("tools")),
    }
    print(json.dumps(view, ensure_ascii=False, indent=1, default=str))
    return params


BaseOpenAILLMService.build_chat_completion_params = spy


async def main():
    logger.remove()
    session = CallSession(template_graph("ariza_fatura"), AgentSettings(), Tracer())
    await session.start()
    await asyncio.sleep(1)
    await session.send_user_text("Merhaba, iki gündür modem sürekli kopuyor.")
    await asyncio.sleep(6)
    await session.stop()


asyncio.run(main())
