"""Offline tests: fake platform pages through the whole round. Run: python -m unittest discover engine/tests"""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import analytics  # noqa: E402
import extract  # noqa: E402
import fetch  # noqa: E402
import radar  # noqa: E402
import store  # noqa: E402
from common import now_uae  # noqa: E402

KEY = "test-pass-123"
TODAY = now_uae().date()


def d(days):
    return (TODAY - dt.timedelta(days=days)).isoformat()


def ld_ad(name, price, year, km, posted, color="White", seller="Person", phone=None):
    obj = {"@context": "https://schema.org", "@type": "Car", "name": name, "vehicleModelDate": str(year),
           "mileageFromOdometer": {"@type": "QuantitativeValue", "value": km, "unitCode": "KMT"}, "color": color,
           "datePosted": posted, "offers": {"@type": "Offer", "price": price, "priceCurrency": "AED",
                                            "seller": {"@type": seller, "name": "Ali"}}}
    tel = f'<a href="tel:{phone}">call</a>' if phone else ""
    return f'<html><head><title>{name}</title><script type="application/ld+json">{json.dumps(obj)}</script></head><body><p>Dubai, UAE</p>{tel}</body></html>'


DZ1 = "/motors/used-cars/toyota/yaris/2026/10/8/toyota-yaris-2022-gcc---0e178fe896f34a32b34968b5266f36dd/"
DZ2 = "/motors/used-cars/toyota/yaris/2026/10/3/toyota-yaris-2020-se---8507a50ad04143bebd4191dbc57586e8/"
DZ_OLD = "/motors/used-cars/toyota/yaris/2026/7/3/toyota-yaris-2021---1111111111111111111111111111aaaa/"
YM = "/used-cars/toyota/yaris/2021/used-toyota-yaris-2021-dubai-2141327"
DC = "/2021-toyota-yaris-982579.html"

PAGES = {
    # dubizzle results: links with card text
    "https://uae.dubizzle.com/motors/used-cars/toyota/yaris/?price__lte=30000&year__gte=2020&year__lte=2022":
        f'<html><body><a href="{DZ1}"><h2>Toyota Yaris 2022</h2><span>AED 26,500</span> 2022 132,000 km</a>'
        f'<a href="{DZ2}"><h2>Toyota Yaris 2020</h2>AED 26,999 2020 249,000 km</a>'
        f'<a href="{DZ_OLD}"><h2>Toyota Yaris 2021</h2>AED 25,000 2021 99,000 km</a>'
        f'<a href="/motors/used-cars/toyota/">all toyota</a></body></html>',
    # market page (no price cap): structured data with prices for the fair-price model
    "https://uae.dubizzle.com/motors/used-cars/toyota/yaris/?year__gte=2019&year__lte=2023":
        '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"hits": [
            {"absolute_url": f"/motors/used-cars/toyota/yaris/2026/10/1/x-{i}---{i:032x}/", "price": p, "year": y, "kilometers": k, "name": "Toyota Yaris"}
            for i, (p, y, k) in enumerate([(31000, 2022, 90000), (33000, 2022, 60000), (29000, 2021, 120000), (30500, 2021, 80000),
                                           (27000, 2020, 150000), (28500, 2020, 110000), (35000, 2022, 40000), (26000, 2020, 200000),
                                           (32000, 2021, 70000), (29500, 2021, 100000), (34000, 2022, 50000), (27500, 2020, 140000)], 1)]}}) + '</script>',
    "https://uae.yallamotor.com/used-cars/toyota/yaris": f'<a href="{YM}">Toyota Yaris 2021 AED 29,500 77,000 km</a>',
    "https://www.dubicars.com/uae/used/toyota/yaris": f'<a href="{DC}">2021 Toyota Yaris AED 29,500 77,000 km</a>',
    "https://uae.dubizzle.com" + DZ1: ld_ad("Toyota Yaris 2022 GCC Specs", 26500, 2022, 132000, d(10), phone="+971501234567"),
    "https://uae.dubizzle.com" + DZ2: ld_ad("Toyota Yaris 2020 SE GCC Urgent sale leaving UAE", 26999, 2020, 249000, d(15)),
    "https://uae.dubizzle.com" + DZ_OLD: ld_ad("Toyota Yaris 2021", 25000, 2021, 99000, d(90)),
    "https://uae.yallamotor.com" + YM: ld_ad("Toyota Yaris 2021 1.5L", 29500, 2021, 77000, d(5), seller="AutoDealer"),
    "https://www.dubicars.com" + DC: ld_ad("Toyota Yaris 2021 1.5L", 29500, 2021, 77000, None, seller="AutoDealer"),
}


def fake_get(url, referer=None, timeout=25, retries=1):
    p = fetch.Page(url)
    if url in PAGES:
        p.status, p.html = 200, PAGES[url]
    else:
        p.status = 404
    return p


