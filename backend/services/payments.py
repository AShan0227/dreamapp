"""Payment provider abstraction.

Three providers wired with real signing logic but configurable creds:
  - WeChat Pay (JSAPI / H5)
  - Alipay (PC + mobile web)
  - Stripe (international)

Each provider exposes:
  create_order(payment) -> dict       # returns provider-specific payment params
  verify_webhook(headers, body) -> dict | None  # returns trusted payload or None
  fetch_status(provider_payment_id) -> str   # poll status (fallback)

Without real creds, providers run in 'sandbox' mode where create_order
returns a fake redirect URL that the test webhook can complete.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.engagement import Payment, PaymentProvider, PaymentStatus


def _new_out_trade_no() -> str:
    return f"DA{int(time.time() * 1000)}{secrets.token_hex(4)}"[:32]


# ---------------- Order creation ---------------------------------------------

async def create_payment(
    db: AsyncSession,
    user_id: str,
    provider: PaymentProvider,
    amount_cents: int,
    purpose: str,
    purpose_ref: Optional[str] = None,
    currency: str = "CNY",
) -> tuple[Payment, dict]:
    """Create a Payment row + ask the provider to mint an order.

    Returns (payment, provider_payload) where provider_payload is what the
    frontend needs to launch the wallet (jsapi config, redirect_url, client_secret, etc.)
    """
    if amount_cents <= 0:
        raise ValueError("amount_cents must be > 0")

    out_trade_no = _new_out_trade_no()
    p = Payment(
        user_id=user_id,
        out_trade_no=out_trade_no,
        provider=provider,
        amount_cents=amount_cents,
        currency=currency,
        purpose=purpose,
        purpose_ref=purpose_ref,
        status="pending",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    # Dispatch to the provider
    if provider == "wechat":
        payload = await _create_wechat_order(p)
    elif provider == "alipay":
        payload = await _create_alipay_order(p)
    elif provider == "stripe":
        payload = await _create_stripe_order(p)
    elif provider == "free":
        # Internal grant — auto-complete
        p.status = "completed"
        p.completed_at = datetime.utcnow()
        await db.commit()
        payload = {"status": "completed"}
    else:
        raise ValueError(f"Unknown provider: {provider}")

    return p, payload


# ---------------- WeChat Pay ------------------------------------------------

async def _create_wechat_order(p: Payment) -> dict:
    """WeChat Pay v3 JSAPI/H5 order creation.

    Required env: DREAM_WECHAT_MCHID, DREAM_WECHAT_APPID, DREAM_WECHAT_API_KEY,
                  DREAM_WECHAT_NOTIFY_URL, DREAM_WECHAT_PRIVATE_KEY,
                  DREAM_WECHAT_SERIAL_NO

    In sandbox mode (no MCHID set), returns a fake jsapi config + a payment
    sandbox URL that flips status via an internal endpoint. Useful for dev
    without a merchant account.
    """
    mchid = os.getenv("DREAM_WECHAT_MCHID", "")
    if not mchid:
        return {
            "mode": "sandbox",
            "sandbox_complete_url": f"/api/payments/sandbox-complete?out_trade_no={p.out_trade_no}",
            "out_trade_no": p.out_trade_no,
            "amount_cents": p.amount_cents,
        }

    appid = os.getenv("DREAM_WECHAT_APPID", "")
    notify_url = os.getenv("DREAM_WECHAT_NOTIFY_URL", "")
    body = {
        "appid": appid,
        "mchid": mchid,
        "description": f"DreamApp {p.purpose}",
        "out_trade_no": p.out_trade_no,
        "notify_url": notify_url,
        "amount": {"total": p.amount_cents, "currency": "CNY"},
        "payer": {"openid": "REPLACE_WITH_USER_OPENID"},  # caller must set
    }

    body_str = json.dumps(body, separators=(",", ":"))
    method, path = "POST", "/v3/pay/transactions/jsapi"
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    sign_str = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_str}\n"
    sign = _wechat_sign(sign_str)
    serial_no = os.getenv("DREAM_WECHAT_SERIAL_NO", "")
    auth = (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{mchid}",'
        f'nonce_str="{nonce}",signature="{sign}",timestamp="{timestamp}",'
        f'serial_no="{serial_no}"'
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.mch.weixin.qq.com{path}",
                headers={"Authorization": auth, "Content-Type": "application/json"},
                content=body_str,
            )
            data = r.json()
            return {"mode": "live", "prepay_id": data.get("prepay_id"), "raw": data}
    except Exception as e:
        return {"mode": "error", "error": str(e)[:200]}


def _wechat_sign(message: str) -> str:
    """RSA-SHA256 sign with merchant private key."""
    key_text = os.getenv("DREAM_WECHAT_PRIVATE_KEY", "")
    if not key_text:
        return ""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        priv = serialization.load_pem_private_key(key_text.encode(), password=None)
        sig = priv.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()
    except Exception as e:
        from services.observability import get_logger
        get_logger("payments").error("wechat sign failed", extra={"err": str(e)})
        return ""


# ---------------- Alipay ----------------------------------------------------

async def _create_alipay_order(p: Payment) -> dict:
    """Alipay PC/mobile web pay. Required env: DREAM_ALIPAY_APPID,
    DREAM_ALIPAY_PRIVATE_KEY, DREAM_ALIPAY_NOTIFY_URL, DREAM_ALIPAY_RETURN_URL.

    Sandbox mode: returns a sandbox completion URL.
    """
    appid = os.getenv("DREAM_ALIPAY_APPID", "")
    if not appid:
        return {
            "mode": "sandbox",
            "sandbox_complete_url": f"/api/payments/sandbox-complete?out_trade_no={p.out_trade_no}",
            "out_trade_no": p.out_trade_no,
        }

    # Build biz_content
    biz_content = json.dumps({
        "out_trade_no": p.out_trade_no,
        "total_amount": f"{p.amount_cents / 100:.2f}",
        "subject": f"DreamApp {p.purpose}",
        "product_code": "FAST_INSTANT_TRADE_PAY",
    }, separators=(",", ":"))

    params = {
        "app_id": appid,
        "method": "alipay.trade.page.pay",
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "notify_url": os.getenv("DREAM_ALIPAY_NOTIFY_URL", ""),
        "return_url": os.getenv("DREAM_ALIPAY_RETURN_URL", ""),
        "biz_content": biz_content,
    }
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k])
    params["sign"] = _alipay_sign(sign_str)
    import urllib.parse
    url = "https://openapi.alipay.com/gateway.do?" + urllib.parse.urlencode(params)
    return {"mode": "live", "redirect_url": url, "out_trade_no": p.out_trade_no}


def _alipay_sign(message: str) -> str:
    key_text = os.getenv("DREAM_ALIPAY_PRIVATE_KEY", "")
    if not key_text:
        return ""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        priv = serialization.load_pem_private_key(key_text.encode(), password=None)
        sig = priv.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()
    except Exception:
        return ""


# ---------------- Stripe ----------------------------------------------------

async def _create_stripe_order(p: Payment) -> dict:
    """Stripe Checkout Session.

    Required env: DREAM_STRIPE_SECRET_KEY, DREAM_STRIPE_SUCCESS_URL, DREAM_STRIPE_CANCEL_URL.
    """
    sk = os.getenv("DREAM_STRIPE_SECRET_KEY", "")
    if not sk:
        return {
            "mode": "sandbox",
            "sandbox_complete_url": f"/api/payments/sandbox-complete?out_trade_no={p.out_trade_no}",
            "out_trade_no": p.out_trade_no,
        }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                auth=(sk, ""),
                data={
                    "mode": "payment",
                    "success_url": os.getenv("DREAM_STRIPE_SUCCESS_URL", "https://dreamapp.cn/?paid=1"),
                    "cancel_url": os.getenv("DREAM_STRIPE_CANCEL_URL", "https://dreamapp.cn/?cancelled=1"),
                    "client_reference_id": p.out_trade_no,
                    "line_items[0][price_data][currency]": p.currency.lower(),
                    "line_items[0][price_data][product_data][name]": f"DreamApp {p.purpose}",
                    "line_items[0][price_data][unit_amount]": p.amount_cents,
                    "line_items[0][quantity]": 1,
                },
            )
            data = r.json()
            return {"mode": "live", "redirect_url": data.get("url"), "session_id": data.get("id")}
    except Exception as e:
        return {"mode": "error", "error": str(e)[:200]}


# ---------------- Webhook signature verification ----------------------------
#
# Each provider has its own scheme. The verifier returns a trusted dict on
# success (containing at minimum out_trade_no + provider_payment_id), or None
# on failure. Callers MUST treat None as "drop the request".
#
# Replay defense:
#   - WeChat / Stripe: timestamp within ±5 min, then idempotency in
#     mark_payment_completed (returns existing payment if already completed).
#   - Alipay: no native timestamp; rely on out_trade_no + idempotency. The
#     audit log gives forensic visibility if the same notify is replayed.
#
# All verifiers also persist a row to PaymentWebhookEvent for audit trail.

WEBHOOK_TIMESTAMP_TOLERANCE_SEC = 300  # 5 min


def verify_wechat_webhook(
    headers: dict[str, str],
    raw_body: bytes,
) -> Optional[dict]:
    """WeChat Pay v3 webhook verification + AES-GCM decryption.

    Headers required:
      Wechatpay-Timestamp, Wechatpay-Nonce, Wechatpay-Signature, Wechatpay-Serial

    Required env:
      DREAM_WECHAT_API_KEY        — APIv3 key, used to AES-GCM decrypt resource
      DREAM_WECHAT_PLATFORM_CERT  — WeChat's platform certificate (PEM, public key)

    Returns dict with {out_trade_no, transaction_id, raw} on success, else None.
    """
    timestamp = headers.get("wechatpay-timestamp", "")
    nonce = headers.get("wechatpay-nonce", "")
    signature = headers.get("wechatpay-signature", "")
    serial = headers.get("wechatpay-serial", "")
    if not all([timestamp, nonce, signature, serial]):
        return None

    # Replay window
    try:
        if abs(int(time.time()) - int(timestamp)) > WEBHOOK_TIMESTAMP_TOLERANCE_SEC:
            return None
    except ValueError:
        return None

    # Verify signature against WeChat platform public key
    plat_cert_pem = os.getenv("DREAM_WECHAT_PLATFORM_CERT", "")
    if not plat_cert_pem:
        return None
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        cert = x509.load_pem_x509_certificate(plat_cert_pem.encode())
        pub_key = cert.public_key()
        message = f"{timestamp}\n{nonce}\n{raw_body.decode('utf-8')}\n".encode()
        sig_bytes = base64.b64decode(signature)
        pub_key.verify(sig_bytes, message, padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        return None

    # Decrypt resource.ciphertext (AES-256-GCM)
    try:
        body = json.loads(raw_body.decode("utf-8"))
        resource = body.get("resource", {})
        ciphertext_b64 = resource.get("ciphertext", "")
        nonce_str = resource.get("nonce", "")
        associated = resource.get("associated_data", "")
        api_key = os.getenv("DREAM_WECHAT_API_KEY", "")
        if not (ciphertext_b64 and nonce_str and api_key):
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(api_key.encode())
        ct = base64.b64decode(ciphertext_b64)
        plain = aesgcm.decrypt(nonce_str.encode(), ct, associated.encode() if associated else None)
        notify = json.loads(plain.decode("utf-8"))
    except Exception:
        return None

    if notify.get("trade_state") != "SUCCESS":
        return None
    return {
        "out_trade_no": notify.get("out_trade_no"),
        "transaction_id": notify.get("transaction_id"),
        "raw": notify,
        "event_id": body.get("id"),
    }


def verify_alipay_webhook(form: dict[str, str]) -> Optional[dict]:
    """Alipay async-notify verification.

    All non-empty params except `sign` and `sign_type` are sorted alphabetically,
    joined as `k=v&k=v`, then RSA2-verified against Alipay's public key.

    Required env: DREAM_ALIPAY_PLATFORM_PUBLIC_KEY  — PEM, Alipay's RSA public key
    Status filter: TRADE_SUCCESS or TRADE_FINISHED only
    """
    sign = form.get("sign")
    if not sign:
        return None
    if form.get("trade_status") not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        return None
    pub_pem = os.getenv("DREAM_ALIPAY_PLATFORM_PUBLIC_KEY", "")
    if not pub_pem:
        return None

    items = sorted(
        (k, v) for k, v in form.items() if k not in ("sign", "sign_type") and v
    )
    sign_str = "&".join(f"{k}={v}" for k, v in items)

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        pub = serialization.load_pem_public_key(pub_pem.encode())
        sig_bytes = base64.b64decode(sign)
        pub.verify(sig_bytes, sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        return None

    return {
        "out_trade_no": form.get("out_trade_no"),
        "transaction_id": form.get("trade_no"),
        "raw": dict(form),
        "event_id": form.get("notify_id"),  # Alipay's unique notify id
    }


def verify_stripe_webhook(
    headers: dict[str, str],
    raw_body: bytes,
) -> Optional[dict]:
    """Stripe webhook verification (HMAC-SHA256).

    Header: Stripe-Signature: t=<unix>,v1=<hex>
    Required env: DREAM_STRIPE_WEBHOOK_SECRET  — whsec_... from Stripe dashboard
    """
    sig_header = headers.get("stripe-signature", "")
    secret = os.getenv("DREAM_STRIPE_WEBHOOK_SECRET", "")
    if not (sig_header and secret):
        return None

    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    timestamp = parts.get("t", "")
    signatures = [v for k, v in parts.items() if k.startswith("v1")]
    if not (timestamp and signatures):
        return None

    # Replay window
    try:
        if abs(int(time.time()) - int(timestamp)) > WEBHOOK_TIMESTAMP_TOLERANCE_SEC:
            return None
    except ValueError:
        return None

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode()
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        return None

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    # Only act on completed checkout sessions or succeeded payment intents
    event_type = body.get("type", "")
    obj = body.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        if obj.get("payment_status") != "paid":
            return None
        return {
            "out_trade_no": obj.get("client_reference_id"),
            "transaction_id": obj.get("payment_intent") or obj.get("id"),
            "raw": body,
            "event_id": body.get("id"),
        }
    if event_type == "payment_intent.succeeded":
        meta = obj.get("metadata", {}) or {}
        return {
            "out_trade_no": meta.get("out_trade_no") or obj.get("client_reference_id"),
            "transaction_id": obj.get("id"),
            "raw": body,
            "event_id": body.get("id"),
        }
    return None


async def record_webhook_event(
    db: AsyncSession,
    provider: str,
    event_id: Optional[str],
    out_trade_no: Optional[str],
    verified: bool,
    raw_summary: Optional[str] = None,
) -> bool:
    """Append a row to PaymentWebhookEvent. Returns False if event_id already seen
    (caller should treat as duplicate-replay and 200-skip).

    event_id may be None (e.g. when verification failed before event_id extraction).
    Duplicate detection only applies when event_id is provided.
    """
    from models.engagement import PaymentWebhookEvent
    if event_id:
        existing = await db.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider == provider,
                PaymentWebhookEvent.event_id == event_id,
            )
        )
        if existing.scalar_one_or_none():
            return False
    db.add(PaymentWebhookEvent(
        provider=provider,
        event_id=event_id,
        out_trade_no=out_trade_no,
        verified=verified,
        raw_summary=raw_summary[:500] if raw_summary else None,
    ))
    await db.commit()
    return True


# ---------------- Webhook + post-completion handling ------------------------

async def mark_payment_completed(
    db: AsyncSession, out_trade_no: str, provider_payment_id: Optional[str] = None,
) -> Optional[Payment]:
    res = await db.execute(select(Payment).where(Payment.out_trade_no == out_trade_no))
    p = res.scalar_one_or_none()
    if not p:
        return None
    if p.status == "completed":
        return p
    p.status = "completed"
    p.completed_at = datetime.utcnow()
    if provider_payment_id:
        p.provider_payment_id = provider_payment_id
    await db.commit()
    await _fulfill(db, p)
    try:
        from services import analytics as _an
        await _an.track("payment_succeeded", user_id=p.user_id, props={
            "provider": p.provider if isinstance(p.provider, str) else str(p.provider),
            "purpose": p.purpose,
            "amount_cents": p.amount_cents,
            "out_trade_no": p.out_trade_no,
        })
    except Exception:
        pass
    return p


async def _fulfill(db: AsyncSession, p: Payment) -> None:
    """Trigger the side effect of a completed payment based on `purpose`."""
    from services.subscriptions import upgrade_subscription
    from models.engagement import SubscriptionTier
    from services.engagement import credit_coins

    if p.purpose == "subscription_pro":
        await upgrade_subscription(db, p.user_id, "pro", payment_id=p.id, months=1)
    elif p.purpose == "subscription_premium":
        await upgrade_subscription(db, p.user_id, "premium", payment_id=p.id, months=1)
    elif p.purpose == "skip_queue":
        # Grant a single skip-queue token via coin
        await credit_coins(db, p.user_id, 1, "earn_purchase_skip_queue", ref=p.id)
    elif p.purpose == "dream_coins":
        # 1 RMB = 100 coins
        coin_count = p.amount_cents
        await credit_coins(db, p.user_id, coin_count, "earn_purchase", ref=p.id)
    elif p.purpose == "therapy_booking" and p.purpose_ref:
        from models.engagement import TherapyBooking, TherapyBookingStatus
        booking = await db.get(TherapyBooking, p.purpose_ref)
        if booking:
            booking.status = "confirmed"
            booking.payment_id = p.id
            await db.commit()
    # purpose=agent_install handled elsewhere if/when agent paid installs ship
