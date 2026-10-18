#!/usr/bin/env python3
"""UAE car radar engine. Runs on GitHub Actions (or any machine with Python 3.11+).

  python engine/radar.py run --mode scheduled      the 10:00 / 20:00 rounds
  python engine/radar.py run --mode manual [--request ID]   "search now" from the dashboard
  python engine/radar.py watch                     price check of the cars you follow
  python engine/radar.py diagnose [--make Toyota --model Yaris]   what each platform shows

Data lives encrypted in data/*.enc (key: RADAR_KEY). Logs print counts only, never ad
or personal data, because the repository and its logs are public.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from progress import Progress
import lifecycle
import analytics  # noqa: E402
import extract  # noqa: E402
import fetch  # noqa: E402
import notify  # noqa: E402
import report  # noqa: E402
import store  # noqa: E402
from common import (COLOR_AR, EMIRATE_AR, FIELD_AR, NO_DATE_PLATFORMS, PLATFORMS, ad_identity, clean_url,  # noqa: E402
                    color_of, date_in_path, emirate_of, has_terms, model_terms, now_uae, parse_date, slug,
                    to_num, window_start, validate_request, request_view, MOURJAN_BRANDS, MOURJAN_ALIASES)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_FILE = os.path.join(ROOT, "data", "user.enc")
ENGINE_FILE = os.path.join(ROOT, "data", "engine.enc")
REPORTS_DIR = os.path.join(ROOT, "reports")
WORK = os.path.join(ROOT, ".work")
SITE = os.environ.get("RADAR_SITE") or "https://uae00060-lab.github.io/uae-car-radar/"

PLACEHOLDER_PHONES = ("1234567", "0000000", "1111111", "9999999")
PLATFORM_PHONES = ("45061300",)  # CarSwitch head office, shown on every ad
MAX_OPEN = {"scheduled": 70, "manual": 45, "watch": 40}
RECHECK_HOURS = 10      # saved ads are re-read at most twice a day
SKIP_DAYS = 7           # an ad that did not match is looked at again after a week
KEEP_REPORTS = 90
KEEP_RUNS = 300
FOLLOWING = ("following", "contacted", "inspection", "negotiating")


def log(msg, **kw):
    print(json.dumps({"msg": msg, **kw}, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------- where to look

def search_urls(plat, req, market=False):
    make, model = slug(req.get("make")), slug(req.get("model"))
    path = f"{make}/{model}" if model else make
    if plat == "dubizzle":
        q = {}
        if req.get("price_max") and not market:
            q["price__lte"] = int(req["price_max"])
        if req.get("year_from"):
            q["year__gte"] = int(req["year_from"]) - (1 if market else 0)
        if req.get("year_to"):
            q["year__lte"] = int(req["year_to"]) + (1 if market else 0)
        return [("https://uae.dubizzle.com/motors/used-cars/" + (path + "/" if path else "")) + ("?" + urllib.parse.urlencode(q) if q else "")]
    if plat == "yallamotor":
        return [f"https://uae.yallamotor.com/used-cars/{path}"]
    if plat == "dubicars":
        return [f"https://www.dubicars.com/uae/used/{path}"]
    if plat == "carswitch":
        return [f"https://carswitch.com/uae/used-cars/{path}"]
    if plat == "autoae":
        return [("https://auto.ae/sale/car/all/" + (path + "/" if path else ""))]
    if plat == "oneclickdrive":
        if not make: return []  # discover through public search instead of guessing a URL
        name = f"{make}-{model}" if model else make
        return [f"https://www.oneclickdrive.com/buy-{name}-used-cars-{c}" for c in ("dubai", "abu-dhabi", "sharjah")]
    if plat == "opensooq":
        return [f"https://ae.opensooq.com/en/cars/cars-for-sale/{path}"]
    if plat == "mourjan":
        brand = MOURJAN_ALIASES.get(make, make)
        brands = [brand if brand in MOURJAN_BRANDS else "other-autos"] if make else list(MOURJAN_BRANDS)
        q = {name: int(req[field]) for field,name in (("year_from","mny"),("year_to","mxy"),("price_max","mxp")) if req.get(field) and not market}
        if make and brand not in MOURJAN_BRANDS: q["q"] = " ".join(x for x in (make, model) if x)
        return [f"https://www.mourjan.com/ae/{brand}/for-sale/" + ("?" + urllib.parse.urlencode(q) if q else "") for brand in brands if brand in MOURJAN_BRANDS]
    return []



def search_queries(plat, req):
    """Search-engine queries that land on individual ads of this platform."""
    make, model = slug(req.get("make")), slug(req.get("model"))
    words = f"{make} {model}".replace("-", " ").strip() or "used cars UAE"
    years = []
    if req.get("year_from") and req.get("year_to") and int(req["year_to"]) - int(req["year_from"]) <= 4:
        years = [str(y) for y in range(int(req["year_from"]), int(req["year_to"]) + 1)]
    site = {"dubizzle": "dubizzle.com/motors/used-cars", "yallamotor": f"uae.yallamotor.com/used-cars/{make}/{model}",
            "dubicars": "dubicars.com", "carswitch": "carswitch.com", "autoae": "auto.ae", "oneclickdrive": "oneclickdrive.com",
            "opensooq": "ae.opensooq.com", "mourjan": "mourjan.com"}[plat]
    qs = [f"site:{site} {words}" + (" used" if plat in ("dubicars", "opensooq", "mourjan") else "")]
    qs += [f"site:{site} {words} {y}" for y in years[:3]]
    return qs


def search_query(plat, req):
    return search_queries(plat, req)[0]


def card_ok(req, c):
    p, y, km = c.get("price"), c.get("year"), c.get("km")
    if req.get("price_max") and p and p > float(req["price_max"]):
        return False
    if req.get("year_from") and y and y < int(req["year_from"]):
        return False
    if req.get("year_to") and y and y > int(req["year_to"]):
        return False
    if req.get("mileage_max") and km and km > float(req["mileage_max"]):
        return False
    text = " ".join(str(c.get(k) or "") for k in ("title", "url")).replace("-", " ").replace("/", " ")
    return has_terms(text, model_terms(req))


def discover(req, plats, diag, progress=None):
    """All ad cards for one request across its platforms, plus market samples from structured cards."""
    cards, samples = {}, []
    for plat in plats:
        d = diag.setdefault(plat, {"pages": 0, "ok": 0, "blocked": 0, "cards": 0, "via_search": 0, "status": []})
        got = 0
        urls = search_urls(plat, req) + (search_urls(plat, req, market=True) if plat == "dubizzle" and req.get("price_max") else [])
        for url in urls:
            if progress: progress.update("discover", progress.discovery_done, progress.discovery_total)
            page = fetch.get(url, timeout=12, retries=0) if plat == "mourjan" and not req.get("make") else fetch.get(url)
            d["pages"] += 1
            if progress: progress.discovery_done += 1
            d["status"].append(page.status)
            if page.blocked:
                d["blocked"] += 1
            if not page.ok:
                continue
            d["ok"] += 1
            if plat == "mourjan" and req.get("model"):
                refined = extract.mourjan_model_url(page.html, url, req["model"])
                if refined:
                    filtered = fetch.get(refined)
                    d["pages"] += 1; d["status"].append(filtered.status)
                    if progress: progress.discovery_total+=1; progress.discovery_done+=1
                    if filtered.ok: page = filtered; d["ok"] += 1
                    elif filtered.blocked: d["blocked"] += 1
            base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(page.final_url))
            for c in extract.results(page.html, base, plat):
                key = f"{plat}-{c['ad_id']}"
                if c.get("src") == "json" and c.get("price") and c.get("year"):
                    samples.append({"id": key, "price": c["price"], "year": c["year"], "km": c.get("km")})
                if key not in cards:
                    cards[key] = c
                    got += 1
        if got == 0:  # results page blocked or unreadable: find ad links through a search engine
            links = [x for q in search_queries(plat, req) for x in fetch.search_links(q)]
            for link, title in links:
                p, ad_id = ad_identity(link)
                if p == plat and ad_id:
                    key = f"{plat}-{ad_id}"
                    if key not in cards:
                        cards[key] = {"url": clean_url(link), "platform": p, "ad_id": ad_id, "title": title, "src": "search"}
                        got += 1
                        d["via_search"] += 1
        d["cards"] += got
    return cards, samples


# ---------------------------------------------------------------- reading one ad

def epoch_or_date(v, today):
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{10}(\d{3})?", v.strip())):
        n = float(v)
        n = n / 1000 if n > 1e12 else n
        try:
            d = dt.datetime.fromtimestamp(n, dt.timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
        return d if dt.date(2015, 1, 1) <= d <= today else None
    return parse_date(v, today)


def read_ad(item, today, debug=None):
    """Open one ad page -> (status, values) where status is ok / sold / gone / failed."""
    page = fetch.get(item["url"])
    if debug is not None:
        debug.update({"status": page.status, "final": page.final_url[:160], "bytes": len(page.html)})
    if page.status in (404, 410):
        return "gone", {}
    if not page.ok:
        return "failed", {"_why": page.error or ("blocked" if page.blocked else f"HTTP {page.status}")}
    p2, id2 = ad_identity(page.final_url)
    if id2 != item["ad_id"] and re.search(r"(?:login|signin|sign-in|auth|captcha)", urllib.parse.urlparse(page.final_url).path, re.I):
        return "failed", {"_why": "authentication required"}
    if id2 != item["ad_id"]:  # redirected to a results page: the ad was removed
        return "gone", {}
    f = extract.ad_page(page.html, page.final_url, item["ad_id"])
    if debug is not None:
        text = extract.text_of(page.html)
        m = extract.SOLD.search(text[:20000])
        debug["sold_hit"] = text[max(0, m.start() - 60): m.end() + 60] if m else None
        debug["values"] = {k: str(v[0])[:80] for k, v in f.items() if isinstance(v, tuple)}
        debug["lines"] = [ln.strip()[:120] for ln in text.split("\n") if re.search(
            r"post|publish|added|updated|date|ago|AED|price|km|kilomet|mileage|year|نشر|تاريخ|منذ|درهم|السعر|كم", ln, re.I) and len(ln.strip()) < 140][:40]
    if f.get("_sold"):
        return "sold", {}
    if f.get("_unavailable"):
        return "gone", {}
    g = lambda k: (f.get(k) or (None, None))[0]
    src = {k: v[1] for k, v in f.items() if isinstance(v, tuple)}
    # Each value must be plausible; otherwise the next source is used (title, then the results card).
    card = item if item.get("src") == "json" else {}
    price = to_num(g("price"))
    price = int(price) if price and 1500 <= price <= 5_000_000 else None
    title_year = re.search(r"\b(19[89]\d|20[0-3]\d)\b", str(g("title") or ""))
    year = next((int(x) for x in (to_num(g("year")), float(title_year[1]) if title_year else None, to_num(card.get("year")))
                 if x and 1980 <= x <= today.year + 1), None)
    km = next((int(x) for x in (to_num(g("km")), to_num(card.get("km"))) if x is not None and 0 <= x <= 1_500_000), None)
    image = g("image")
    image = image if isinstance(image, str) and image.startswith("http") else None
    st = str(g("seller_type") or "").lower()
    seller_type = "dealer" if st in ("dealer", "showroom", "معرض") else "owner" if st in ("owner", "private seller", "by owner", "مالك", "بائع خاص") else None
    loc = g("location")
    loc = loc if isinstance(loc, str) and (emirate_of(loc) or "," in loc) and len(loc) <= 120 else None
    date, kind = None, None
    for key, k in (("posted", "posted"), ("updated", "updated")):
        d = epoch_or_date(g(key), today)
        if d:
            date, kind = d, k
            break
    if not date and item["platform"] in ("dubizzle", "yallamotor"):
        d = date_in_path(image, today)
        if d:
            date, kind = d, "photos"
    if not date:
        d = parse_date(g("inspected"), today)
        if d:
            date, kind = d, "inspected"
    phone = g("phone")
    phone = str(phone).strip() if phone and len(re.sub(r"\D", "", str(phone))) >= 8 else None
    if phone and (re.sub(r"\D", "", phone)[-7:] in PLACEHOLDER_PHONES or re.sub(r"\D", "", phone).endswith(PLATFORM_PHONES)):
        phone = None  # a sample number in the page template, or the platform's own office line
    return "ok", {
        "title": str(g("title") or item.get("title") or "")[:160], "price": price,
        "availability": "reserved" if f.get("_reserved") else "available",
        "price_source": src.get("price"), "price_currency": "AED" if price else None, "price_version": 3, "year": year, "km": km,
        "color": color_of(str(g("color") or "")), "emirate": emirate_of(" ".join(str(x or "") for x in (loc, g("title"), item["url"]))),
        **{k: g(k) for k in ("vin", "vin_source", "vin_status", "phone_source", "phone_status", "identity_version")},
        "location": loc[:120] if loc else None, "phone": phone, "seller_name": str(g("seller") or "")[:80] or None,
        "seller_type": seller_type, "specs": str(g("specs") or "")[:30] or None, "transmission": str(g("transmission") or "")[:30] or None,
        "image": image, "date": date, "date_kind": kind, "desc": None, "_src": src,
    }


def assess(req, v, start, plat):
    c = {}
    names = " ".join(str(x or "") for x in (v.get("title"), v.get("_url", "").replace("-", " ").replace("/", " ")))
    c["model"] = "matched" if has_terms(names, model_terms(req)) else "unknown"
    if req.get("year_from") or req.get("year_to"):
        if v["year"] is None:
            c["year"] = "unknown"
        else:
            ok = (not req.get("year_from") or v["year"] >= int(req["year_from"])) and \
                 (not req.get("year_to") or v["year"] <= int(req["year_to"]))
            c["year"] = "matched" if ok else "mismatched"
    if req.get("price_max"):
        c["price"] = "unknown" if v["price"] is None else ("matched" if v["price"] <= float(req["price_max"]) else "mismatched")
    if req.get("mileage_max"):
        c["km"] = "unknown" if v["km"] is None else ("matched" if v["km"] <= float(req["mileage_max"]) else "mismatched")
    want = color_of(req.get("color"))
    if want:
        c["color"] = "unknown" if not v["color"] else ("matched" if v["color"] == want else "mismatched")
    want = emirate_of(req.get("emirate"))
    if want:
        c["emirate"] = "unknown" if not v["emirate"] else ("matched" if v["emirate"] == want else "mismatched")
    d, kind = v["date"], v["date_kind"]
    if d is None:
        c["posted"] = "unknown"
    elif kind == "posted":
        c["posted"] = "matched" if start <= d <= now_uae().date() else "mismatched"
    elif d >= start:
        c["posted"] = "approx"
    else:
        c["posted"] = "unknown" if kind == "inspected" else "mismatched"
    return c


def state_of(checks, plat, known):
    bad = [f for f, s in checks.items() if s == "mismatched"]
    unknown = [f for f, s in checks.items() if s == "unknown"]
    if bad:
        return "excluded", "لا يطابق: " + "، ".join(FIELD_AR[f] for f in bad)
    if unknown:
        if unknown == ["posted"] and plat in NO_DATE_PLATFORMS:
            return "approx", "المواصفات متوافقة؛ تاريخ النشر غير متاح ويحتاج تأكيدًا"
        return "unverified", "غير ظاهر في الإعلان: " + "، ".join(FIELD_AR[f] for f in unknown)
    if checks.get("posted") == "approx":
        return "approx", "المواصفات متوافقة؛ التاريخ المعروض تحديث أو صور أو فحص، وتاريخ النشر يحتاج تأكيدًا"
    return "verified", ""


# ---------------------------------------------------------------- the round

def load_all(key):
    user = store.read_json(USER_FILE, key, {})
    eng = store.read_json(ENGINE_FILE, key, {})
    for k, v in (("listings", {}), ("runs", []), ("reports", []), ("market", {}), ("skipped", {}), ("drops", [])):
        eng.setdefault(k, v)
    return user, eng


def marks_of(user):
    return user.get("marks") or {}


def trusted_price(listing):
    return bool(listing.get("price")) and listing.get("price_version") == 3 and listing.get("price_currency") == "AED" and not str(listing.get("price_source") or "").startswith("card")


def mark_duplicates(listings):
    """Hide a copy only with the same valid VIN and equivalent request coverage.

    Model year, odometer, price and a shared dealer are not unique vehicle identities.
    Scopes must agree so a cheap copy cannot hide a match belonging to another request.
    """
    from identity import vin_status
    groups = {}
    for listing in listings.values():
        for key in ("dup_of", "duplicates", "dup_version"):
            listing.pop(key, None)
        if not trusted_price(listing) or listing.get("state") in ("sold", "excluded") or listing.get("availability", "available") != "available":
            continue
        vin, _ = vin_status(listing.get("vin"))
        if not vin:
            continue
        req_ids = sorted(listing.get("request_ids", [listing.get("request_id")]) or [])
        coverage = tuple((rid, (listing.get("by_request", {}).get(rid) or {}).get("state", listing.get("state"))) for rid in req_ids)
        groups.setdefault((vin, coverage), []).append(listing)
    count = 0
    for group in groups.values():
        if len({listing["platform"] for listing in group}) < 2:
            continue
        best = min(group, key=lambda listing: (listing["price"], listing.get("state") != "verified", listing["id"]))
        best["dup_version"] = 2
        best["duplicates"] = [{"id": item["id"], "platform": item["platform"], "url": item["url"], "price": item["price"]}
                              for item in sorted(group, key=lambda item: item["price"]) if item is not best]
        for item in group:
            if item is not best:
                item.update(dup_of=best["id"], dup_version=2)
        count += 1
    return count


def load_presence(key):
    """Only a fresh, authenticated activity record can suppress a scheduled search."""
    try:
        payload = store.read_json(os.path.join(WORK, "activity.enc"), key, {})
        age = (now_uae() - dt.datetime.fromisoformat(payload["at"])).total_seconds()
        return 0 <= age < 180
    except (OSError, ValueError, KeyError, TypeError, store.BadPassphrase):
        return False


def reassess_saved(listings, reqs, start, today):
    for listing in listings.values():
        if listing.get("state") == "sold":
            continue
        for req in reqs:
            if req["id"] not in listing.get("request_ids", [listing.get("request_id")]):
                continue
            v = {"title": listing.get("title"), "_url": listing.get("url"), "year": listing.get("year"),
                 "price": listing.get("price"), "km": listing.get("mileage"), "color": color_of(listing.get("color")),
                 "emirate": emirate_of(listing.get("emirate")), "date": parse_date(listing.get("date"), today),
                 "date_kind": listing.get("date_kind")}
            checks = assess(req, v, start, listing["platform"])
            state, note = state_of(checks, listing["platform"], True)
            listing.setdefault("by_request", {})[req["id"]] = {"state": state, "note": note, "checks": checks}


def run_round(a, key):
    t0 = time.time()
    now = now_uae()
    today, stamp = now.date(), now.isoformat(timespec="seconds")
    start = window_start(today)
    user, eng = load_all(key)
    marks = marks_of(user)
    run_id = a.run_id or (("s" if a.mode == "scheduled" else "m") + now.strftime("%Y%m%d%H%M"))
    reqs = [r for r in (user.get("requests") or []) if r.get("active", True)]
    if a.request and a.request != "all":
        reqs = [r for r in reqs if r.get("id") == a.request]
    if a.mode == "scheduled":
        if load_presence(key):
            log("scheduled_skipped", why="dashboard active")
            return
        reqs = [r for r in reqs if r.get("scheduled")]
    invalid = [validate_request(r) for r in reqs if validate_request(r)]
    reqs = [r for r in reqs if not validate_request(r)]
    progress=Progress(run_id)
    progress.discovery_total=sum(len(search_urls(p,r)) + (len(search_urls(p,r,market=True)) if p=="dubizzle" and r.get("price_max") else 0) for r in reqs for p in (r.get("platforms") or list(PLATFORMS)) if p in PLATFORMS)
    progress.update("discover",0,progress.discovery_total,force=True)
    listings = eng["listings"]
    for book in eng.get("market", {}).values():
        for listing_id in list(book):
            if str((listings.get(listing_id) or {}).get("price_source") or "").startswith("card"):
                del book[listing_id]
    diag, opened_stats = {}, {}
    new_ids, drops, sold = [], [], []

    reassess_saved(listings, reqs, start, today)

    # 1) find ads
    plan = []  # (request, card)
    funnel = {}  # counts per platform, saved with the run (encrypted) to explain each round
    for req in reqs:
        plats = [p for p in (req.get("platforms") or list(PLATFORMS)) if p in PLATFORMS]
        cards, samples = discover(req, plats, diag, progress)
        # Price estimates use opened ad evidence, never unverified result-card prices/years.
        model_key = slug(req.get("make")) + "/" + slug(req.get("model"))
        if eng.setdefault("market_models", {}).get(req["id"]) != model_key:
            eng["market"][req["id"]] = {}
            eng["market_models"][req["id"]] = model_key
        for k, c in cards.items():
            st = funnel.setdefault(c["platform"], {"cards": 0, "known": 0, "skipped_recently": 0, "card_rejected": 0, "planned": 0, "states": {}, "excluded_by": {}})
            st["cards"] += 1
            if k in listings:
                st["known"] += 1
                if req["id"] not in listings[k].get("by_request", {}):
                    plan.append((req, {**c, "id": k, "_recheck": True}))
                continue
            sk = eng["skipped"].get(k)
            if sk and sk.get("request_id") == req["id"] and sk.get("at", "") > (now - dt.timedelta(days=SKIP_DAYS)).isoformat():
                st["skipped_recently"] += 1
                continue
            if card_ok(req, c):
                plan.append((req, {**c, "id": k}))
                st["planned"] += 1
            else:
                st["card_rejected"] += 1
    # new ads platform by platform in turn, so one busy site cannot take every slot
    cap = MAX_OPEN[a.mode]
    queues = {}
    for item in plan:
        queues.setdefault(item[1]["platform"], []).append(item)
    order = []
    while any(queues.values()):
        for q in queues.values():
            if q:
                order.append(q.pop(0))
    deferred = max(0, len(order) - cap)
    order = order[:cap]
    # saved ads due for a price / sold check
    req_by_id = {r["id"]: r for r in (user.get("requests") or [])}
    run_req_ids = {r["id"] for r in reqs}
    due = []
    for l in listings.values():
        m = marks.get(l["id"]) or {}
        if l.get("state") in ("sold", "excluded") or m.get("status") in ("dismissed", "purchased"):
            continue
        if not (set(l.get("request_ids", [l.get("request_id")])) & run_req_ids):
            continue
        try:
            age = (now - dt.datetime.fromisoformat(l.get("last_checked") or l.get("first_seen"))).total_seconds() / 3600
        except (TypeError, ValueError):
            age = 1e9
        if not l.get("price") or l.get("price_version", 0) < 3 or l.get("identity_version", 0) < 1 or str(l.get("price_source") or "").startswith("card"):
            age += 1e8
        if age >= RECHECK_HOURS:
            due.append((age, l))
    due.sort(key=lambda x: -x[0])
    order += [(req_by_id[next(r for r in l.get("request_ids", [l["request_id"]]) if r in run_req_ids)], {"id": l["id"], "url": l["url"], "platform": l["platform"],
                                           "ad_id": l["ad_id"], "title": l.get("title"), "_recheck": True})
              for _, l in due[: max(20, cap - len(order))]]

    # 2) read the ad pages
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=[]
        progress.update("read",0,len(order),force=True)
        for result in pool.map(lambda it: read_ad(it[1], today), order):
            results.append(result); progress.update("read",len(results),len(order))

    # 3) decide
    for (req, item), (status, v) in zip(order, results):
        plat = item["platform"]
        ps = opened_stats.setdefault(plat, {"opened": 0, "read_ok": 0, "read_failed": 0, "fields": {}})
        ps["opened"] += 1
        prev = listings.get(item["id"])
        events = lifecycle.observe(eng, prev, status, v, stamp) if prev else []
        if status in ("sold", "gone"):
            if prev and any(c["field"]=="availability" for e in events for c in e["changes"]):
                prev.update({"state": "sold", "last_checked": stamp})
                sold.append(prev)
            continue
        if status == "failed":
            ps["read_failed"] += 1
            if prev:
                continue  # keep it; try again next round
            v = {"title": item.get("title") or "", "price": None, "year": item.get("year"), "km": item.get("km"),
                 "color": None, "emirate": emirate_of(item.get("title")), "location": None, "phone": None,
                 "seller_name": None, "seller_type": None, "specs": None, "transmission": None,
                 "image": item.get("image"), "date": None, "date_kind": None, "desc": None, "_src": {}}
            fetched = False
        else:
            ps["read_ok"] += 1
            for f, s in v["_src"].items():
                ps["fields"][f] = ps["fields"].get(f, 0) + 1
            fetched = True
        if not v.get("price"):
            fs = funnel.setdefault(plat, {"cards": 0, "known": 0, "skipped_recently": 0, "card_rejected": 0, "planned": 0, "states": {}, "excluded_by": {}})
            fs["missing_price"] = fs.get("missing_price", 0) + 1
            if prev:
                prev.update({"price": None, "price_source": None, "price_currency": None, "price_version": 3, "last_checked": stamp})
            # Keep no-price evidence only in diagnostics, never as a user-facing offer.
            continue
        if fetched and v["price"] and v["year"] and has_terms(v["title"] + " " + item["url"].replace("-", " "), model_terms(req)):
            analytics.add_samples(eng["market"], req["id"], [{"id": item["id"], "price": v["price"], "year": v["year"], "km": v["km"]}], today)
        v["_url"] = item["url"]
        checks = assess(req, v, start, plat)
        if not fetched:
            st, note = "unverified", "تعذّر فتح صفحة الإعلان؛ البيانات من صفحة النتائج"
        else:
            st, note = state_of(checks, plat, bool(prev))
        fs = funnel.setdefault(plat, {"cards": 0, "known": 0, "skipped_recently": 0, "card_rejected": 0, "planned": 0, "states": {}, "excluded_by": {}})
        fs["states"][st] = fs["states"].get(st, 0) + 1
        for f, c in checks.items():
            if c == "mismatched":
                fs["excluded_by"][f] = fs["excluded_by"].get(f, 0) + 1
        if st == "excluded" and not prev:
            eng["skipped"][item["id"]] = {"request_id": req["id"], "at": stamp, "reason": note}
            continue
        extra = {"color": COLOR_AR.get(v["color"]) if v["color"] else None,
                 "emirate": EMIRATE_AR.get(v["emirate"]) if v["emirate"] else None}
        if prev:
            prev["request_ids"] = sorted(set(prev.get("request_ids", [prev["request_id"]])) | {req["id"]})
            prev.setdefault("by_request", {})[req["id"]] = {"state": st, "note": note, "checks": checks}
            patch = {"last_seen": stamp, "last_checked": stamp, "state": st, "note": note, "checks": checks,
                     "price_source": v.get("price_source"), "price_currency": "AED", "price_version": 3}
            patch.update({k: v.get(k) for k in ("vin", "vin_source", "vin_status", "phone", "phone_source", "phone_status", "identity_version")})
            for k in ("seller_name", "seller_type", "specs", "transmission", "image", "location", "mileage", "year"):
                val = v.get("km" if k == "mileage" else k)
                if val and not prev.get(k):
                    patch[k] = val
            for k, val in extra.items():
                if val and not prev.get(k):
                    patch[k] = val
            if v["date"] and not prev.get("date"):
                patch.update({"date": v["date"].isoformat(), "date_kind": v["date_kind"],
                              "posted": v["date"].isoformat() if v["date_kind"] == "posted" else None})
            if v["price"] and not prev.get("price"):
                patch["price"] = v["price"]
            if v["price"] and prev.get("price") and v["price"] != prev["price"]:
                hist = list(prev.get("price_history") or []) + [{"at": stamp, "price": v["price"]}]
                patch.update({"price": v["price"], "price_prev": prev["price"], "price_changed_at": stamp, "price_history": hist[-30:]})
                drop = analytics.price_drop(prev["price"], v["price"])
                if drop:
                    drops.append({"id": prev["id"], "name": report.car_name(prev, req), "from": prev["price"], "to": v["price"],
                                  "pct": drop[1], "url": prev["url"], "at": stamp, "request_id": req["id"]})
            prev.update(patch)
            continue
        doc = {
            "id": item["id"], "ad_id": item["ad_id"], "request_id": req["id"],
            "request_ids": [req["id"]], "by_request": {req["id"]: {"state": st, "note": note, "checks": checks}}, "platform": plat, "url": item["url"],
            "title": v["title"], "price": v["price"], "price_source": v.get("price_source"), "price_currency": "AED", "price_version": 3, "year": v["year"], "mileage": v["km"], **extra,
            **{k: v.get(k) for k in ("vin", "vin_source", "vin_status", "phone_source", "phone_status", "identity_version")},
            "location": v["location"], "phone": v["phone"], "seller_name": v["seller_name"], "seller_type": v["seller_type"],
            "availability": v.get("availability", "available"), "specs": v["specs"], "transmission": v["transmission"], "image": v["image"],
            "date": (v["date"] or today).isoformat(), "date_kind": v["date_kind"] or "first_seen",
            "posted": v["date"].isoformat() if v["date"] and v["date_kind"] == "posted" else None,
            "state": st, "note": note, "checks": checks, "first_seen": stamp, "last_seen": stamp,
            "last_checked": stamp if fetched else None, "run_id": run_id,
            "price_history": [{"at": stamp, "price": v["price"]}] if v["price"] else [],
        }
        listings[item["id"]] = doc
        new_ids.append(item["id"])

    reassess_saved(listings, reqs, start, today)
    for listing in listings.values():
        if listing.get("state") == "sold":
            continue
        assessments = list(listing.get("by_request", {}).values())
        if assessments:
            best = min(assessments, key=lambda x: {"verified": 0, "unverified": 1, "approx": 1, "excluded": 2}.get(x["state"], 3))
            listing.update(best)

    mark_duplicates(listings)

    # 4) analytics for every live listing of the round's requests
    market_info = {}
    for req in reqs:
        book = eng["market"].get(req["id"]) or {}
        prices = sorted(s["price"] for s in book.values())
        market_info[req["id"]] = {"n": len(prices), "median": int(prices[len(prices) // 2]) if prices else None}
    for l in listings.values():
        if not (set(l.get("request_ids", [l.get("request_id")])) & run_req_ids) or l.get("state") in ("sold", "excluded"):
            continue
        fp = analytics.fair_price(eng["market"].get(l["request_id"]) or {}, l.get("year"), l.get("mileage"), exclude_id=l["id"])
        rating, dev = analytics.rate(l.get("price"), fp)
        score, level, why = analytics.urgency(l, today, dev)
        l.update({"fair": fp, "rating": rating, "dev": round(dev, 4) if dev is not None else None,
                  "urgency": {"score": score, "level": level, "why": why}})

    progress.update("save", len(order), len(order), force=True)
    # 5) report
    live = lambda l: not l.get("dup_of") and trusted_price(l) and l.get("price_version") == 3 and l.get("price_currency") == "AED" and l.get("availability", "available") == "available" and l.get("state") in ("verified", "approx", "unverified") and (marks.get(l["id"]) or {}).get("status") not in ("dismissed", "purchased")
    full = a.mode == "manual"
    groups, cur_ver, cur_cand = [], 0, 0
    for req in reqs:
        # A request's first scheduled round (or the first after its conditions changed) lists the whole month.
        done_at = (eng.get("sched_done") or {}).get(req["id"], "")
        first = a.mode == "scheduled" and (not done_at or done_at < (req.get("sched_reset_at") or ""))
        rows = []
        for listing in listings.values():
            l = request_view(listing, req["id"])
            if l and live(l):
                if l.get("date_kind") == "posted" and not (start.isoformat() <= l.get("posted", "") <= today.isoformat()):
                    continue
                rows.append(dict(l, _new=l["id"] in new_ids))
        if not (full or first):  # later scheduled rounds: what is new or changed price
            fresh = set(new_ids) | {d["id"] for d in drops} | {e["listing_id"] for e in eng.get("alerts",[]) if e["at"]==stamp}
            rows = [l for l in rows if l["id"] in fresh]
        ver = [l for l in rows if l["state"] == "verified"]
        cand = [l for l in rows if l["state"] in ("unverified", "approx")]
        cur_ver += len(ver)
        cur_cand += len(cand)
        groups.append((req, ver, cand))
    if a.mode == "scheduled":
        eng.setdefault("sched_done", {}).update({r["id"]: stamp for r in reqs})
    blocked = [PLATFORMS[p]["name"] for p, d in diag.items() if d["pages"] and not d["ok"] and not d["via_search"]]
    run = {"id": run_id, "at": stamp, "mode": a.mode, "status": "done", "requests": [r["id"] for r in reqs],
           "request_names": [r.get("name") for r in reqs], "found": sum(d["cards"] for d in diag.values()),
           "opened": len(order), "new": len([i for i in new_ids if listings[i]["state"] == "verified"]),
           "new_unverified": len([i for i in new_ids if listings[i]["state"] in ("unverified", "approx")]),
           "price_drops": len(drops), "sold": len(sold), "current_offers": cur_ver, "candidates": cur_cand,
           "deferred": deferred, "market": market_info, "missing_price": sum(d.get("missing_price", 0) for d in funnel.values()),
           "warning": "؛ ".join(invalid + ([("تعذّر الوصول إلى: " + "، ".join(blocked))] if blocked else [])),
           "platforms": {p: {**diag.get(p, {}), **opened_stats.get(p, {})} for p in set(diag) | set(opened_stats)}}
    if reqs and not sum(d.get("ok", 0) for d in diag.values()) and not run["found"]:
        run["status"] = "failed"
        run["warning"] = (run.get("warning", "") + "؛ لم تُفحص أي صفحة نتائج بنجاح؛ لا يمكن استنتاج عدم وجود عروض").strip("؛ ")
    if not reqs:
        run.update({"status": "failed" if invalid else "done", "warning": "؛ ".join(invalid) if invalid else "لا توجد طلبات بحث مفعّلة لهذه الجولة"})
    eng["drops"] = (drops + eng["drops"])[:200]
    for problem in quality_warnings():
        run["warning"] = (run.get("warning", "") + "؛ " + problem).strip("؛ ")
    profile = user.get("profile") or {}
    os.makedirs(WORK, exist_ok=True)
    pdf_plain = os.path.join(WORK, f"{run_id}.pdf")
    wants_pdf = a.mode == "scheduled" and bool(reqs)
    have_pdf = wants_pdf and report.to_pdf(report.render_html(run, groups, drops, now, start, profile, sorted(diag)),
                                            os.path.join(WORK, f"{run_id}.html"), pdf_plain)
    if wants_pdf and not have_pdf:
        run["warning"] = (run.get("warning", "") + "؛ تعذّر إنشاء PDF").strip("؛ ")
    morning = now.hour < 15
    full_text = report.summary_text(run, groups, drops, now, start, SITE, short=False)
    short_text = report.summary_text(run, groups, drops, now, start, SITE, short=True)
    round_events=[e for e in eng.get("alerts",[]) if e["at"]==stamp]
    run["changes"]=len(round_events)
    if round_events:
        change_text=lifecycle.message(round_events,SITE)
        full_text += "\n\n"+change_text; short_text += "\n\n"+change_text
    if have_pdf:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        with open(pdf_plain, "rb") as f:
            store.write_file(os.path.join(REPORTS_DIR, f"{run_id}.pdf.enc"), f.read(), key)
        eng["reports"].insert(0, {"id": run_id, "at": stamp, "mode": a.mode, "file": f"reports/{run_id}.pdf.enc",
                                  "current_offers": cur_ver, "candidates": cur_cand, "new": run["new"] + run["new_unverified"],
                                  "identity_coverage": {"total": len({l["id"] for _,v,c in groups for l in v+c}),
                                  "vin": len({l["id"] for _,v,c in groups for l in v+c if l.get("vin") and l.get("identity_version") == 1}),
                                  "phone": len({l["id"] for _,v,c in groups for l in v+c if l.get("phone") and l.get("identity_version") == 1})},
                                  "price_drops": len(drops), "request_names": run["request_names"], "summary": full_text[:4000]})
    # 6) notify: scheduled rounds only (manual searches show in the dashboard)
    if a.mode == "scheduled" and reqs:
        subject = f"رادار السيارات — {'ملخص الصباح' if morning else 'تقرير المساء'} {now:%d/%m/%Y}"
        run["notify"] = notify.send_all(subject, full_text, short_text, pdf_plain if have_pdf else None,
                                        f"car-report-{now:%Y-%m-%d-%H%M}.pdf")
        problem = notify.delivery_problem(run["notify"])
        if problem:
            run["warning"] = (run.get("warning", "") + "؛ " + problem).strip("؛ ")
    run["seconds"] = round(time.time() - t0)
    run["funnel"] = {p: {**{k: v for k, v in diag.get(p, {}).items() if k != "status"}, "http": diag.get(p, {}).get("status"),
                         **{k: v for k, v in opened_stats.get(p, {}).items() if k != "fields"}, **funnel.get(p, {})}
                     for p in set(diag) | set(opened_stats) | set(funnel)}
    eng["runs"].insert(0, run)
    finish(eng, key)
    log("round", id=run_id, mode=a.mode, requests=len(reqs), found=run["found"], opened=run["opened"], new=run["new"],
        new_unverified=run["new_unverified"], drops=len(drops), sold=len(sold), seconds=run["seconds"],
        platforms={p: {k: v for k, v in d.items() if k != "fields"} for p, d in run["platforms"].items()},
        notify=run.get("notify"))


def watch(a, key):
    """Weekly review of saved searches, or an explicit review of followed cars. No PDF."""
    now=now_uae(); today=now.date(); stamp=now.isoformat(timespec="seconds")
    user,eng=load_all(key); marks=marks_of(user)
    reqs={r["id"]:r for r in user.get("requests",[]) if r.get("active",True)}
    weekly=getattr(a,"weekly",False)
    targets=[l for l in eng["listings"].values() if (l.get("state")!='excluded' or (marks.get(l["id"]) or {}).get("favorite") or (marks.get(l["id"]) or {}).get("status") in FOLLOWING) and any(r in reqs for r in l.get("request_ids",[l.get("request_id")])) and (weekly or (marks.get(l["id"]) or {}).get("favorite") or (marks.get(l["id"]) or {}).get("status") in FOLLOWING) and (marks.get(l["id"]) or {}).get("status") not in ('dismissed','purchased')]
    targets.sort(key=lambda l:l.get('last_reviewed') or '')
    total=len(targets); targets=targets[:100]
    events=[]; drops=[]; failed=0
    with ThreadPoolExecutor(max_workers=6) as pool:
        res=list(pool.map(lambda l:read_ad({"url":l["url"],"ad_id":l["ad_id"],"platform":l["platform"]},today),targets))
    for l,(status,v) in zip(targets,res):
        events += lifecycle.observe(eng,l,status,v,stamp)
        l['last_reviewed']=stamp
        if status!='ok':
            if status=='failed': failed+=1
            continue
        l['last_checked']=stamp
        if v.get('price'):
            if l.get('price') and v['price']!=l['price']:
                old=l['price']; hist=list(l.get('price_history') or [])+[{"at":stamp,"price":v['price']}]
                if v['price']<old: drops.append({"id":l['id'],"from":old,"to":v['price'],"at":stamp,"url":l['url']})
                l.update(price_prev=old,price_changed_at=stamp,price_history=hist[-30:])
            l.update(price=v['price'],price_version=3,price_currency='AED',price_source=v.get('price_source'))
        else:
            l.update(price=None,price_currency=None,price_version=3)
        for k in ('vin','vin_source','vin_status','phone','phone_source','phone_status','identity_version','availability'):
            l[k]=v.get(k)
        for k in ('title','year','mileage','location'):
            val=v.get('km' if k=='mileage' else k)
            if val is not None: l[k]=val
        if v.get('color'):l['color']=COLOR_AR.get(v['color'],v['color'])
    reassess_saved(eng['listings'],list(reqs.values()),window_start(today),today)
    for listing in eng['listings'].values():
        if listing.get('state')=='sold': continue
        assessments=list(listing.get('by_request',{}).values())
        if assessments:
            listing.update(min(assessments,key=lambda x:{'verified':0,'unverified':1,'approx':1,'excluded':2}.get(x['state'],3)))
    mark_duplicates(eng["listings"])
    sent=None
    if events:
        text=lifecycle.message(events,SITE)
        sent=notify.send_all('تحديثات السيارات المحفوظة',text,text)
    warnings=quality_warnings()
    if failed: warnings.append(f"تعذّر فحص {failed} سيارة؛ احتُفظ بآخر حالة مؤكدة.")
    delivery=notify.delivery_problem(sent)
    if delivery: warnings.append(delivery)
    eng['last_weekly_review']=stamp if weekly else eng.get('last_weekly_review')
    eng['runs'].insert(0,{"id":"w"+now.strftime('%Y%m%d%H%M'),"at":stamp,"mode":"watch","weekly":weekly,"status":"done","opened":len(targets),"changes":len(events),"price_drops":len(drops),"failed":failed,"deferred":max(0,total-len(targets)),"warning":"؛ ".join(warnings),"notify":sent})
    finish(eng,key);log('watch',reviewed=len(targets),changes=len(events),failed=failed,notify=sent)


def quality_warnings():
    """Checks that ran before the search (see the workflow) and failed. They never stop a round."""
    out = []
    if os.environ.get("RADAR_TESTS") == "failure":
        out.append("فشلت اختبارات الجودة قبل هذه الجولة؛ راجع النتائج بحذر")
    if os.environ.get("RADAR_PDF_CHECK") == "failure":
        out.append("فشل فحص مولّد التقارير قبل هذه الجولة")
    return out


def finish(eng, key):
    eng["runs"] = eng["runs"][:KEEP_RUNS]
    keep = eng["reports"][:KEEP_REPORTS]
    for r in eng["reports"][KEEP_REPORTS:]:
        p = os.path.join(ROOT, r["file"])
        if os.path.exists(p):
            os.remove(p)
    eng["reports"] = keep
    cutoff = (now_uae() - dt.timedelta(days=30)).isoformat()
    eng["skipped"] = {k: v for k, v in eng["skipped"].items() if v.get("at", "") > cutoff}
    eng["updated"] = now_uae().isoformat(timespec="seconds")
    store.write_json(ENGINE_FILE, eng, key)


def diagnose(a, key):
    """What each platform returns from GitHub's servers; saved inside the encrypted data."""
    req = {"id": "probe", "make": a.make, "model": a.model, "year_from": a.year_from, "year_to": a.year_to}
    today = now_uae().date()
    diag = {}
    cards, samples = discover(req, list(PLATFORMS), diag)
    per = {}
    for c in cards.values():
        per.setdefault(c["platform"], []).append(c)
    out = {}
    for plat in PLATFORMS:
        sample = per.get(plat, [])[:2]
        reads = []
        for c in sample:
            dbg = {}
            status, v = read_ad({**c, "id": f"{plat}-{c['ad_id']}"}, today, dbg)
            reads.append({"status": status, "debug": dbg, "url": c["url"], "found": sorted(v.get("_src", {}).items()) if status == "ok" else v.get("_why"),
                          "has": {k: bool(v.get(k)) for k in ("price", "year", "km", "date", "phone", "image", "color", "emirate")} if status == "ok" else None})
        out[plat] = {**diag.get(plat, {}), "card_sources": sorted({c.get("src") for c in per.get(plat, [])}),
                     "cards_with_price": sum(1 for c in per.get(plat, []) if c.get("price")), "ad_reads": reads}
    out["_samples"] = len(samples)
    out["_search"] = {}
    for plat in ("dubizzle", "mourjan"):
        q = search_query(plat, req)
        out["_search"][plat] = {"query": q, **fetch.search_debug(q)}
    mj = fetch.get("https://www.mourjan.com/ae/")
    out["_mourjan_home"] = {"status": mj.status, "bytes": len(mj.html), "links": sorted(set(re.findall(r'href="([^"#]+)"', mj.html)))[:120]}
    bp = fetch.get(search_urls("dubizzle", req)[0])
    out["_dubizzle_page"] = {"status": bp.status, "blocked": bp.blocked, "bytes": len(bp.html),
                             "head": re.sub(r"\s+", " ", extract.text_of(bp.html))[:300]}
    out = {p: {k: v for k, v in d.items() if k in ("pages", "ok", "blocked", "cards", "via_search", "status", "cards_with_price")}
           for p, d in out.items() if p in PLATFORMS}
    log("diagnose", platforms=len(out))
    user, eng = load_all(key)
    eng["diagnose"] = {"at": now_uae().isoformat(timespec="seconds"), "platforms": out}
    finish(eng, key)