class Engine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        radar.ROOT = self.tmp
        radar.USER_FILE = os.path.join(self.tmp, "data", "user.enc")
        radar.ENGINE_FILE = os.path.join(self.tmp, "data", "engine.enc")
        radar.REPORTS_DIR = os.path.join(self.tmp, "reports")
        radar.WORK = os.path.join(self.tmp, ".work")
        fetch.get = fake_get
        fetch.search_links = lambda q, limit=30: []
        radar.notify.send_all = lambda *a, **k: {"telegram": "test"}
        os.makedirs(os.path.join(self.tmp, "data"))
        store.write_json(radar.USER_FILE, {"requests": [{
            "id": "r1", "name": "يارس", "make": "Toyota", "model": "Yaris", "year_from": 2020, "year_to": 2022,
            "price_max": 30000, "color": "أبيض", "platforms": ["dubizzle", "yallamotor", "dubicars"], "scheduled": True}],
            "marks": {}}, KEY)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def args(self, mode="manual"):
        return type("A", (), {"mode": mode, "request": "all", "run_id": ""})()

    def test_round(self):
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        L = eng["listings"]
        self.assertIn("dubizzle-0e178fe896f34a32b34968b5266f36dd", L)
        self.assertEqual(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["state"], "verified")
        self.assertEqual(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["phone"], "+971501234567")
        self.assertNotIn("dubizzle-1111111111111111111111111111aaaa", L)        # posted 90 days ago
        self.assertIn("dubizzle-1111111111111111111111111111aaaa", eng["skipped"])
        # same car on yallamotor and dubicars -> one record pointing at the other link
        twins = [l for l in L.values() if l.get("mileage") == 77000]
        self.assertEqual(len(twins), 1)
        self.assertTrue(twins[0].get("also_on"))
        # fair price from 12 market samples + opened ads
        self.assertIsNotNone(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["fair"])
        self.assertIn(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["rating"], ("excellent", "good", "fair"))
        self.assertEqual(L["dubizzle-8507a50ad04143bebd4191dbc57586e8"]["urgency"]["level"] in ("medium", "high"), True)
        self.assertEqual(len(eng["reports"]), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, eng["reports"][0]["file"])))
        # second round: price drop is detected and nothing is duplicated
        PAGES["https://uae.dubizzle.com" + DZ1] = ld_ad("Toyota Yaris 2022 GCC Specs", 24900, 2022, 132000, d(10))
        for l in L.values():
            l["last_checked"] = d(2) + "T00:00:00+04:00"
        store.write_json(radar.ENGINE_FILE, eng, KEY)
        radar.run_round(self.args(), KEY)
        eng2 = store.read_json(radar.ENGINE_FILE, KEY, {})
        self.assertEqual(len(eng2["listings"]), len(L))
        x = eng2["listings"]["dubizzle-0e178fe896f34a32b34968b5266f36dd"]
        self.assertEqual((x["price"], x["price_prev"]), (24900, 26500))
        self.assertEqual(eng2["runs"][0]["price_drops"], 1)

    def test_watch_alerts_followed_only(self):
        radar.run_round(self.args(), KEY)
        user = store.read_json(radar.USER_FILE, KEY, {})
        user["marks"] = {"dubizzle-0e178fe896f34a32b34968b5266f36dd": {"favorite": True}}
        store.write_json(radar.USER_FILE, user, KEY)
        PAGES["https://uae.dubizzle.com" + DZ1] = ld_ad("Toyota Yaris 2022 GCC Specs", 23000, 2022, 132000, d(10))
        sent = []
        radar.notify.send_all = lambda *a, **k: sent.append(a) or {"telegram": "test"}
        radar.watch(self.args(), KEY)
        self.assertEqual(len(sent), 1)
        self.assertIn("23,000", sent[0][1])

    def test_wrong_key(self):
        with self.assertRaises(store.BadPassphrase):
            store.read_json(radar.USER_FILE, "wrong", {})


class Parts(unittest.TestCase):
    def test_fair_price_regression(self):
        s = {str(i): {"price": 40000 - 3000 * (2022 - y) - k // 10, "year": y, "km": k} for i, (y, k) in enumerate(
            [(2020, 100000), (2020, 150000), (2021, 80000), (2021, 120000), (2022, 40000), (2022, 90000),
             (2020, 60000), (2021, 50000), (2022, 20000), (2021, 160000), (2020, 200000), (2022, 70000)])}
        fp = analytics.fair_price(s, 2021, 100000)
        self.assertEqual(fp["method"], "regression")
        self.assertAlmostEqual(fp["expected"], 27000, delta=1500)

    def test_urgency_words_and_cuts(self):
        l = {"title": "Yaris urgent sale", "price_history": [{"price": 30000}, {"price": 28000}], "first_seen": d(30), "seller_type": "owner"}
        score, level, why = analytics.urgency(l, TODAY)
        self.assertEqual(level, "high")

    def test_ad_page_sold(self):
        f = extract.ad_page("<html><body>This ad is no longer available</body></html>", "u", "1")
        self.assertTrue(f["_sold"])

    def test_crypto_roundtrip(self):
        t = store.encrypt_bytes(b'{"a":1}', "k")
        self.assertEqual(store.decrypt_bytes(t, "k"), b'{"a":1}')


if __name__ == "__main__":
    unittest.main()
