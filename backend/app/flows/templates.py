"""Ready-made flows offered when creating an agent."""

from app.flows.schema import FlowGraph

# The HTTP templates call the stand-in APIs in app/api/demo.py; point api_adresi elsewhere to
# use a real service with the same fields.
DEMO_API = "http://127.0.0.1:8000/api/demo"

ARIZA_FATURA = {
    "schema_version": 1,
    "global": {
        "persona": "Sen {{ sirket_adi }} şirketinin çağrı merkezi asistanısın. Nazik ve çözüm odaklısın.",
        "rules": "Kişisel verileri yalnızca kayıt açmak için iste.",
    },
    "variables": [{"name": "sirket_adi", "description": "Şirketin adı", "default": "Örnek Telekom"}],
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 80}},
        {
            "id": "karsilama",
            "type": "say",
            "label": "Karşılama",
            "text": "{{ sirket_adi }} müşteri hizmetlerine hoş geldiniz. Size nasıl yardımcı olabilirim?",
            "position": {"x": 220, "y": 40},
        },
        {
            "id": "yonlendir",
            "type": "llm_router",
            "label": "Talep yönlendirme",
            "prompt": "Arayanın talebini anla.",
            "routes": [
                {"id": "fatura", "description": "Fatura, ücret veya ödeme sorusu"},
                {"id": "ariza", "description": "İnternet, modem veya hat arızası"},
            ],
            "position": {"x": 540, "y": 20},
        },
        {
            "id": "musteri_no",
            "type": "collect",
            "label": "Müşteri numarası",
            "prompt": "Müşteriye sorununu anladığını kısaca söyle.",
            "fields": [
                {"name": "musteri_no", "description": "Müşteri numarası, yalnızca rakamlar"}
            ],
            "fallback": True,
            "position": {"x": 880, "y": 40},
        },
        {
            "id": "numara_var_mi",
            "type": "condition",
            "label": "Numara alındı mı?",
            "rules": [{"id": "var", "variable": "musteri_no", "operator": "exists"}],
            "position": {"x": 1200, "y": 40},
        },
        {
            "id": "kayit_acildi",
            "type": "end",
            "label": "Kayıt açıldı",
            "text": "{{ musteri_no }} numaralı kaydınız açıldı, bir temsilcimiz en kısa sürede sizi arayacak. İyi günler dileriz.",
            "outcome": "ticket_created",
            "position": {"x": 1520, "y": -60},
        },
        {
            "id": "temsilci",
            "type": "transfer",
            "label": "Temsilciye aktar",
            "target": "Müşteri hizmetleri",
            "text": "Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 1520, "y": 160},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "karsilama"},
        {"id": "e2", "source": "karsilama", "target": "yonlendir"},
        {"id": "e3", "source": "yonlendir", "source_handle": "fatura", "target": "musteri_no"},
        {"id": "e4", "source": "yonlendir", "source_handle": "ariza", "target": "musteri_no"},
        {"id": "e5", "source": "musteri_no", "target": "numara_var_mi"},
        {"id": "e8", "source": "musteri_no", "source_handle": "fallback", "target": "temsilci"},
        {"id": "e6", "source": "numara_var_mi", "source_handle": "var", "target": "kayit_acildi"},
        {"id": "e7", "source": "numara_var_mi", "source_handle": "else", "target": "temsilci"},
    ],
}

