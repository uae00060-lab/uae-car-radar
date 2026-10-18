"""Offline tests: fake platform pages through the whole round. Run: python -m unittest discover engine/tests"""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

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
    "https://uae.dubizzle.com" + DZ1: ld_ad("Toyota Yaris 2022 GCC Specs", 26500, 2022, 132000, d(10), phone="+971552398817"),
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
        self.original_pages = dict(PAGES)
        for obj, attr in ((radar, "ROOT"), (radar, "USER_FILE"), (radar, "ENGINE_FILE"), (radar, "REPORTS_DIR"), (radar, "WORK"), (fetch, "get"), (fetch, "search_links"), (radar.notify, "send_all")):
            original = getattr(obj, attr)
            self.addCleanup(setattr, obj, attr, original)
        def fake_pdf(html, html_path, pdf_path):
            # The engine contract is tested offline; PDF rendering has a separate smoke test.
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4\n" + b"0" * 1200)
            return True
        self.pdf_patch = patch.object(radar.report, "to_pdf", side_effect=fake_pdf)
        self.pdf_patch.start(); self.addCleanup(self.pdf_patch.stop)
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
        PAGES.clear(); PAGES.update(self.original_pages)
        shutil.rmtree(self.tmp)

    def args(self, mode="manual"):
        return type("A", (), {"mode": mode, "request": "all", "run_id": ""})()

    def test_round(self):
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        L = eng["listings"]
        self.assertIn("dubizzle-0e178fe896f34a32b34968b5266f36dd", L)
        self.assertEqual(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["state"], "verified")
        self.assertEqual(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["phone"], "+971552398817")
        self.assertNotIn("dubizzle-1111111111111111111111111111aaaa", L)        # posted 90 days ago
        self.assertIn("dubizzle-1111111111111111111111111111aaaa", eng["skipped"])
        # Matching price/year/km is not enough evidence to merge distinct ads.
        twins = [l for l in L.values() if l.get("mileage") == 77000]
        self.assertEqual(len(twins), 2)
        self.assertFalse(any(l.get("also_on") for l in twins))
        # Result cards cannot contaminate estimates; opened comparables are still too few.
        self.assertIsNone(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["fair"])
        self.assertEqual(L["dubizzle-0e178fe896f34a32b34968b5266f36dd"]["rating"], "unknown")
        self.assertEqual(L["dubizzle-8507a50ad04143bebd4191dbc57586e8"]["urgency"]["level"] in ("medium", "high"), True)
        self.assertEqual(len(eng["reports"]), 0)  # manual searches never create reports
        self.assertFalse(os.path.exists(radar.REPORTS_DIR))
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

    def test_platform_health_persists_and_warns_after_two_empty_rounds(self):
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        self.assertTrue(eng["platform_health"]["dubizzle"]["latest"]["had_price"])
        def empty(req, plats, diag, progress=None):
            for platform in plats:
                diag[platform] = {"pages": 1, "ok": 1, "cards": 0, "blocked": 0, "via_search": 0, "status": [200]}
            return {}, []
        with patch.object(radar, "discover", side_effect=empty):
            radar.run_round(self.args(), KEY)
            first = store.read_json(radar.ENGINE_FILE, KEY, {})
            self.assertFalse(first["runs"][0]["health_warnings"])
            radar.run_round(self.args(), KEY)
        final = store.read_json(radar.ENGINE_FILE, KEY, {})
        self.assertTrue(final["platform_health"]["dubizzle"]["latest"]["alert"])
        self.assertIn("جولتين", final["runs"][0]["warning"])
        self.assertEqual(final["reports"], [])

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

    def test_invalid_make_reports_failure(self):
        user = store.read_json(radar.USER_FILE, KEY, {})
        user["requests"][0]["make"] = "اسم غير معروف"
        store.write_json(radar.USER_FILE, user, KEY)
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        self.assertEqual(eng["runs"][0]["status"], "failed")
        self.assertIn("الماركة", eng["runs"][0]["warning"])

    def test_scheduled_round_always_runs_and_notifies(self):
        # An open dashboard must never cancel a scheduled round or its report.
        with open(os.path.join(self.tmp, "data", "presence.json"), "w") as f:
            json.dump({"at": now_uae().isoformat()}, f)
        sent = []
        radar.notify.send_all = lambda *a, **k: sent.append(a) or {"telegram": radar.notify.SENT}
        radar.run_round(self.args("scheduled"), KEY)
        self.assertTrue(os.path.exists(radar.ENGINE_FILE))
        self.assertEqual(len(sent), 1)

    def test_one_ad_matches_two_requests(self):
        user = store.read_json(radar.USER_FILE, KEY, {})
        user["requests"].append({**user["requests"][0], "id": "r2", "price_max": 27000})
        store.write_json(radar.USER_FILE, user, KEY)
        base = "https://uae.dubizzle.com/motors/used-cars/toyota/yaris/?price__lte=30000&year__gte=2020&year__lte=2022"
        PAGES[base.replace("30000", "27000")] = PAGES[base]
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        ad = eng["listings"]["dubizzle-0e178fe896f34a32b34968b5266f36dd"]
        self.assertEqual(set(ad["request_ids"]), {"r1", "r2"})
        self.assertEqual(ad["by_request"]["r2"]["state"], "verified")

    def test_unpriced_ads_never_become_offers(self):
        PAGES["https://uae.dubizzle.com" + DZ1] = ld_ad("Toyota Yaris 2022", None, 2022, 132000, d(2))
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        self.assertNotIn("dubizzle-0e178fe896f34a32b34968b5266f36dd", eng["listings"])
        self.assertTrue(all(l["price"] for l in eng["listings"].values()))

    def test_missing_saved_price_is_repaired_without_waiting_ten_hours(self):
        radar.run_round(self.args(), KEY)
        eng = store.read_json(radar.ENGINE_FILE, KEY, {})
        ad = eng["listings"]["dubizzle-0e178fe896f34a32b34968b5266f36dd"]
        ad["price"] = None; ad["price_version"] = 1
        store.write_json(radar.ENGINE_FILE, eng, KEY)
        radar.run_round(self.args(), KEY)
        ad = store.read_json(radar.ENGINE_FILE, KEY, {})["listings"][ad["id"]]
        self.assertEqual(ad["price"], 26500)
        self.assertEqual(ad["price_currency"], "AED")
        self.assertEqual(ad["price_version"], 3)

    def test_wrong_key(self):
        with self.assertRaises(store.BadPassphrase):
            store.read_json(radar.USER_FILE, "wrong", {})

    def test_manual_search_never_calls_pdf_renderer(self):
        with patch.object(radar.report,"to_pdf") as pdf:
            radar.run_round(self.args(),KEY)
            pdf.assert_not_called()
        self.assertEqual(store.read_json(radar.ENGINE_FILE,KEY,{})["reports"],[])

    def test_scheduled_report_is_created_only_when_absent(self):
        radar.run_round(self.args("scheduled"),KEY)
        eng=store.read_json(radar.ENGINE_FILE,KEY,{})
        self.assertEqual(len(eng["reports"]),1)
        self.assertEqual(eng["reports"][0]["mode"],"scheduled")

    def test_weekly_review_covers_saved_search_without_favorites(self):
        radar.run_round(self.args(),KEY)
        eng=store.read_json(radar.ENGINE_FILE,KEY,{})
        target=next(iter(eng["listings"]))
        args=self.args();args.weekly=True
        def observation(item,today):
            return ("gone",{}) if item["ad_id"]==eng["listings"][target]["ad_id"] else ("failed",{})
        with patch.object(radar,"read_ad",side_effect=observation), patch.object(radar.report,"to_pdf") as pdf, patch.object(radar,"mark_duplicates",wraps=radar.mark_duplicates) as dedup:
            radar.watch(args,KEY);pdf.assert_not_called();dedup.assert_called_once()
        updated=store.read_json(radar.ENGINE_FILE,KEY,{})
        self.assertEqual(updated["listings"][target]["availability"],"unavailable")
        self.assertEqual(len(updated["alerts"]),1)
        self.assertEqual(updated["runs"][0]["opened"],len(eng["listings"]))
        self.assertTrue(updated["last_weekly_review"])
        self.assertEqual(len(updated["reports"]),0)

    def test_encrypted_activity_suppresses_only_scheduled_search(self):
        store.write_json(os.path.join(radar.WORK,"activity.enc"),{"at":now_uae().isoformat()},KEY)
        radar.run_round(self.args("scheduled"),KEY)
        self.assertFalse(os.path.exists(radar.ENGINE_FILE))
        radar.run_round(self.args(),KEY)
        self.assertTrue(os.path.exists(radar.ENGINE_FILE))

    def test_expired_or_wrong_key_activity_does_not_suppress(self):
        path=os.path.join(radar.WORK,"activity.enc")
        store.write_json(path,{"at":(now_uae()-dt.timedelta(seconds=181)).isoformat()},KEY)
        self.assertFalse(radar.load_presence(KEY))
        store.write_json(path,{"at":now_uae().isoformat()},"different-key")
        self.assertFalse(radar.load_presence(KEY))

    def test_quality_warning_is_in_pdf_input(self):
        rendered=[]
        with patch.dict(os.environ,{"RADAR_TESTS":"failure"}), patch.object(radar.report,"to_pdf",side_effect=lambda html,*args: rendered.append(html) or False):
            radar.run_round(self.args("scheduled"),KEY)
        self.assertIn("فشلت اختبارات الجودة",rendered[0])


