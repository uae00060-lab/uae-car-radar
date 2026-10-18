"""Free chassis-number decoding from the US government's vPIC service (NHTSA), no key needed.

vPIC knows what each manufacturer registered for a VIN pattern: make, model, model year and the
country of the plant. It cannot tell GCC from American specs (both can come from the same plant),
so it is used only to check the ad's make and year against the car's own number.
A VIN that vPIC cannot read is reported as such, never as a fault of the car.
"""

import json
import time
import urllib.request

URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{}?format=json"
PER_ROUND = 40        # new VINs decoded per round; the rest wait for the next one
BUDGET_SECONDS = 90


def _get(vin):
    req = urllib.request.Request(URL.format(vin), headers={"User-Agent": "uae-car-radar"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["Results"][0]


def decode(vin, get=_get):
    """{"make", "model", "year", "trim", "plant"} from vPIC, {} if it does not know the VIN, None on error."""
    try:
        row = get(vin)
    except Exception:  # noqa: BLE001 - try again next round
        return None
    year = str(row.get("ModelYear") or "").strip()
    info = {"make": (row.get("Make") or "").strip().title() or None, "model": (row.get("Model") or "").strip() or None,
            "year": int(year) if year.isdigit() else None, "trim": (row.get("Trim") or "").strip() or None,
            "plant": (row.get("PlantCountry") or "").strip().title() or None}
    return info if info["make"] else {}


def _norm(make):
    return "".join(ch for ch in str(make or "").lower() if ch.isalnum()).replace("mercedesbenz", "mercedes")


def compare(info, listing, request_make=None):
    """Arabic notes where the chassis number disagrees with the ad."""
    notes = []
    if not info:
        return notes
    make = request_make or listing.get("make")
    if info.get("make") and make and _norm(make) not in _norm(info["make"]) and _norm(info["make"]) not in _norm(make):
        notes.append(f"الشاصي مسجل باسم {info['make']} وليس {make}")
    if info.get("year") and listing.get("year") and info["year"] != listing["year"]:
        notes.append(f"سنة الموديل حسب الشاصي {info['year']} والإعلان يقول {listing['year']}")
    return notes


def update(eng, listings, requests, get=_get, now=time.monotonic):
    """Decode new VINs of the given listings, cache them and store the comparison on each listing."""
    cache = eng.setdefault("vin_decoded", {})
    makes = {r["id"]: r.get("make") for r in requests}
    started, fresh = now(), 0
    for l in listings:
        vin = l.get("vin")
        if not vin or l.get("identity_version") != 1:
            continue
        if vin not in cache:
            if fresh >= PER_ROUND or now() - started > BUDGET_SECONDS:
                continue
            fresh += 1
            info = decode(vin, get)
            if info is None:
                continue
            cache[vin] = info
        info = cache[vin]
        l["vin_info"] = info or None
        l["vin_check"] = compare(info, l, makes.get(l.get("request_id")))
    return fresh


def prune(eng, listings):
    """Forget decoded VINs of ads the radar no longer keeps."""
    keep = {l.get("vin") for l in listings}
    cache = eng.get("vin_decoded") or {}
    for vin in [v for v in cache if v not in keep]:
        del cache[vin]
