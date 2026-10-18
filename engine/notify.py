"""Telegram, WhatsApp (CallMeBot) and email. A channel is used only when its secrets are set.

Secrets (GitHub → Settings → Secrets and variables → Actions):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  CALLMEBOT_PHONE (e.g. +9715xxxxxxxx), CALLMEBOT_APIKEY
  SMTP_USER (Gmail address), SMTP_PASSWORD (Gmail app password), MAIL_TO (optional, defaults to SMTP_USER)
"""

import json
import os
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
        if pdf and os.path.exists(pdf):
            boundary = uuid.uuid4().hex
            with open(pdf, "rb") as f:
                blob = f.read()
            # One document message, with its summary in the caption; details are in the PDF.
            caption = text[:850] + ("\nالتفاصيل الكاملة داخل التقرير المرفق." if len(text) > 850 else "")
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{pdf_name}\"\r\n"
                    f"Content-Type: application/pdf\r\n\r\n").encode() + blob + f"\r\n--{boundary}--\r\n".encode()
            _post(base + "/sendDocument", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)
        else:
            caption = text if len(text) <= 3900 else text[:3400] + "\nالتفاصيل في لوحة الرادار."
            _post(base + "/sendMessage", urllib.parse.urlencode({"chat_id": chat, "text": caption, "disable_web_page_preview": "true"}).encode())
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
        q = urllib.parse.urlencode({"phone": phone, "text": part, "apikey": key})
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


def send_all(subject, full_text, short_text, pdf=None, pdf_name="report.pdf"):
    """Telegram and email get the full text + PDF; WhatsApp gets the short text."""
    # Exactly one configured destination per round: email can contain every offer inline.
    result = {"telegram": "غير مختار", "whatsapp": "غير مختار", "email": "غير مختار"}
    if env("SMTP_USER") and env("SMTP_PASSWORD"):
        result["email"] = email(subject, full_text, pdf, pdf_name)
    elif env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        result["telegram"] = telegram(full_text, pdf, pdf_name)
    elif env("CALLMEBOT_PHONE") and env("CALLMEBOT_APIKEY"):
        result["whatsapp"] = whatsapp(full_text)
    else:
        result = {k: "غير مفعّل" for k in result}
    return result



if __name__ == "__main__":  # python notify.py test  -> sends a test message on every configured channel
    print(json.dumps(send_all("اختبار رادار السيارات", "✅ رسالة اختبار من رادار سيارات الإمارات.",
                              "✅ رسالة اختبار من رادار سيارات الإمارات."), ensure_ascii=False))
