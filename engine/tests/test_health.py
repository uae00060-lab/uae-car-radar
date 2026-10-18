import os,sys,unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import health

class Health(unittest.TestCase):
    def setUp(self):
        self.e={}; self.req=[{'id':'r1','name':'طلب','make':'Toyota','price_max':30000,'platforms':['opensooq']}];self.i=0
    def step(self,cards=4,ok=1,read=0,priced=0,requests=None):
        self.i+=1
        return health.update(self.e,requests or self.req,{'opensooq':{'pages':1,'ok':ok,'cards':cards,'blocked':int(not ok)}},{'opensooq':{'opened':read,'read_ok':read,'priced':priced}},str(self.i).zfill(3),{'opensooq':'السوق المفتوح'})
    @property
    def row(self): return self.e['platform_health']['opensooq']['latest']
    def test_zero_without_prior_success_is_not_failure(self):
        for _ in range(3): self.assertEqual(self.step(0),[])
        self.assertFalse(self.row['alert'])
    def test_two_zeros_and_recovery(self):
        self.step();self.assertEqual(self.step(0),[]);self.assertTrue(self.step(0));self.assertEqual(self.row['zero_streak'],2)
        self.assertEqual(self.step(),[]);self.assertEqual(self.row['status'],'recovered');self.step();self.assertEqual(self.row['status'],'ok')
    def test_changed_search_does_not_inherit_streak(self):
        self.step();self.step(0)
        self.assertEqual(self.step(0,requests=[dict(self.req[0],price_max=1000)]),[])
        self.assertEqual(self.step(0,requests=[dict(self.req[0],price_max=1000)]),[])
    def test_skipped_platform_does_not_advance(self):
        self.step();self.step(0)
        health.update(self.e,self.req,{}, {},'003',{})
        self.assertEqual(self.row['zero_streak'],1)
    def test_price_extraction_loss_despite_links(self):
        self.step(read=3,priced=2);self.assertEqual(self.step(read=3),[]);self.assertTrue(self.step(read=3));self.assertTrue(self.row['detail_alert'])
        self.step(read=0);self.assertTrue(self.row['alert'])
        self.step(read=2,priced=1);self.assertEqual(self.row['status'],'recovered')
    def test_network_failure_is_not_price_parser_failure(self):
        self.step(read=3,priced=2)
        self.step(ok=0);self.step(ok=0)
        self.assertFalse(self.row['detail_alert']);self.assertEqual(self.row['status'],'limited')
    def test_reachable_empty_warns_without_claiming_sold(self):
        self.step();self.step(0);self.step(0)
        self.assertNotIn('sold',str(self.e));self.assertEqual(self.row['status'],'alert')

class RealPages(unittest.TestCase):
    def test_opensooq_real_vehicle_price(self):
        from pathlib import Path
        import extract
        h=(Path(__file__).parent/'fixtures/opensooq-vehicle.html').read_text()
        fields=extract.ad_page(h,'https://ae.opensooq.com/en/search/288585074','288585074')
        self.assertEqual(fields['price'][0],24000)
        self.assertEqual(fields['price'][1],'ad:AED-offer')
    def test_mourjan_real_car_links(self):
        from pathlib import Path
        import extract
        h=(Path(__file__).parent/'fixtures/mourjan-results.html').read_text()
        cards=extract.results(h,'https://www.mourjan.com','mourjan')
        self.assertGreaterEqual(len(cards),2)
        self.assertIn('26950405',[c['ad_id'] for c in cards])
