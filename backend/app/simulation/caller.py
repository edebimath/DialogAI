"""The simulated caller: an LLM playing a customer with a persona and a goal.

Its context is the mirror of the agent's: the agent's words are its "user" messages and its
own lines are the "assistant" ones. Every turn is schema-constrained JSON saying what it says
and whether it hangs up: small local models often write "I'm calling the hang-up tool" instead
of calling a tool, but they fill a required boolean reliably.
"""

import json
import re
from dataclasses import dataclass

from app.simulation.llm import SimulationLLMError, chat

INSTRUCTION = """\
Bir çağrı merkezini arayan bir müşteriyi canlandırıyorsun. Konuşma boyunca rolünden çıkma; \
test, simülasyon veya yapay zekâ olduğundan asla bahsetme.

Kimsin: {persona}

Bu aramadan ne istiyorsun: {goal}

Ajanın söyledikleri sana kullanıcı mesajı olarak gelir. Her turda şu alanlarla JSON döndür:
- soz: ajana söyleyeceğin; bir veya iki kısa, konuşma dilinde cümle, birinci tekil şahısla. \
Gerçek bir arayan gibi bir seferde tek bir şey söyle; ajan sormadan bütün bilgileri bir anda \
verme, ama sorulan bilgiyi ver. Her zaman Türkçe.
- telefonu_kapat: amacına ulaştıysan ya da ajanın sana yardım edemeyeceği netleştiyse true, \
aksi halde false. true ise soz kısa bir vedalaşma olabilir.
- amacima_ulastim: bu aramada amacına ulaştıysan true.
- neden: telefonu kapatıyorsan tek cümlelik nedeni, kapatmıyorsan boş."""

SCHEMA = {
    "type": "object",
    "properties": {
        "soz": {"type": "string"},
        "telefonu_kapat": {"type": "boolean"},
        "amacima_ulastim": {"type": "boolean"},
        "neden": {"type": "string"},
    },
    "required": ["soz", "telefonu_kapat", "amacima_ulastim", "neden"],
}

# Speaker labels or stage directions a small model sometimes adds.
_NOISE = re.compile(r"^\s*(arayan|müşteri|musteri)\s*:\s*|\([^)]*\)|\*[^*]*\*", re.IGNORECASE)


@dataclass
class CallerTurn:
    text: str | None = None
    hangup: dict | None = None  # {"success": bool, "reason": str}


class SimulatedCaller:
    def __init__(self, persona: str, goal: str):
        self._system = INSTRUCTION.format(
            persona=persona.strip() or "Sıradan bir müşteri.",
            goal=goal.strip() or "Sorununu çözmek.",
        )
        self._history: list[dict[str, str]] = []

    async def respond(self, agent_said: str) -> CallerTurn:
        self._history.append({"role": "user", "content": agent_said})
        messages = [{"role": "system", "content": self._system}, *self._history]
        data = None
        for _ in range(2):  # one retry on unparseable output
            reply = await chat(messages, schema=SCHEMA)
            try:
                data = json.loads(reply.content)
                break
            except ValueError:
                continue
        if data is None:
            raise SimulationLLMError("Simüle arayan geçerli bir cevap üretemedi.")

        text = _NOISE.sub("", str(data.get("soz", ""))).strip().strip('"').strip() or None
        if text:
            self._history.append({"role": "assistant", "content": text})
        if data.get("telefonu_kapat"):
            return CallerTurn(
                text=text,
                hangup={"success": bool(data.get("amacima_ulastim")), "reason": str(data.get("neden", ""))},
            )
        return CallerTurn(text=text)
