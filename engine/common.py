"""Shared constants and helpers: platforms, ad URL shapes, names, dates, matching."""

import datetime as dt
import json
import os
import re
import urllib.parse
from zoneinfo import ZoneInfo

UAE = ZoneInfo("Asia/Dubai")

PLATFORMS = {
    "dubizzle":   {"name": "دوبيزل",       "hosts": ("dubizzle.com",)},
    "yallamotor": {"name": "يلا موتور",     "hosts": ("uae.yallamotor.com",)},
    "dubicars":   {"name": "DubiCars",      "hosts": ("dubicars.com",)},
    "carswitch":  {"name": "CarSwitch",     "hosts": ("carswitch.com",)},
    "opensooq":   {"name": "السوق المفتوح", "hosts": ("ae.opensooq.com",)},
    "mourjan":    {"name": "مرجان",         "hosts": ("mourjan.com",)},
    "autoae":     {"name": "AUTO.AE",       "hosts": ("auto.ae",)},
    "oneclickdrive": {"name": "OneClickDrive", "hosts": ("oneclickdrive.com",)},
}
# auto.ae lists the whole region on one page; its first path segment is the city.
AUTOAE_FOREIGN = ("saudi", "egypt", "oman", "qatar", "kuwait", "bahrain", "jordan", "lebanon", "iraq", "turkey")
# Platforms whose ad page shows no posting date at all; the date shown is when the radar first saw the ad.
NO_DATE_PLATFORMS = ("dubicars", "oneclickdrive")
DUBIZZLE_UAE = ("uae", "dubai", "abudhabi", "sharjah", "ajman", "rak", "fujairah", "uaq", "alain")

# Individual-ad URL shapes, checked against real pages on 2026-10-18. Anything else
# (results pages, model pages, other countries) is never opened as an ad.
AD_PATTERNS = {
    "dubizzle":   re.compile(r"^/motors/used-cars/[^/]+/[^/]+/\d{4}/\d{1,2}/\d{1,2}/[^/]*---([0-9a-f]{32})/?$"),
    "yallamotor": re.compile(r"^/used-cars/[^/]+/[^/]+/\d{4}/used-[a-z0-9-]+-(\d{6,})/?$"),
    "dubicars":   re.compile(r"^/(?:\d{4})-[a-z0-9-]+-(\d{5,})\.html$"),
    "carswitch":  re.compile(r"^/[a-z-]+/used-car/[^/]+/[^/]+/\d{4}/(\d{5,})/?$"),
    "opensooq":   re.compile(r"^/(?:en|ar)/search/(\d{6,})/?$"),
    "mourjan":    re.compile(r"^/ae/(?:[a-z-]+/)?([a-z-]+)/for-sale/(\d{7,})/?$"),
    "autoae":     re.compile(r"^/([a-z0-9-]+)/sale/car/[^/]+/[^/]+/id/(\d+)/?$"),
    "oneclickdrive": re.compile(r"^/details/index/search-usedcar-[a-z-]+/[^/]+/[^/]+/?$"),
}

EMIRATES = {
    "dubai": ("dubai", "دبي"), "abu dhabi": ("abu dhabi", "abudhabi", "ابوظبي", "أبوظبي", "al ain", "العين"),
    "sharjah": ("sharjah", "الشارقة"), "ajman": ("ajman", "عجمان"),
    "ras al khaimah": ("ras al khaimah", "ras al-khaimah", "rak", "رأس الخيمة", "راس الخيمة"),
    "fujairah": ("fujairah", "الفجيرة"), "umm al quwain": ("umm al quwain", "uaq", "أم القيوين", "ام القيوين"),
}
EMIRATE_AR = {"dubai": "دبي", "abu dhabi": "أبوظبي", "sharjah": "الشارقة", "ajman": "عجمان",
              "ras al khaimah": "رأس الخيمة", "fujairah": "الفجيرة", "umm al quwain": "أم القيوين"}

