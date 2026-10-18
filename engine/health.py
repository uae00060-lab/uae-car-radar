"""Parser health, scoped to unchanged searches; never changes vehicle availability."""
import hashlib
import json

FIELDS = ('id', 'make', 'model', 'keywords', 'year_from', 'year_to', 'price_max', 'mileage_max', 'color', 'emirate')


def scope_of(requests, platform):
    rows = [{k: r.get(k) for k in FIELDS} for r in requests if platform in (r.get('platforms') or [platform])]
    rows.sort(key=lambda r: str(r.get('id', '')))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=True).encode()).hexdigest()[:20]


def update(engine, requests, diagnostics, opened, stamp, names):
    """Only attempted platforms count. No baseline means zero is inconclusive.

    Match counts never drive parser alerts: valid ads may simply fail the user's filters.
    A detail-parser streak advances only when detail pages were successfully read.
    """
    state = engine.setdefault('platform_health', {})
    warnings = []
    for platform, d in diagnostics.items():
        if not d.get('pages'):
            continue
        record = state.setdefault(platform, {'scopes': {}})
        scope = scope_of(requests, platform)
        scopes = record.setdefault('scopes', {})
        previous = scopes.get(scope, {})
        o = opened.get(platform, {})
        cards, pages = d.get('cards', 0), d.get('ok', 0)
        read, priced = o.get('read_ok', 0), o.get('priced', 0)
        zero = previous.get('zero_streak', 0) + 1 if not cards else 0
        detail_zero = previous.get('detail_zero_streak', 0)
        if read:
            detail_zero = 0 if priced else detail_zero + 1
        had_cards = bool(previous.get('had_cards') or cards)
        had_price = bool(previous.get('had_price') or priced)
        discovery_alert = had_cards and zero >= 2
        detail_alert = had_price and detail_zero >= 2
        alert = discovery_alert or detail_alert
        was_alert = previous.get('alert', False)
        if discovery_alert:
            reason = 'لم يُستخرج أي رابط إعلان في جولتين متتاليتين بالشروط نفسها؛ قد يكون الوصول محجوبًا أو تغيّر تصميم الموقع.'
        elif detail_alert:
            reason = 'فُتحت صفحات إعلانات دون استخراج سعر مؤكد في جولتين متتاليتين؛ يحتاج قارئ الأسعار إلى فحص.'
        elif not pages:
            reason = 'تعذّر الوصول المباشر؛ ' + ('عُثر على روابط من البحث البديل.' if cards else 'لا يمكن تأكيد خلو المنصة من الإعلانات.')
        elif not cards:
            reason = 'لم تُستخرج روابط؛ لا يكفي ذلك لإثبات تعطل المنصة أو عدم وجود عروض.'
        elif o.get('read_failed'):
            reason = 'عُثر على إعلانات وتعذّر فتح بعض صفحات التفاصيل.'
        else:
            reason = 'استخراج الروابط يعمل؛ النتائج المطابقة تعتمد على شروط البحث.'
        recovered = bool(was_alert and not alert and cards and (not previous.get('detail_alert') or priced))
        status = 'alert' if alert else 'recovered' if recovered else 'limited' if not pages or o.get('read_failed') else 'empty' if not cards else 'ok'
        row = dict(at=stamp, scope=scope, request_names=[r.get('name') or r.get('id') for r in requests if platform in (r.get('platforms') or [platform])],
                   status=status, reason=reason, alert=bool(alert), detail_alert=bool(detail_alert), recovered=recovered,
                   had_cards=had_cards, had_price=had_price, zero_streak=zero, detail_zero_streak=detail_zero,
                   pages=d.get('pages', 0), reachable=pages, blocked=d.get('blocked', 0), cards=cards,
                   opened=o.get('opened', 0), read_ok=read, priced=priced, failed=o.get('read_failed', 0))
        scopes[scope] = row
        record['scopes'] = dict(sorted(scopes.items(), key=lambda pair: pair[1]['at'], reverse=True)[:12])
        record['latest'] = row
        if alert:
            warnings.append(f"{names.get(platform, platform)}: {reason}")
    return warnings
