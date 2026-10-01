"""Stand-in business APIs for the HTTP Aracı templates, so they run without an outside service.

Unauthenticated on purpose: flows call them like any external API. Stateless on purpose too:
a booking doesn't take its slot, so scenario runs never depend on what an earlier run booked.
"""

import itertools
import re
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/demo", tags=["demo"])

# --- Arayan sorgulama (CRM) ----------------------------------------------------------

CUSTOMERS = {
    "5321112233": {"ad": "Ayşe Yılmaz", "tarife": "Fiber 100"},
    "5334445566": {"ad": "Mehmet Kaya", "tarife": "Fiber 50"},
}


@router.get("/musteri")
async def caller(telefon: str = ""):
    """Who is calling: a known number is an existing customer, anything else a new one."""
    digits = re.sub(r"\D", "", telefon)[-10:]
    found = CUSTOMERS.get(digits)
    if found is None:
        return {"kayitli": False, "tip": "yeni müşteri", "ad": "", "tarife": ""}
    return {"kayitli": True, "tip": "mevcut müşteri", **found}


# --- Kargo takip -------------------------------------------------------------------

SHIPMENTS = {
    "123456": {
        "durum": "yolda",
        "durum_metni": "Gönderiniz yolda, dağıtım şubesine ulaştı. Yarın saat 18:00'e kadar teslim edilmesi bekleniyor.",
        "tahmini_teslim": "yarın 18:00'e kadar",
        "sube": "Kadıköy şubesi",
    },
    "654321": {
        "durum": "teslim_edildi",
        "durum_metni": "Gönderiniz dün saat 14:20'de teslim edildi, teslim alan kişi bina görevlisi.",
        "tahmini_teslim": "",
        "sube": "Ataşehir şubesi",
    },
    "111222": {
        "durum": "subede",
        "durum_metni": "Adreste kimse bulunamadığı için gönderiniz Beşiktaş şubesinde bekliyor. Cuma gününe kadar kimliğinizle teslim alabilirsiniz.",
        "tahmini_teslim": "",
        "sube": "Beşiktaş şubesi",
    },
}


@router.get("/kargo/{takip_no}")
async def shipment(takip_no: str):
    digits = re.sub(r"\D", "", takip_no)
    found = SHIPMENTS.get(digits)
    if found is None:
        raise HTTPException(404, "Bu takip numarasıyla bir gönderi bulunamadı.")
    return {"takip_no": digits, **found}


# --- Randevu -----------------------------------------------------------------------

DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
WEEKDAY_SLOTS = ["09:30", "11:00", "14:00", "16:30"]
SATURDAY_SLOTS = ["10:00", "11:30"]
_numbers = itertools.count(1001)


def _fold(text: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return text.translate(table).lower()


# Longer names first: "pazartesi" contains "pazar", "cumartesi" contains "cuma".
_DAY_WORDS = sorted(((_fold(d), i) for i, d in enumerate(DAYS)), key=lambda x: -len(x[0]))


def parse_day(text: str, today: date | None = None) -> str | None:
    """Turkish day name ("salı", "Salı'ya", "perşembe günü"), "bugün" or "yarın"."""
    folded = _fold(text)
    today = today or date.today()
    if "yarin" in folded:
        return DAYS[(today + timedelta(days=1)).weekday()]
    if "bugun" in folded:
        return DAYS[today.weekday()]
    for word, i in _DAY_WORDS:
        if word in folded:
            return DAYS[i]
    return None


def parse_time(text: str) -> str | None:
    """"14:00", "14.30", "saat 2" (afternoon), "on bir" is not supported."""
    match = re.search(r"(\d{1,2})(?:[:.](\d{2}))?", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if hour < 8:  # "saat 2" on a clinic line means 14:00
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def free_slots(day: str) -> list[str]:
    return SATURDAY_SLOTS if day == "Cumartesi" else [] if day == "Pazar" else WEEKDAY_SLOTS


@router.get("/randevu/musait")
async def availability(gun: str = ""):
    day = parse_day(gun)
    if day is None:
        return {"musait": False, "gun": "", "saatler": [], "mesaj": f"'{gun}' gününü anlayamadım."}
    slots = free_slots(day)
    if day == "Pazar":
        message = "Pazar günleri kapalıyız."
    elif not slots:
        message = f"{day} günü için boş saatimiz kalmadı."
    else:
        message = f"{day} günü için boş saatler: {', '.join(slots)}."
    return {"musait": bool(slots), "gun": day, "saatler": slots, "mesaj": message}


class BookingIn(BaseModel):
    ad_soyad: str = ""
    gun: str = ""
    saat: str = ""


@router.post("/randevu", status_code=201)
async def book(body: BookingIn):
    day, slot = parse_day(body.gun), parse_time(body.saat)
    if day is None or slot is None:
        raise HTTPException(400, "Gün veya saat anlaşılamadı.")
    if slot not in free_slots(day):
        raise HTTPException(409, f"{day} {slot} uygun değil.")
    return {"randevu_no": f"R{next(_numbers)}", "ad_soyad": body.ad_soyad.strip(), "gun": day, "saat": slot}