SSS = {
    "schema_version": 1,
    "global": {
        "persona": "Sen {{ sirket_adi }} şirketinin çağrı merkezi asistanısın. Nazik ve net konuşursun.",
        "rules": "",
        "kb_ids": [],
        # Entries tagged "mevcut müşteri" or "yeni müşteri" only reach those callers.
        "caller_tags": "{{ musteri_tipi }}",
    },
    "variables": [
        {"name": "sirket_adi", "description": "Şirketin adı", "default": "Örnek Telekom"},
        {"name": "arayan_no", "description": "Arayanın telefon numarası (santralden gelir)", "default": "05321112233"},
        {"name": "api_adresi", "description": "Müşteri sorgulama servisinin adresi", "default": DEMO_API},
    ],
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 80}},
        {
            "id": "arayan",
            "type": "http_request",
            "label": "Arayanı tanı",
            "method": "GET",
            "url": "{{ api_adresi }}/musteri?telefon={{ arayan_no }}",
            "outputs": [
                {"variable": "musteri_tipi", "path": "tip"},
                {"variable": "musteri_adi", "path": "ad"},
            ],
            "position": {"x": 220, "y": 40},
        },
        {
            "id": "karsilama",
            "type": "say",
            "label": "Karşılama",
            "text": "{{ sirket_adi }} müşteri hizmetlerine hoş geldiniz. Hangi konuda bilgi almak istersiniz?",
            "position": {"x": 540, "y": 40},
        },
        {
            "id": "sss",
            "type": "kb_answer",
            "label": "Soruları cevapla",
            "prompt": "Müşterinin sorularını bilgi tabanına dayanarak cevapla. Her cevaptan sonra başka bir sorusu olup olmadığını sor.",
            "kb_ids": [],
            "top_k": 4,
            "exits": [
                {"id": "bitti", "description": "Müşterinin başka sorusu yok"},
                {"id": "temsilci", "description": "Müşteri bir temsilciyle görüşmek istiyor"},
            ],
            "position": {"x": 860, "y": 20},
        },
        {
            "id": "vedalas",
            "type": "end",
            "label": "Vedalaşma",
            "text": "Bizi aradığınız için teşekkür ederiz, iyi günler dileriz.",
            "outcome": "resolved",
            "position": {"x": 1200, "y": -60},
        },
        {
            "id": "aktar",
            "type": "transfer",
            "label": "Temsilciye aktar",
            "target": "Müşteri hizmetleri",
            "text": "Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 1200, "y": 160},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "arayan"},
        {"id": "e5", "source": "arayan", "target": "karsilama"},
        # Lookup down: carry on untagged; only entries for everyone are used.
        {"id": "e6", "source": "arayan", "source_handle": "error", "target": "karsilama"},
        {"id": "e2", "source": "karsilama", "target": "sss"},
        {"id": "e3", "source": "sss", "source_handle": "bitti", "target": "vedalas"},
        {"id": "e4", "source": "sss", "source_handle": "temsilci", "target": "aktar"},
    ],
}

ARIZA_FATURA_SCENARIOS = [
    {
        "name": "Modemi kopan müşteri",
        "persona": "Ayşe, 45 yaşında, sabırlı ama teknolojiden pek anlamayan bir ev hanımı. Müşteri numarası 552190.",
        "goal": "İki gündür kopan internet için arıza kaydı açtırmak.",
        "success_criteria": "Ajan arıza kaydını müşterinin verdiği 552190 numarasıyla açtığını söyledi.",
        "expected_outcome": "ticket_created",
    },
    {
        "name": "Faturasına itiraz eden müşteri",
        "persona": "Mehmet, 38 yaşında, biraz sinirli bir esnaf. Bu ayki faturasında bilmediği 120 liralık bir ücret var. Müşteri numarası 771230.",
        "goal": "Faturadaki fazla ücret için kayıt açtırmak.",
        "success_criteria": "Ajan talebin fatura ile ilgili olduğunu anladı ve 771230 numarasıyla kayıt açıldığını söyledi.",
        "expected_outcome": "ticket_created",
    },
    {
        "name": "Numarasını bilmeyen müşteri",
        "persona": "Hasan, 70 yaşında, emekli. Müşteri numarasını bilmiyor ve bulamıyor; sorulursa bilmediğini söyler.",
        "goal": "İnternetinin çalışmadığını bildirmek.",
        "success_criteria": "Ajan, müşteri numarası alınmadan kayıt açıldığını söylemedi.",
        "expected_outcome": "transferred",
    },
]

