"""PDF report and notification texts."""

import html
import base64
import os
import re
import shutil
import subprocess

from analytics import RATING_AR, URGENCY_AR
from common import DATE_KIND_AR, PLATFORMS, SELLER_AR

AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
TITLE_NOISE = re.compile(
    r"AED\s*[\d,]+\s*/\s*month|\b0\s*down\s*payment\b|down\s*payment\s*deal|free\s+\d+\s+\w+\s+warranty|"
    r"\d+\s*day\s*return|ref\s*#\s*\d+|listing\s*#\s*\d+|for\s+sale:?.*$|^buy\s+|\s+in\s+uae\b.*$|"
    r"own\s+through.*$|\bmodel\s+available.*$|no\s+convenience\s+fees?|\bdown\s*payment\b|under\s+warranty|"
    r"certified\s+pre[\s-]*owned|\b\d+\s*%|\blow\s+fuel\b|\burgent\s+sale\b|\bavailable\b|\bcash\b|\bfinance\b|\(\s*\)", re.I)


def fmt_price(p):
    return f"{p:,} درهم" if p else "السعر غير مذكور"


def fmt_date(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "—"


def date_label(l):
    kind = l.get("date_kind") or ("posted" if l.get("posted") else "first_seen")
    return f"{DATE_KIND_AR[kind]} {fmt_date(l.get('date') or l.get('posted') or (l.get('first_seen') or '')[:10])}"


def criteria_text(r):
    bits = [" ".join(x for x in (r.get("make"), r.get("model"), r.get("keywords")) if x)]
    if r.get("year_from") or r.get("year_to"):
        bits.append(f"موديل {r.get('year_from') or 'أي'}–{r.get('year_to') or 'أي'}")
    if r.get("price_max"):
        bits.append(f"حتى {int(r['price_max']):,} درهم")
    if r.get("mileage_max"):
        bits.append(f"ممشى حتى {int(r['mileage_max']):,} كم")
    bits.append(r.get("color") or "أي لون")
    bits.append(r.get("emirate") or "كل الإمارات")
    return " · ".join(b for b in bits if b)


def car_name(l, req):
    make = (req.get("make") or "").strip().title()
    model = (req.get("model") or "").strip().title()
    name = " ".join(x for x in (make, model, str(l.get("year") or "")) if x)
    return name or (l.get("title") or "إعلان")[:60]


def ad_variant(l, req):
    t = l.get("title") or ""
    parts = [p.strip() for p in t.split("|") if p.strip()]
    t = " ".join(p for p in parts if not TITLE_NOISE.fullmatch(p)) if parts else t
    t = TITLE_NOISE.sub(" ", t)
    for w in (req.get("make"), req.get("model"), str(l.get("year") or "")):
        if w:
            t = re.sub(re.escape(w), " ", t, flags=re.I)
    t = re.sub(r"\(\s*\)", " ", t)
    t = re.sub(r"[\s\-–—|:,/]+", " ", t).strip(" -|()")
    if len(t) > 48:
        t = t[:48].rsplit(" ", 1)[0] + "…"
    return t


def place(l):
    emirate = l.get("emirate") or ""
    area = (l.get("location") or "").split(",")[0].strip()
    if area and emirate and area.lower() != emirate.lower():
        return emirate, area
    return emirate or area or "—", ""


def seller(l):
    name = (l.get("seller_name") or "").strip()
    if len(name) > 26:
        name = name[:26].rsplit(" ", 1)[0] + "…"
    return SELLER_AR.get(l.get("seller_type") or "", "—"), name


def rating_text(l):
    r = l.get("rating") or "unknown"
    if r == "unknown" or l.get("dev") is None:
        return RATING_AR["unknown"]
    return f"{RATING_AR[r]} ({l['dev']:+.0%})"


def best_of(rows):
    picks = []
    rated = [l for l in rows if l.get("dev") is not None and l.get("rating") != "suspicious"]
    if rated:
        picks.append(("أفضل صفقة مقابل السوق", min(rated, key=lambda l: l["dev"])))
    priced = [l for l in rows if l.get("price")]
    if priced:
        picks.append(("الأقل سعرًا", min(priced, key=lambda l: l["price"])))
    driven = [l for l in rows if l.get("mileage")]
    if driven:
        picks.append(("الأقل ممشى", min(driven, key=lambda l: (l["mileage"], l.get("price") or 10**9))))
    seen, out = set(), []
    for label, l in picks:
        if l["id"] not in seen:
            seen.add(l["id"])
            out.append((label, l))
    return out[:3]


def deal_score(l):
    """Sort key for 'best first': under-market first, then price."""
    return (l.get("dev") if l.get("dev") is not None else 0.5, l.get("price") or 10**9)


# ---------------------------------------------------------------- texts

def summary_text(run, groups, drops, now, start, link, short=False):
    """Plain text for Telegram / email / WhatsApp. short=True: the morning brief (top 3)."""
    lines = ["🚗 رادار سيارات الإمارات" + (" — ملخص الصباح" if short else ""),
             f"{AR_DAYS[now.weekday()]} {now:%d/%m/%Y} · {now:%H:%M} بتوقيت الإمارات",
             f"مطابقة: {run['current_offers']} · تحتاج تأكيدًا: {run['candidates']} · جديد: {run['new']} · "
             f"تخفيضات: {len(drops)}", ""]
    if run.get("warning"):
        lines += ["⚠️ " + run["warning"], ""]
    if drops:
        lines.append("📉 تخفيضات أسعار")
        for d in drops[:8]:
            lines.append(f"• {d['name']}: {d['from']:,} ← {d['to']:,} درهم (−{d['pct']:.0%})")
            lines.append(f"  {d['url']}")
        lines.append("")
    for req, ver, cand in groups:
        lines += ["━━━━━━━━━━━━━━━━", f"▌ {req.get('name') or 'طلب'}", f"   {criteria_text(req)}"]
        rows = sorted(ver, key=deal_score)[:3] if short else ver
        if not rows:
            lines += ["   لا عروض مطابقة الآن.", ""]
            continue
        if short:
            lines.append("   أفضل 3 عروض اليوم:")
        for i, l in enumerate(rows, 1):
            em, area = place(l)
            kind, name = seller(l)
            lines.append(f"{i}) {car_name(l, req)}{' 🆕' if l.get('_new') else ''} — {fmt_price(l.get('price'))}")
            lines.append(f"   ⚖️ {rating_text(l)}"
                         + (f" · 🔥 استعجال {URGENCY_AR[l['urgency']['level']]}" if (l.get("urgency") or {}).get("level") in ("high", "medium") else ""))
            lines.append(f"   🛣 {(format(l['mileage'], ',') + ' كم') if l.get('mileage') else 'الممشى غير مذكور'} · 📍 {em}"
                         f"{' – ' + area if area else ''} · {PLATFORMS[l['platform']]['name']} · {date_label(l)}")
            if not short:
                lines.append(f"   VIN: {l.get('vin') if l.get('identity_version') == 1 and l.get('vin') else 'غير متوفر كاملًا'}")
                lines.append(f"   👤 {kind}{' – ' + name if name else ''} · 📞 {(l.get('phone') if l.get('identity_version') == 1 else None) or 'غير منشور بوضوح'}")
            lines.append(f"   🔗 {l['url']}")
        if not short and cand:
            lines.append(f"   + {len(cand)} عروض تحتاج تأكيدًا (في التقرير واللوحة)")
        lines.append("")
    lines.append(f"اللوحة: {link}")
    return "\n".join(lines).strip() + "\n"


def drop_alert_text(drops, link):
    lines = ["📉 تخفيض سعر على سيارة تتابعها"]
    for d in drops:
        lines += [f"{d['name']}", f"{d['from']:,} ← {d['to']:,} درهم (−{d['pct']:.0%}, وفّرت {d['from'] - d['to']:,})",
                  f"{d['url']}", ""]
    lines.append(f"اللوحة: {link}")
    return "\n".join(lines)


# ---------------------------------------------------------------- PDF

def render_html(run, groups, drops, now, start, profile, platforms_used):
    e = html.escape
    mark_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo-mark.svg")
    logo = ""
    if os.path.exists(mark_path):
        with open(mark_path, "rb") as f:
            logo = "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()

    def row(i, l, req, cand=False):
        tags = ""
        if l.get("_new"):
            tags += "<span class='tag new'>جديد</span>"
        if l.get("price_prev") and l.get("price") and l["price"] < l["price_prev"]:
            tags += f"<span class='tag down'>انخفض من {l['price_prev']:,}</span>"
        elif l.get("price_prev") and l.get("price") and l["price"] > l["price_prev"]:
            tags += f"<span class='tag up'>ارتفع من {l['price_prev']:,}</span>"
        if l.get("also_on"):
            tags += "<span class='tag'>على أكثر من منصة</span>"
        em, area = place(l)
        kind, name = seller(l)
        variant = ad_variant(l, req)
        rt = l.get("rating") or "unknown"
        rate_cell = (f"<span class='rate r-{rt}'>{RATING_AR[rt]}</span>"
                     + (f"<div class='sub n'>{l['dev']:+.0%} · متوقع {int(l['fair']['expected']):,}</div>" if l.get("dev") is not None else ""))
        u = l.get("urgency") or {}
        urg = f"<span class='u-{u.get('level', 'low')}'>{URGENCY_AR.get(u.get('level'), '—')}</span>" if u else "—"
        miss = f"<div class='miss'>{e(l['note'])}</div>" if cand and l.get("note") else ""
        vin = l.get("vin") if l.get("identity_version") == 1 else None
        phone = l.get("phone") if l.get("identity_version") == 1 else None
        vin_note = "فحص الصيغة وخانة التحقق" if l.get("vin_status") == "checksum" else "صيغة 17 خانة؛ كما نشره المعلن"
        return f"""<article class="dossier">
<div class="dossier-head"><div><span class="serial">{i:02d}</span><b>{e(car_name(l, req))}</b><div class="var">{e(variant)}</div><div class="tags">{tags}</div></div><div class="asking"><b class="n">{l['price']:,}</b><small>درهم</small></div></div>
{miss}<div class="dossier-facts"><div><small>مقابل السوق</small>{rate_cell}</div><div><small>الممشى واللون</small><b class="n">{format(l['mileage'], ',') if l.get('mileage') else '—'}</b> كم · {e(l.get('color') or '—')}</div><div><small>الموقع</small>{e(em)} {e(area)}</div><div><small>البائع</small>{e(kind)} {e(name)}</div><div><small>المنصة والتاريخ</small>{e(PLATFORMS[l['platform']]['name'])} · {e(date_label(l))}</div><div><small>استعجال البائع</small>{urg}</div></div>
<div class="identity-strip"><div><small>رقم الشاصي / VIN</small><b class="n">{e(vin) if vin else 'غير متوفر من مصدر موثوق'}</b><div class="sub">{e(vin_note) if vin else 'لم يُنشر كاملًا، أو تعذّر التحقق من نسبته لهذه السيارة'}</div></div><div><small>هاتف البائع</small><b class="n">{e(phone) if phone else 'غير متوفر بوضوح'}</b><div class="sub">{'رابط اتصال أو بيانات بائع داخل الإعلان' if phone else 'لا تُستخدم أرقام خدمة المنصة أو الأرقام المخفية'}</div></div><a href="{e(l['url'])}">المصدر الأصلي ↗</a></div>
</article>"""

    head = ("<thead><tr><th>#</th><th>السيارة</th><th>السعر</th><th>مقابل السوق</th><th>الممشى</th><th>الموقع</th>"
            "<th>البائع</th><th>المنصة والتاريخ</th><th>استعجال البائع</th><th>الهاتف</th><th>الرابط</th></tr></thead>")

    sections = []
    for req, ver, cand in groups:
        ver = sorted(ver, key=lambda l: l.get("price") or 10**9)
        cand = sorted(cand, key=lambda l: l.get("price") or 10**9)
        prices = [l["price"] for l in ver if l.get("price")]
        stats = ""
        if prices:
            stats = (f"<div class='st'><span>أقل سعر <b class='n'>{min(prices):,}</b></span>"
                     f"<span>متوسط <b class='n'>{round(sum(prices) / len(prices)):,}</b></span>"
                     f"<span>أعلى <b class='n'>{max(prices):,}</b></span></div>")
        mk = (run.get("market") or {}).get(req.get("id")) or {}
        market = (f"<div class='mk'>سوق هذا الطراز: <b class='n'>{mk['n']}</b> إعلانًا مسعّرًا رصدها الرادار خلال 60 يومًا"
                  + (f" · السعر الوسيط <b class='n'>{mk['median']:,}</b> درهم" if mk.get("median") else "") + "</div>") if mk.get("n") else ""
        picks = "".join(
            f"<div class='pick'><div class='pl'>{label}</div><b>{e(car_name(l, req))}</b>"
            f"<div><span class='n'>{l['price']:,}</span> درهم{' · <span class=n>' + format(l['mileage'], ',') + '</span> كم' if l.get('mileage') else ''}</div>"
            f"<div class='sub'>{e(rating_text(l))} · {e(PLATFORMS[l['platform']]['name'])}</div></div>"
            for label, l in best_of(ver) if l.get("price"))
        body = ""
        if ver:
            body += f"<h3>مطابقة لكل الشروط <span class='cnt'>{len(ver)}</span></h3><div class='dossier-list'>" + \
                    "".join(row(i, l, req) for i, l in enumerate(ver, 1)) + "</div>"
        if cand:
            body += (f"<h3 class='h-c'>تحتاج تأكيدًا <span class='cnt'>{len(cand)}</span><span class='hint'>لا تخالف شروطك، لكن بعض بياناتها غير ظاهرة</span></h3>"
                     f"<div class='dossier-list'>" + "".join(row(i, l, req, True) for i, l in enumerate(cand, len(ver) + 1)) + "</div>")
        if not ver and not cand:
            body = "<p class='empty'>لا توجد عروض ضمن الشروط في هذه الجولة.</p>"
        sections.append(f"""<section><div class="sh"><div><h2>{e(req.get('name') or 'طلب')}</h2><div class="cr">{e(criteria_text(req))}</div></div>{stats}</div>
{market}{f'<div class="picks">{picks}</div>' if picks else ''}{body}</section>""")

    drop_html = ""
    if drops:
        drop_html = "<section><div class='sh'><h2>تخفيضات أسعار منذ الجولة السابقة</h2></div><table><thead><tr><th>السيارة</th><th>كان</th><th>أصبح</th><th>التخفيض</th><th>الرابط</th></tr></thead><tbody>" + "".join(
            f"<tr><td><b>{e(d['name'])}</b></td><td class='n'>{d['from']:,}</td><td class='n'><b>{d['to']:,}</b></td><td class='n'>−{d['pct']:.0%}</td><td><a href='{e(d['url'])}'>فتح الإعلان</a></td></tr>"
            for d in drops) + "</tbody></table></section>"
    who = " · ".join(e(x) for x in (profile.get("name"), profile.get("phone"), profile.get("city")) if x)
    plats = "، ".join(PLATFORMS[p]["name"] for p in platforms_used if p in PLATFORMS)
    warn = f"<div class='warn'><b>تنبيه:</b> {e(run['warning'])}</div>" if run.get("warning") else ""
    mode = {"scheduled": "جولة مجدولة", "manual": "بحث يدوي"}.get(run["mode"], run["mode"])
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>تقرير رادار سيارات الإمارات</title>
<style>
@page {{ size: A4 portrait; margin: 12mm 10mm 15mm;
  @bottom-left {{ content: "صفحة " counter(page) " من " counter(pages); font: 7.5pt "Noto Sans Arabic", "DejaVu Sans"; color: #6b7785; }}
  @bottom-right {{ content: "رادار سيارات الإمارات · {now:%d/%m/%Y %H:%M}"; font: 7.5pt "Noto Sans Arabic", "DejaVu Sans"; color: #6b7785; }} }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Noto Sans Arabic", "Noto Sans", "DejaVu Sans", sans-serif; color: #17212b; font-size: 9pt; margin: 0; line-height: 1.45; }}
.n {{ direction: ltr; unicode-bidi: isolate; font-variant-numeric: tabular-nums; }}
header {{ background: #0B1732; color: #fff; border-radius: 6px; padding: 12px 16px; display: flex; justify-content: space-between; gap: 16px; }}
header h1 {{ margin: 0 0 3px; font-size: 16pt; }} header .m {{ font-size: 8.4pt; opacity: .92; }}
header .who {{ text-align: left; font-size: 8.4pt; opacity: .92; align-self: flex-end; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 9px 0 2px; }}
.kpi {{ border: 1px solid #d3dbe2; border-radius: 6px; padding: 6px 10px; }}
.kpi b {{ display: block; font-size: 14pt; color: #0B1732; line-height: 1.2; }} .kpi span {{ color: #5b6876; font-size: 8pt; }}
.warn {{ background: #fbe9e6; color: #8f2216; border: 1px solid #f1c6bf; padding: 6px 10px; border-radius: 6px; margin-top: 8px; }}
section {{ margin-top: 12px; }}
.sh {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #0B1732; padding-bottom: 4px; break-after: avoid; }}
h2 {{ margin: 0; font-size: 12.5pt; }} .cr {{ color: #5b6876; font-size: 8pt; margin-top: 1px; }}
.st {{ display: flex; gap: 14px; color: #5b6876; font-size: 8pt; }} .st b {{ color: #17212b; font-size: 9.5pt; }}
.mk {{ color: #45525f; font-size: 7.8pt; margin-top: 4px; }}
.picks {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 7px 0 4px; break-inside: avoid; }}
.pick {{ background: #f1f6f7; border-radius: 6px; padding: 6px 10px; }} .pick .pl {{ color: #0B1732; font-size: 7.5pt; font-weight: bold; }}
h3 {{ font-size: 9.5pt; margin: 10px 0 4px; color: #0B1732; break-after: avoid; }} h3.h-c {{ color: #7c5100; }}
.cnt {{ background: #E6EEF8; color: #0B1732; border-radius: 8px; padding: 0 7px; font-size: 8pt; margin-inline-start: 4px; }}
.h-c .cnt {{ background: #fbefd2; color: #7c5100; }} .hint {{ color: #6b7785; font-weight: normal; font-size: 7.5pt; margin-inline-start: 8px; }}
table {{ width: 100%; border-collapse: collapse; }} thead {{ display: table-header-group; }} tr {{ break-inside: avoid; }}
th {{ background: #edf2f5; color: #45525f; font-size: 7.4pt; padding: 5px 4px; text-align: right; white-space: nowrap; }}
td {{ padding: 5px 4px; border-bottom: 1px solid #e3e8ec; vertical-align: top; }}
tbody tr:nth-child(even) td {{ background: #fafbfc; }}
td.i {{ color: #8793a0; width: 16px; }} td.car {{ width: 21%; }} td.car b {{ font-size: 8.8pt; }} .var {{ color: #5b6876; font-size: 7.4pt; }}
.tags {{ margin-top: 1px; }} .tag {{ display: inline-block; font-size: 6.8pt; padding: 0 6px; border-radius: 8px; margin-left: 3px; background: #edf2f5; color: #45525f; }}
.tag.new {{ background: #dcf1e3; color: #17663a; }} .tag.down {{ background: #dcf1e3; color: #17663a; }} .tag.up {{ background: #fbe9e6; color: #8f2216; }}
.rate {{ font-size: 7.4pt; padding: 1px 6px; border-radius: 8px; background: #edf2f5; color: #45525f; }}
.r-excellent {{ background: #cfeedb; color: #086D63; font-weight: bold; }} .r-good {{ background: #dcf1e3; color: #17663a; }}
.r-fair {{ background: #E6EEF8; color: #0B1732; }} .r-high {{ background: #fbe9e6; color: #8f2216; }} .r-suspicious {{ background: #fbefd2; color: #7c5100; }}
.u-high {{ color: #8f2216; font-weight: bold; }} .u-medium {{ color: #7c5100; }} .u-low {{ color: #6b7785; }}
.miss {{ color: #7c5100; font-size: 7.2pt; margin-top: 1px; }}
td.pr {{ white-space: nowrap; }} td.pr b {{ font-size: 9.8pt; }} small {{ color: #6b7785; font-size: 7pt; margin-right: 3px; }}
td.c {{ white-space: nowrap; }} .sub {{ color: #6b7785; font-size: 7pt; white-space: normal; max-width: 32mm; }}
.na {{ color: #8793a0; }} a {{ color: #0B1732; font-weight: bold; text-decoration: none; }}
.empty {{ color: #5b6876; padding: 8px 2px; margin: 0; }}
.foot {{ margin-top: 12px; color: #6b7785; font-size: 7pt; line-height: 1.6; border-top: 1px solid #e3e8ec; padding-top: 5px; }}
.dossier {{ border:1px solid #dce4ef; border-radius:9px; margin:9px 0; padding:12px; break-inside:avoid; }}
.dossier-head {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid #edf1f6; padding-bottom:8px; }}
.dossier-head b {{ font-size:12pt; color:#0B1732; }} .serial {{ display:inline-block; background:#0B1732; color:#36D5C1; border-radius:5px; padding:2px 6px; margin-left:7px; font:9pt sans-serif; }}
.asking {{ white-space:nowrap; text-align:left; }} .asking b {{ font-size:17pt; }} .asking small {{ display:block; }}
.dossier-facts {{ display:grid; grid-template-columns:repeat(3,1fr); gap:9px 12px; padding:10px 0; font-size:8pt; }}
.dossier-facts small, .identity-strip small {{ display:block; margin:0 0 3px; color:#63718a; font-size:7pt; }}
.identity-strip {{ background:#f1f5fa; border-right:3px solid #36D5C1; border-radius:5px; padding:8px 10px; display:grid; grid-template-columns:1.3fr 1fr auto; gap:10px; align-items:center; font-size:8pt; }}
.identity-strip .sub {{ max-width:none; font-size:6.7pt; margin-top:3px; }} .identity-strip b {{ font-size:8.5pt; }}
</style></head><body>
<header><div><h1>{f'<img src="{logo}" alt="" style="width:35px;height:35px;vertical-align:middle;margin-left:9px">' if logo else ""}تقرير رادار سيارات الإمارات</h1>
<div class="m">{AR_DAYS[now.weekday()]} {now:%d/%m/%Y} · {now:%H:%M} بتوقيت الإمارات · {mode} · الفترة <span class="n">{start:%d/%m/%Y}</span> – <span class="n">{now:%d/%m/%Y}</span></div>
<div class="m">المنصات: {e(plats) or '—'}</div></div>
{f'<div class="who">{who}</div>' if who else ''}</header>
<div class="kpis">
<div class="kpi"><b class="n">{run['current_offers']}</b><span>مطابقة لكل الشروط</span></div>
<div class="kpi"><b class="n">{run['candidates']}</b><span>تحتاج تأكيدًا</span></div>
<div class="kpi"><b class="n">{run['new']}</b><span>جديدة في هذه الجولة</span></div>
<div class="kpi"><b class="n">{len(drops)}</b><span>تخفيضات أسعار</span></div></div>
{warn}{drop_html}{''.join(sections)}
<div class="foot">الشاصي والهاتف يُعرضان فقط عند نشرهما بوضوح ونسبتهما للإعلان نفسه؛ فحص الصيغة لا يثبت ملكية السيارة أو تاريخ حوادثها. اطلب صورة الشاصي وطابقها بالملكية قبل الشراء. البيانات من صفحة الإعلان، والإعلان يُحفظ مرة واحدة ويُحدَّث سعره إن تغيّر. «مقابل السوق» يقارن السعر بالسعر المتوقع لنفس الطراز والسنة والممشى، محسوبًا من الإعلانات التي رصدها الرادار خلال 60 يومًا. «استعجال البائع» يجمع مدة عرض الإعلان وعدد مرات تخفيض سعره وعبارات مثل «مستعجل» و«مسافر». بجانب كل تاريخ مصدره: «نُشر» تاريخ النشر في المنصة، و«رصده الرادار» يعني أن المنصة لا تعرض تاريخًا.</div>
</body></html>"""


def chrome_path():
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
              "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"):
        p = shutil.which(c) or (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def to_pdf(html_text, html_path, pdf_path):
    with open(html_path, "w") as f:
        f.write(html_text)
    chrome = chrome_path()
    if not chrome:
        return False
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", f"file://{os.path.abspath(html_path)}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000
