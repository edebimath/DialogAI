"""Browser voice call: Chromium's fake microphone plays a scripted Turkish caller.

The caller audio is a WAV of pauses and Piper-synthesized lines, timed to leave room for the
agent's replies. Needs the API (:8000, Whisper + Piper), Vite (:5173) and Ollama running.
Usage: python e2e/voice_ui_smoke.py [screenshot_dir]
"""

import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from piper import PiperVoice
from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e/screens")
OUT.mkdir(parents=True, exist_ok=True)
RATE = 16000
SCRIPT = [  # (seconds of silence before, line)
    (8, "Merhaba, iki gündür modemim sürekli kopuyor."),
    (14, "Müşteri numaram dört yüz elli iki, altı yüz on sekiz."),
]


def caller_wav() -> Path:
    voice = PiperVoice.load(Path.home() / ".cache" / "pipecat" / "piper" / "tr_TR-dfki-medium.onnx")
    parts = []
    for pause, text in SCRIPT:
        parts.append(np.zeros(pause * RATE, np.int16))
        pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in voice.synthesize(text)])
        src = voice.config.sample_rate
        idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * RATE / src))
        parts.append(np.interp(idx, np.arange(len(pcm)), pcm).astype(np.int16))
    parts.append(np.zeros(40 * RATE, np.int16))
    path = Path(tempfile.gettempdir()) / "dialogai_caller.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(np.concatenate(parts).tobytes())
    return path


problems: list[str] = []
wav = caller_wav()

with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={wav}%noloop",
            "--autoplay-policy=no-user-gesture-required",
        ]
    )
    context = browser.new_context(viewport={"width": 1500, "height": 900}, permissions=["microphone"])
    page = context.new_page()
    page.on("console", lambda m: m.type == "error" and problems.append(f"{m.type}: {m.text}"))
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    page.goto(BASE)
    page.get_by_label("E-posta").fill("admin@dialogai.local")
    page.get_by_label("Şifre").fill("admin123")
    page.get_by_role("button", name="Giriş yap").click()
    page.get_by_role("button", name="Yeni ajan").click()
    page.get_by_placeholder("Ör. Fatura destek hattı").fill("Sesli UI testi")
    page.get_by_role("button", name="Fatura / Arıza kaydı").click()
    page.get_by_role("button", name="Oluştur", exact=True).click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=10_000)

    page.get_by_role("button", name="Test et").click()
    drawer = page.locator("aside").filter(has_text="Test çağrısı")
    drawer.get_by_role("button", name="Sesli").click()
    drawer.get_by_role("button", name="Çağrıyı başlat").click()
    expect(drawer.get_by_text("müşteri hizmetlerine hoş geldiniz")).to_be_visible(timeout=30_000)
    expect(drawer.get_by_title("Sessize al")).to_be_visible()
    expect(drawer.get_by_text("sesli").first).to_be_visible(timeout=30_000)
    page.screenshot(path=OUT / "v1-voice-midway.png")
    expect(drawer.get_by_text("Çağrı bitti")).to_be_visible(timeout=90_000)
    page.screenshot(path=OUT / "v2-voice-ended.png")

    drawer.get_by_role("button", name="Geçmiş").click()
    drawer.locator("li button").first.click()
    expect(drawer.locator("audio")).to_be_visible(timeout=10_000)
    page.screenshot(path=OUT / "v3-voice-history.png")
    transcript = drawer.inner_text()
    browser.close()

print("screens:", OUT.resolve())
print("caller lines heard:", transcript.count("sesli"))
print("console problems:" if problems else "no console problems")
for line in problems:
    print("  ", line)
