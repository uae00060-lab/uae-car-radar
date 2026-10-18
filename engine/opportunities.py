"""Evidence-based fresh purchase shortlist. No AI calls; never infer a seller's profession."""
import datetime as dt
import analytics
from identity import vin_status


def candidates(engine, user, now):
    picks = {}
    if user.get('opportunities_enabled') is False:
        return []
    modified = {e.get('listing_id') for e in engine.get('alerts', []) if any(c.get('field') != 'availability' for c in e.get('changes', []))}
    for listing in engine.get('listings', {}).values():
        l = listing
        mark = user.get('marks', {}).get(l['id'], {})
        if (l.get('availability', 'available') != 'available' or l.get('state') in ('sold','excluded') or l.get('dup_of')
                or mark.get('status') in ('dismissed','purchased') or l['id'] in modified
                or l.get('check_status') == 'unreachable' or l.get('price_changed_at') or len(l.get('price_history', [])) > 1):
            continue
        price = l.get('price')
        if not price or l.get('price_version') != 3 or l.get('price_currency') != 'AED' or not str(l.get('price_source') or '').startswith('ad:'):
            continue
        try:
            posted = dt.date.fromisoformat(l['posted'])
            age = (now.date()-posted).days
            checked = (now-dt.datetime.fromisoformat(l['last_checked'])).total_seconds()
            if l.get('date_kind') != 'posted' or not 0 <= age <= 2 or not 0 <= checked <= 21600:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        for req in user.get('requests', []):
            if req.get('active') is False or not req.get('make') or not req.get('model') or req['id'] not in l.get('request_ids', [l.get('request_id')]):
                continue
            state = (l.get('by_request', {}).get(req['id']) or {}).get('state', l.get('state'))
            if state != 'verified':
                continue
            fp = analytics.fair_price(engine.get('market', {}).get(req['id'], {}), l.get('year'), l.get('mileage'), exclude_id=l['id'])
            if not fp or fp['n'] < 8:
                continue
            discount = 1-price/fp['expected']
            if discount < .04:
                continue
            missing = []
            if not l.get('phone') or l.get('identity_version') != 1: missing.append('هاتف البائع غير منشور؛ التواصل من الإعلان')
            if not l.get('mileage'): missing.append('الممشى يحتاج تأكيدًا')
            if not l.get('vin') or l.get('identity_version') != 1: missing.append('الشاصي غير منشور؛ اطلب مطابقته بالملكية')
            strong = discount >= .10 and price <= fp['low'] and discount < .35
            tier = 'verify' if discount >= .35 or (strong and (not l.get('phone') or l.get('identity_version') != 1 or not l.get('mileage'))) else 'call' if strong else 'watch'
            if discount >= .35: missing.insert(0,'انخفاض غير معتاد؛ تحقّق من السعر وحالة السيارة قبل أي دفع')
            vin, _ = vin_status(l.get('vin')) if l.get('identity_version') == 1 else (None,None)
            key = 'vin:'+vin if vin else l['id']
            item = dict(key=key,listing_id=l['id'],request_id=req['id'],request_name=req.get('name'),tier=tier,price=price,
                        expected=fp['expected'],comparables=fp['n'],discount=round(discount,4),posted=l['posted'],checked_at=l['last_checked'],
                        reasons=[f'أقل من تقدير الإعلانات المشابهة بنحو {round(discount*100)}٪',f'المقارنة من {fp["n"]} إعلانًا، وليست تقييم فحص للسيارة','نشر حديث: '+l['posted']],missing=missing)
            previous=picks.get(key)
            if previous is None or price < previous['price']: picks[key]=item
    return sorted(picks.values(),key=lambda x:({'call':0,'verify':1,'watch':2}[x['tier']],-dt.date.fromisoformat(x['posted']).toordinal(),-x['discount']))[:12]


def update(engine,user,now,notify=False):
    rows=candidates(engine,user,now)
    box=engine.setdefault('opportunities',{})
    events=box.setdefault('events',[])
    known={e['key'] for e in events}
    fresh=[]
    for row in rows:
        if row['tier']=='call' and row['key'] not in known:
            event=dict(row,at=now.isoformat(timespec='seconds'),id='op:'+row['key'])
            events.insert(0,event);known.add(row['key']);fresh.append(event)
    box.update(items=rows,updated=now.isoformat(timespec='seconds'),events=events[:300])
    # Never send expired or subsequently disqualified events, even if delivery failed before.
    active={r['key'] for r in rows if r['tier']=='call'}
    pending=[e for e in events if e['key'] in active and not e.get('notified')]
    if notify and pending:
        import notify as channels
        from common import PLATFORMS
        lines=['فرص شراء حديثة تستحق التواصل — بيانات الإعلان تحتاج فحصًا قبل الشراء']
        for e in pending[:5]:
            l=engine['listings'][e['listing_id']]
            lines.append(f"{l.get('title','سيارة')} — {e['price']:,} درهم · أقل بنحو {round(e['discount']*100)}٪ · {PLATFORMS.get(l['platform'],{}).get('name',l['platform'])}\n{l['url']}")
        text='\n\n'.join(lines)
        result=channels.send_all('فرص سيارات حديثة',text,text)
        box['delivery']=result
        if any(v==channels.SENT for v in result.values()):
            for e in pending[:5]: e['notified']=now.isoformat(timespec='seconds')
    return fresh