SSS_SCENARIOS = [
    {
        "name": "Son ödeme gününü soran müşteri",
        "persona": "Zeynep, 29 yaşında, işinden telefonla arayan aceleci bir müşteri.",
        "goal": "Faturanın son ödeme gününü öğrenmek, sonra teşekkür edip kapatmak.",
        "success_criteria": "Ajan son ödeme tarihinin ayın 15'i olduğunu söyledi.",
        "expected_outcome": "resolved",
    },
    {
        "name": "Bilgi tabanında olmayan soru",
        "persona": "Can, 34 yaşında, yurt dışı seyahatine çıkacak bir müşteri.",
        "goal": "Yurt dışında roaming ücretinin ne kadar olduğunu öğrenmek.",
        "success_criteria": "Ajan roaming ücreti için bir rakam uydurmadı; bu bilginin olmadığını söyledi veya temsilciye yönlendirdi.",
    },
    {
        "name": "Temsilci isteyen müşteri",
        "persona": "Elif, 52 yaşında, otomatik sistemlerle konuşmayı sevmeyen bir müşteri.",
        "goal": "Hemen bir müşteri temsilcisiyle görüşmek.",
        "success_criteria": "Ajan müşteriyi bir temsilciye aktardığını söyledi.",
        "expected_outcome": "transferred",
    },
]

KARGO = {
    "schema_version": 1,
    "global": {
        "persona": "Sen {{ firma_adi }} kargo şirketinin çağrı merkezi asistanısın. Nazik, sakin ve net konuşursun.",
        "rules": "Gönderi hakkında yalnızca sistemden gelen bilgileri söyle, tahminde bulunma.",
        "kb_ids": [],
    },
    "variables": [
        {"name": "firma_adi", "description": "Kargo şirketinin adı", "default": "Örnek Kargo"},
        {"name": "api_adresi", "description": "Gönderi sorgulama servisinin adresi", "default": DEMO_API},
    ],
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 120}},
        {
            "id": "karsilama",
            "type": "say",
            "label": "Karşılama",
            "text": "{{ firma_adi }} kargo takip hattına hoş geldiniz. Gönderinizin takip numarasını söyler misiniz?",
            "position": {"x": 220, "y": 80},
        },
        {
            "id": "takip",
            "type": "collect",
            "label": "Takip numarası",
            "prompt": "",
            "fields": [{"name": "takip_no", "description": "Gönderi takip numarası, yalnızca rakamlar"}],
            "fallback": True,
            "position": {"x": 540, "y": 80},
        },
        {
            "id": "sorgu",
            "type": "http_request",
            "label": "Gönderiyi sorgula",
            "method": "GET",
            "url": "{{ api_adresi }}/kargo/{{ takip_no }}",
            "outputs": [
                {"variable": "durum", "path": "durum"},
                {"variable": "durum_metni", "path": "durum_metni"},
                {"variable": "sube", "path": "sube"},
            ],
            "position": {"x": 860, "y": 80},
        },
        {
            "id": "durum_bilgisi",
            "type": "say",
            "label": "Durumu bildir",
            "text": "{{ durum_metni }} Başka bir konuda yardımcı olabilir miyim?",
            "position": {"x": 1180, "y": 0},
        },
        {
            "id": "yardim",
            "type": "llm_task",
            "label": "Ek sorular",
            "prompt": "Gönderinin durumu: {{ durum_metni }} İlgili şube: {{ sube }}. Arayanın gönderiyle ilgili sorularını yalnızca bu bilgilere dayanarak kısaca cevapla; bilmediğin bir şeyi uydurma. Arayan teşekkür eder, vedalaşır veya başka isteği olmadığını söylerse cevap yazma, hemen ilgili fonksiyonu çağır.",
            "exits": [
                {"id": "bitti", "description": "Arayanın başka sorusu veya isteği yok"},
                {"id": "sikayet", "description": "Arayan şikayet etmek, paketini alamadığını bildirmek veya bir temsilciyle görüşmek istiyor"},
            ],
            "position": {"x": 1500, "y": 0},
        },
        {
            "id": "vedalas",
            "type": "end",
            "label": "Vedalaşma",
            "text": "Bizi aradığınız için teşekkür ederiz, iyi günler dileriz.",
            "outcome": "resolved",
            "position": {"x": 1840, "y": -80},
        },
        {
            "id": "sikayet_aktar",
            "type": "transfer",
            "label": "Şikayet birimine aktar",
            "target": "Şikayet birimi",
            "text": "Talebinizi anladım. Sizi şikayet birimimizdeki bir temsilcimize aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 1840, "y": 140},
        },
        {
            "id": "bulunamadi",
            "type": "transfer",
            "label": "Gönderi bulunamadı",
            "target": "Müşteri hizmetleri",
            "text": "{{ takip_no }} numarasıyla bir gönderi bulamadım. Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 1180, "y": 260},
        },
        {
            "id": "numarasiz",
            "type": "transfer",
            "label": "Numara yok",
            "target": "Müşteri hizmetleri",
            "text": "Takip numarası olmadan gönderinizi sorgulayamıyorum. Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 860, "y": 360},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "karsilama"},
        {"id": "e2", "source": "karsilama", "target": "takip"},
        {"id": "e3", "source": "takip", "target": "sorgu"},
        {"id": "e4", "source": "takip", "source_handle": "fallback", "target": "numarasiz"},
        {"id": "e5", "source": "sorgu", "target": "durum_bilgisi"},
        {"id": "e6", "source": "sorgu", "source_handle": "error", "target": "bulunamadi"},
        {"id": "e7", "source": "durum_bilgisi", "target": "yardim"},
        {"id": "e8", "source": "yardim", "source_handle": "bitti", "target": "vedalas"},
        {"id": "e9", "source": "yardim", "source_handle": "sikayet", "target": "sikayet_aktar"},
    ],
}

