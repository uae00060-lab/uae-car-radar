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

import analytics  # noqa: E402
import extract  # noqa: E402
import fetch  # noqa: E402
import notify  # noqa: E402
import report  # noqa: E402
import store  # noqa: E402
from common import (COLOR_AR, EMIRATE_AR, FIELD_AR, NO_DATE_PLATFORMS, PLATFORMS, ad_identity, clean_url,  # noqa: E402
                    color_of, date_in_path, emirate_of, has_terms, model_terms, now_uae, parse_date, slug,
                    to_num, window_start, validate_request, request_view)

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
    if not make:
        return []
    path = f"{make}/{model}" if model else make
    if plat == "dubizzle":
        q = {}
        if req.get("price_max") and not market:
            q["price__lte"] = int(req["price_max"])
        if req.get("year_from"):
            q["year__gte"] = int(req["year_from"]) - (1 if market else 0)
        if req.get("year_to"):
            q["year__lte"] = int(req["year_to"]) + (1 if market else 0)
        return [f"https://uae.dubizzle.com/motors/used-cars/{path}/" + ("?" + urllib.parse.urlencode(q) if q else "")]
    if plat == "yallamotor":
        return [f"https://uae.yallamotor.com/used-cars/{path}"]
    if plat == "dubicars":
        return [f"https://www.dubicars.com/uae/used/{path}"]
    if plat == "carswitch":
        return [f"https://carswitch.com/uae/used-cars/{path}"]
    if plat == "autoae":
        return [f"https://auto.ae/sale/car/all/{path}/"]
    if plat == "oneclickdrive":
        name = f"{make}-{model}" if model else make
        return [f"https://www.oneclickdrive.com/buy-{name}-used-cars-{c}" for c in ("dubai", "abu-dhabi", "sharjah")]
    if plat == "opensooq":
        return [f"https://ae.opensooq.com/en/cars/cars-for-sale/{path}"]
    if plat == "mourjan":
        if not make:
            return []
        # Public form values observed on the Toyota category, not guessed URL slugs.
        toyota_models = {"yaris": 250, "camry": 205, "corolla": 209, "land-cruiser": 223, "prado": 2209, "fortuner": 2205}
        q = {}
        if make == "toyota" and model in toyota_models: q["cm"] = toyota_models[model]
        for field, name in (("year_from", "mny"), ("year_to", "mxy"), ("price_max", "mxp")):
            if req.get(field) and not market: q[name] = int(req[field])
        return [f"https://www.mourjan.com/ae/{make}/for-sale/" + ("?" + urllib.parse.urlencode(q) if q else "")]
    return []


def search_queries(plat, req):
    """Search-engine queries that land on individual ads of this platform."""
    make, model = slug(req.get("make")), slug(req.get("model"))
    words = f"{make} {model}".replace("-", " ").strip()
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


def discover(req, plats, diag):
    """All ad cards for one request across its platforms, plus market samples from structured cards."""
    cards, samples = {}, []
    for plat in plats:
        d = diag.setdefault(plat, {"pages": 0, "ok": 0, "blocked": 0, "cards": 0, "via_search": 0, "status": []})
        got = 0
        urls = search_urls(plat, req) + (search_urls(plat, req, market=True) if plat == "dubizzle" and req.get("price_max") else [])
        for url in urls:
            page = fetch.get(url)
            d["pages"] += 1
            d["status"].append(page.status)
            if page.blocked:
                d["blocked"] += 1
            if not page.ok:
                continue
            d["ok"] += 1
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
    if price and not to_num(g("price")):
        src["price"] = "card"
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
            return "unverified", "كل شروطك مطابقة؛ المنصة لا تعرض تاريخ النشر"
        return "unverified", "غير ظاهر في الإعلان: " + "، ".join(FIELD_AR[f] for f in unknown)
    if checks.get("posted") == "approx":
        return "unverified", "تاريخ النشر غير مؤكد؛ التاريخ المتاح تحديث أو صور أو فحص"
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


