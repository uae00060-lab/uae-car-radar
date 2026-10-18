"""Polite page fetching: browser-like headers, per-host pacing, one retry, and a
search-engine fallback for finding ad links when a platform blocks its results page.

Never tries to get around a site that refuses access (no proxies, no CAPTCHA solving):
a refused page is recorded and the ad stays "needs confirmation".
"""

import gzip
import http.cookiejar
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html import unescape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
MIN_GAP = 1.2      # seconds between two requests to the same host
MAX_BYTES = 4_000_000

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_host_lock = {}
_host_last = {}
_glock = threading.Lock()


class Page:
    __slots__ = ("url", "final_url", "status", "html", "error", "blocked", "elapsed")

    def __init__(self, url):
        self.url, self.final_url, self.status, self.html = url, url, 0, ""
        self.error, self.blocked, self.elapsed = "", False, 0.0

    @property
    def ok(self):
        return self.status == 200 and bool(self.html) and not self.blocked


BLOCK_MARKS = re.compile(
    r"captcha|cf-browser-verification|challenge-platform|Access Denied|Request unsuccessful\. Incapsula|"
    r"_Incapsula_Resource|Pardon Our Interruption|are you a robot|px-captcha|perimeterx", re.I)


def _pace(host):
    with _glock:
        lock = _host_lock.setdefault(host, threading.Lock())
    lock.acquire()
    try:
        wait = _host_last.get(host, 0) + MIN_GAP + random.uniform(0, .6) - time.time()
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.time()
    finally:
        lock.release()


def _decode(raw, enc, ctype):
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    m = re.search(r"charset=([\w-]+)", ctype or "")
    return raw.decode(m[1] if m else "utf-8", "replace")


def get(url, referer=None, timeout=25, retries=1):
    """Fetch one page. Never raises; the Page says what happened."""
    page = Page(url)
    host = urllib.parse.urlparse(url).netloc
    for attempt in range(retries + 1):
        _pace(host)
        hdr = dict(HEADERS)
        if referer:
            hdr["Referer"] = referer
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=hdr)
            with _opener.open(req, timeout=timeout) as r:
                page.status = r.status
                page.final_url = r.geturl()
                page.html = _decode(r.read(MAX_BYTES), r.headers.get("Content-Encoding"), r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:
            page.status, page.error = e.code, f"HTTP {e.code}"
            try:
                page.html = _decode(e.read(200_000), e.headers.get("Content-Encoding"), e.headers.get("Content-Type"))
            except Exception:  # noqa: BLE001 - an unreadable error body changes nothing
                page.html = ""
        except Exception as e:  # noqa: BLE001 - timeouts, resets, DNS: all just "not fetched"
            page.status, page.error = 0, type(e).__name__
        page.elapsed = time.time() - t0
        page.blocked = page.status in (401, 403, 429) or (
            page.status == 200 and len(page.html) < 60_000 and bool(BLOCK_MARKS.search(page.html[:60_000])))
        if page.ok or page.status in (404, 410) or attempt == retries:
            break
        time.sleep(2.5 + attempt * 3)
    return page


# ---------------------------------------------------------------- search-engine fallback

def search_debug(query):
    """Status of each search engine for one query (for the diagnose run)."""
    out = {}
    for name, url in (("ddg", "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query, "kl": "ae-en"})),
                      ("bing", "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": "50", "setlang": "en"}))):
        p = get(url, retries=0)
        out[name] = {"status": p.status, "blocked": p.blocked, "bytes": len(p.html),
                     "result_a": p.html.count('class="result__a"'), "b_algo": p.html.count('class="b_algo"'),
                     "head": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p.html))[:200]}
    links = search_links(query)
    out["links"] = len(links)
    out["sample"] = [u for u, _ in links[:12]]
    return out


def search_links(query, limit=40):
    """Result links from Bing (two pages), then DuckDuckGo. Returns [(url, title)]."""
    out = []
    for first in (1, 11, 21):
        p = get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "first": first, "setlang": "en", "cc": "AE"}), retries=0)
        if not p.ok:
            break
        got = 0
        for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', p.html, re.S):
            out.append((unescape(m[1]), re.sub(r"<[^>]+>", "", unescape(m[2])).strip()))
            got += 1
        if got < 5:
            break
    if len(out) < 3:
        p = get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query, "kl": "ae-en"}), retries=0)
        if p.ok:
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', p.html, re.S):
                href = unescape(m[1])
                q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
                out.append((q[0] if q else href, re.sub(r"<[^>]+>", "", unescape(m[2])).strip()))
    seen, uniq = set(), []
    for u, t in out:
        if u not in seen:
            seen.add(u)
            uniq.append((u, t))
    return uniq[:limit]
