import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analytics  # noqa: E402
import vindecode  # noqa: E402
from condition import red_flags, spec_of  # noqa: E402


def kinds(text):
    return sorted(f["kind"] for f in red_flags(text))


class Specs(unittest.TestCase):
    def test_platform_field_wins(self):
        self.assertEqual(spec_of("GCC Specs", "imported from USA"), "gcc")
        self.assertEqual(spec_of("American Specs"), "american")
        self.assertEqual(spec_of("Other"), "other")

    def test_read_from_title_or_description(self):
        self.assertEqual(spec_of(None, "Land Cruiser GXR GCC full option"), "gcc")
        self.assertEqual(spec_of(None, "نظيفة جدا وارد امريكا"), "american")
        self.assertEqual(spec_of(None, "مواصفات خليجية"), "gcc")
        self.assertEqual(spec_of(None, "Non-GCC, Japan import"), "other")
        self.assertIsNone(spec_of(None, "Toyota Camry 2020 low mileage"))


class Flags(unittest.TestCase):
    def test_stated_problems(self):
        self.assertEqual(kinds("car has minor accident on front bumper"), ["accident"])
        self.assertEqual(kinds("السيارة مصدومة من الامام"), ["accident"])
        self.assertEqual(kinds("Salvage title, for export only"), ["export", "salvage"])
        self.assertEqual(kinds("flooded car sold as is"), ["flood"])
        self.assertEqual(kinds("gearbox problem, needs repair"), ["mechanical"])
        self.assertEqual(kinds("فيها رش خفيف على الباب"), ["repaint"])
        self.assertEqual(kinds("airbags deployed"), ["airbag"])
        self.assertEqual(kinds("Registration expired, without mulkiya"), ["registration"])

    def test_denials_are_not_flags(self):
        for text in ("Accident free, full service history", "بدون حوادث صبغ وكالة", "مافيها حوادث ولا صبغ",
                     "Accident history: None. Flood: No", "0 accidents, clean title", "Original paint, no accident",
                     "الملكية سارية، لا يوجد حادث", "صبغة وكالة"):
            self.assertEqual(kinds(text), [], text)

    def test_denial_does_not_cross_into_the_next_clause(self):
        self.assertEqual(kinds("No accidents, repainted bumper"), ["repaint"])
        self.assertEqual(kinds("Accident free. Repainted roof"), ["repaint"])

    def test_dealer_boilerplate_is_ignored(self):
        for text in ("Available for export and local", "للتصدير والمحلي", "free accident & warranty check",
                     "تأمين شامل ضد الحوادث", "paint protection film (PPF)"):
            self.assertEqual(kinds(text), [], text)


class SpecAwareFairPrice(unittest.TestCase):
    def book(self):
        b = {}
        for i in range(6):
            b[f"g{i}"] = {"price": 100_000 + i * 1000, "year": 2020, "km": None, "spec": "gcc"}
            b[f"a{i}"] = {"price": 70_000 + i * 1000, "year": 2020, "km": None, "spec": "american"}
        return b

    def test_gcc_and_imports_are_never_mixed(self):
        gcc = analytics.fair_price(self.book(), 2020, None, spec="gcc")
        imp = analytics.fair_price(self.book(), 2020, None, spec="american")
        self.assertEqual((gcc["basis"], gcc["n"]), ("gcc", 6))
        self.assertEqual((imp["basis"], imp["n"]), ("import", 6))
        self.assertGreater(gcc["expected"], 95_000)
        self.assertLess(imp["expected"], 80_000)

    def test_unstated_specs_leave_out_declared_imports(self):
        fp = analytics.fair_price(self.book(), 2020, None)
        self.assertEqual(fp["basis"], "not-import")
        self.assertGreater(fp["low"], 95_000)

    def test_too_few_imports_gives_no_rating(self):
        book = {k: v for k, v in self.book().items() if k.startswith("g")}
        book["a0"] = {"price": 70_000, "year": 2020, "km": None, "spec": "american"}
        self.assertIsNone(analytics.fair_price(book, 2020, None, spec="american"))

    def test_samples_keep_their_specs(self):
        market = {}
        analytics.add_samples(market, "r", [{"id": "x", "price": 1000, "year": 2020, "km": 5, "spec": "gcc"}], dt.date(2026, 10, 1))
        self.assertEqual(market["r"]["x"]["spec"], "gcc")