KARGO_SCENARIOS = [
    {
        "name": "Paketini bekleyen müşteri",
        "persona": "Selin, 27 yaşında, evden çalışan bir grafiker. Gönderi takip numarası 123456.",
        "goal": "Paketinin ne zaman geleceğini öğrenmek, sonra teşekkür edip kapatmak.",
        "success_criteria": "Ajan gönderinin yolda olduğunu ve yarın 18:00'e kadar teslim edilmesinin beklendiğini söyledi.",
        "expected_outcome": "resolved",
    },
    {
        "name": "Paketi eline geçmeyen müşteri",
        "persona": "Burak, 44 yaşında, sinirli bir muhasebeci. Takip numarası 654321. Sistem paketi teslim edildi gösteriyor ama paket eline geçmedi; bundan şikayetçi ve bir yetkiliyle görüşmek istiyor.",
        "goal": "Paketin neden teslim edildi göründüğünü öğrenmek ve şikayetini bir yetkiliye iletmek.",
        "success_criteria": "Ajan gönderinin bina görevlisine teslim edildiğini söyledi ve müşteriyi bir temsilciye aktardı.",
        "expected_outcome": "transferred",
    },
    {
        "name": "Yanlış takip numarası",
        "persona": "Nur, 66 yaşında, emekli bir öğretmen. Takip numarası olarak 999888 verir (bu numara sistemde yok).",
        "goal": "Kızının gönderdiği paketin nerede olduğunu öğrenmek.",
        "success_criteria": "Ajan bu numarayla bir gönderi bulamadığını söyledi ve gönderi için bir durum uydurmadı.",
        "expected_outcome": "transferred",
    },
]

