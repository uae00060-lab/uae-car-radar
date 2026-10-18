"""Chassis number (VIN) and seller phone, read conservatively from one ad.

Nothing is guessed: a value is kept only when the ad publishes it explicitly and it passes a
format check. Two different values on one page are reported as a conflict, not picked from.
"""

import re
from html import unescape
from html.parser import HTMLParser

VIN_LABEL = re.compile(
    r"(?:\bVIN\b|vehicle identification number|chassis(?: number| no\.?)?|رقم\s*(?:الشاصي|الشاسيه|الشاسي|الهيكل))"
    r"\s*[:#：-]?\s*([A-Za-z0-9*•_-]{5,30})", re.I)

# ISO 3779 transliteration and position weights for the check digit (9th character).
VIN_LETTERS = dict(zip("ABCDEFGHJKLMNPRSTUVWXYZ", (1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 7, 9, 2, 3, 4, 5, 6, 7, 8, 9)))
VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
PLACEHOLDER_ENDINGS = ("1234567", "0000000", "1111111", "9999999")
PLATFORM_OFFICE = "45061300"  # CarSwitch head office, printed on every ad


def vin_status(value):
    """(vin, status): status is checksum / format / invalid-checksum / missing."""
    value = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value) or len(set(value)) < 4:
        return None, "missing"
    total = sum((int(c) if c.isdigit() else VIN_LETTERS[c]) * w for c, w in zip(value, VIN_WEIGHTS)) % 11
    check = "X" if total == 10 else str(total)
    # The check digit is mandatory only for North American manufacturers (WMI starting 1-5).
    if value[0] in "12345" and value[8] != check:
        return None, "invalid-checksum"
    return value, "checksum" if value[8] == check else "format"


def phone_value(value):
    """A UAE number in +971 form, or None for masked, foreign, sample or office numbers."""
    value = unescape(str(value or "")).strip()
    if re.search(r"[*•xX]", value):
        return None  # masked by the platform
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00971"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "971" + digits[1:]
    elif not digits.startswith("971"):
        return None
    if not re.fullmatch(r"971(?:5[024568]\d{7}|[234679]\d{7})", digits):
        return None
    if digits[-7:] in PLACEHOLDER_ENDINGS or digits.endswith(PLATFORM_OFFICE):
        return None
    return "+" + digits


EXCLUDED_TAGS = ("header", "footer", "nav", "script", "style", "noscript")
EXCLUDED_MARKERS = re.compile(r"recommend|related|similar|support|footer|header|navbar", re.I)
VOID_TAGS = ("meta", "link", "img", "br", "hr", "input", "source", "wbr", "area", "embed", "param")
BLOCK_TAGS = ("p", "div", "li", "section", "dt", "dd", "br")


class AdText(HTMLParser):
    """Text and contact links of the ad itself, skipping navigation and recommended-car blocks."""

    def __init__(self):
        super().__init__()
        self.stack = []   # (tag, hidden) for every open element
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        marker = " ".join(str(attrs.get(k, "")) for k in ("class", "id", "aria-label"))
        excluded = tag in EXCLUDED_TAGS or bool(EXCLUDED_MARKERS.search(marker))
        hidden = excluded or (self.stack[-1][1] if self.stack else False)
        if tag not in VOID_TAGS:
            self.stack.append((tag, hidden))
        if hidden:
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and re.match(r"(?:tel:|https?://wa.me/)", attrs.get("href", "")):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data + " ")


def _schema_candidates(primary):
    """VINs and seller phones from the ad's own schema.org Car/Offer objects."""
    vins, phones = [], []
    for car in primary:
        for key in ("vehicleIdentificationNumber", "vin", "VIN", "chassisNumber"):
            if car.get(key):
                vins.append((car[key], "ad:schema:" + key))
        offers = car.get("offers")
        seller = car.get("seller") or (offers.get("seller") if isinstance(offers, dict) else None)
        if isinstance(seller, dict):
            contact = seller.get("contactPoint")
            for value in (seller.get("telephone"), contact.get("telephone") if isinstance(contact, dict) else None):
                if value:
                    phones.append((value, "ad:seller.telephone"))
    return vins, phones


def extract_identity(html, primary, description=""):
    """Identity fields for one ad: vin/vin_source/vin_status and phone/phone_source/phone_status."""
    vins, phones = _schema_candidates(primary)
    page = AdText()
    page.feed(html)
    for m in VIN_LABEL.finditer(description or ""):
        vins.append((m[1], "ad:description:VIN"))
    for m in VIN_LABEL.finditer("".join(page.parts)):
        vins.append((m[1], "ad:label:VIN"))
    # Only explicit contact links in the ad body.
    for link in page.links:
        phones.append((re.sub(r"^(?:tel:|https?://wa.me/)", "", link).split("?")[0], "ad:contact-link"))

    valid_vins, saw_invalid = {}, False
    for value, source in vins:
        vin, status = vin_status(value)
        if vin:
            valid_vins[vin] = (source, status)
        else:
            saw_invalid = True
    valid_phones = {phone_value(v): s for v, s in phones if phone_value(v)}

    out = {"identity_version": 1,
           "vin": None, "vin_source": None,
           "vin_status": "conflict" if len(valid_vins) > 1 else "unavailable-or-invalid" if saw_invalid else "missing",
           "phone": None, "phone_source": None,
           "phone_status": "conflict" if len(valid_phones) > 1 else "missing"}
    if len(valid_vins) == 1:
        out["vin"], (out["vin_source"], out["vin_status"]) = next(iter(valid_vins.items()))
    if len(valid_phones) == 1:
        out["phone"], out["phone_source"] = next(iter(valid_phones.items()))
        out["phone_status"] = "published"
    return out
