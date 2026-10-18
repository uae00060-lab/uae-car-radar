import json
import os
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import extract
from identity import extract_identity, vin_status, phone_value
from common import ad_identity
import radar

VIN='1HGCM82633A004352'
class Identity(unittest.TestCase):
    def test_valid_and_invalid_vin(self):
        self.assertEqual(vin_status(VIN),(VIN,'checksum'))
        for v in ('1HGCM82633A004353','VIN123','JTD********123456','IIIIIIIIIIIIIIIII','00000000000000000'):
            self.assertIsNone(vin_status(v)[0])
    def test_related_schema_and_footer_are_not_seller_evidence(self):
        h='<footer><a href="tel:0552398817">Support</a> VIN: '+VIN+'</footer><div class="related">VIN: '+VIN+'</div>'
        h+='<script type="application/ld+json">'+json.dumps([{'@type':'Car','url':'https://x/own','offers':{'price':25000,'priceCurrency':'AED'}},{'@type':'Car','url':'https://x/other','vehicleIdentificationNumber':VIN,'seller':{'telephone':'0552398817'}}])+'</script>'
        f=extract.ad_page(h,'https://x/own','own')
        self.assertIsNone(f['vin'][0]); self.assertIsNone(f['phone'][0])
    def test_own_schema_identity(self):
        car={'@type':'Car','url':'https://x/own','vehicleIdentificationNumber':VIN,'seller':{'telephone':'0552398817'}}
        f=extract.ad_page('<script type="application/ld+json">'+json.dumps(car)+'</script>','https://x/own','own')
        self.assertEqual(f['vin'][0],VIN);self.assertEqual(f['phone'][0],'+971552398817')
    def test_labels_and_ambiguous_contacts(self):
        f=extract_identity('<main><p>رقم الشاصي: '+VIN+'</p><a href="tel:0552398817">call seller</a></main>',[])
        self.assertEqual(f['vin'],VIN);self.assertEqual(f['phone'],'+971552398817')
        f=extract_identity('<main><a href="tel:0552398817">call</a><a href="tel:0522398817">call</a></main>',[])
        self.assertIsNone(f['phone']);self.assertEqual(f['phone_status'],'conflict')
    def test_phone_validation(self):
        for p in ('0551234567','+9714 5061300','055***8817','123456789123456'):self.assertIsNone(phone_value(p))
        self.assertEqual(phone_value('00971552398817'),'+971552398817')
    def test_mourjan_unquoted_and_non_car_exclusion(self):
        url='https://www.mourjan.com/ae/ajman/toyota/for-sale/30474560/'
        h='<a href=/ae/ajman/toyota/for-sale/30474560/><div>Toyota Camry 2009 AED 9000</div></a><a href=/ae/dubai/housemaids/seeking-work/30024891/>other</a>'
        cards=extract.results(h,'https://www.mourjan.com','mourjan')
        self.assertEqual(len(cards),1);self.assertEqual(cards[0]['url'],url)
        self.assertIn('Camry', cards[0]['title'])
        self.assertEqual(radar.search_urls('mourjan',{'make':'تويوتا'}),['https://www.mourjan.com/ae/toyota/for-sale/'])