# Arabic names the user may type -> the English slug the platforms use.
AR_NAMES = {
    "تيوتا": "toyota", "تويوتا": "toyota", "نيسان": "nissan", "هوندا": "honda", "هيونداي": "hyundai", "هونداي": "hyundai",
    "كيا": "kia", "ميتسوبيشي": "mitsubishi", "متسوبيشي": "mitsubishi", "لكزس": "lexus", "شفروليه": "chevrolet",
    "شيفروليه": "chevrolet", "فورد": "ford", "مازدا": "mazda", "سوزوكي": "suzuki", "مرسيدس": "mercedes-benz",
    "بي ام دبليو": "bmw", "رينو": "renault", "جيلي": "geely", "شانجان": "changan", "إم جي": "mg", "ام جي": "mg",
    "يارس": "yaris", "ياريس": "yaris", "كورولا": "corolla", "كامري": "camry", "لاندكروزر": "land-cruiser", "برادو": "prado",
    "صني": "sunny", "التيما": "altima", "باترول": "patrol", "سنترا": "sentra", "سيفيك": "civic", "أكورد": "accord",
    "اكورد": "accord", "النترا": "elantra", "إلنترا": "elantra", "أكسنت": "accent", "اكسنت": "accent",
    "سوناتا": "sonata", "توسان": "tucson", "بيكانتو": "picanto", "ريو": "rio", "سيراتو": "cerato",
    "سبورتاج": "sportage", "لانسر": "lancer", "اتراج": "attrage", "أتراج": "attrage", "سويفت": "swift",
    "دزاير": "dzire", "سيليريو": "celerio",
    # Common spellings in UAE Arabic ads (normalised with ar_norm before comparison).
    "لاند كروزر": "land-cruiser", "لاندكروز": "land-cruiser", "لاند كروز": "land-cruiser", "شاص": "land-cruiser",
    "هايلكس": "hilux", "هيلوكس": "hilux", "فورتشنر": "fortuner", "فورتونر": "fortuner", "راف فور": "rav4", "راف 4": "rav4",
    "هايلاندر": "highlander", "افالون": "avalon", "سيكويا": "sequoia", "تندرا": "tundra", "هايس": "hiace", "اف جي": "fj-cruiser",
    "اكس تريل": "x-trail", "اكستريل": "x-trail", "باثفايندر": "pathfinder", "كيكس": "kicks", "ارمادا": "armada", "ماكسيما": "maxima",
    "مورانو": "murano", "نافارا": "navara", "جي تي ار": "gt-r", "سي ار في": "cr-v", "بايلوت": "pilot", "اوديسي": "odyssey",
    "سنتافي": "santa-fe", "سانتافي": "santa-fe", "سانتا في": "santa-fe", "كريتا": "creta", "باليسيد": "palisade", "ازيرا": "azera",
    "سورينتو": "sorento", "تيلورايد": "telluride", "كارنفال": "carnival", "سيلتوس": "seltos", "اوبتيما": "optima", "كادينزا": "cadenza",
    "باجيرو": "pajero", "باجيرو سبورت": "pajero-sport", "اوتلاندر": "outlander", "تاهو": "tahoe", "سوبربان": "suburban",
    "سلفرادو": "silverado", "كمارو": "camaro", "ماليبو": "malibu", "كابتيفا": "captiva", "يوكن": "yukon", "سييرا": "sierra",
    "اكسبلورر": "explorer", "اكسبديشن": "expedition", "موستنج": "mustang", "رينجر": "ranger", "اف 150": "f-150", "برونكو": "bronco",
    "رانج روفر": "range-rover", "رنج روفر": "range-rover", "ديفندر": "defender", "ديسكفري": "discovery", "رانجلر": "wrangler",
    "جراند شيروكي": "grand-cherokee", "شيروكي": "cherokee", "تشارجر": "charger", "تشالنجر": "challenger", "دورانجو": "durango",
    "جيمني": "jimny", "فيتارا": "vitara", "ارتيجا": "ertiga", "سيلتوس": "seltos",
}
with open(os.path.join(os.path.dirname(__file__), "mourjan_catalog.json"), encoding="utf-8") as _catalog:
    MOURJAN_BRANDS = {b["slug"]: b for b in json.load(_catalog)["brands"]}
MOURJAN_ALIASES = {"hyundai": "hyunday", "mercedes-benz": "mercedes", "volkswagen": "volks-wagen", "infiniti": "infinity", "maserati": "maseratti", "mini": "mini-cooper"}
for _brand in MOURJAN_BRANDS.values():
    if re.search(r"[؀-ۿ]", _brand["name"]):
        AR_NAMES.setdefault(_brand["name"], next((k for k,v in MOURJAN_ALIASES.items() if v == _brand["slug"]), _brand["slug"]))

