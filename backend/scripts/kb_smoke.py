"""Knowledge-base smoke test against a running API with Ollama (bge-m3 + qwen3).

Creates a knowledge base from scripts/samples, an agent from the "sss" template wired to it,
then asks questions over the test-session WebSocket: two answerable, one not in the documents.
Usage: python scripts/kb_smoke.py
"""

import asyncio
import json
import time
from pathlib import Path

import httpx
import websockets

API = "http://127.0.0.1:8000"
SAMPLE = Path(__file__).parent / "samples" / "ornek_telekom_sss.md"
QUESTIONS = [
    "Faturamı en geç ne zamana kadar ödemem gerekiyor?",
    "Modemin ışıkları kırmızı yanıyor, ne yapayım?",
    "Yurt dışında roaming ücreti ne kadar?",  # not in the document: must not be made up
    "Başka sorum yok, teşekkürler.",
]


async def main():
    async with httpx.AsyncClient(base_url=API, timeout=60) as http:
        r = await http.post("/api/auth/login", data={"username": "admin@dialogai.local", "password": "admin123"})
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        kb = (await http.post("/api/knowledge-bases", json={"name": "Örnek SSS"}, headers=h)).json()
        files = [("files", (SAMPLE.name, SAMPLE.read_bytes(), "text/markdown"))]
        await http.post(f"/api/knowledge-bases/{kb['id']}/documents", files=files, headers=h)
        t0 = time.time()
        while True:
            detail = (await http.get(f"/api/knowledge-bases/{kb['id']}", headers=h)).json()
            doc = detail["documents"][0]
            if doc["status"] in ("ready", "failed"):
                break
            await asyncio.sleep(0.3)
        print(f"indexed: {doc['status']} {doc['chunk_count']} chunks in {time.time() - t0:.1f}s {doc['error'] or ''}")

        agent = (await http.post("/api/agents", json={"name": "SSS testi", "template": "sss"}, headers=h)).json()
        flow = (await http.get(f"/api/agents/{agent['id']}/flow", headers=h)).json()
        print("issues before selecting KB:", [i["code"] for i in flow["issues"]])
        for node in flow["graph"]["nodes"]:
            if node["type"] == "kb_answer":
                node["kb_ids"] = [kb["id"]]
        saved = (await http.put(f"/api/agents/{agent['id']}/flow", json={"graph": flow["graph"]}, headers=h)).json()
        print("issues after:", [i["code"] for i in saved["issues"]])

    pending = list(QUESTIONS)
    async with websockets.connect("ws://127.0.0.1:8000/api/sessions/ws") as ws:
        await ws.send(json.dumps({"type": "start", "token": token, "agent_id": agent["id"]}))
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] == "error":
                print("ERROR", msg["message"])
                break
            if msg["type"] != "event":
                continue
            e = msg["event"]
            d = e["data"]
            if e["type"] == "kb_search":
                print(f"  [kb] '{d['query']}' -> " + ", ".join(f"{x['score']:.2f}" for x in d["hits"]) + f" ({d['ms']} ms)")
            elif e["type"] in ("say", "bot_message", "user_message"):
                who = "ARAYAN" if e["type"] == "user_message" else "AJAN  "
                print(f"{e['ts']:6.1f}s {who} {d['text']}")
            elif e["type"] in ("function_call", "node_entered", "session_ended"):
                print(f"{e['ts']:6.1f}s   {e['type']} {e['node_id'] or ''} {d.get('name', '')} {d.get('outcome', '')}")
            if e["type"] in ("say", "bot_message") and pending:
                await asyncio.sleep(0.3)
                await ws.send(json.dumps({"type": "user_text", "text": pending.pop(0)}))
            if e["type"] == "session_ended":
                break


asyncio.run(main())