def load_presence():
    try:
        path = os.path.join(WORK, "presence.json")
        if not os.path.exists(path):
            path = os.path.join(ROOT, "data", "presence.json")
        with open(path) as f:
            at = dt.datetime.fromisoformat(json.load(f)["at"])
        age = (now_uae() - at).total_seconds()
        return 0 <= age < 180
    except (OSError, ValueError, KeyError, TypeError):
        return False


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
        reqs = [r for r in reqs if r.get("scheduled")]
    if a.mode == "scheduled":
        presence = load_presence()
        if presence:
            log("scheduled_skipped", why="dashboard active")
            return
    invalid = [validate_request(r) for r in reqs if validate_request(r)]
    reqs = [r for r in reqs if not validate_request(r)]
    listings = eng["listings"]
    diag, opened_stats = {}, {}
    new_ids, drops, sold = [], [], []

    reassess_saved(listings, reqs, start, today)

    # 1) find ads
    plan = []  # (request, card)
    funnel = {}  # counts only, published as data/last_run.json to explain each round
    for req in reqs:
        plats = [p for p in (req.get("platforms") or list(PLATFORMS)) if p in PLATFORMS]
        cards, samples = discover(req, plats, diag)
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
        if not l.get("price") or l.get("price_version", 0) < 3 or l.get("identity_version", 0) < 1:
            age += 1e8
        if age >= RECHECK_HOURS:
            due.append((age, l))
    due.sort(key=lambda x: -x[0])
    order += [(req_by_id[next(r for r in l.get("request_ids", [l["request_id"]]) if r in run_req_ids)], {"id": l["id"], "url": l["url"], "platform": l["platform"],
                                           "ad_id": l["ad_id"], "title": l.get("title"), "_recheck": True})
              for _, l in due[: max(20, cap - len(order))]]

    # 2) read the ad pages
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda it: read_ad(it[1], today), order))

    # 3) decide
    for (req, item), (status, v) in zip(order, results):
        plat = item["platform"]
        ps = opened_stats.setdefault(plat, {"opened": 0, "read_ok": 0, "read_failed": 0, "fields": {}})
        ps["opened"] += 1
        prev = listings.get(item["id"])
        if status in ("sold", "gone"):
            if prev and prev.get("state") != "sold":
                prev.update({"state": "sold", "note": "الإعلان مباع أو محذوف", "last_checked": stamp})
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
            "specs": v["specs"], "transmission": v["transmission"], "image": v["image"],
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

    # 5) report
    live = lambda l: bool(l.get("price")) and l.get("price_version") == 3 and l.get("price_currency") == "AED" and l.get("state") in ("verified", "approx", "unverified") and (marks.get(l["id"]) or {}).get("status") not in ("dismissed", "purchased")
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
            fresh = set(new_ids) | {d["id"] for d in drops}
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
           "new_unverified": len([i for i in new_ids if listings[i]["state"] == "unverified"]),
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
    profile = user.get("profile") or {}
    os.makedirs(WORK, exist_ok=True)
    pdf_plain = os.path.join(WORK, f"{run_id}.pdf")
    have_pdf = bool(reqs) and report.to_pdf(report.render_html(run, groups, drops, now, start, profile, sorted(diag)),
                                            os.path.join(WORK, f"{run_id}.html"), pdf_plain)
    if not have_pdf and reqs:
        run["warning"] = (run.get("warning", "") + "؛ تعذّر إنشاء PDF").strip("؛ ")
    morning = now.hour < 15
    full_text = report.summary_text(run, groups, drops, now, start, SITE, short=False)
    short_text = report.summary_text(run, groups, drops, now, start, SITE, short=True)
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
    run["seconds"] = round(time.time() - t0)
    eng["runs"].insert(0, run)
    finish(eng, key)
    with open(os.path.join(ROOT, "data", "last_run.json"), "w") as f:  # public: numbers only, no criteria or ads
        json.dump({"at": stamp, "mode": a.mode, "requests": len(reqs), "seconds": run["seconds"], "opened": run["opened"],
                   "saved_new": len(new_ids), "drops": len(drops), "sold": len(sold), "listings_total": len(listings),
                   "platforms": {p: {**{k: v for k, v in diag.get(p, {}).items() if k != "status"}, "http": diag.get(p, {}).get("status"),
                                     **{k: v for k, v in opened_stats.get(p, {}).items() if k != "fields"}, **funnel.get(p, {})}
                                 for p in set(diag) | set(opened_stats) | set(funnel)}}, f, ensure_ascii=False, indent=1)
    log("round", id=run_id, mode=a.mode, requests=len(reqs), found=run["found"], opened=run["opened"], new=run["new"],
        new_unverified=run["new_unverified"], drops=len(drops), sold=len(sold), seconds=run["seconds"],
        platforms={p: {k: v for k, v in d.items() if k != "fields"} for p, d in run["platforms"].items()},
        notify=run.get("notify"))


