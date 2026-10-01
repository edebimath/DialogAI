"""Batch run of a template's scenarios against a running API (needs Ollama).

Usage: python scripts/sim_batch_smoke.py [template]   (default: ariza_fatura)
"""

import asyncio
import sys
import time

import httpx

API = "http://127.0.0.1:8000"
TEMPLATE = sys.argv[1] if len(sys.argv) > 1 else "ariza_fatura"


async def main():
    async with httpx.AsyncClient(base_url=API, timeout=60) as http:
        r = await http.post("/api/auth/login", data={"username": "admin@dialogai.local", "password": "admin123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        agent = (await http.post("/api/agents", json={"name": f"Toplu test ({TEMPLATE})", "template": TEMPLATE}, headers=h)).json()
        run = (await http.post(f"/api/agents/{agent['id']}/scenario-runs", json={}, headers=h)).json()
        if "id" not in run:
            print("run failed:", run)
            return
        t0 = time.time()
        while True:
            detail = (await http.get(f"/api/scenario-runs/{run['id']}", headers=h)).json()
            if detail["status"] in ("done", "cancelled"):
                break
            await asyncio.sleep(2)
        print(f"run {detail['status']} in {time.time() - t0:.0f}s: {detail['passed']}/{detail['total']} passed\n")
        for res in detail["results"]:
            v = res["verdict"]
            print(f"[{res['status'].upper():7}] {res['scenario_name']}  ({res['turns']} tur, {res['duration']} sn, sonuç={res['outcome']}, bitiş={res['end_reason']})")
            for c in v.get("checks", []):
                print(f"     {'✓' if c['passed'] else '✗'} {c['name']}: {c['detail']}")
            if v.get("judge"):
                print(f"     {'✓' if v['judge']['passed'] else '✗'} Hakem: {v['judge']['reason']}")
            if v.get("error"):
                print("     hata:", v["error"])
            session = (await http.get(f"/api/sessions/{res['session_id']}", headers=h)).json()
            for e in session["events"]:
                if e["type"] in ("say", "bot_message", "user_message"):
                    who = "  arayan" if e["type"] == "user_message" else "  ajan  "
                    print(f"   {who}: {e['data']['text']}")
            print()


asyncio.run(main())
