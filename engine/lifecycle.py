"""Source-backed changes. A network error is never evidence that a car was sold."""
import hashlib
import json

FIELDS = {'price':'السعر', 'title':'عنوان الإعلان', 'year':'الموديل', 'mileage':'الممشى', 'color':'اللون', 'location':'الموقع', 'phone':'هاتف البائع', 'vin':'رقم الشاصي'}
LABELS = {'available':'متاح', 'sold':'مباع حسب المنصة', 'unavailable':'الإعلان غير متاح', 'reserved':'محجوز حسب المنصة'}

def observe(eng, listing, status, values, at):
    if status == 'failed':
        listing['check_status']='unreachable'; listing['last_check_attempt']=at
        return []
    listing['check_status']='checked'; listing['last_check_attempt']=at
    old_avail=listing.get('availability') or ('unavailable' if listing.get('state')=='sold' else 'available')
    new_avail='sold' if status=='sold' else 'unavailable' if status=='gone' else values.get('availability') or 'available'
    changes=[]
    if old_avail != new_avail:
        changes.append({'field':'availability','label':'حالة الإعلان','old':old_avail,'new':new_avail})
    if status == 'ok':
        for field,label in FIELDS.items():
            new=values.get('km' if field=='mileage' else field)
            old=listing.get(field)
            if field=='color':
                from common import color_of, COLOR_AR
                old=COLOR_AR.get(color_of(str(old or '')),old); new=COLOR_AR.get(color_of(str(new or '')),new)
            # Absence on a newly rendered page is not proof the seller edited a field.
            if old not in (None,'') and new not in (None,'') and str(old).strip()!=str(new).strip():
                changes.append({'field':field,'label':label,'old':old,'new':new})
    listing['availability']=new_avail
    if new_avail in ('sold','unavailable'):
        if listing.get('state')!='sold': listing['last_active_state']=listing.get('state','unverified')
        listing.update(state='sold',note=LABELS[new_avail],last_checked=at)
    elif listing.get('state')=='sold':
        listing['state']=listing.get('last_active_state','unverified')
    if not changes: return []
    payload={'listing_id':listing['id'],'at':at,'title':listing.get('title') or 'سيارة محفوظة','url':listing['url'],'platform':listing['platform'],'changes':changes}
    payload['id']=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
    eng.setdefault('alerts',[]).insert(0,payload)
    eng['alerts']=eng['alerts'][:300]
    listing['last_changed_at']=at
    return [payload]

def message(events, site):
    lines=['تحديثات السيارات المحفوظة']
    for event in events[:30]:
        lines.append(event['title'])
        for c in event['changes']:
            old,new=c['old'],c['new']
            if c['field']=='availability': old,new=LABELS.get(old,old),LABELS.get(new,new)
            old=format(old,',') if isinstance(old,(int,float)) else old
            new=format(new,',') if isinstance(new,(int,float)) else new
            lines.append(f"• {c['label']}: {old} ← {new}")
        lines.append(event['url'])
    if len(events)>30: lines.append(f'وبقية التحديثات ({len(events)-30}) في اللوحة')
    lines.append(site)
    return '\n'.join(lines)