COLORS = {
    "white": ("white", "أبيض", "ابيض", "pearl white"), "black": ("black", "أسود", "اسود"),
    "silver": ("silver", "فضي"), "grey": ("grey", "gray", "رمادي"), "red": ("red", "أحمر", "احمر"),
    "blue": ("blue", "أزرق", "ازرق"), "beige": ("beige", "بيج"), "brown": ("brown", "بني"),
    "gold": ("gold", "ذهبي"), "green": ("green", "أخضر", "اخضر"), "orange": ("orange", "برتقالي"),
    "yellow": ("yellow", "أصفر", "اصفر"),
}
COLOR_AR = {"white": "أبيض", "black": "أسود", "silver": "فضي", "grey": "رمادي", "red": "أحمر", "blue": "أزرق",
            "beige": "بيج", "brown": "بني", "gold": "ذهبي", "green": "أخضر", "orange": "برتقالي", "yellow": "أصفر"}
FIELD_AR = {"model": "الماركة والطراز", "year": "سنة الموديل", "price": "السعر", "km": "الممشى",
            "color": "اللون", "emirate": "الإمارة", "posted": "تاريخ النشر"}
# Where an ad's date came from, strongest first. Only "posted" is the platform's own posting date.
DATE_KIND_AR = {"posted": "نُشر", "updated": "آخر تحديث", "photos": "رُفعت الصور", "inspected": "فُحصت السيارة",
                "first_seen": "رصده الرادار"}
