import os
import sys
import unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from lifecycle import observe
from common import ad_identity,has_terms,model_terms,validate_request,MOURJAN_BRANDS
from radar import search_urls
from extract import mourjan_model_url,ad_page

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.eng={};self.car={'id':'a','url':'https://www.dubicars.com/2020-toyota-yaris-100000.html','platform':'dubicars','state':'verified','price':25000,'color':'أبيض','title':'Toyota Yaris','mileage':100000}
    def test_network_error_never_means_sold(self):
        self.assertEqual(observe(self.eng,self.car,'failed',{},'2026-10-19T08:00:00+04:00'),[])
        self.assertEqual(self.car['state'],'verified');self.assertEqual(self.car['check_status'],'unreachable')
        self.assertNotIn('alerts',self.eng)
    def test_removed_is_not_claimed_sold_and_not_repeated(self):
        self.assertEqual(len(observe(self.eng,self.car,'gone',{},'a')),1)
        self.assertEqual(self.car['availability'],'unavailable')
        self.assertEqual(observe(self.eng,self.car,'gone',{},'b'),[])
        self.assertEqual(len(self.eng['alerts']),1)
        self.assertEqual(len(observe(self.eng,self.car,'ok',{'price':25000,'color':'white'},'c')),1)
        self.assertEqual(self.car['state'],'verified')
        self.assertEqual(self.car['availability'],'available')
    def test_price_and_reservation_events(self):
        events=observe(self.eng,self.car,'ok',{'price':24000,'color':'white','availability':'reserved'},'a')
        self.assertEqual({c['field'] for c in events[0]['changes']},{'price','availability'})
        self.assertEqual(self.car['availability'],'reserved')
    def test_missing_identity_is_not_an_edit(self):
        self.car['phone']='+971552398817'
        self.assertEqual(observe(self.eng,self.car,'ok',{'price':25000,'phone':None,'color':'white'},'a'),[])
    def test_all_makes_and_mourjan_aliases(self):
        self.assertGreaterEqual(len(search_urls('mourjan',{})),69)
        for make,slug in [('Hyundai','hyunday'),('Mercedes-Benz','mercedes'),('Volkswagen','volks-wagen'),('Nissan','nissan'),('BMW','bmw')]:
            self.assertIn('/'+slug+'/',search_urls('mourjan',{'make':make})[0])
            self.assertEqual(ad_identity(f'https://www.mourjan.com/ae/dubai/{slug}/for-sale/30474560/'),('mourjan','30474560'))
        self.assertIsNone(validate_request({}))
        self.assertTrue(has_terms('نيسان صني للبيع',model_terms({'make':'Nissan','model':'Sunny'})))
        self.assertEqual(ad_identity('https://www.mourjan.com/ae/dubai/housemaids/for-sale/30474560/'),(None,None))
    def test_live_model_ids_are_not_toyota_only(self):
        h='<div id=_cm class=options><div data-value=0>غير محدد</div><div data-value=917>SUNNY</div></div>'
        self.assertEqual(mourjan_model_url(h,'https://www.mourjan.com/ae/nissan/for-sale/?mxp=20000','صني'),'https://www.mourjan.com/ae/nissan/for-sale/?mxp=20000&cm=917')
    def test_related_sold_status_cannot_remove_own_car(self):
        h='<script type="application/ld+json">[{"@type":"Car","url":"https://x/own","offers":{"price":25000,"priceCurrency":"AED","availability":"https://schema.org/InStock"}},{"@type":"Car","url":"https://x/other","offers":{"availability":"https://schema.org/SoldOut"}}]</script>'
        f=ad_page(h,'https://x/own','own');self.assertFalse(f['_sold'])
