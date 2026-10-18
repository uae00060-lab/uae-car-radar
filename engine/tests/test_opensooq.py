import os,sys,unittest,json
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import extract,radar
class OpenSooq(unittest.TestCase):
    def test_http_schema_is_same_ad_as_https_page(self):
        obj={'@type':'Vehicle','url':'http://ae.opensooq.com/en/search/288585074','name':'تويوتا يارس 2019 سيدان خليجي','offers':{'@type':'Offer','url':'http://ae.opensooq.com/en/search/288585074','price':'24000','priceCurrency':'AED'}}
        h='<script type="application/ld+json">'+json.dumps(obj)+'</script>'
        f=extract.ad_page(h,'https://ae.opensooq.com/en/search/288585074','288585074')
        self.assertEqual(f['price'][0],24000);self.assertEqual(f['price'][1],'ad:AED-offer')
    def test_other_ad_offer_stays_excluded(self):
        h='<script type="application/ld+json">'+json.dumps({'@type':'Vehicle','url':'http://ae.opensooq.com/en/search/288585075','offers':{'price':24000,'priceCurrency':'AED'}})+'</script>'
        self.assertNotIn('price',extract.ad_page(h,'https://ae.opensooq.com/en/search/288585074','288585074'))
    def test_posting_year_is_not_vehicle_year(self):
        h='<script type="application/ld+json">'+json.dumps({'@type':'Vehicle','url':'https://ae.opensooq.com/en/search/288585074','name':'تويوتا يارس 2019 سيدان خليجي','offers':{'price':24000,'priceCurrency':'AED'}})+'</script><a href="/en/search/288585074">13-10-2026 تويوتا يارس 2019 سيدان خليجي AED 24000</a>'
        c=extract.results(h,'https://ae.opensooq.com','opensooq')[0]
        self.assertEqual(c['year'],2019)
        self.assertTrue(radar.card_ok({'make':'Toyota','model':'Yaris','price_max':31000,'year_from':2019,'year_to':2023},c))
