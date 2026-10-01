"""Browser smoke test: login -> create agent from template -> canvas -> test call.

Needs the API (:8000), Vite (:5173) and Ollama running.
Usage: python e2e/ui_smoke.py [screenshot_dir]
"""

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e/screens")
OUT.mkdir(parents=True, exist_ok=True)

problems: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 900}, locale="tr-TR")
    page.on("console", lambda m: m.type in ("error", "warning") and problems.append(f"{m.type}: {m.text}"))
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    page.goto(BASE)
    page.get_by_label("E-posta").fill("admin@dialogai.local")
    page.get_by_label("Şifre").fill("admin123")
    page.get_by_role("button", name="Giriş yap").click()
    expect(page.get_by_role("heading", name="Ajanlar")).to_be_visible()
    page.screenshot(path=OUT / "1-agents.png")

    page.get_by_role("button", name="Yeni ajan").click()
    page.get_by_placeholder("Ör. Fatura destek hattı").fill("UI Test Hattı")
    page.get_by_role("button", name="Fatura / Arıza kaydı").click()
    page.get_by_role("button", name="Oluştur", exact=True).click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=10_000)
    page.wait_for_timeout(800)
    page.screenshot(path=OUT / "2-editor.png")

    # Select a node and edit it; autosave should run.
    page.locator(".react-flow__node").filter(has_text="Talep yönlendirme").click()
    expect(page.get_by_text("Seçenekler", exact=True)).to_be_visible()
    page.screenshot(path=OUT / "3-inspector.png")
    page.locator(".react-flow__pane").click(position={"x": 50, "y": 50})

    # Drop a new card: it has empty content, so the flow must report errors.
    page.get_by_role("button", name="Söylem").first.click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("hata", timeout=5_000)
    expect(page.get_by_text("Kaydedildi")).to_be_visible(timeout=5_000)
    page.screenshot(path=OUT / "4-new-node-errors.png")
    page.keyboard.press("Delete")
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=5_000)

    # Test call
    page.get_by_role("button", name="Test et").click()
    page.get_by_role("button", name="Yazılı").click()
    page.get_by_role("button", name="Çağrıyı başlat").click()
    expect(page.get_by_text("müşteri hizmetlerine hoş geldiniz")).to_be_visible(timeout=20_000)
    box = page.get_by_placeholder("Arayan olarak yazın…")
    drawer = page.locator("aside").filter(has_text="Test çağrısı")

    def say(text: str) -> None:
        """Send a caller line and wait until the agent has answered it."""
        box.fill(text)
        box.press("Enter")
        expect(drawer.get_by_text(text, exact=True)).to_be_visible()
        expect(drawer.get_by_text("Ajan düşünüyor…")).to_be_hidden(timeout=60_000)

    say("Merhaba, modemim sürekli kopuyor.")
    page.screenshot(path=OUT / "5-call-midway.png")
    say("Müşteri numaram 452618")
    expect(drawer.get_by_text("Çağrı bitti")).to_be_visible(timeout=30_000)
    page.screenshot(path=OUT / "6-call-ended.png")

    page.get_by_role("button", name="Geçmiş").click()
    page.locator("aside li button").first.click()
    expect(page.get_by_text("Listeye dön")).to_be_visible()
    page.screenshot(path=OUT / "7-history.png")
    browser.close()

print("screens:", OUT.resolve())
print("console problems:" if problems else "no console problems")
for line in problems:
    print("  ", line)
