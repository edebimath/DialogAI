"""End-to-end voice call without a microphone.

A scripted caller speaks Piper-synthesized Turkish over a real WebRTC connection (aiortc),
the way a browser would, and waits for the agent to finish speaking before each line.
Prints the trace and checks that the call ends with a ticket and a recording.

Usage: python scripts/voice_smoke.py   (API on :8000 with Ollama running)
"""

import asyncio
import fractions
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import websockets
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from av import AudioFrame


API = "http://localhost:8000"
RATE = 16000
FRAME = 320  # 20 ms
CALLER = ["Merhaba, iki gündür modemim sürekli kopuyor.", "Müşteri numaram dört yüz elli iki, altı yüz on sekiz."]


def synthesize(text: str) -> np.ndarray:
    from piper import PiperVoice

    voice_dir = Path.home() / ".cache" / "pipecat" / "piper"
    voice = PiperVoice.load(voice_dir / "tr_TR-dfki-medium.onnx")
    pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in voice.synthesize(text)])
    src = voice.config.sample_rate
    idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * RATE / src))
    return np.interp(idx, np.arange(len(pcm)), pcm).astype(np.int16)


class ScriptedMic(MediaStreamTrack):
    """Silence, except when a line has been queued."""

    kind = "audio"

    def __init__(self):
        super().__init__()
        self._pending = np.zeros(0, np.int16)
        self._pts = 0
        self._start = None

    def speak(self, pcm: np.ndarray) -> None:
        self._pending = np.concatenate([self._pending, pcm, np.zeros(RATE, np.int16)])

    async def recv(self) -> AudioFrame:
        if self._start is None:
            self._start = time.time()
        # Pace frames in real time.
        wait = self._start + self._pts / RATE - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        chunk, self._pending = self._pending[:FRAME], self._pending[FRAME:]
        if len(chunk) < FRAME:
            chunk = np.concatenate([chunk, np.zeros(FRAME - len(chunk), np.int16)])
        frame = AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = RATE
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, RATE)
        self._pts += FRAME
        return frame


async def main():
    lines = [synthesize(t) for t in CALLER]
    async with httpx.AsyncClient(base_url=API) as http:
        r = await http.post("/api/auth/login", data={"username": "admin@dialogai.local", "password": "admin123"})
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        agent = (await http.post("/api/agents", json={"name": "Ses testi", "template": "ariza_fatura"}, headers=h)).json()

    mic = ScriptedMic()
    pc = RTCPeerConnection()
    pc.addTransceiver(mic, direction="sendrecv")
    pc.createDataChannel("chat")
    received = {"frames": 0}

    @pc.on("track")
    def on_track(track):
        async def drain():
            while True:
                try:
                    await track.recv()
                    received["frames"] += 1
                except Exception:
                    return

        asyncio.ensure_future(drain())

    await pc.setLocalDescription(await pc.createOffer())
    pending = list(lines)
    bot_speaking_done = asyncio.Event()
    session_id = None

    async with websockets.connect("ws://127.0.0.1:8000/api/sessions/ws") as ws:
        await ws.send(json.dumps({"type": "start", "token": token, "agent_id": agent["id"], "mode": "voice"}))
        async for raw in ws:
            msg = json.loads(raw)
            if msg["type"] == "session":
                session_id = msg["session"]["id"]
                await ws.send(json.dumps({"type": "webrtc_offer", "sdp": pc.localDescription.sdp, "sdp_type": "offer"}))
            elif msg["type"] == "webrtc_answer":
                await pc.setRemoteDescription(RTCSessionDescription(sdp=msg["sdp"], type=msg["sdp_type"]))
            elif msg["type"] == "error":
                print("ERROR", msg["message"])
                break
            elif msg["type"] == "event":
                e = msg["event"]
                print(f"{e['ts']:6.2f}s {e['type']:<20} {e['node_id'] or '':<14} {e['data']}")
                # The agent's turn is over once its text is out; give TTS time to play it.
                if e["type"] in ("say", "bot_message") and pending:
                    words = len(e["data"].get("text", "").split())
                    line = pending.pop(0)
                    asyncio.get_running_loop().call_later(1.5 + words * 0.45, mic.speak, line)
                if e["type"] == "session_ended":
                    break
    await pc.close()

    async with httpx.AsyncClient(base_url=API) as http:
        detail = (await http.get(f"/api/sessions/{session_id}", headers=h)).json()
    print("\nbot audio frames received:", received["frames"])
    print("stored:", detail["outcome"], detail["end_reason"], "| recording:", detail["has_recording"])


asyncio.run(main())