def record_crash(a, key, error):
    """Save a failed run with the error type and place, without ad or personal data."""
    import traceback
    frame = traceback.extract_tb(error.__traceback__)[-1] if error.__traceback__ else None
    where = f"{os.path.basename(frame.filename)}:{frame.lineno}" if frame else "?"
    try:
        _, eng = load_all(key)
        now = now_uae()
        eng["runs"].insert(0, {"id": "e" + now.strftime("%Y%m%d%H%M"), "at": now.isoformat(timespec="seconds"),
                               "mode": getattr(a, "mode", a.cmd) if a.cmd == "run" else a.cmd, "status": "failed",
                               "warning": f"توقفت الجولة بسبب خطأ برمجي ({type(error).__name__} في {where}). "
                                          "الجولات التالية ستعمل كالمعتاد."})
        finish(eng, key)
    except Exception:  # noqa: BLE001 - nothing more can be saved
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "watch", "diagnose"])
    ap.add_argument("--weekly", action="store_true", help="review saved searches weekly")
    ap.add_argument("--mode", choices=["scheduled", "manual"], default="scheduled")
    ap.add_argument("--request", default="all")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--make", default="Toyota")
    ap.add_argument("--model", default="Yaris")
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--year-to", type=int, default=None)
    a = ap.parse_args()
    key = os.environ.get("RADAR_KEY", "")
    if not key:
        log("error", why="RADAR_KEY secret is missing")
        sys.exit(2)
    try:
        {"watch": watch, "diagnose": diagnose}.get(a.cmd, run_round)(a, key)
    except store.BadPassphrase:
        log("error", why="RADAR_KEY does not match the dashboard password")
        sys.exit(3)
    except Exception as e:  # noqa: BLE001 - record any crash so the dashboard can show it
        log("error", why=type(e).__name__)
        record_crash(a, key, e)
        sys.exit(1)


if __name__ == "__main__":
    main()
