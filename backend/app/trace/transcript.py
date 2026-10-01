"""A call's trace as plain text, for the LLM judge and the handoff summary."""

from app.trace.events import TraceEvent


def transcript(events: list[TraceEvent]) -> str:
    """Who said what, and what the agent did."""
    lines: list[str] = []
    for e in events:
        d = e.data
        match e.type:
            case "say" | "bot_message":
                lines.append(f"Ajan: {d.get('text', '')}")
            case "user_message":
                lines.append(f"Arayan: {d.get('text', '')}")
            case "function_call":
                lines.append(f"[ajan fonksiyon çağırdı] {d.get('name')} {d.get('args') or ''}".rstrip())
            case "kb_search":
                lines.append(f"[bilgi tabanı araması] '{d.get('query')}' -> {len(d.get('hits', []))} sonuç")
            case "variables_set":
                lines.append(f"[kaydedilen bilgi] {d.get('values')}")
            case "http_request":
                if d.get("ok"):
                    lines.append(f"[sistem sorgusu] {d.get('method')} {d.get('url')} -> {d.get('values') or 'başarılı'}")
                else:
                    lines.append(f"[sistem sorgusu başarısız] {d.get('method')} {d.get('url')}: {d.get('error')}")
            case "transfer":
                lines.append(f"[temsilciye aktarıldı] {d.get('target') or ''}".rstrip())
            case "session_ended":
                lines.append(f"[çağrı bitti] sonuç: {d.get('outcome')}")
    return "\n".join(lines)