class DescriptionFromAdPage(unittest.TestCase):
    def test_schema_description_and_meta_fallback(self):
        import extract
        ld = ('<script type="application/ld+json">{"@type":"Car","url":"https://x.ae/ad/123","name":"Patrol 2019",'
              '"description":"GCC specs, minor accident on rear bumper","offers":{"price":90000,"priceCurrency":"AED"}}</script>')
        found = extract.ad_page("<html><head>" + ld + "</head><body></body></html>", "https://x.ae/ad/123", "123")
        self.assertIn("minor accident", found["description"][0])
        meta = '<meta property="og:description" content="Clean car, no accidents">'
        found = extract.ad_page("<html><head>" + meta + "</head></html>", "https://x.ae/ad/9", "9")
        self.assertEqual(found["description"], ("Clean car, no accidents", "meta:description"))


class ArabicNames(unittest.TestCase):
    def test_spelling_variants_match(self):
        from common import has_terms, model_terms
        terms = lambda make, model: model_terms({"make": make, "model": model})
        self.assertTrue(has_terms("تويوتا لاندكروزر 2020", terms("Toyota", "Land Cruiser")))
        self.assertTrue(has_terms("تويوتا لاند كروزر GXR", terms("Toyota", "Land Cruiser")))
        self.assertTrue(has_terms("هيونداي سنتافي 2019", terms("Hyundai", "Santa Fe")))
        self.assertTrue(has_terms("للبيع تويوتا اليارس", terms("Toyota", "Yaris")))
        self.assertTrue(has_terms("نيسان باترول", terms("Nissan", "Patrol")))
        self.assertFalse(has_terms("تويوتا كامري", terms("Toyota", "Corolla")))


class VinDecode(unittest.TestCase):
    VIN = "JTMHV05J604123456"

    def test_decode_and_compare(self):
        row = {"Make": "TOYOTA", "Model": "Land Cruiser", "ModelYear": "2018", "Trim": "", "PlantCountry": "JAPAN"}
        info = vindecode.decode(self.VIN, get=lambda vin: row)
        self.assertEqual(info, {"make": "Toyota", "model": "Land Cruiser", "year": 2018, "trim": None, "plant": "Japan"})
        self.assertEqual(vindecode.compare(info, {"year": 2018}, "Toyota"), [])
        notes = vindecode.compare(info, {"year": 2019}, "Nissan")
        self.assertEqual(len(notes), 2)
        self.assertIn("Nissan", notes[0])
        self.assertIn("2018", notes[1])

    def test_mercedes_spelling(self):
        self.assertEqual(vindecode.compare({"make": "Mercedes-Benz"}, {}, "Mercedes-Benz"), [])
        self.assertEqual(vindecode.compare({"make": "Mercedes-Benz"}, {}, "Mercedes"), [])

    def test_unknown_vin_and_network_error(self):
        self.assertEqual(vindecode.decode(self.VIN, get=lambda vin: {"Make": "", "ModelYear": ""}), {})

        def fail(vin):
            raise OSError("down")
        self.assertIsNone(vindecode.decode(self.VIN, get=fail))

    def test_update_caches_limits_and_prunes(self):
        calls = []

        def get(vin):
            calls.append(vin)
            return {"Make": "TOYOTA", "ModelYear": "2018"}
        eng = {}
        ads = [{"id": "a", "vin": self.VIN, "identity_version": 1, "year": 2018, "request_id": "r"},
               {"id": "b", "vin": None, "identity_version": 1}]
        vindecode.update(eng, ads, [{"id": "r", "make": "Toyota"}], get=get)
        vindecode.update(eng, ads, [{"id": "r", "make": "Toyota"}], get=get)
        self.assertEqual(calls, [self.VIN])           # decoded once, then from the cache
        self.assertEqual(ads[0]["vin_check"], [])
        self.assertEqual(ads[0]["vin_info"]["year"], 2018)
        vindecode.prune(eng, [])
        self.assertEqual(eng["vin_decoded"], {})


if __name__ == "__main__":
    unittest.main()
