"""Real PDF renderer smoke check, separate from the deterministic engine tests."""
import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import report
with tempfile.TemporaryDirectory() as work:
    from common import now_uae
    now = now_uae()
    start = now.date().replace(day=1)
    req = {"id": "sample", "name": "معاينة تقرير السيارات", "make": "Toyota", "model": "Yaris", "price_max": 31000}
    cars = [{"id": str(i), "title": "Toyota Yaris 2019", "year": 2019, "price": 25000+i*500, "mileage": 95000,
             "platform": "dubicars", "url": "https://www.dubicars.com/2019-toyota-yaris-1035981.html",
             "emirate": "دبي", "seller_name": "بائع الاختبار", "seller_type": "owner", "color": "أبيض",
             "date": now.date().isoformat(), "date_kind": "first_seen", "identity_version": 1,
             "vin": "1HGCM82633A004352" if i == 0 else None, "vin_status": "checksum",
             "phone": "+971552398817" if i == 0 else None} for i in range(6)]
    run = {"mode": "manual", "current_offers": 6, "candidates": 0, "new": 6}
    html = report.render_html(run, [(req, cars, [])], [], now, start, {}, ["dubicars"])
    assert html.count('class="dossier"') == 6
    assert '1HGCM82633A004352' in html
    path = os.path.join(work, "report.pdf")
    assert report.to_pdf(html, os.path.join(work, "report.html"), path), "PDF renderer unavailable or failed"
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-", "Invalid PDF header"
    print("Real Arabic PDF smoke check passed")