def watch(a, key):
    """Re-read the ads you follow; alert at once on a price drop."""
    now = now_uae()
    today, stamp = now.date(), now.isoformat(timespec="seconds")
    user, eng = load_all(key)
    marks = marks_of(user)
    reqs = {r["id"]: r for r in (user.get("requests") or [])}
    targets = [l for l in eng["listings"].values()
               if l.get("state") not in ("sold", "excluded") and l.get("request_id") in reqs
               and ((marks.get(l["id"]) or {}).get("favorite") or (marks.get(l["id"]) or {}).get("status") in FOLLOWING)]
    targets = targets[:MAX_OPEN["watch"]]
    if not targets:
        log("watch", followed=0)
        return
    with ThreadPoolExecutor(max_workers=6) as pool:
        res = list(pool.map(lambda l: read_ad({"url": l["url"], "ad_id": l["ad_id"], "platform": l["platform"]}, today), targets))
    drops = []
    for l, (status, v) in zip(targets, res):
        if status in ("sold", "gone"):
            l.update({"state": "sold", "note": "الإعلان مباع أو محذوف", "last_checked": stamp})
            continue
        if status != "ok":
            continue
        l["last_checked"] = stamp
        l.update({k: v.get(k) for k in ("vin", "vin_source", "vin_status", "phone", "phone_source", "phone_status", "identity_version")})
        if v["price"] and l.get("price") and v["price"] != l["price"]:
            hist = list(l.get("price_history") or []) + [{"at": stamp, "price": v["price"]}]
            d = analytics.price_drop(l["price"], v["price"])
            if d:
                drops.append({"id": l["id"], "name": report.car_name(l, reqs[l["request_id"]]), "from": l["price"],
                              "to": v["price"], "pct": d[1], "url": l["url"], "at": stamp, "request_id": l["request_id"]})
            l.update({"price": v["price"], "price_prev": l["price"], "price_changed_at": stamp, "price_history": hist[-30:]})
    sent = None
    if drops:
        text = report.drop_alert_text(drops, SITE)
        sent = notify.send_all("📉 تخفيض سعر على سيارة تتابعها", text, text)
        eng["drops"] = (drops + eng["drops"])[:200]
    eng["runs"].insert(0, {"id": "w" + now.strftime("%Y%m%d%H%M"), "at": stamp, "mode": "watch", "status": "done",
                           "opened": len(targets), "price_drops": len(drops), "notify": sent})
    finish(eng, key)
    log("watch", followed=len(targets), drops=len(drops), notify=sent)


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


def diagnose(a):
    """Public, data-free check of what each platform returns from GitHub's servers."""
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
    log("diagnose", platforms=out)
    with open(os.path.join(ROOT, "data", "diagnose.json"), "w") as f:
        json.dump({"at": now_uae().isoformat(timespec="seconds"), "probe": "platform availability", "platforms": out}, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "watch", "diagnose"])
    ap.add_argument("--mode", choices=["scheduled", "manual"], default="scheduled")
    ap.add_argument("--request", default="all")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--make", default="Toyota")
    ap.add_argument("--model", default="Yaris")
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--year-to", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "diagnose":
        return diagnose(a)
    key = os.environ.get("RADAR_KEY", "")
    if not key:
        log("error", why="RADAR_KEY secret is missing")
        sys.exit(2)
    try:
        (watch if a.cmd == "watch" else run_round)(a, key)
    except store.BadPassphrase:
        log("error", why="RADAR_KEY does not match the dashboard password")
        sys.exit(3)


if __name__ == "__main__":
    main()
