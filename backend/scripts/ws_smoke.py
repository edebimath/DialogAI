"""Smoke test against a running API: create an agent from a template and talk to it over WS.

Usage: python scripts/ws_smoke.py  (API on localhost:8000, Ollama running)
"""

import asyncio
import json

import httpx
import websockets

API = "http://localhost:8000"
CALLER = ["Faturamda anlamadığım bir ücret var.", "Numaram 77 12 30."]


async def main():
    async with httpx.AsyncClient(base_url=API) as http:
        r = await http.post(
            "/api/auth/login", data={"username": "admin@dialogai.local", "password": "admin123"}
        )
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        agent = (await http.post("/api/agents", json={"name": "Smoke", "template": "ariza_fatura"}, headers=h)).json()

    async with websockets.connect("ws://127.0.0.1:8000/api/sessions/ws") as ws:
        await ws.send(json.dumps({"type": "start", "token": token, "agent_id": agent["id"], "variables": {"sirket_adi": "Deneme AŞ"}}))
        pending = list(CALLER)
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] != "event":
                print(msg["type"], msg.get("message") or msg.get("session", {}).get("id"))
                continue
            e = msg["event"]
            print(f"{e['ts']:6.2f}s {e['type']:<20} {e['node_id'] or '':<14} {e['data']}")
            if e["type"] in ("say", "bot_message") and pending:
                await ws.send(json.dumps({"type": "user_text", "text": pending.pop(0)}))
            if e["type"] == "session_ended":
                break

    async with httpx.AsyncClient(base_url=API) as http:
        sessions = (await http.get(f"/api/agents/{agent['id']}/sessions", headers=h)).json()
        detail = (await http.get(f"/api/sessions/{sessions[0]['id']}", headers=h)).json()
        print("\nstored:", detail["outcome"], detail["end_reason"], len(detail["events"]), "events")


asyncio.run(main())
