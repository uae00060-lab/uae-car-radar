import datetime as dt,os,sys,unittest
from unittest.mock import patch
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import opportunities
NOW=dt.datetime(2026,10,19,3,tzinfo=dt.timezone(dt.timedelta(hours=4)))
class Opportunities(unittest.TestCase):
 def setUp(self):
  self.l=dict(id='opensooq-1',request_id='r',request_ids=['r'],by_request={'r':{'state':'verified'}},platform='opensooq',url='https://ae.opensooq.com/en/search/1',title='Toyota Yaris',state='verified',availability='available',price=25000,price_version=3,price_currency='AED',price_source='ad:AED-offer',year=2022,mileage=90000,posted='2026-10-19',date_kind='posted',last_checked=NOW.isoformat(),phone='+971501234567',identity_version=1,price_history=[{'price':25000}])
  self.e={'listings':{'opensooq-1':self.l},'market':{'r':{str(i):{'year':2022,'km':90000,'price':30000,'seen':'2026-10-19'} for i in range(8)}}}
  self.u={'requests':[{'id':'r','make':'Toyota','model':'Yaris','name':'طلب'}]}
 def rows(self):return opportunities.candidates(self.e,self.u,NOW)
 def test_strong_fresh_discount(self):
  row=self.rows()[0];self.assertEqual(row['tier'],'call');self.assertEqual(row['comparables'],8)
 def test_no_phone_or_extreme_discount_needs_verification(self):
  self.l['phone']=None;self.assertEqual(self.rows()[0]['tier'],'verify')
  self.l['phone']='+971501234567';self.l['price']=15000;self.assertEqual(self.rows()[0]['tier'],'verify')
 def test_sold_reserved_changed_old_stale_or_unknown_date_are_excluded(self):
  for values in ({'availability':'sold'},{'availability':'reserved'},{'posted':'2026-10-15'},{'last_checked':(NOW-dt.timedelta(hours=7)).isoformat()},{'date_kind':'first_seen'},{'price_changed_at':NOW.isoformat()},{'price_source':'card:json'},{'check_status':'unreachable'}):
   with self.subTest(values=values):
    original=dict(self.l);self.l.update(values);self.assertEqual(self.rows(),[]);self.l.clear();self.l.update(original)
 def test_modified_ad_not_a_new_opportunity(self):
  self.e['alerts']=[{'listing_id':self.l['id'],'changes':[{'field':'title'}]}];self.assertEqual(self.rows(),[])
 def test_no_mixed_model_or_small_comparison_pool(self):
  self.u['requests'][0]['model']='';self.assertEqual(self.rows(),[])
  self.u['requests'][0]['model']='Yaris';self.e['market']['r'].pop('1');self.assertEqual(self.rows(),[])
 def test_one_alert_and_no_external_manual_delivery(self):
  with patch('notify.send_all',return_value={'email':'أُرسل'}) as send:
   self.assertEqual(len(opportunities.update(self.e,self.u,NOW)),1);send.assert_not_called()
   opportunities.update(self.e,self.u,NOW,notify=True);self.assertEqual(send.call_count,1)
   opportunities.update(self.e,self.u,NOW,notify=True);self.assertEqual(send.call_count,1)
 def test_expired_or_sold_pending_event_never_sent(self):
  opportunities.update(self.e,self.u,NOW);self.l['availability']='sold'
  with patch('notify.send_all') as send:opportunities.update(self.e,self.u,NOW,notify=True);send.assert_not_called()
 def test_pause_and_watch_price(self):
  self.l['price']=28000;self.assertEqual(self.rows()[0]['tier'],'watch')
  self.u['opportunities_enabled']=False;self.assertEqual(self.rows(),[])

 def test_shared_ad_prefers_strongest_supported_request_at_same_price(self):
  self.u['requests'].append(dict(self.u['requests'][0],id='r2'))
  self.l['request_ids'].append('r2');self.l['by_request']['r2']={'state':'verified'}
  self.e['market']['r2']={k:dict(v) for k,v in self.e['market']['r'].items()}
  for sample in self.e['market']['r'].values():sample['price']=27000
  self.assertEqual(self.rows()[0]['tier'],'call')
  self.assertEqual(self.rows()[0]['request_id'],'r2')
