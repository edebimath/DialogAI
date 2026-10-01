# DialogAI

Çağrı merkezi sesli ajanlarını sürükle-bırak bir canvas üzerinde tasarlayıp tarayıcıdan test etmek için kurum içi bir platform. Bir akış çizersiniz, sağdan açılan panelde aynı akışla yazarak ya da konuşarak bir çağrı yaparsınız ve çağrı boyunca sistemin ne yaptığını adım adım görürsünüz.

Varsayılan kurulum API anahtarı gerektirmez: LLM, konuşma tanıma ve seslendirme kendi makinenizde çalışır ([Ollama](https://ollama.com), Whisper, Piper). İsterseniz LLM olarak Google Gemini kullanılabilir.

## Neler yapabilir?

**Akış editörü**
- Canvas üzerinde kartları sürükleyip birbirine bağlayarak diyalog akışı kurulur; akış her değişiklikte otomatik kaydedilir ve hatalar kart üzerinde gösterilir.
- Kartlar: **Söylem** (sabit metin), **LLM Görevi**, **Bilgi Toplama**, **Akıllı Yönlendirici** (niyete göre dallanma), **Koşul** (değişkene göre kural tabanlı dallanma), **Bilgi Tabanı**, **HTTP Aracı** (dış servis çağrısı), **Temsilciye Aktar** (devir özetiyle) ve **Bitiş**.
- Hazır şablonlar: Fatura / Arıza kaydı, Bilgi tabanlı SSS hattı, Kargo takip hattı, Randevu hattı.
- Akışı yayınlayınca değişmez bir sürüm (v1, v2…) oluşur; eski sürümler taslağa geri yüklenebilir.
- Konuşma tanıma, seslendirme ve sıra alma ayarları ajan bazında "Ses & Model" panelinden yapılır.

**Test paneli**
- **Yazılı**, **sesli** (tarayıcı mikrofonu, WebRTC) ve **simüle** çağrı modları.
- Çağrı sırasında canvas'ta aktif kart canlı vurgulanır; zaman çizelgesinde konuşmalar, geçilen kartlar, çağrılan fonksiyonlar, toplanan değişkenler, HTTP istekleri, bilgi tabanı aramaları ve gecikme ölçümleri görünür.
- Geçmiş çağrılar (sesli olanların kaydıyla birlikte) yeniden izlenebilir.

**Bilgi tabanı**
- Doküman (PDF, DOCX, TXT, MD) yükleme ve elle soru-cevap girme; dokümanın parçaları görüntülenip düzeltilebilir.
- Anlamsal arama (pgvector). Girdilere ekrandan tanımladığınız **etiketler** verilebilir; böylece bir girdi yalnızca belirli arayanlara (ör. mevcut müşteri) gösterilir.

**Senaryo testleri**
- Bir LLM, verdiğiniz kişilik ve amaçla arayan rolüne girip ajanla konuşur; bir LLM hakem sonucu başarı kriterine göre değerlendirir. Tüm senaryolar tek seferde koşulabilir.

**Yönetim**
- Kullanıcı yönetimi ve roller: yönetici, editör, izleyici.

## Mimari

```
Tarayıcı (React) ──► nginx / Vite ──► API (FastAPI) ──► PostgreSQL + pgvector
                                          │
                                          ├──► Ollama (LLM, gömme modeli)
                                          └──► Pipecat boru hattı: Whisper (STT) · Piper (TTS) · WebRTC
```

- Canvas'taki akış bir JSON şemasıdır; çalışma anında [Pipecat Flows](https://github.com/pipecat-ai/pipecat) düğümlerine derlenir.
- Çağrının her adımı bir "olay" olarak kaydedilir; test paneli bu olayları canlı gösterir.

Kullanılan başlıca teknolojiler: Python 3.12, FastAPI, SQLAlchemy, Alembic, Pipecat 1.12; React 19, TypeScript, Vite, Tailwind, React Flow.

## Gereksinimler

- Python 3.12
- Node.js 22 veya üzeri
- PostgreSQL 17 + [pgvector](https://github.com/pgvector/pgvector) eklentisi
- [Ollama](https://ollama.com) — `ollama pull qwen3:8b` ve `ollama pull bge-m3`
- Sesli çağrı için önerilen: 8 GB belleğe sahip bir NVIDIA ekran kartı (Whisper ve LLM birlikte ~7.6 GB kullanır). Kart yoksa `WHISPER_DEVICE=cpu` ile çalışır, ancak belirgin şekilde yavaştır.

## Kurulum

**1. Veritabanı.** Süper kullanıcıyla bir rol, iki veritabanı ve pgvector eklentisini oluşturun:

```sql
CREATE ROLE dialogai LOGIN PASSWORD 'SIFRENIZ';
CREATE DATABASE dialogai OWNER dialogai;
CREATE DATABASE dialogai_test OWNER dialogai;   -- yalnızca testler için
\c dialogai
CREATE EXTENSION vector;
\c dialogai_test
CREATE EXTENSION vector;
```

pgvector'u kolayca kurmanın yolu, yalnızca veritabanını Docker ile çalıştırmaktır: `docker run -d --name dialogai-db -p 5432:5432 -e POSTGRES_PASSWORD=SIFRENIZ pgvector/pgvector:pg17`. Linux'ta `postgresql-17-pgvector` paketi de vardır.

**2. Ayarlar.** `.env.example` dosyasını `.env` olarak kopyalayıp doldurun (veritabanı adresi, `JWT_SECRET`). Seçenekler aşağıda.

**3. Backend.**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install uv
cd backend
uv pip install -r pyproject.toml --extra dev
```

**4. Arayüz.**

```bash
cd frontend
npm install
```

## Çalıştırma

İki ayrı terminalde:

```bash
# API — http://127.0.0.1:8000  (veritabanı migration'larını açılışta kendisi uygular)
cd backend
python -m uvicorn app.main:app --port 8000

# Arayüz — http://localhost:5173
cd frontend
npm run dev
```

Tarayıcıda `http://localhost:5173` adresini açın. İlk açılışta bir yönetici hesabı oluşturulur: `admin@dialogai.local` / `admin123`. Giriş yaptıktan sonra Kullanıcılar sayfasından şifreyi değiştirin.

Notlar:
- API'yi `--reload` ile çalıştırmayın: sesli çağrılardan sonra Windows'ta takılıyor. Backend'de değişiklik yapınca API'yi yeniden başlatın.
- Sesli test için tarayıcıya mikrofon izni verin. Çağrı kayıtları `data/recordings/` altına yazılır.
- Whisper ve Piper modelleri ilk sesli çağrıda (ya da API açılışında) indirilir.

## Yapılandırma

Ayarlar `.env` dosyasından (ya da ortam değişkenlerinden) okunur; tam liste [backend/app/core/config.py](backend/app/core/config.py) içindedir.

| Değişken | Açıklama |
|---|---|
| `DATABASE_URL` | PostgreSQL bağlantısı (`postgresql+asyncpg://…`) |
| `JWT_SECRET` | Oturum imzalama anahtarı; en az 32 karakter, rastgele |
| `OLLAMA_URL` | Ollama adresi (varsayılan `http://127.0.0.1:11434`) |
| `WHISPER_DEVICE` | `cuda` (varsayılan) ya da `cpu` |
| `GOOGLE_API_KEY` | Gemini'yi LLM olarak kullanmak için (isteğe bağlı) |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | İlk yönetici hesabı |
| `DATA_DIR` | Yüklenen dosyalar ve çağrı kayıtları klasörü |
| `HTTP_TOOL_ALLOWED_HOSTS` | HTTP Aracı'nın çağırabileceği sunucular (boşsa, engellenenler dışında hepsi) |
| `SECRET_<AD>` | HTTP Aracı gizli değerleri; kartta `{{ secret.ad }}` olarak kullanılır |
| `APP_ENV` | `production` iken güvenli olmayan ayarlarla başlamaz (aşağıya bakın) |

## Üretim ve güvenlik

`APP_ENV=production` olduğunda:
- API varsayılan ya da kısa `JWT_SECRET`, varsayılan yönetici şifresi veya varsayılan veritabanı şifresiyle **başlamaz**;
- API belgeleri (`/docs`) ve şablonların kullandığı demo servisleri kapalıdır (`DEMO_API=true` ile açılır).

Diğer önlemler:
- Hatalı girişlerde geçici kilit; şifre değişince eski oturumlar geçersiz olur.
- HTTP Aracı, bulut metadata adresi, link-local adresler ve sistemin kendi veritabanı/Ollama uç noktalarına istek atamaz; yönlendirmeleri izlemez, cevabı sınırlar. Sunucu listesi `HTTP_TOOL_ALLOWED_HOSTS` ile daraltılabilir.
- API anahtarları akışa yazılmaz: sunucuda `SECRET_CRM_TOKEN` gibi tanımlanır, kartta `{{ secret.crm_token }}` yazılır. Değer kayıtlarda maskelenir.
- Yüklemeler boyut ve tür açısından denetlenir; nginx güvenlik başlıklarını ve içerik güvenlik politikasını ekler.
- Oturum anahtarı tarayıcıda `localStorage`'da tutulur; güvenilmeyen bir alan adında çalıştırmayın.

## Docker ile kurulum

Beş servis: PostgreSQL + pgvector, Ollama (ilk açılışta modeller otomatik indirilir), API ve nginx arkasında arayüz. Docker Compose v2.24 veya üzeri gerekir.

```bash
cd deploy
cp .env.example .env                 # veritabanı şifresi, JWT anahtarı, yönetici şifresi
cp secrets.env.example secrets.env   # isteğe bağlı: HTTP Aracı gizli değerleri
docker compose up -d --build                                                   # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build   # NVIDIA GPU
```

Arayüz `http://<sunucu>:8080` adresinde açılır. İlk açılış modelleri indirdiği için uzun sürer (qwen3:8b yaklaşık 5 GB); modeller volume'larda kalır.

- **GPU:** sunucuda NVIDIA sürücüsü ve NVIDIA Container Toolkit gerekir.
- **Başka makinelerden sesli çağrı:** tarayıcılar mikrofona yalnızca https üzerinde izin verir ve WebRTC sesi tarayıcı ile API arasında doğrudan UDP ile gider. Bunun için Linux sunucuda `docker-compose.lan.yml` eklentisini kullanın ve `deploy/certs/` altına bir TLS sertifikası koyun ([deploy/certs/README.md](deploy/certs/README.md)); arayüz `https://<sunucu>:8443` olur. Yazılı test ve simülasyonlar bu eklenti olmadan da her yerden çalışır.
- **Demo servisleri** üretimde kapalıdır; şablonları denemek için `deploy/.env` içinde `DEMO_API=true` yapın.
- **Yedekleme:** `db-data` (veritabanı) ve `app-data` (yüklenen dosyalar, kayıtlar) volume'ları.
- API tek süreç olarak çalışır (canlı çağrılar ve kuyruklar bellektedir); birden fazla API konteyneri çalıştırmayın.

## Testler

```bash
# Birim ve API testleri (TEST_DATABASE_URL gerekir; tablolar her çalıştırmada sıfırlanır)
cd backend
python -m pytest

# Tarayıcı testleri: API, arayüz ve Ollama açıkken
cd frontend
playwright install chromium     # bir kereye mahsus
python e2e/ui_smoke.py          # yazılı çağrı
python e2e/voice_ui_smoke.py    # sahte mikrofonla sesli çağrı
python e2e/kb_ui_smoke.py       # bilgi tabanı ve etiketler
python e2e/scenarios_ui_smoke.py
python e2e/tools_ui_smoke.py    # HTTP Aracı ve Temsilciye Aktar
```

`backend/scripts/` altında çalışan bir API'ye karşı uçtan uca denemeler (yazılı çağrı, WebRTC sesli çağrı, bilgi tabanı, senaryo koşusu) bulunur.

## Proje yapısı

```
backend/app/api/         REST uçları ve test oturumu WebSocket'i
backend/app/flows/       akış şeması, doğrulayıcı, derleyici, şablonlar, HTTP Aracı
backend/app/runtime/     çağrı oturumu (Pipecat boru hattı), sağlayıcılar, ses servisleri
backend/app/trace/       çağrı olayları ve gözlemci
backend/app/kb/          bilgi tabanı: ayrıştırma, gömme, indeksleme, arama, etiketler
backend/app/simulation/  simüle arayan, LLM hakem, senaryo koşuları
backend/app/db/          modeller ve veritabanı bağlantısı
backend/migrations/      Alembic migration'ları
frontend/src/editor/     canvas, kart kataloğu, düzenleme panelleri
frontend/src/test/       sağdan açılan test paneli
frontend/src/knowledge/  bilgi tabanı ekranları
deploy/                  Docker Compose dosyaları
```

Akış şeması iki yerde tanımlıdır ve birlikte değişmelidir: `backend/app/flows/schema.py` ve `frontend/src/lib/types.ts`.

## Kullanım amacı ve lisans notları

DialogAI ticari bir ürün değil; sesli ajan akışlarının nasıl tasarlanıp test edilebileceğini gösteren bir **açık kaynak örnek projedir**. Kişisel, eğitim ve araştırma amaçlı olarak serbestçe inceleyebilir, çalıştırabilir ve geliştirebilirsiniz.

Üçüncü taraf bileşenlerin kendi lisansları geçerlidir; bunlar depoda bulunmaz, kurulumda ayrıca indirilir:
- **Varsayılan Türkçe ses** (`tr_TR-dfki-medium`) CC BY-NC-SA lisanslıdır: yalnızca ticari olmayan kullanıma izin verir. Projeyi ticari bir ortamda kullanacaksanız bu sesi, kullanım hakkı uygun bir sesle değiştirmeniz gerekir.
- **Piper TTS** GPL-3.0 lisanslıdır.
- Whisper modelleri, Qwen3 ve bge-m3 kendi lisanslarıyla gelir; kullanmadan önce kendi koşullarına bakın.

Docker yapılandırması farklı makinelerde henüz yaygın denenmedi; sorun çıkarsa lütfen bildirin.
