"""Payment webhook signature verification + replay protection.

These are UNIT tests (pure Python, no HTTP) so they can run in CI without
Postgres or network. Real integration tests against live provider sandboxes
are out-of-scope.

Covers the three signature verifiers implemented in services/payments.py:
  - WeChat Pay v3 (RSA-SHA256 over timestamp.nonce.body + AES-GCM decrypt)
  - Alipay RSA2 (RSA-SHA256 over sorted params, excluding sign/sign_type)
  - Stripe (HMAC-SHA256 over t.body, v1 signature, timestamp tolerance)

A failure in ANY of these is the #1 audit-identified CRITICAL bug:
attackers can forge "payment completed" without a private key. Test
each case:
  1. Bad signature → rejected (None)
  2. Expired timestamp → rejected
  3. Good signature at current time → accepted with out_trade_no

Run:
    pytest tests/test_payment_webhooks.py -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.payments import (  # noqa: E402
    verify_wechat_webhook,
    verify_alipay_webhook,
    verify_stripe_webhook,
    WEBHOOK_TIMESTAMP_TOLERANCE_SEC,
)


# ---------- Stripe --------------------------------------------------------

def _stripe_sign(secret: str, timestamp: str, body: bytes) -> str:
    signed = f"{timestamp}.{body.decode('utf-8')}".encode()
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def test_stripe_rejects_without_secret_env(monkeypatch):
    """If no secret configured, webhook verification ALWAYS fails —
    fail-closed is correct for security-sensitive code."""
    monkeypatch.delenv("DREAM_STRIPE_WEBHOOK_SECRET", raising=False)
    result = verify_stripe_webhook({"stripe-signature": "t=1,v1=abc"}, b'{"type":"x"}')
    assert result is None


def test_stripe_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("DREAM_STRIPE_WEBHOOK_SECRET", "whsec_test123")
    ts = str(int(time.time()))
    bad_sig = "deadbeef" * 8
    assert verify_stripe_webhook(
        {"stripe-signature": f"t={ts},v1={bad_sig}"},
        b'{"type":"checkout.session.completed"}',
    ) is None


def test_stripe_rejects_expired_timestamp(monkeypatch):
    secret = "whsec_test123"
    monkeypatch.setenv("DREAM_STRIPE_WEBHOOK_SECRET", secret)
    old_ts = str(int(time.time()) - WEBHOOK_TIMESTAMP_TOLERANCE_SEC - 60)
    body = b'{"type":"checkout.session.completed","id":"evt_1"}'
    sig = _stripe_sign(secret, old_ts, body)
    assert verify_stripe_webhook(
        {"stripe-signature": f"t={old_ts},v1={sig}"}, body
    ) is None


def test_stripe_accepts_valid_completed_session(monkeypatch):
    secret = "whsec_test123"
    monkeypatch.setenv("DREAM_STRIPE_WEBHOOK_SECRET", secret)
    ts = str(int(time.time()))
    body = json.dumps({
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "payment_status": "paid",
                "client_reference_id": "DA1234567890abcd",
                "payment_intent": "pi_xyz",
            }
        },
    }).encode()
    sig = _stripe_sign(secret, ts, body)
    result = verify_stripe_webhook(
        {"stripe-signature": f"t={ts},v1={sig}"}, body
    )
    assert result is not None
    assert result["out_trade_no"] == "DA1234567890abcd"
    assert result["transaction_id"] == "pi_xyz"
    assert result["event_id"] == "evt_1"


def test_stripe_rejects_unpaid_checkout(monkeypatch):
    """checkout.session.completed but payment_status != 'paid' → drop."""
    secret = "whsec_test123"
    monkeypatch.setenv("DREAM_STRIPE_WEBHOOK_SECRET", secret)
    ts = str(int(time.time()))
    body = json.dumps({
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {"payment_status": "unpaid", "client_reference_id": "X"}},
    }).encode()
    sig = _stripe_sign(secret, ts, body)
    assert verify_stripe_webhook(
        {"stripe-signature": f"t={ts},v1={sig}"}, body
    ) is None


# ---------- Alipay --------------------------------------------------------

def test_alipay_rejects_without_pubkey_env(monkeypatch):
    monkeypatch.delenv("DREAM_ALIPAY_PLATFORM_PUBLIC_KEY", raising=False)
    assert verify_alipay_webhook({
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": "X",
        "sign": "abc",
    }) is None


def test_alipay_rejects_unsuccessful_trade_status(monkeypatch):
    """Only TRADE_SUCCESS / TRADE_FINISHED should pass."""
    monkeypatch.setenv("DREAM_ALIPAY_PLATFORM_PUBLIC_KEY", "dummy")
    for status in ("WAIT_BUYER_PAY", "TRADE_CLOSED", ""):
        assert verify_alipay_webhook({
            "trade_status": status,
            "out_trade_no": "X",
            "sign": "abc",
        }) is None


def test_alipay_rejects_missing_sign(monkeypatch):
    monkeypatch.setenv("DREAM_ALIPAY_PLATFORM_PUBLIC_KEY", "dummy")
    assert verify_alipay_webhook({
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": "X",
    }) is None


# ---------- WeChat --------------------------------------------------------

def test_wechat_rejects_missing_headers(monkeypatch):
    monkeypatch.delenv("DREAM_WECHAT_PLATFORM_CERT", raising=False)
    assert verify_wechat_webhook({}, b'{}') is None


def test_wechat_rejects_expired_timestamp(monkeypatch):
    monkeypatch.setenv("DREAM_WECHAT_PLATFORM_CERT", "dummy_cert")
    monkeypatch.setenv("DREAM_WECHAT_API_KEY", "dummy_apiv3_key_____")
    old_ts = str(int(time.time()) - WEBHOOK_TIMESTAMP_TOLERANCE_SEC - 60)
    headers = {
        "wechatpay-timestamp": old_ts,
        "wechatpay-nonce": "abc",
        "wechatpay-signature": base64.b64encode(b"sig").decode(),
        "wechatpay-serial": "xx",
    }
    assert verify_wechat_webhook(headers, b'{"resource":{}}') is None


def test_wechat_rejects_bad_signature(monkeypatch):
    """Invalid signature (no valid cert) → None. Fail-closed."""
    monkeypatch.setenv("DREAM_WECHAT_PLATFORM_CERT", "-----BEGIN CERTIFICATE-----\nbad\n-----END CERTIFICATE-----")
    monkeypatch.setenv("DREAM_WECHAT_API_KEY", "dummy_apiv3_key_____")
    ts = str(int(time.time()))
    headers = {
        "wechatpay-timestamp": ts,
        "wechatpay-nonce": "abc",
        "wechatpay-signature": base64.b64encode(b"sig").decode(),
        "wechatpay-serial": "xx",
    }
    assert verify_wechat_webhook(headers, b'{"resource":{}}') is None
