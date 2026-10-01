"""Browser: template scenarios -> run one from the scenarios page -> watch one live in the test panel.

Needs the API (:8000), Vite (:5173) and Ollama running. Passing or failing scenarios are both fine
here: the test checks that runs complete and verdicts are shown, not the agent's quality.
Usage: python e2e/scenarios_ui_smoke.py [screenshot_dir]
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e/screens")
OUT.mkdir(parents=True, exist_ok=True)
FINAL = re.compile("Geçti|Kaldı|Hata")
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
    page.get_by_placeholder("Ör. Fatura destek hattı").fill("Senaryo UI testi")
    page.get_by_role("button", name="Fatura / Arıza kaydı").click()
    page.get_by_role("button", name="Oluştur", exact=True).click()
    expect(page.get_by_title("Sorunları göster")).to_contain_text("Akış geçerli", timeout=10_000)

    # Scenarios page: the template brought three scenarios; run one of them.
    page.get_by_role("link", name="Senaryolar").click()
    expect(page.get_by_text("Faturasına itiraz eden müşteri")).to_be_visible()
    card = page.locator("div.group").filter(has_text="Faturasına itiraz eden müşteri")
    card.get_by_title("Yalnızca bunu çalıştır").click()
    result_row = page.locator("li button").filter(has_text="Faturasına itiraz eden müşteri")
    expect(result_row).to_contain_text(FINAL, timeout=180_000)
    result_row.click()
    expect(page.get_by_text("Çağrı düzgün bitti")).to_be_visible(timeout=10_000)
    page.screenshot(path=OUT / "s1-scenarios-page.png", full_page=True)

    # Live simulation in the test panel
    page.get_by_title("Akışa dön").click()
    expect(page.get_by_role("button", name="Test et")).to_be_visible(timeout=10_000)
    page.get_by_role("button", name="Test et").click()
    drawer = page.locator("aside").filter(has_text="Test çağrısı")
    drawer.get_by_role("button", name="Simüle").click()
    drawer.get_by_role("combobox").last.select_option(label="Modemi kopan müşteri")
    drawer.get_by_role("button", name="Simülasyonu başlat").click()
    expect(drawer.get_by_text("simüle arayan").first).to_be_visible(timeout=60_000)
    page.screenshot(path=OUT / "s2-live-simulation.png")
    expect(drawer.get_by_text("Değerlendirme")).to_be_visible(timeout=180_000)
    expect(drawer.locator("span").filter(has_text=FINAL).first).to_be_visible(timeout=120_000)
    page.screenshot(path=OUT / "s3-live-verdict.png")
    browser.close()

print("screens:", OUT.resolve())
print("console problems:" if problems else "no console problems")
for line in problems:
    print("  ", line)
