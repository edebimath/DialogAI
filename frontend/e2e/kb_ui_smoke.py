"""Browser: a tag created on the tags screen -> knowledge base with a file and tagged
question-answer entries -> chunk edit -> tag filter -> search as a caller -> tag renamed and
deleted -> SSS agent whose caller lookup tags the call.

Needs the API (:8000), Vite (:5173) and Ollama (qwen3:8b, bge-m3) running.
Usage: python e2e/kb_ui_smoke.py [screenshot_dir]
"""

import re
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e/screens")
OUT.mkdir(parents=True, exist_ok=True)
STAMP = int(time.time())
KB_NAME = f"UI SSS {STAMP}"
CUSTOM_TAG = f"ui etiketi {STAMP}"
RENAMED_TAG = f"ui kategori {STAMP}"
SAMPLE = Path(__file__).resolve().parents[2] / "backend" / "scripts" / "samples" / "ornek_telekom_sss.md"
LOYAL = "Sadakat indirimi var mı?"
WELCOME = "Yeni müşteri kampanyası var mı?"
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

    # A tag of our own, defined on the tags screen
    page.get_by_role("link", name="Bilgi Tabanları").click()
    page.get_by_role("link", name="Etiketler").click()
    page.get_by_role("button", name="Yeni etiket").click()
    tag_dialog = page.locator("div.fixed").filter(has_text="Yeni etiket")
    tag_dialog.get_by_placeholder("Ör. VIP müşteri").fill(CUSTOM_TAG.upper().replace("I", "İ"))
    tag_dialog.get_by_role("textbox").nth(1).fill("Arayüz testinin oluşturduğu kategori")
    tag_dialog.get_by_role("button", name="sky").click()
    tag_dialog.get_by_role("button", name="Oluştur").click()
    expect(page.locator("tr").filter(has_text=CUSTOM_TAG)).to_contain_text("Arayüz testinin oluşturduğu kategori")
    page.screenshot(path=OUT / "k0-tags.png")

    page.get_by_role("link", name="Bilgi tabanları", exact=True).click()
    page.get_by_role("button", name="Yeni bilgi tabanı").click()
    page.get_by_placeholder("Ör. Fatura ve ödeme SSS").fill(KB_NAME)
    page.get_by_role("button", name="Oluştur", exact=True).click()
    expect(page.get_by_text("Soru-cevap", exact=True).first).to_be_visible()  # empty state explains both kinds

    # A file, and two question-answer entries for different callers
    page.locator("input[type=file]").set_input_files(str(SAMPLE))
    file_row = page.locator("li").filter(has_text="ornek_telekom_sss.md")
    expect(file_row).to_contain_text(re.compile(r"\d+ parça"), timeout=30_000)

    def add_qa(question: str, answer: str, tag: str) -> None:
        page.get_by_role("button", name="Soru-cevap ekle").first.click()
        dialog = page.locator("div.fixed").filter(has_text="Yeni soru-cevap")
        dialog.get_by_placeholder("Ör. Faturamı ne zamana kadar ödemeliyim?").fill(question)
        dialog.get_by_placeholder("Ör. Son ödeme günü her ayın 15'idir.").fill(answer)
        tags = dialog.get_by_label("Etiket ara veya oluştur")
        tags.fill(tag)
        tags.press("Enter")  # picks the defined tag, or creates it
        dialog.get_by_role("button", name="Kaydet").click()
        expect(dialog).to_be_hidden(timeout=15_000)

    add_qa(LOYAL, "Mevcut müşterilerimize her yıl yüzde 20 sadakat indirimi uygulanır.", "Mevcut Müşteri")
    add_qa(WELCOME, "Yeni müşterilerimize ilk üç ay yüzde 50 indirim uygulanır.", "yeni müşteri")
    add_qa("Kurumsal fatura nasıl alınır?", "Vergi numaranızı iletmeniz yeterlidir.", str(STAMP))  # typed part of the name, picked from the list
    expect(page.locator("li").filter(has_text="Kurumsal fatura")).to_contain_text(CUSTOM_TAG)
    expect(page.locator("li").filter(has_text=LOYAL)).to_contain_text("mevcut müşteri")  # normalized
    page.screenshot(path=OUT / "k1-entries.png", full_page=True)

    # Tag filter
    page.locator("span").filter(has_text=re.compile("^yeni müşteri$")).first.click()
    expect(page.locator("li").filter(has_text=LOYAL)).to_be_hidden()
    expect(page.locator("li").filter(has_text=WELCOME)).to_be_visible()
    page.get_by_role("button", name="temizle").click()

    # The file's chunks, one edited by hand
    file_row.get_by_role("button").first.click()
    dialog = page.locator("div.fixed").filter(has_text="Parçalar")
    expect(dialog.get_by_text("#1", exact=True)).to_be_visible()
    first = dialog.locator("div.group").first
    first.get_by_title("Düzenle").click()
    first.locator("textarea").fill("Müşteri hizmetlerine hafta içi 08:00-22:00 arasında 444 0 000 numarasından ulaşabilirsiniz.")
    first.get_by_role("button", name="Kaydet").click()
    expect(first.get_by_text("elle düzenlendi")).to_be_visible(timeout=15_000)
    page.screenshot(path=OUT / "k2-chunks.png")
    page.get_by_role("button", name="Kapat").click()
    expect(file_row).to_contain_text("1 parça elle düzenlendi")

    # Search as a new customer: the loyalty answer is not for them
    tester = page.locator("section").filter(has_text="Deneme araması")
    tester.get_by_role("button", name="Bir arayan gibi").click()
    caller_tags = tester.get_by_label("Etiket ara veya oluştur")
    caller_tags.fill("yeni müşteri")
    caller_tags.press("Enter")
    tester.get_by_placeholder("Ör. İndirim var mı?").fill("indirim var mı")
    tester.get_by_role("button", name="Ara", exact=True).click()
    expect(tester.get_by_text(WELCOME, exact=True)).to_be_visible(timeout=10_000)
    expect(tester.get_by_text(LOYAL, exact=True)).to_be_hidden()
    page.screenshot(path=OUT / "k3-search-as-caller.png", full_page=True)

    # Renaming the tag reaches the entry; deleting it leaves the entry for everyone.
    kb_url = page.url
    page.goto(f"{BASE}/knowledge/tags")
    page.locator("tr").filter(has_text=CUSTOM_TAG).get_by_title("Düzenle").click()
    edit = page.locator("div.fixed").filter(has_text="Etiketi düzenle")
    edit.get_by_placeholder("Ör. VIP müşteri").fill(RENAMED_TAG)
    expect(edit.get_by_text("1 girdiye de yansır")).to_be_visible()
    edit.get_by_role("button", name="Kaydet").click()
    expect(page.locator("tr").filter(has_text=RENAMED_TAG)).to_be_visible()
    page.goto(kb_url)
    expect(page.locator("li").filter(has_text="Kurumsal fatura")).to_contain_text(RENAMED_TAG)
    page.goto(f"{BASE}/knowledge/tags")
    page.locator("tr").filter(has_text=RENAMED_TAG).get_by_title("Sil").click()
    page.locator("div.fixed").filter(has_text="Etiketi sil").get_by_role("button", name="Sil").click()
    expect(page.locator("tr").filter(has_text=RENAMED_TAG)).to_be_hidden()
    page.goto(kb_url)
    expect(page.locator("li").filter(has_text="Kurumsal fatura")).to_contain_text("Herkese")

    # SSS agent: the caller lookup tags the call "mevcut müşteri" (demo number by default)
    page.get_by_role("link", name="Ajanlar").click()
    page.get_by_role("button", name="Yeni ajan").click()
    page.get_by_placeholder("Ör. Fatura destek hattı").fill("UI SSS hattı")
    page.get_by_role("button", name="Bilgi tabanlı SSS hattı").click()
    page.get_by_role("button", name="Oluştur", exact=True).click()
    issues = page.get_by_title("Sorunları göster")
    expect(issues).to_contain_text("hata", timeout=10_000)
    page.locator(".react-flow__node").filter(has_text="Soruları cevapla").click()
    page.get_by_role("checkbox", name=KB_NAME).check()
    expect(issues).to_contain_text("Akış geçerli", timeout=5_000)
    page.locator(".react-flow__pane").click(position={"x": 50, "y": 50})
    expect(page.locator("input[value='{{ musteri_tipi }}']")).to_be_visible()
    page.screenshot(path=OUT / "k4-sss-flow.png")

    page.get_by_role("button", name="Test et").click()
    drawer = page.locator("aside").filter(has_text="Test çağrısı")
    drawer.get_by_role("button", name="Yazılı").click()
    drawer.get_by_role("button", name="Çağrıyı başlat").click()
    expect(drawer.get_by_text("Hangi konuda bilgi almak istersiniz")).to_be_visible(timeout=20_000)
    box = drawer.get_by_placeholder("Arayan olarak yazın…")
    box.fill("Sadakat indirimi var mı?")
    box.press("Enter")
    expect(drawer.get_by_text("Arayan etiketleri: mevcut müşteri")).to_be_visible(timeout=60_000)
    expect(drawer.get_by_text("Ajan düşünüyor…")).to_be_hidden(timeout=60_000)
    page.screenshot(path=OUT / "k5-tagged-call.png")
    answer = drawer.inner_text()
    browser.close()

print("screens:", OUT.resolve())
print("answer mentions 20:", "20" in answer)
print("console problems:" if problems else "no console problems")
for line in problems:
    print("  ", line)
