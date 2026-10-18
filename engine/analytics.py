"""Market analytics from the radar's own observations.

fair_price  expected price for a year/mileage, from every priced ad of the same model the
            radar has seen in the last 60 days (including ads above your budget).
urgency     how motivated the seller looks: time on market, price cuts, wording.
"""

import datetime as dt
import math
import re
import statistics

SAMPLE_DAYS = 60
MIN_RATE = 5          # fewer comparable ads than this: no rating, just "not enough data"

RATING_AR = {"excellent": "صفقة ممتازة", "good": "سعر جيد", "fair": "سعر عادل", "high": "أعلى من السوق",
             "suspicious": "أقل من السوق بشكل غير معتاد", "unknown": "بيانات السوق غير كافية"}
URGENCY_AR = {"high": "مرتفع", "medium": "متوسط", "low": "منخفض"}
URGENT_WORDS = re.compile(
    r"urgent|must sell|quick sale|leaving (?:the )?(?:uae|country)|travell?ing|relocat|negotiable|best offer|"
    r"price drop|reduced|مستعجل|للبيع السريع|بداعي السفر|مسافر|سفر|قابل للتفاوض|قابلة للتفاوض|بسعر مغري|تخفيض", re.I)


def add_samples(market, request_id, obs, today):
    """obs: [{id, price, year, km}] seen today. Keeps one entry per ad, newest wins."""
    book = market.setdefault(request_id, {})
    for o in obs:
        if o.get("price") and o.get("year"):
            book[o["id"]] = {"price": int(o["price"]), "year": int(o["year"]),
                             "km": int(o["km"]) if o.get("km") else None, "seen": today.isoformat()}
    cutoff = (today - dt.timedelta(days=SAMPLE_DAYS)).isoformat()
    for k in [k for k, v in book.items() if v["seen"] < cutoff]:
        del book[k]
    if len(book) > 800:
        for k, _ in sorted(book.items(), key=lambda kv: kv[1]["seen"])[: len(book) - 800]:
            del book[k]


def _clean(samples):
    prices = [s["price"] for s in samples]
    if len(prices) < 3:
        return samples
    med = statistics.median(prices)
    return [s for s in samples if 0.4 * med <= s["price"] <= 2.5 * med]


def _solve3(a, b):
    """Solve a 3x3 linear system by Cramer's rule; None if singular."""
    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(a)
    if abs(d) < 1e-9:
        return None
    out = []
    for i in range(3):
        m = [row[:] for row in a]
        for r in range(3):
            m[r][i] = b[r]
        out.append(det(m) / d)
    return out


def fair_price(samples, year, km, exclude_id=None):
    """{"expected", "low", "high", "n", "method"} or None."""
    pool = _clean([s for k, s in samples.items() if k != exclude_id])
    if not year or len(pool) < MIN_RATE:
        return None
    with_km = [s for s in pool if s.get("km")]
    years = {s["year"] for s in with_km}
    # Regression on log price over year and mileage when the data spans enough variety.
    if km and len(with_km) >= 12 and len(years) >= 2:
        y0 = statistics.mean(s["year"] for s in with_km)
        xs = [(1.0, s["year"] - y0, s["km"] / 10000) for s in with_km]
        ys = [math.log(s["price"]) for s in with_km]
        ata = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
        aty = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(3)]
        coef = _solve3(ata, aty)
        # Sane only if newer is dearer (or flat) and more kilometres is cheaper (or flat).
        if coef and -0.02 <= coef[1] <= 0.35 and -0.08 <= coef[2] <= 0.005:
            pred = math.exp(coef[0] + coef[1] * (year - y0) + coef[2] * km / 10000)
            resid = sorted(y - (coef[0] + coef[1] * x[1] + coef[2] * x[2]) for x, y in zip(xs, ys))
            q1, q3 = resid[len(resid) // 4], resid[(3 * len(resid)) // 4]
            if year in years or min(abs(year - y) for y in years) <= 1:
                return {"expected": round(pred, -2), "low": round(pred * math.exp(q1), -2),
                        "high": round(pred * math.exp(q3), -2), "n": len(with_km), "method": "regression"}
    # Otherwise the median of the same model year (or within one year).
    for span in (0, 1):
        near = [s for s in pool if abs(s["year"] - year) <= span]
        if len(near) >= MIN_RATE:
            p = sorted(s["price"] for s in near)
            exp = statistics.median(p)
            if km:  # nudge for mileage against the group's median mileage: ~2% per 20,000 km
                kms = [s["km"] for s in near if s.get("km")]
                if len(kms) >= 3:
                    exp *= max(0.85, min(1.15, 1 - 0.02 * (km - statistics.median(kms)) / 20000))
            return {"expected": round(exp, -2), "low": p[len(p) // 4], "high": p[(3 * len(p)) // 4],
                    "n": len(near), "method": "median" if span == 0 else "median±1"}
    return None


def rate(price, fp):
    if not price or not fp:
        return "unknown", None
    dev = (price - fp["expected"]) / fp["expected"]
    if dev <= -0.35:
        return "suspicious", dev
    if dev <= -0.12:
        return "excellent", dev
    if dev <= -0.04:
        return "good", dev
    if dev <= 0.05:
        return "fair", dev
    return "high", dev


def urgency(listing, today, dev=None):
    """(score 0-100, level, [reasons in Arabic])."""
    score, why = 0, []
    since = listing.get("posted") or listing.get("date") or (listing.get("first_seen") or "")[:10]
    try:
        days = (today - dt.date.fromisoformat(since)).days
    except ValueError:
        days = None
    if days is not None:
        if days > 45:
            score += 25
            why.append(f"معروض منذ {days} يومًا")
        elif days > 21:
            score += 15
            why.append(f"معروض منذ {days} يومًا")
        elif days > 10:
            score += 5
    hist = [h["price"] for h in (listing.get("price_history") or []) if h.get("price")]
    cuts = sum(1 for a, b in zip(hist, hist[1:]) if b < a)
    if cuts:
        score += min(30, 15 * cuts)
        drop = (hist[0] - hist[-1]) / hist[0] if hist[0] else 0
        why.append(f"خفّض السعر {cuts} مرة" + (f" بإجمالي {drop:.0%}" if drop >= 0.01 else ""))
        if drop >= 0.05:
            score += 10
    words = {w.lower() for w in URGENT_WORDS.findall(" ".join(str(listing.get(k) or "") for k in ("title", "desc")))}
    if words:
        score += min(30, 12 * len(words))
        why.append("عبارات استعجال في الإعلان: " + "، ".join(sorted(words))[:60])
    if dev is not None and dev <= -0.08:
        score += 10
        why.append("السعر أقل من السوق")
    if listing.get("seller_type") == "owner":
        score += 5
        why.append("بائع فرد وليس معرضًا")
    score = min(100, score)
    level = "high" if score >= 55 else "medium" if score >= 30 else "low"
    return score, level, why


def price_drop(old, new):
    """(amount, pct) when the price went down, else None."""
    if old and new and new < old:
        return old - new, (old - new) / old
    return None
