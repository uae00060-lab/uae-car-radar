"""Car details from an ad's own free text, for classifieds whose ad pages cannot be opened.

Mourjan refuses GitHub's servers on ad pages but its results page shows each ad's text, written by
the seller: "للبيع لاند كروزر 2023، ماشي 40 ألف كيلو، المطلوب 170 ألف، أبوظبي". Numbers count only
next to a word that says what they are (price, mileage); a bare number is never guessed at.
"""

import datetime as dt
import re

from common import AR_DIGITS

NUM = r"(\d{1,3}(?:[,٬.]\d{3})+|\d+(?:\.\d+)?)"
THOUSAND = r"(?:\s*(ألف|الف|آلاف|الاف|k\b))?"
PRICE_WORD = r"(?:المطلوب|مطلوب|السعر|سعر|بسعر|السعر النهائي|price|asking|for)"
CURRENCY = r"(?:درهم|د\.إ|aed|dhs?|dirhams?)"
KM_UNIT = r"(?:كم|كيلو(?:متر)?|km|kms|kilomet(?:er|re)s?)"
MILE_UNIT = r"(?:ميل|miles?)"
KM_WORD = r"(?:ماشي[ةه]?|ممشى|الممشى|مماشي|مشي|العداد|عداد|mileage|odometer|driven)"


def _number(digits, thousand):
    value = float(re.sub(r"[,٬]", "", digits)) if re.search(r"[,٬]", digits) or digits.count(".") != 1 or len(digits.split(".")[1]) != 3 \
        else float(digits.replace(".", ""))
    return value * 1000 if thousand else value


def price_of(text):
    """Asking price in AED: next to a price word or a currency, '170 ألف' read as 170,000."""
    t = text.translate(AR_DIGITS).lower()
    for rx in (PRICE_WORD + r"\s*[:：]?\s*" + NUM + THOUSAND + r"(?:\s*" + CURRENCY + r")?",
               NUM + THOUSAND + r"\s*" + CURRENCY):
        for m in re.finditer(rx, t, re.I):
            before, after = t[max(0, m.start() - 20): m.start()], t[m.end(): m.end() + 12]
            if re.match(r"\s*(?:/|في|شهري|monthly|per|a month|كم|km|كيلو|ميل)", after) or \
                    re.search(r"(?:قسط|أقساط|اقساط|شهري|دفع[ةه]|مقدم|installment|monthly|down\s*payment)\W*\w*\W*$", before):
                continue  # an instalment, a down payment or a distance, not the asking price
            value = _number(m[1], m[2])
            if 5000 <= value <= 5_000_000:
                return int(value)
    return None


def km_of(text):
    """Mileage in km from 'ماشي 40 ألف كيلو', '215 كم', '99000 ميل' (miles converted)."""
    t = text.translate(AR_DIGITS).lower()
    for rx, miles in ((NUM + THOUSAND + r"\s*" + KM_UNIT, False), (NUM + THOUSAND + r"\s*" + MILE_UNIT, True),
                      (KM_WORD + r"\s*[:：]?\s*" + NUM + THOUSAND, False)):
        m = re.search(rx, t, re.I)
        if m:
            value = _number(m[1], m[2]) * (1.609 if miles else 1)
            if 0 <= value <= 1_500_000:
                return int(round(value))
    return None


def posted_of(text, now):
    """Posting date from 'منذ 21 دقيقة', 'منذ ساعتين', 'منذ 3 أيام', 'أمس'; None if not stated."""
    t = text.translate(AR_DIGITS)
    m = re.search(r"منذ\s*(\d+)?\s*(دقيقتين|دقيقة|دقائق|ساعتين|ساعة|ساعات|يومين|يوم|أيام|ايام|أسبوعين|اسبوعين|أسبوع|اسبوع|أسابيع|اسابيع)", t)
    if m:
        n = int(m[1]) if m[1] else (2 if m[2].endswith("ين") else 1)
        unit = m[2]
        if unit.startswith("دقي") or unit.startswith("ساع"):
            delta = dt.timedelta(minutes=n) if unit.startswith("دقي") else dt.timedelta(hours=n)
        elif unit.startswith("يوم") or unit in ("أيام", "ايام"):
            delta = dt.timedelta(days=n)
        else:
            delta = dt.timedelta(weeks=n)
        return (now - delta).date()
    if re.search(r"(^|\s)(?:أمس|امس)(\s|$)", t):
        return (now - dt.timedelta(days=1)).date()
    return None


def clean_title(text):
    """The card text without its photo count and age prefix ('5منذ 21 دقيقةللبيع ...')."""
    t = re.sub(r"^\s*\d{1,2}(?=[\u0600-\u06ff])", "", text.strip())
    t = re.sub(r"^منذ\s*\d*\s*(?:دقيقتين|دقيقة|دقائق|ساعتين|ساعة|ساعات|يومين|يوم|أيام|ايام|أسبوعين|اسبوعين|أسبوع|اسبوع|أسابيع|اسابيع)", "", t).strip()
    return re.sub(r"\s+", " ", t)[:160]


def values(card, now):
    """read_ad-style values from a results card's ad text; the state stays 'needs confirmation'."""
    text = card.get("text") or card.get("title") or ""
    title = clean_title(text)
    year = card.get("year")
    posted = posted_of(text, now)
    return {"title": title, "price": price_of(text), "price_source": "text:results" if price_of(text) else None,
            "year": year, "km": km_of(text), "desc": re.sub(r"\s+", " ", text)[:600], "date": posted,
            "date_kind": "posted" if posted else None}
