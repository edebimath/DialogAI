"""Verdict on a simulated call: rule checks plus an LLM judge for the success criterion."""

import json

from pydantic import BaseModel

from app.simulation.llm import SimulationLLMError, chat
from app.trace.events import TraceEvent
from app.trace.transcript import transcript

JUDGE_INSTRUCTION = """\
Bir çağrı merkezi test değerlendiricisisin. Sana bir ajan ile arayan arasındaki konuşmanın \
dökümü, ajanın çağırdığı fonksiyonlar ve bir başarı kriteri verilecek. Kriterin bu \
konuşmada karşılanıp karşılanmadığına karar ver. Yalnızca dökümde gerçekten olanlara bak: \
ajanın niyetine değil, söylediklerine ve yaptıklarına göre karar ver. Emin değilsen \
"karşılanmadı" de. Gerekçeyi kısa ve Türkçe yaz."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"gerekce": {"type": "string"}, "karsilandi": {"type": "boolean"}},
    "required": ["gerekce", "karsilandi"],
}

GOOD_ENDINGS = {"flow_ended": "Akış bir Bitiş veya Aktarma kartıyla tamamlandı", "caller_hangup": "Arayan telefonu kapattı"}
BAD_ENDINGS = {
    "max_turns": "Tur sınırına ulaşıldı",
    "loop": "Konuşma döngüye girdi (arayan aynı şeyi tekrarlıyor)",
    "silence": "Ajan cevap vermedi",
    "timeout": "Süre sınırı doldu",
    "error": "Hata oluştu",
    "user_hangup": "Test durduruldu",
    "client_disconnected": "Bağlantı kesildi",
}


class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class JudgeVerdict(BaseModel):
    passed: bool
    reason: str


class Verdict(BaseModel):
    passed: bool
    checks: list[Check]
    judge: JudgeVerdict | None = None
    caller: dict | None = None  # the caller's own view: {"success", "reason"}


# Thinking can run on for minutes on a long transcript; past this, judge again without it.
THINKING_TIMEOUT_SECS = 60


async def judge_criterion(events: list[TraceEvent], criterion: str) -> JudgeVerdict:
    prompt = f"Başarı kriteri: {criterion}\n\nKonuşma dökümü:\n{transcript(events)}"
    messages = [{"role": "system", "content": JUDGE_INSTRUCTION}, {"role": "user", "content": prompt}]
    try:
        try:
            # Thinking on: the judge is not latency-bound and reasons better with it.
            reply = await chat(messages, schema=JUDGE_SCHEMA, think=True, temperature=0, timeout=THINKING_TIMEOUT_SECS)
        except SimulationLLMError:
            reply = await chat(messages, schema=JUDGE_SCHEMA, think=False, temperature=0)
        data = json.loads(reply.content)
        return JudgeVerdict(passed=bool(data["karsilandi"]), reason=str(data["gerekce"]).strip())
    except (SimulationLLMError, ValueError, KeyError) as e:
        return JudgeVerdict(passed=False, reason=f"Değerlendirme yapılamadı: {e}")


async def evaluate(
    events: list[TraceEvent],
    *,
    outcome: str | None,
    end_reason: str | None,
    expected_outcome: str | None,
    success_criteria: str,
    caller: dict | None,
) -> Verdict:
    checks: list[Check] = []
    ending = GOOD_ENDINGS.get(end_reason or "") or BAD_ENDINGS.get(end_reason or "", end_reason or "?")
    checks.append(Check(name="Çağrı düzgün bitti", passed=end_reason in GOOD_ENDINGS, detail=ending))
    errors = [e.data.get("message", "") for e in events if e.type == "error"]
    checks.append(Check(name="Hata yok", passed=not errors, detail="; ".join(errors)[:300]))
    if expected_outcome:
        checks.append(
            Check(
                name="Beklenen sonuç",
                passed=outcome == expected_outcome,
                detail=f"beklenen: {expected_outcome}, gerçekleşen: {outcome or '—'}",
            )
        )
    judge = await judge_criterion(events, success_criteria) if success_criteria.strip() else None
    passed = all(c.passed for c in checks) and (judge.passed if judge else True)
    return Verdict(passed=passed, checks=checks, judge=judge, caller=caller)
