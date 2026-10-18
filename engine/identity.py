"""Conservative ad identity extraction; never infer a VIN or a seller phone."""
import re
from html.parser import HTMLParser
from html import unescape

VIN_LABEL = re.compile(r'(?:\bVIN\b|vehicle identification number|chassis(?: number| no\.?)?|رقم\s*(?:الشاصي|الشاسيه|الشاسي|الهيكل))\s*[:#：-]?\s*([A-Za-z0-9*•_-]{5,30})', re.I)

def vin_status(value):
    value = str(value or '').strip().upper()
    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', value) or len(set(value)) < 4:
        return None, 'missing'
    # ISO 3779 check digit is mandatory for North American WMI prefixes only.
    letters = dict(zip('ABCDEFGHJKLMNPRSTUVWXYZ', (1,2,3,4,5,6,7,8,1,2,3,4,5,7,9,2,3,4,5,6,7,8,9)))
    weights = (8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2)
    n = sum((int(c) if c.isdigit() else letters[c])*w for c,w in zip(value,weights)) % 11
    check = 'X' if n == 10 else str(n)
    if value[0] in '12345' and value[8] != check:
        return None, 'invalid-checksum'
    return value, 'checksum' if value[8] == check else 'format'

def phone_value(value):
    value = unescape(str(value or '')).strip()
    if re.search(r'[*•xX]', value): return None
    digits = re.sub(r'\D', '', value)
    if digits.startswith('00971'): digits = digits[2:]
    if digits.startswith('0'): digits = '971' + digits[1:]
    elif not digits.startswith('971'): return None
    if not re.fullmatch(r'971(?:5[024568]\d{7}|[234679]\d{7})', digits): return None
    if digits[-7:] in ('1234567','0000000','1111111','9999999') or digits.endswith('45061300'): return None
    return '+' + digits

class AdText(HTMLParser):
    """Ignore site navigation, executable content, and recommendations."""
    def __init__(self):
        super().__init__(); self.stack=[]; self.parts=[]; self.links=[]
    def handle_starttag(self, tag, attrs):
        d=dict(attrs); marker=' '.join(str(d.get(k,'')) for k in ('class','id','aria-label'))
        excluded = tag in ('header','footer','nav','script','style','noscript') or bool(re.search(r'recommend|related|similar|support|footer|header|navbar',marker,re.I))
        blocked = excluded or (self.stack[-1][1] if self.stack else False)
        if tag not in ('meta','link','img','br','hr','input','source','wbr','area','embed','param'): self.stack.append((tag,blocked))
        if not blocked:
            if tag in ('p','div','li','section','dt','dd','br'): self.parts.append('\n')
            if tag=='a' and re.match(r'(?:tel:|https?://wa.me/)',d.get('href','')): self.links.append(d['href'])
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag: del self.stack[i:]; break
    def handle_data(self,data):
        if not self.stack or not self.stack[-1][1]: self.parts.append(data+' ')

def extract_identity(html, primary, description=''):
    vins=[]; phones=[]
    for car in primary:
        for key in ('vehicleIdentificationNumber','vin','VIN','chassisNumber'):
            if car.get(key): vins.append((car[key],'ad:schema:'+key))
        offers=car.get('offers'); seller=car.get('seller') or (offers.get('seller') if isinstance(offers,dict) else None)
        if isinstance(seller,dict):
            contact=seller.get('contactPoint')
            for v in (seller.get('telephone'),contact.get('telephone') if isinstance(contact,dict) else None):
                if v: phones.append((v,'ad:seller.telephone'))
    p=AdText();p.feed(html)
    for m in VIN_LABEL.finditer(description or ''): vins.append((m[1],'ad:description:VIN'))
    for m in VIN_LABEL.finditer(''.join(p.parts)): vins.append((m[1],'ad:label:VIN'))
    # Only explicit contact links in the ad body. Multiple different contacts are ambiguous.
    for link in p.links: phones.append((re.sub(r'^(?:tel:|https?://wa.me/)','',link).split('?')[0],'ad:contact-link'))
    valid={}; invalid=False
    for value,source in vins:
        v,status=vin_status(value)
        if v: valid[v]=(source,status)
        else: invalid=True
    phone_map={phone_value(v):s for v,s in phones if phone_value(v)}
    out={'identity_version':1,'vin':None,'vin_source':None,'vin_status':'conflict' if len(valid)>1 else 'unavailable-or-invalid' if invalid else 'missing', 'phone':None,'phone_source':None,'phone_status':'conflict' if len(phone_map)>1 else 'missing'}
    if len(valid)==1:
        out['vin'],(out['vin_source'],out['vin_status'])=next(iter(valid.items()))
    if len(phone_map)==1:
        out['phone'],out['phone_source']=next(iter(phone_map.items()));out['phone_status']='published'
    return out