RANDEVU = {
    "schema_version": 1,
    "global": {
        "persona": "Sen {{ kurum_adi }} randevu hattının asistanısın. Güler yüzlü ve kısa konuşursun.",
        "rules": "Randevu saatlerini yalnızca sistemden gelen listeden öner, saat uydurma.",
        "kb_ids": [],
    },
    "variables": [
        {"name": "kurum_adi", "description": "Kurumun adı", "default": "Örnek Klinik"},
        {"name": "api_adresi", "description": "Randevu servisinin adresi", "default": DEMO_API},
    ],
    "nodes": [
        {"id": "start", "type": "start", "position": {"x": 0, "y": 120}},
        {
            "id": "karsilama",
            "type": "say",
            "label": "Karşılama",
            "text": "{{ kurum_adi }} randevu hattına hoş geldiniz. Randevu için adınızı, soyadınızı ve hangi gün gelmek istediğinizi söyler misiniz?",
            "position": {"x": 220, "y": 80},
        },
        {
            "id": "bilgiler",
            "type": "collect",
            "label": "Ad ve gün",
            "prompt": "Boş saatleri sen bilemezsin, sistem sorgulayacak: saat önerme, randevu oluşturduğunu söyleme.",
            "fields": [
                {"name": "ad_soyad", "description": "Arayanın adı ve soyadı"},
                {"name": "gun", "description": "Randevu istenen gün, arayanın söylediği gibi (ör. salı, yarın)"},
            ],
            "position": {"x": 540, "y": 80},
        },
        {
            "id": "gun",
            "type": "collect",
            "label": "Yeni gün",
            "prompt": "Arayan yeni bir gün söylediği anda bilgileri_kaydet fonksiyonunu çağır. Saat önerme, randevu oluşturduğunu söyleme.",
            "fields": [{"name": "gun", "description": "Arayanın yeni istediği gün (ör. salı, yarın)"}],
            "position": {"x": 860, "y": 380},
        },
        {
            "id": "musait",
            "type": "http_request",
            "label": "Boş saatleri sorgula",
            "method": "GET",
            "url": "{{ api_adresi }}/randevu/musait?gun={{ gun }}",
            "outputs": [
                {"variable": "musait", "path": "musait"},
                {"variable": "gun_adi", "path": "gun"},
                {"variable": "saatler", "path": "saatler"},
                {"variable": "musait_mesaj", "path": "mesaj"},
            ],
            "position": {"x": 860, "y": 80},
        },
        {
            "id": "bos_mu",
            "type": "condition",
            "label": "Boş saat var mı?",
            "rules": [{"id": "var", "variable": "musait", "operator": "eq", "value": "true"}],
            "position": {"x": 1180, "y": 80},
        },
        {
            "id": "baska_gun",
            "type": "say",
            "label": "Başka gün iste",
            "text": "{{ musait_mesaj }} Başka hangi gün sizin için uygun olur?",
            "position": {"x": 1180, "y": 380},
        },
        {
            "id": "saat",
            "type": "collect",
            "label": "Saat seçimi",
            "prompt": "{{ gun_adi }} günü için boş saatler: {{ saatler }}. Bu saatleri arayana söyle ve hangisini istediğini sor. Arayan bu saatlerin hiçbirine gelemeyeceğini söylerse ısrar etme.",
            "fields": [{"name": "saat", "description": "Arayanın listeden seçtiği saat, SS:DD biçiminde (ör. 14:00)"}],
            "fallback": True,
            "position": {"x": 1820, "y": 20},
        },
        {
            "id": "gun_degistir",
            "type": "say",
            "label": "Gün değiştir",
            "text": "Anlıyorum, başka bir güne bakalım. Hangi gün uygun olur?",
            "position": {"x": 1820, "y": 380},
        },
        {
            "id": "olustur",
            "type": "http_request",
            "label": "Randevuyu oluştur",
            "method": "POST",
            "url": "{{ api_adresi }}/randevu",
            "body": '{"ad_soyad": "{{ ad_soyad }}", "gun": "{{ gun_adi }}", "saat": "{{ saat }}"}',
            "outputs": [
                {"variable": "randevu_no", "path": "randevu_no"},
                {"variable": "saat", "path": "saat"},
            ],
            "position": {"x": 2140, "y": 20},
        },
        {
            "id": "saat_dolu",
            "type": "say",
            "label": "Saat uygun değil",
            "text": "Seçtiğiniz saat uygun değil. {{ gun_adi }} günü için boş saatler: {{ saatler }}. Hangisini istersiniz?",
            "position": {"x": 2140, "y": 300},
        },
        {
            "id": "onay",
            "type": "end",
            "label": "Randevu oluşturuldu",
            "text": "{{ ad_soyad }}, {{ gun_adi }} günü saat {{ saat }} için randevunuz oluşturuldu. Randevu numaranız {{ randevu_no }}. Sağlıklı günler dileriz.",
            "outcome": "appointment_booked",
            "position": {"x": 2460, "y": 20},
        },
        {
            "id": "sistem_hatasi",
            "type": "transfer",
            "label": "Sistem hatası",
            "target": "Randevu birimi",
            "text": "Şu anda randevu sistemine ulaşamıyorum. Sizi bir temsilcimize aktarıyorum, lütfen hatta kalın.",
            "position": {"x": 1500, "y": -180},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "karsilama"},
        {"id": "e2", "source": "karsilama", "target": "bilgiler"},
        {"id": "e3", "source": "bilgiler", "target": "musait"},
        {"id": "e4", "source": "gun", "target": "musait"},
        {"id": "e5", "source": "musait", "target": "bos_mu"},
        {"id": "e6", "source": "musait", "source_handle": "error", "target": "sistem_hatasi"},
        {"id": "e7", "source": "bos_mu", "source_handle": "var", "target": "saat"},
        {"id": "e8", "source": "bos_mu", "source_handle": "else", "target": "baska_gun"},
        {"id": "e9", "source": "baska_gun", "target": "gun"},
        {"id": "e10", "source": "saat", "target": "olustur"},
        {"id": "e11", "source": "saat", "source_handle": "fallback", "target": "gun_degistir"},
        {"id": "e12", "source": "gun_degistir", "target": "gun"},
        {"id": "e13", "source": "olustur", "target": "onay"},
        {"id": "e14", "source": "olustur", "source_handle": "error", "target": "saat_dolu"},
        {"id": "e15", "source": "saat_dolu", "target": "saat"},
    ],
}

