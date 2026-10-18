"""Telegram, WhatsApp (CallMeBot) and email. A channel is used only when its secrets are set.

Secrets (GitHub → Settings → Secrets and variables → Actions):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  CALLMEBOT_PHONE (e.g. +9715xxxxxxxx), CALLMEBOT_APIKEY
  SMTP_USER (Gmail address), SMTP_PASSWORD (Gmail app password), MAIL_TO (optional, defaults to SMTP_USER)
"""

import json
import os
import time
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage

env = os.environ.get


def _post(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def chunks(text, size):
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size and cur:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def telegram(text, pdf=None, pdf_name="report.pdf"):
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "غير مفعّل"
    base = f"https://api.telegram.org/bot{token}"
    try:
        # The whole report as text first, so every offer is readable without opening a file.
        for part in chunks(text, 3900):
            _post(base + "/sendMessage", urllib.parse.urlencode(
                {"chat_id": chat, "text": part, "disable_web_page_preview": "true"}).encode())
        if pdf and os.path.exists(pdf):
            boundary = uuid.uuid4().hex
            with open(pdf, "rb") as f:
                blob = f.read()
            caption = "التقرير الكامل بصيغة PDF"
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{pdf_name}\"\r\n"
                    f"Content-Type: application/pdf\r\n\r\n").encode() + blob + f"\r\n--{boundary}--\r\n".encode()
            _post(base + "/sendDocument", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)
        return "أُرسل"
    except Exception as e:  # noqa: BLE001 - report, never crash the run over a notification
        return f"فشل ({type(e).__name__})"


def whatsapp(text):
    phone, key = env("CALLMEBOT_PHONE"), env("CALLMEBOT_APIKEY")
    if not phone or not key:
        return "غير مفعّل"
    try:
        link = next((line for line in reversed(text.splitlines()) if "https://" in line), "")
        part = text if len(text) <= 1400 else text[:1100] + "\nالتفاصيل الكاملة في اللوحة:\n" + link
        phone = "+" + re.sub(r"\D", "", phone).removeprefix("00")  # CallMeBot wants +<country><number>
        q = urllib.parse.urlencode({"phone": phone, "text": part, "apikey": key.strip()})
        status, body = _post("https://api.callmebot.com/whatsapp.php?" + q)
        if status != 200:
            return f"فشل (HTTP {status})"
        return "أُرسل"
    except Exception as e:  # noqa: BLE001
        return f"فشل ({type(e).__name__})"


def email(subject, text, pdf=None, pdf_name="report.pdf"):
    user, pw = env("SMTP_USER"), env("SMTP_PASSWORD")
    if not user or not pw:
        return "غير مفعّل"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, env("MAIL_TO") or user
    msg.set_content(text)
    msg.add_alternative(f'<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;white-space:pre-wrap;line-height:1.6">'
                        f'{text.replace("&", "&amp;").replace("<", "&lt;")}</div>', subtype="html")
    if pdf and os.path.exists(pdf):
        with open(pdf, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=pdf_name)
    try:
        with smtplib.SMTP_SSL(env("SMTP_HOST") or "smtp.gmail.com", int(env("SMTP_PORT") or 465),
                              context=ssl.create_default_context(), timeout=60) as s:
            s.login(user, pw)
            s.send_message(msg)
        return "أُرسل"
    except Exception as e:  # noqa: BLE001
        return f"فشل ({type(e).__name__})"


SENT = "أُرسل"
OFF = "غير مفعّل"


def _with_retry(send):
    """One retry after a short pause: a brief network hiccup should not cost a report."""
    result = send()
    if result not in (SENT, OFF):
        time.sleep(8)
        result = send()
    return result


def send_all(subject, full_text, short_text, pdf=None, pdf_name="report.pdf"):
    """Every configured channel gets the report: Telegram and email the full text and the PDF,
    WhatsApp the short text with the dashboard link (CallMeBot accepts short messages only)."""
    return {
        "telegram": _with_retry(lambda: telegram(full_text, pdf, pdf_name)),
        "whatsapp": _with_retry(lambda: whatsapp(short_text)),
        "email": _with_retry(lambda: email(subject, full_text, pdf, pdf_name)),
    }


def delivery_problem(result):
    """A sentence for the dashboard when the report did not reach every configured channel, else ''."""
    names = {"telegram": "تيليجرام", "whatsapp": "واتساب", "email": "البريد"}
    if not result:
        return ""
    if all(v == OFF for v in result.values()):
        return "لم يُرسل التقرير: لا توجد قناة إشعار مفعّلة (أضف أسرار تيليجرام أو واتساب أو البريد في GitHub)"
    failed = [f"{names[k]} {v}" for k, v in result.items() if v not in (SENT, OFF)]
    return ("تعذّر إرسال التقرير عبر: " + "، ".join(failed)) if failed else ""


REQUIRED = {"telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"), "whatsapp": ("CALLMEBOT_PHONE", "CALLMEBOT_APIKEY"),
            "email": ("SMTP_USER", "SMTP_PASSWORD")}


def report_test(result):
    """Per-channel outcome of a test message as GitHub annotations and job summary; 1 if not all good."""
    names = {"telegram": "تيليجرام", "whatsapp": "واتساب", "email": "البريد"}
    lines = []
    for k, v in result.items():
        level = "notice" if v == SENT else "warning" if v == OFF else "error"
        missing = [n for n in REQUIRED[k] if not (env(n) or "").strip()]
        if v == OFF and missing:
            v = f"{v}: لا يصل للخادم {' و'.join(missing)}"
        print(f"::{level} title={names[k]}::{v}")
        lines.append(f"{names[k]}: {v}")
    summary = env("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### نتيجة الإشعار التجريبي\n\n" + "\n".join("- " + line for line in lines) + "\n")
    return 0 if not delivery_problem(result) else 1


if __name__ == "__main__":  # python notify.py  -> sends a test message on every configured channel
    outcome = send_all("اختبار رادار السيارات", "✅ رسالة اختبار من رادار سيارات الإمارات.",
                       "✅ رسالة اختبار من رادار سيارات الإمارات.")
    print(json.dumps(outcome, ensure_ascii=False))
    raise SystemExit(report_test(outcome))