class Additions(unittest.TestCase):
    def ad(self, i, plat, price, km=88000, year=2021, vin=None):
        return {"id": f"{plat}-{i}", "platform": plat, "url": f"https://x/{plat}/{i}", "price": price, "year": year,
                "mileage": km, "vin": vin, "state": "verified", "request_ids": ["r1"], "price_version": 3, "price_currency": "AED", "price_source": "ad:AED-offer"}

    def test_same_car_on_two_platforms_shows_cheapest(self):
        L = {a["id"]: a for a in (self.ad(1, "dubicars", 29500, vin="JTDBT923X71000000"), self.ad(2, "yallamotor", 28900, vin="JTDBT923X71000000"),
                                  self.ad(3, "carswitch", 29500, km=91000))}
        self.assertEqual(radar.mark_duplicates(L), 1)
        self.assertEqual(L["dubicars-1"]["dup_of"], "yallamotor-2")
        self.assertEqual([d["price"] for d in L["yallamotor-2"]["duplicates"]], [29500])
        self.assertNotIn("dup_of", L["carswitch-3"])          # different mileage: a different car
        # Same mileage but very different price: not merged.
        L2 = {a["id"]: a for a in (self.ad(1, "dubicars", 29500), self.ad(2, "yallamotor", 21000))}
        self.assertEqual(radar.mark_duplicates(L2), 0)
        # Same VIN always merges; a later round recomputes from scratch.
        L3 = {a["id"]: a for a in (self.ad(1, "dubicars", 30000, km=1, vin="JTDBT923X71000000"),
                                   self.ad(2, "autoae", 31000, km=2, vin="JTDBT923X71000000"))}
        self.assertEqual(radar.mark_duplicates(L3), 1)
        L3["dubicars-1"]["vin"] = None
        self.assertEqual(radar.mark_duplicates(L3), 0)
        self.assertNotIn("dup_of", L3["autoae-2"])


    def test_similar_cars_and_conflicting_vins_never_hide_each_other(self):
        for vin_a,vin_b in ((None,None),("JTDBT923X71000000","JTDKB20U773205781")):
            cars={a["id"]:a for a in (self.ad(1,"dubicars",29500,vin=vin_a), self.ad(2,"yallamotor",28900,vin=vin_b))}
            self.assertEqual(radar.mark_duplicates(cars),0)
            self.assertFalse(any(a.get("dup_of") for a in cars.values()))

    def test_duplicates_do_not_hide_different_request_coverage(self):
        a=self.ad(1,"dubicars",29500,vin="JTDBT923X71000000")
        b=self.ad(2,"yallamotor",28900,vin="JTDBT923X71000000");b["request_ids"].append("r2")
        self.assertEqual(radar.mark_duplicates({a['id']:a,b['id']:b}),0)

    def test_duplicate_reselection_after_price_or_availability_change(self):
        a=self.ad(1,"dubicars",29500,vin="JTDBT923X71000000")
        b=self.ad(2,"yallamotor",28900,vin="JTDBT923X71000000")
        cars={a['id']:a,b['id']:b};radar.mark_duplicates(cars)
        self.assertEqual(a['dup_of'],b['id'])
        a['price']=28000;radar.mark_duplicates(cars)
        self.assertEqual(b['dup_of'],a['id'])
        a['availability']='reserved';radar.mark_duplicates(cars)
        self.assertNotIn('dup_of',b)
        a['availability']='unavailable';a['state']='sold';radar.mark_duplicates(cars)
        self.assertNotIn('dup_of',b)

    def test_card_price_is_not_used_when_detail_has_none(self):
        page = fetch.Page("https://www.oneclickdrive.com/details/index/search-usedcar-dubai/Toyota/Yaris/?id=855142")
        page.status, page.html = 200, "<html><title>Toyota Yaris 2021 in Dubai</title><body>Model year: 2021</body></html>"
        item = {"url": page.url, "ad_id": "855142", "platform": "oneclickdrive", "src": "json", "price": 31000, "year": 2021}
        with patch.object(fetch, "get", return_value=page):
            status, v = radar.read_ad(item, TODAY)
            self.assertEqual(status,"ok")
            self.assertIsNone(v["price"])  # card-only asking prices are not confirmed by the detail page
            # An instalment-sized figure is never taken as the asking price.
            status, v = radar.read_ad({**item, "price": 1999}, TODAY)
            self.assertIsNone(v["price"])

    def test_crash_and_failed_checks_are_recorded_not_fatal(self):
        tmp = tempfile.mkdtemp()
        try:
            radar.ROOT, radar.ENGINE_FILE = tmp, os.path.join(tmp, "data", "engine.enc")
            radar.USER_FILE = os.path.join(tmp, "data", "user.enc")
            os.makedirs(os.path.join(tmp, "data"))
            args = type("A", (), {"cmd": "run", "mode": "scheduled"})()
            try:
                raise KeyError("boom")
            except KeyError as e:
                radar.record_crash(args, KEY, e)
            run = store.read_json(radar.ENGINE_FILE, KEY, {})["runs"][0]
            self.assertEqual(run["status"], "failed")
            self.assertIn("KeyError", run["warning"])
            with patch.dict(os.environ, {"RADAR_TESTS": "failure"}):
                self.assertEqual(len(radar.quality_warnings()), 1)
        finally:
            shutil.rmtree(tmp)


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

    def test_alias_and_validation(self):
        from common import slug, validate_request
        self.assertEqual(slug("تيوتا"), "toyota")
        self.assertTrue(radar.search_urls("yallamotor", {"make": "تيوتا", "model": "يارس"}))
        self.assertIsNotNone(validate_request({"make": "غير معروف"}))

    def test_price_year_boundaries_and_unconfirmed_date(self):
        from common import window_start
        req = {"make": "Toyota", "model": "Yaris", "price_max": 30000, "year_from": 2022, "year_to": 2026}
        v = {"title": "Toyota Yaris", "year": 2022, "price": 29000, "date": TODAY, "date_kind": "posted"}
        for price in (29000, 30000):
            c = radar.assess(req, {**v, "price": price}, window_start(TODAY), "yallamotor")
            self.assertEqual(radar.state_of(c, "yallamotor", False)[0], "verified")
        c = radar.assess(req, {**v, "price": 30001}, window_start(TODAY), "yallamotor")
        self.assertEqual(radar.state_of(c, "yallamotor", False)[0], "excluded")
        for year in (2022, 2026):
            self.assertEqual(radar.assess(req, {**v, "year": year}, window_start(TODAY), "yallamotor")["year"], "matched")
        # Every condition matched but the date is a photo date: shown, labelled as "no posting date".
        c = radar.assess(req, {**v, "date_kind": "photos"}, window_start(TODAY), "yallamotor")
        self.assertEqual(radar.state_of(c, "yallamotor", False)[0], "approx")
        c = radar.assess(req, {**v, "date": TODAY - dt.timedelta(days=90)}, window_start(TODAY), "yallamotor")
        self.assertEqual(radar.state_of(c, "yallamotor", True)[0], "excluded")

    def test_currency_and_total_cash_price(self):
        html = ld_ad("Toyota Yaris 2022", 8719, 2022, 90000, d(2)).replace('"AED"', '"USD"')
        html = html.replace("</body>", "<p>AED 31,999 (+ AED 3,000 Convenience Fee)</p></body>")
        f = extract.ad_page(html, "u", "1")
        self.assertEqual(f["price"][0], 34999)
        self.assertEqual(f["currency"][0], "AED")
        f = extract.ad_page(ld_ad("Toyota Yaris", 8719, 2022, 90000, d(2)).replace('"AED"', '"USD"'), "u", "1")
        self.assertNotIn("price", f)
        self.assertTrue(f["_price_uncertain"])

    def test_report_goes_to_every_configured_channel(self):
        import notify
        env = {"SMTP_USER": "a", "SMTP_PASSWORD": "b", "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}
        with patch.dict(os.environ, env, clear=True), patch.object(notify, "email", return_value=notify.SENT) as mail, \
                patch.object(notify, "telegram", return_value=notify.SENT) as tg, patch.object(notify, "whatsapp", return_value=notify.OFF) as wa:
            result = notify.send_all("subject", "all offers", "short")
            mail.assert_called_once(); tg.assert_called_once(); wa.assert_called_once_with("short")
            self.assertEqual(notify.delivery_problem(result), "")
        # A failed channel is retried once and then reported.
        with patch.object(notify, "email", return_value="فشل (timeout)") as mail, patch.object(notify, "telegram", return_value=notify.OFF), \
                patch.object(notify, "whatsapp", return_value=notify.OFF), patch.object(notify.time, "sleep"):
            result = notify.send_all("subject", "all offers", "short")
            self.assertEqual(mail.call_count, 2)
            self.assertIn("البريد", notify.delivery_problem(result))
        self.assertIn("لا توجد قناة", notify.delivery_problem({"telegram": notify.OFF, "whatsapp": notify.OFF, "email": notify.OFF}))
        # Telegram: the whole text as messages, then the PDF.
        with tempfile.NamedTemporaryFile() as f, patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}, clear=True), patch.object(notify, "_post", return_value=(200, b"{}")) as post:
            notify.telegram("details\n" * 1000, f.name)
            urls = [c.args[0] for c in post.call_args_list]
            self.assertTrue(all(u.endswith("/sendMessage") for u in urls[:-1]) and len(urls) > 2)
            self.assertTrue(urls[-1].endswith("/sendDocument"))

    def test_recover_aed_metadata_from_foreign_schema(self):
        html = ld_ad("Toyota Yaris 2019", 6807, 2019, 106000, d(2)).replace('"AED"', '"USD"')
        html = html.replace("<head>", "<head><meta content='Buy this car for just AED 25000.' property='og:description'>")
        found = extract.ad_page(html, "https://www.dubicars.com/2019-toyota-yaris-1035981.html", "1035981")
        self.assertEqual(found["price"][0], 25000)
        self.assertEqual(found["currency"][0], "AED")

    def test_no_monthly_or_recommendation_price(self):
        from extract import aed_amount
        self.assertIsNone(aed_amount("AED 2,500/month"))
        self.assertIsNone(aed_amount("Down payment AED 5,000"))
        html = '<script type="application/ld+json">' + json.dumps({"@type":"Car", "url":"https://www.dubicars.com/2020-toyota-yaris-111111.html", "offers":{"price":25000,"priceCurrency":"AED"}}) + '</script>'
        f = extract.ad_page(html, "https://www.dubicars.com/2019-toyota-yaris-1035981.html", "1035981")
        self.assertNotIn("price", f)

    def test_conflicting_aed_prices_are_not_guessed(self):
        html = ld_ad("Toyota Yaris", 25000, 2020, 100000, d(2))
        html = html.replace("<head>", '<head><meta name="description" content="AED 31000">')
        f = extract.ad_page(html, "u", "1")
        self.assertNotIn("price", f)
        self.assertIn("conflicting", f["_price_reason"])

    def test_crypto_roundtrip(self):
        t = store.encrypt_bytes(b'{"a":1}', "k")
        self.assertEqual(store.decrypt_bytes(t, "k"), b'{"a":1}')


if __name__ == "__main__":
    unittest.main()