RANDEVU_SCENARIOS = [
    {
        "name": "Salı öğleden sonra randevu",
        "persona": "Fatma Demir, 41 yaşında bir öğretmen. Salı günü öğleden sonra gelebilir; sunulan saatlerden öğleden sonraki ilk saati seçer.",
        "goal": "Salı günü öğleden sonrası için randevu almak.",
        "success_criteria": "Ajan Fatma Demir adına salı günü öğleden sonra bir saate randevu oluşturduğunu söyledi ve randevu numarasını verdi.",
        "expected_outcome": "appointment_booked",
    },
    {
        "name": "Pazar günü isteyen arayan",
        "persona": "Murat Kaya, 35 yaşında bir mühendis. Önce pazar günü randevu ister; o gün olmazsa perşembe gününü kabul eder ve sunulan ilk saati seçer.",
        "goal": "Pazar, olmazsa perşembe günü randevu almak.",
        "success_criteria": "Ajan pazar günü randevu verilemediğini söyledi ve perşembe günü için randevu oluşturdu.",
        "expected_outcome": "appointment_booked",
    },
    {
        "name": "Saatleri uymayan arayan",
        "persona": "Ali Yıldız, 50 yaşında bir esnaf. Cuma günü randevu ister ama yalnızca 18:00'den sonra gelebilir. Cuma günü uygun saat yoksa pazartesi 09:30'u kabul eder.",
        "goal": "Cuma akşamı, olmazsa pazartesi sabahı randevu almak.",
        "success_criteria": "Ajan cuma günü için sistemde olmayan bir akşam saati uydurmadı ve pazartesi günü randevu oluşturdu.",
        "expected_outcome": "appointment_booked",
    },
]

BLANK = {
    "schema_version": 1,
    "global": {"persona": "", "rules": ""},
    "variables": [],
    "nodes": [{"id": "start", "type": "start", "position": {"x": 0, "y": 0}}],
    "edges": [],
}

TEMPLATES = {
    "blank": {"name": "Boş akış", "description": "Yalnızca Başlangıç düğümü.", "graph": BLANK},
    "ariza_fatura": {
        "name": "Fatura / Arıza kaydı",
        "description": "Karşılama, talep yönlendirme, müşteri numarası alma ve kayıt açma.",
        "graph": ARIZA_FATURA,
        "scenarios": ARIZA_FATURA_SCENARIOS,
    },
    "sss": {
        "name": "Bilgi tabanlı SSS hattı",
        "description": "Arayanı numarasından tanır, soruları bilgi tabanından (müşteri tipine göre "
        "etiketli girdilerle) cevaplar; bitince vedalaşır veya temsilciye aktarır. Oluşturduktan sonra "
        "'Soruları cevapla' kartında bilgi tabanını seçin.",
        "graph": SSS,
        "scenarios": SSS_SCENARIOS,
    },
    "kargo": {
        "name": "Kargo takip hattı",
        "description": "Takip numarasını alır, gönderiyi HTTP Aracı ile sorgular, durumu bildirir; "
        "şikayette temsilciye aktarır. Demo servisle çalışır.",
        "graph": KARGO,
        "scenarios": KARGO_SCENARIOS,
    },
    "randevu": {
        "name": "Randevu hattı",
        "description": "Ad ve gün alır, boş saatleri sorgular, seçilen saate randevu oluşturur. "
        "Demo servisle çalışır.",
        "graph": RANDEVU,
        "scenarios": RANDEVU_SCENARIOS,
    },
}


def template_graph(key: str) -> FlowGraph:
    return FlowGraph.model_validate(TEMPLATES[key]["graph"])
