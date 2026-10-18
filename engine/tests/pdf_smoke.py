"""Real PDF renderer smoke check, separate from the deterministic engine tests."""
import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import report
with tempfile.TemporaryDirectory() as work:
    html = '<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><body><h1>تقرير اختبار رادار السيارات</h1><p>تويوتا يارس — 29,000 درهم</p></body></html>'
    path = os.path.join(work, "report.pdf")
    assert report.to_pdf(html, os.path.join(work, "report.html"), path), "PDF renderer unavailable or failed"
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-", "Invalid PDF header"
    print("Real Arabic PDF smoke check passed")
