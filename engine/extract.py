"""Reading results pages and ad pages without any AI.

Sources, strongest first: schema.org JSON-LD, the page's embedded app data
(__NEXT_DATA__, __NUXT__, window.__INITIAL_STATE__ and other JSON scripts), meta tags,
then labelled text ("Kilometers 132,000", "Posted on 8 October 2026"). Every value
carries the name of the source it came from so a run can report what each platform shows.
"""

import json
import re
from html import unescape

from common import AR_DIGITS, ad_identity, clean_url, to_num

SCRIPT_JSON = re.compile(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', re.S | re.I)
NEXT_DATA = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
STATE_ASSIGN = re.compile(r"(?:window\.)?(__INITIAL_STATE__|__PRELOADED_STATE__|__NUXT__|__APOLLO_STATE__|__DATA__)\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
HREF = re.compile(r'href="([^"#]+)"', re.I)
QUOTED_PATH = re.compile(r'"((?:https?:\\?/\\?/[^"\s]+)?\\?/[a-z0-9][^"\s]{10,300})"', re.I)


def text_of(html):
    t = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d|dd|dt|span|td|th|section|article)>", "\n", t, flags=re.I)
    t = unescape(re.sub(r"<[^>]+>", " ", t)).translate(AR_DIGITS)
    t = re.sub(r"[ \t\r\f\v ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def json_blobs(html):
    out = []
    for rx in (SCRIPT_JSON, NEXT_DATA):
        for m in rx.finditer(html):
            try:
                out.append(json.loads(m[1].strip()))
            except ValueError:
                pass
    for m in STATE_ASSIGN.finditer(html):
        try:
            out.append(json.loads(m[2]))
        except ValueError:
            pass
    return out


def walk(o, depth=0):
    if depth > 40:
        return
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, depth + 1)


def scalar(v):
    if isinstance(v, dict):
        for k in ("value", "amount", "name", "label", "text", "en", "display", "formatted"):
            if k in v and not isinstance(v[k], (dict, list)):
                return v[k]
        return None
    if isinstance(v, list):
        return scalar(v[0]) if v else None
    return v


# Field -> key names used by car sites in their embedded data (compared case-insensitively).
KEYS = {
    "price": ("price", "price_aed", "pricevalue", "priceamount", "sale_price", "saleprice", "asking_price", "amount"),
    "year": ("year", "model_year", "modelyear", "manufacture_year", "manufactureyear", "vehiclemodeldate", "modeldate", "productiondate"),
    "km": ("kilometers", "kilometres", "mileage", "km", "odometer", "mileagefromodometer", "kms"),
    "color": ("exterior_color", "exteriorcolor", "exterior_colour", "color", "colour", "body_color"),
    "posted": ("dateposted", "posted_at", "postedat", "added", "created_at", "createdat", "published_at", "publishedat",
               "date_posted", "activated_at", "activatedat", "first_published", "listed_at", "listedat", "creation_date", "datepublished"),
    "updated": ("updated_at", "updatedat", "modified_at", "datemodified", "last_updated", "refreshed_at", "bumped_at"),
    "phone": ("telephone", "phone", "phone_number", "phonenumber", "mobile", "mobile_number", "whatsapp", "contact_number", "contactnumber"),
    "seller": ("seller_name", "sellername", "dealer_name", "dealername", "agent_name", "user_name", "advertiser_name", "company_name"),
    "location": ("location", "address", "area", "neighbourhood", "neighborhood", "city_name", "locality"),
    "specs": ("regional_specs", "regionalspecs", "specs", "specification", "regional_spec"),
    "transmission": ("transmission", "vehicletransmission", "transmission_type", "gearbox"),
    "image": ("image", "main_image", "mainimage", "photo", "thumbnail", "cover_image", "image_url", "imageurl"),
    "title": ("name", "title", "headline"),
}
LOOKUP = {k: f for f, ks in KEYS.items() for k in ks}


def pick_from_dict(d, found, src, depth=0):
    """Fill missing fields from one dict and its small children."""
    if depth > 2 or not isinstance(d, dict):
        return
    for k, v in d.items():
        f = LOOKUP.get(str(k).lower())
        if f and f not in found:
            s = scalar(v)
            if s not in (None, "", 0, False) and not (f == "location" and isinstance(s, (int, float))):
                found[f] = (s, f"{src}:{k}")
        if isinstance(v, dict) and str(k).lower() in ("offers", "brand", "seller", "mileagefromodometer", "location",
                                                     "address", "attributes", "details", "specs", "vehicle", "contact"):
            pick_from_dict(v, found, src, depth + 1)
        if isinstance(v, list) and str(k).lower() in ("attributes", "details", "specs", "features", "properties"):
            for item in v[:80]:
                if isinstance(item, dict):
                    label = str(item.get("key") or item.get("name") or item.get("label") or "").lower().replace(" ", "_")
                    f2 = LOOKUP.get(label)
                    val = scalar(item.get("value") if "value" in item else item.get("display_value"))
                    if f2 and f2 not in found and val not in (None, ""):
                        found[f2] = (val, f"{src}:{label}")


# ---------------------------------------------------------------- results pages

CARD_PRICE_PRE = re.compile(r"(?:AED|د\.إ|درهم)\s*([\d,]{4,9})()(?!\s*/\s*(?:mo|month))", re.I)
CARD_PRICE = re.compile(r"()([\d,]{4,9})\s*(?:AED|درهم)(?!\s*/\s*(?:mo|month))", re.I)
CARD_KM = re.compile(r"([\d,]{1,9})\s*(?:km|kms|كم|كيلومتر)\b", re.I)
CARD_YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


def results(html, base, plat):
    """Ad cards on a results page: [{url, platform, ad_id, title, price, year, km, image, src}]."""
    cards = {}

    def add(url, data, src):
        if url.startswith("/"):
            url = base.rstrip("/") + url
        url = url.replace("\\/", "/")
        p, ad_id = ad_identity(url)
        if not ad_id or p != plat:
            return
        c = cards.setdefault(ad_id, {"url": clean_url(url), "platform": p, "ad_id": ad_id, "src": src})
        for k, v in data.items():
            if v not in (None, "") and not c.get(k):
                c[k] = v

    # 1) embedded data: any dict that carries an ad link
    for blob in json_blobs(html):
        for d in walk(blob):
            link = None
            for k in ("url", "link", "href", "permalink", "absolute_url", "absoluteUrl", "detail_url", "slug", "@id"):
                v = d.get(k)
                if isinstance(v, str) and ("/" in v):
                    link = v
                    break
            if not link:
                continue
            found = {}
            pick_from_dict(d, found, "json")
            add(link, {"title": str(found.get("title", ("",))[0])[:160] or None,
                       "price": to_num(found.get("price", (None,))[0]),
                       "year": to_num(found.get("year", (None,))[0]),
                       "km": to_num(found.get("km", (None,))[0]),
                       "image": found.get("image", (None,))[0] if isinstance(found.get("image", (None,))[0], str) else None}, "json")
    # 2) plain links, with the text of the card around each link
    for m in HREF.finditer(html):
        href = unescape(m[1])
        gt = html.find(">", m.end())
        chunk = text_of(html[gt + 1: gt + 2500])[:600] if gt != -1 else ""
        price = CARD_PRICE_PRE.search(chunk) or CARD_PRICE.search(chunk)
        km = CARD_KM.search(chunk)
        year = CARD_YEAR.search(chunk)
        add(href, {"price": to_num(price[1] or price[2]) if price else None,
                   "km": to_num(km[1]) if km else None,
                   "year": to_num(year[1]) if year else None,
                   "title": chunk.split("\n")[0][:160] if chunk else None}, "link")
    # 3) ad paths quoted anywhere in scripts (client-rendered lists)
    for m in QUOTED_PATH.finditer(html):
        add(m[1].replace("\\/", "/"), {}, "script")
    out = list(cards.values())
    for c in out:  # sanity: card numbers outside plausible ranges are dropped, not trusted
        if c.get("price") and not (1500 <= c["price"] <= 5_000_000):
            c["price"] = None
        if c.get("km") and not (0 <= c["km"] <= 1_500_000):
            c["km"] = None
        if c.get("year") and not (1980 <= c["year"] <= 2030):
            c["year"] = None
    return out


# ---------------------------------------------------------------- ad pages

SOLD = re.compile(r"this (?:ad|listing) (?:is )?no longer (?:available|active)|ad has (?:been )?(?:expired|removed|sold)|"
                  r"listing (?:has )?expired|car (?:has been|is) sold|\bsold out\b|"
                  r"هذا الإعلان (?:لم يعد|غير) متاح|الإعلان منتهي|تم بيع", re.I)
LABELS = {
    "price": r"(?:price|السعر)\s*[:\-]?\s*(?:AED|درهم)?\s*([\d,]{4,9})",
    "km": r"(?:kilometers|kilometres|mileage|odometer|الكيلومترات|المسافة المقطوعة|عداد|الممشى)\s*[:\-]?\s*([\d,]{1,9})",
    "year": r"(?:^|\n)\s*(?:year|model year|سنة الصنع|السنة|الموديل)\s*[:\-]?\s*(19[89]\d|20[0-3]\d)",
    "color": r"(?:exterior colou?r|colou?r|لون الهيكل|اللون الخارجي|اللون)\s*[:\-]?\s*([A-Za-z؀-ۿ ]{3,20})",
    "posted": r"(?:posted(?: on)?|published(?: on)?|date posted|added on|listed on|ad posted|تاريخ النشر|نُشر في|نشر في|تاريخ الإعلان)\s*[:\-]?\s*([^\n]{3,40})",
    "updated": r"(?:last updated|updated(?: on)?|آخر تحديث|تم التحديث)\s*[:\-]?\s*([^\n]{3,40})",
    "inspected": r"(?:inspected(?: on)?|inspection date|تاريخ الفحص)\s*[:\-]?\s*([^\n]{3,40})",
    "specs": r"(?:regional specs|specs|المواصفات الإقليمية|المواصفات)\s*[:\-]?\s*(GCC|American|Japanese|European|Canadian|Korean|Chinese|خليجي[ةه]?|أمريكي[ةه]?|ياباني[ةه]?|أوروبي[ةه]?)",
    "transmission": r"(?:transmission(?: type)?|ناقل الحركة|القير)\s*[:\-]?\s*(automatic|manual|اوتوماتيك|أوتوماتيك|عادي|يدوي)",
    "seller_type": r"\b(dealer|showroom|private seller|owner|by owner|معرض|مالك|بائع خاص)\b",
}
PHONE = re.compile(r'href="(?:tel|https?://wa\.me/|whatsapp://send\?phone=)([+\d][\d\s\-]{7,16})"|(\+971[\s\-]?\d{1,2}[\s\-]?\d{3}[\s\-]?\d{4}|\b05\d[\s\-]?\d{3}[\s\-]?\d{4}\b)', re.I)


LINE_LABELS = {
    "km": ("kilometers", "kilometres", "mileage", "odometer", "km driven", "الكيلومترات", "المسافة المقطوعة", "عدد الكيلومترات", "الممشى"),
    "year": ("year", "model year", "سنة الصنع", "سنة الموديل", "الموديل", "السنة"),
    "color": ("exterior color", "exterior colour", "color", "colour", "لون الهيكل", "اللون الخارجي", "اللون"),
    "posted": ("posted", "posted on", "published", "published date", "published on", "date posted", "ad posted", "listed on", "added on",
               "تاريخ النشر", "نشر في", "نُشر في", "تاريخ الإعلان"),
    "updated": ("last updated", "updated", "updated on", "آخر تحديث"),
    "specs": ("regional specs", "specs", "المواصفات الإقليمية", "المواصفات"),
    "transmission": ("transmission", "transmission type", "ناقل الحركة"),
    "location": ("location", "city", "area", "الموقع", "المدينة", "المنطقة"),
    "seller": ("seller", "posted by", "dealer", "البائع"),
}
_LL = {lab: f for f, labs in LINE_LABELS.items() for lab in labs}


def label_pairs(text):
    """Values from label/value pairs in the page text (first occurrence wins)."""
    out = {}
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for i, ln in enumerate(lines[:4000]):
        m = re.match(r"^([A-Za-z\u0600-\u06FF ]{3,30}?)\s*[:：]\s*(.{1,60})$", ln)
        if m and m[1].strip().lower() in _LL:
            f = _LL[m[1].strip().lower()]
            out.setdefault(f, m[2].strip())
            continue
        key = ln.rstrip(":：").strip().lower()
        if key in _LL and i + 1 < len(lines):
            nxt = lines[i + 1]
            if len(nxt) <= 60 and nxt.rstrip(":：").strip().lower() not in _LL:
                out.setdefault(_LL[key], nxt)
    return out


def color_ok(v):
    from common import color_of
    return bool(color_of(str(v)))


def ad_page(html, url, ad_id):
    """Values for one ad page, each as (value, source). Also 'sold' and 'single'."""
    found = {}
    blobs = json_blobs(html)
    # schema.org first: the publisher's own structured description of this car
    for blob in blobs:
        for d in walk(blob):
            t = d.get("@type")
            t = t if isinstance(t, list) else [t]
            if any(x in ("Car", "Vehicle", "Product", "Motorcycle", "Offer", "IndividualProduct") for x in t if isinstance(x, str)):
                pick_from_dict(d, found, "ld")
                offers = d.get("offers")
                s = d.get("seller") or (offers.get("seller") if isinstance(offers, dict) else None)
                if isinstance(s, dict) and "seller_type" not in found:
                    st = str(s.get("@type") or "").lower()
                    if st in ("autodealer", "organization", "localbusiness", "automotivebusiness", "store"):
                        found["seller_type"] = ("dealer", "ld:seller")
                    elif st == "person":
                        found["seller_type"] = ("owner", "ld:seller")
                    if s.get("name") and "seller" not in found:
                        found["seller"] = (s["name"], "ld:seller.name")
    # embedded app data: the dict that names this ad
    for blob in blobs:
        best = None
        for d in walk(blob):
            vals = [v for v in d.values() if isinstance(v, (str, int))]
            if any(str(v) == str(ad_id) or (isinstance(v, str) and str(ad_id) in v and len(v) < 400) for v in vals):
                score = sum(1 for k in d if str(k).lower() in LOOKUP)
                if not best or score > best[0]:
                    best = (score, d)
        if best and best[0] >= 2:
            pick_from_dict(best[1], found, "app")
    # meta tags
    for prop, f in (("og:title", "title"), ("og:image", "image"), ("article:published_time", "posted"),
                    ("product:price:amount", "price"), ("og:price:amount", "price")):
        m = re.search(r'<meta[^>]+(?:property|name)="' + re.escape(prop) + r'"[^>]+content="([^"]+)"', html, re.I) or \
            re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="' + re.escape(prop) + r'"', html, re.I)
        if m and f not in found:
            found[f] = (unescape(m[1]), "meta:" + prop)
    # labelled text: "Label" on one line and its value on the next, or "Label: value"
    text = text_of(html)
    for f, val in label_pairs(text).items():
        if f not in found:
            found[f] = (val, "label")
    for f, rx in LABELS.items():
        if f not in found:
            m = re.search(rx, text, re.I)
            if m:
                found[f] = (m[1].strip(), "text")
    if "color" in found and not color_ok(found["color"][0]):
        del found["color"]
    if "phone" not in found:
        m = PHONE.search(html)
        if m:
            found["phone"] = ((m[1] or m[2]).strip(), "tel")
    if "title" not in found:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            found["title"] = (unescape(m[1]).strip(), "title")
    avail = ""
    for blob in blobs:
        for d in walk(blob):
            a = d.get("availability")
            if isinstance(a, str):
                avail = a.lower()
    if avail:
        found["_sold"] = any(x in avail for x in ("soldout", "outofstock", "discontinued"))
    else:
        found["_sold"] = "price" not in found and bool(SOLD.search(text[:20000]))
    return found