SELLER_AR = {"dealer": "معرض", "owner": "مالك"}

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS.update({"sept": 9, "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5,
               "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
               "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12})


# ---------------------------------------------------------------- helpers

def now_uae():
    return dt.datetime.now(UAE)


def window_start(today):
    """Same calendar day one month back (18/10 -> 18/09), clamped at month end."""
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(y, m, min(today.day, last))


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def slug(s):
    s = (s or "").strip().lower()
    s = AR_NAMES.get(s, s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).translate(AR_DIGITS).replace(",", "").replace("٬", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m[0]) if m else None


def digits(v):
    return re.sub(r"\D", "", str(v or "").translate(AR_DIGITS))


def json_from_text(text):
    """WebFetch answers are JSON wrapped in prose or code fences; pull out the JSON."""
    if isinstance(text, (list, dict)):
        return text
    s = str(text)
    for open_, close in (("[", "]"), ("{", "}")):
        i, j = s.find(open_), s.rfind(close)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except ValueError:
                continue
    return None


def parse_date(text, today):
    if not text:
        return None
    s = str(text).translate(AR_DIGITS)
    t = s.lower()
    if re.search(r"\b(today|just now|hours? ago|minutes? ago)\b|اليوم|منذ \d* ?(ساعة|ساعات|دقيقة|دقائق)", t):
        return today
    if re.search(r"\byesterday\b|أمس|امس", t):
        return today - dt.timedelta(days=1)
    m = re.search(r"\b(\d+)\s+(day|week|month|year)s?\s+ago\b", t)
    if m:
        return today - dt.timedelta(days=int(m[1]) * {"day": 1, "week": 7, "month": 30, "year": 365}[m[2]])
    m = re.search(r"\b(?:about |almost |over )?an? (day|week|month|year) ago\b", t)
    if m:
        return today - dt.timedelta(days={"day": 1, "week": 7, "month": 30, "year": 365}[m[1]])
    for rx, order in ((r"(\d{4})-(\d{2})-(\d{2})", "ymd"), (r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", "dmy")):
        m = re.search(rx, s)
        if m:
            y, mo, d = (int(m[1]), int(m[2]), int(m[3])) if order == "ymd" else (int(m[3]), int(m[2]), int(m[1]))
            return _valid(y, mo, d, today)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z؀-ۿ]+)\.?,?\s+(\d{4})", s)
    if m and m[2].lower() in MONTHS:
        return _valid(int(m[3]), MONTHS[m[2].lower()], int(m[1]), today)
    m = re.search(r"\b([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
    if m and m[1].lower() in MONTHS:
        return _valid(int(m[3]), MONTHS[m[1].lower()], int(m[2]), today)
    m = re.search(r"\b([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!,?\s*\d{4})", s)
    if m and m[1].lower() in MONTHS:  # "October 2" with no year: this year, or last year if still ahead
        x = _valid(today.year, MONTHS[m[1].lower()], int(m[2]), dt.date(today.year, 12, 31))
        if x and x > today:
            x = _valid(today.year - 1, x.month, x.day, today)
        return x
    return None


def date_in_path(url, today):
    """Photo CDNs file uploads under /YYYY/M/D/ (dubizzle, yallamotor): the day the photos went up."""
    m = re.search(r"/(20\d\d)/(\d{1,2})/(\d{1,2})/", url or "")
    return _valid(int(m[1]), int(m[2]), int(m[3]), today) if m else None


def _valid(y, mo, d, today):
    try:
        x = dt.date(y, mo, d)
    except ValueError:
        return None
    return x if dt.date(2015, 1, 1) <= x <= today else None


def platform_of(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    for key, p in PLATFORMS.items():
        for h in p["hosts"]:
            if host == h or host.endswith("." + h):
                if key == "dubizzle" and host.split(".")[0] not in DUBIZZLE_UAE:
                    return None
                if key == "carswitch" and host not in ("carswitch.com", "www.carswitch.com"):
                    return None  # ksa.carswitch.com etc.
                if key == "autoae" and host not in ("auto.ae", "www.auto.ae"):
                    return None
                return key
    return None


def ad_identity(url):
    """(platform, ad_id) for an individual UAE ad URL, else (platform, None)."""
    try:
        u = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None, None
    if u.scheme not in ("https", "http"):
        return None, None
    plat = platform_of(url)
    if not plat:
        return None, None
    m = AD_PATTERNS[plat].search(u.path)
    if not m:
        return plat, None
    if plat == "autoae":
        if m[1].startswith(AUTOAE_FOREIGN):
            return None, None
        return plat, m[2]
    if plat == "mourjan":
        return (plat, m[2]) if m[1] in MOURJAN_BRANDS else (None, None)
    if plat == "oneclickdrive":
        q = urllib.parse.parse_qs(u.query).get("id", [""])[0]
        return plat, (q if q.isdigit() else None)
    return plat, m[1]


def clean_url(url):
    u = urllib.parse.urlparse(url.strip())
    keep = ""
    if "oneclickdrive.com" in u.netloc:  # the ad number lives in ?id=
        q = urllib.parse.parse_qs(u.query).get("id", [""])[0]
        keep = f"?id={q}" if q else ""
    return f"https://{u.netloc.lower()}{u.path}{keep}"


def emirate_of(text):
    t = (text or "").lower()
    for key, names in EMIRATES.items():
        if any(n in t for n in names):
            return key
    return None


def color_of(text):
    t = (text or "").lower()
    for key, names in COLORS.items():
        if any(re.search(r"(^|\W)" + re.escape(n) + r"($|\W)", t) for n in names):
            return key
    return None


def model_terms(req):
    out = []
    for k in ("make", "model"):
        v = (req.get(k) or "").strip()
        if v:
            key=slug(v)
            alts={key.replace("-", " "), v.lower()}
            alts.update(k.lower() for k,val in AR_NAMES.items() if slug(val)==key)
            alts.add(MOURJAN_ALIASES.get(key,key).replace("-"," "))
            out.append(alts)
    return out


def ar_norm(text):
    """One spelling for Arabic letters that ads write either way: أإآ→ا، ى→ي، ة→ه، no diacritics or tatweel."""
    text = re.sub(r"[\u064b-\u0652\u0640]", "", str(text or ""))
    return text.translate(str.maketrans("أإآىة", "ااايه"))


def has_terms(text, terms):
    t = re.sub(r"[^a-z0-9؀-ۿ]+", " ", ar_norm(text).lower())
    # "اليارس", "واللاندكروزر": an Arabic name may carry ال or و+ال in front.
    return all(any(re.search(r"(^|\s)(?:و?ال)?" + re.escape(ar_norm(a)) + r"(\s|$)", t) for a in alts if a) for alts in terms)



def validate_request(req):
    """Reject names that cannot produce a platform path instead of an empty round."""
    if req.get("make") and not slug(req.get("make")):
        return "اسم الماركة غير معروف؛ اختر اسمًا من القائمة أو اكتبه بالإنجليزية"
    if req.get("model") and not slug(req.get("model")):
        return "اسم الطراز غير معروف؛ اختر اسمًا من القائمة أو اكتبه بالإنجليزية"
    if req.get("year_from") and req.get("year_to") and int(req["year_from"]) > int(req["year_to"]):
        return "نطاق سنوات الموديل غير صحيح"
    return None


def request_view(listing, request_id):
    """One ad, independently assessed against every request that found it."""
    if request_id not in listing.get("request_ids", [listing.get("request_id")]):
        return None
    return {**listing, **listing.get("by_request", {}).get(request_id, {}), "request_id": request_id}
