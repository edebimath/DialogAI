"""Browser: HTTP Aracı and Temsilciye Aktar cards in the editor, and a text call through both.

Needs the API (:8000, which also serves the demo APIs), Vite (:5173) and Ollama running.
Usage: python e2e/tools_ui_smoke.py [screenshot_dir]
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
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.on("console", lambda m: m.type == "error" and problems.append(f"{m.type}: {m.text}"))
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    page.goto(BASE)
    page.get_by_label("E-posta").fill("admin@dialogai.local")
    page.get_by_label("Şifre").fill("admin123")
    page.get_by_role("button", name="Giriş yap").click()
    page.get_by_role("button", name="Yeni ajan").click()
    page.get_by_placeholder("Ör. Fatura destek hattı").fill("Kargo UI testi")
    page.get_by_role("button", name="Kargo takip hattı").click()
    page.get_by_role("button", name="Oluştur", exact=True).click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=10_000)
    page.wait_for_timeout(800)
    page.screenshot(path=OUT / "t1-kargo-flow.png")

    # Inspectors of the two new cards
    page.locator(".react-flow__node").filter(has_text="Gönderiyi sorgula").click()
    expect(page.get_by_text("Cevaptan alınacak değerler")).to_be_visible()
    expect(page.locator("input[value='{{ api_adresi }}/kargo/{{ takip_no }}']")).to_be_visible()
    page.screenshot(path=OUT / "t2-http-inspector.png")
    page.locator(".react-flow__node").filter(has_text="Şikayet birimine aktar").click()
    expect(page.get_by_text("Aktarılacak birim")).to_be_visible()
    page.locator(".react-flow__pane").click(position={"x": 50, "y": 50})

    # A fresh HTTP card has no address: the flow reports it until the card is removed.
    page.get_by_role("button", name="HTTP Aracı").first.click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("hata", timeout=5_000)
    expect(page.get_by_text("İstek adresi (URL) boş.")).to_be_visible()
    page.keyboard.press("Delete")
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=5_000)

    # Text call: an unknown tracking number takes the HTTP error exit into a transfer.
    page.get_by_role("button", name="Test et").click()
    drawer = page.locator("aside").filter(has_text="Test çağrısı")
    drawer.get_by_role("button", name="Yazılı").click()
    drawer.get_by_role("button", name="Çağrıyı başlat").click()
    expect(drawer.get_by_text("kargo takip hattına hoş geldiniz")).to_be_visible(timeout=20_000)
    box = page.get_by_placeholder("Arayan olarak yazın…")
    box.fill("Takip numaram 999888")
    box.press("Enter")
    expect(drawer.get_by_text("Temsilciye aktarıldı: Müşteri hizmetleri")).to_be_visible(timeout=60_000)
    expect(drawer.get_by_text("/api/demo/kargo/999888")).to_be_visible()
    expect(drawer.get_by_text("Çağrı bitti")).to_be_visible(timeout=30_000)
    expect(drawer.get_by_text("transferred")).to_be_visible()
    page.screenshot(path=OUT / "t3-transfer-call.png")
    browser.close()

print("screens:", OUT.resolve())
print("console problems:" if problems else "no console problems")
for line in problems:
    print("  ", line)
