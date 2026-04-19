"""Pluggable notifiers (email + SMS).

Right now both are noops that log the message. Replace `_send` with a
real provider call when ready (Mailgun/SES for email, Aliyun/Twilio for
SMS). Both interfaces look identical so swapping providers is one edit.

The OTP service pulls from here so phone OTP and email password-reset
codes share the same dispatch surface.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("dreamapp.notifier")


class EmailNotifier:
    """Sends transactional email.

    Provider switching via DREAM_EMAIL_PROVIDER:
      - "" or "noop"   → log only (default)
      - "smtp"         → generic SMTP (requires DREAM_EMAIL_SMTP_*)
      - "mailgun"      → Mailgun HTTPS API (requires DREAM_EMAIL_MAILGUN_*)
    """

    @staticmethod
    async def send(to: str, subject: str, body: str) -> bool:
        provider = os.getenv("DREAM_EMAIL_PROVIDER", "").lower()
        if provider == "" or provider == "noop":
            log.warning(
                "[EMAIL noop] to=%s subject=%s body=%s — wire DREAM_EMAIL_PROVIDER for production",
                to, subject, body,
            )
            return True
        if provider == "smtp":
            return await _send_email_smtp(to, subject, body)
        if provider == "mailgun":
            return await _send_email_mailgun(to, subject, body)
        log.error("Unknown DREAM_EMAIL_PROVIDER=%s — falling back to noop", provider)
        return False


async def _send_email_smtp(to: str, subject: str, body: str) -> bool:
    """Generic SMTP. Required env: HOST, PORT, USER, PASSWORD, FROM."""
    import asyncio
    import smtplib
    from email.message import EmailMessage

    host = os.getenv("DREAM_EMAIL_SMTP_HOST", "")
    port = int(os.getenv("DREAM_EMAIL_SMTP_PORT", "587"))
    user = os.getenv("DREAM_EMAIL_SMTP_USER", "")
    pw = os.getenv("DREAM_EMAIL_SMTP_PASSWORD", "")
    sender = os.getenv("DREAM_EMAIL_SMTP_FROM", user)

    if not all([host, user, pw, sender]):
        log.error("SMTP misconfigured — missing HOST/USER/PASSWORD/FROM")
        return False

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    def _send_blocking():
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)

    try:
        await asyncio.to_thread(_send_blocking)
        return True
    except Exception as e:
        log.exception("SMTP send failed: %s", e)
        return False


async def _send_email_mailgun(to: str, subject: str, body: str) -> bool:
    """Mailgun HTTPS API. Required env: API_KEY, DOMAIN, FROM."""
    import httpx

    api_key = os.getenv("DREAM_EMAIL_MAILGUN_API_KEY", "")
    domain = os.getenv("DREAM_EMAIL_MAILGUN_DOMAIN", "")
    sender = os.getenv("DREAM_EMAIL_MAILGUN_FROM", f"DreamApp <noreply@{domain}>")
    region = os.getenv("DREAM_EMAIL_MAILGUN_REGION", "us")  # "us" or "eu"

    if not api_key or not domain:
        log.error("Mailgun misconfigured — missing API_KEY or DOMAIN")
        return False

    base = "https://api.eu.mailgun.net" if region == "eu" else "https://api.mailgun.net"
    url = f"{base}/v3/{domain}/messages"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                auth=("api", api_key),
                data={"from": sender, "to": to, "subject": subject, "text": body},
            )
            if resp.status_code == 200:
                return True
            log.error("Mailgun rejected: %s %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        log.exception("Mailgun request failed: %s", e)
        return False


class SmsNotifier:
    """Sends SMS. Default is a noop logger. Used by services/otp.py.

    Provider switching via DREAM_SMS_PROVIDER:
      - "" or "noop"  → log only (default)
      - "aliyun"     → Aliyun SMS (requires DREAM_SMS_ALIYUN_*)
      - "twilio"     → reserved
    """

    @staticmethod
    async def send(phone: str, body: str) -> bool:
        provider = os.getenv("DREAM_SMS_PROVIDER", "").lower()
        if provider == "" or provider == "noop":
            log.warning(
                "[SMS noop] phone=%s body=%s — wire DREAM_SMS_PROVIDER for production",
                phone, body,
            )
            return True
        if provider == "aliyun":
            return await _send_aliyun(phone, body)
        log.error("Unknown DREAM_SMS_PROVIDER=%s — falling back to noop", provider)
        return False


async def _send_aliyun(phone: str, body: str) -> bool:
    """Aliyun SMS via SendSms API.

    Required env:
      DREAM_SMS_ALIYUN_ACCESS_KEY      access key id
      DREAM_SMS_ALIYUN_ACCESS_SECRET   access key secret
      DREAM_SMS_ALIYUN_SIGN_NAME       e.g. "DreamApp"
      DREAM_SMS_ALIYUN_TEMPLATE_CODE   e.g. "SMS_xxx"
      DREAM_SMS_ALIYUN_REGION          default "cn-hangzhou"

    OTP `body` is parsed for the 6-digit code so we can fill the
    Aliyun template parameter (Aliyun does not allow free-form bodies).
    """
    import re
    import json
    import base64
    import hmac
    import hashlib
    import urllib.parse
    import uuid
    import time as _time

    ak = os.getenv("DREAM_SMS_ALIYUN_ACCESS_KEY", "")
    sk = os.getenv("DREAM_SMS_ALIYUN_ACCESS_SECRET", "")
    sign_name = os.getenv("DREAM_SMS_ALIYUN_SIGN_NAME", "")
    template = os.getenv("DREAM_SMS_ALIYUN_TEMPLATE_CODE", "")
    region = os.getenv("DREAM_SMS_ALIYUN_REGION", "cn-hangzhou")

    if not all([ak, sk, sign_name, template]):
        log.error("Aliyun SMS misconfigured — missing one of access_key/secret/sign_name/template_code")
        return False

    code_match = re.search(r"\b(\d{4,8})\b", body)
    code = code_match.group(1) if code_match else ""
    if not code:
        log.error("Aliyun SMS: could not extract OTP code from body")
        return False

    # Build canonical query for Aliyun SignatureMethod=HMAC-SHA1, v3 RPC
    params = {
        "AccessKeyId": ak,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": region,
        "SignName": sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": template,
        "TemplateParam": json.dumps({"code": code}),
        "Timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "Version": "2017-05-25",
    }
    sorted_params = sorted(params.items())
    canonicalized = "&".join(
        f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(v, safe='~')}"
        for k, v in sorted_params
    )
    string_to_sign = f"GET&{urllib.parse.quote('/', safe='')}&{urllib.parse.quote(canonicalized, safe='')}"
    signature = base64.b64encode(
        hmac.new((sk + "&").encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    params["Signature"] = signature
    url = f"https://dysmsapi.aliyuncs.com/?{urllib.parse.urlencode(params)}"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            if data.get("Code") == "OK":
                return True
            log.error("Aliyun SMS rejected: code=%s msg=%s", data.get("Code"), data.get("Message"))
            return False
    except Exception as e:
        log.exception("Aliyun SMS request failed: %s", e)
        return False
