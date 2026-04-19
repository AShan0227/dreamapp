"""One-time password (OTP) for phone login + email password reset.

In-memory store keyed by `(channel, recipient)`. Sufficient for
single-process dev; production should use Redis with TTL keys.

Dispatch goes through services.notifier; SMS provider noop is at
DREAM_SMS_PROVIDER, email at DREAM_EMAIL_PROVIDER.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from services.notifier import EmailNotifier, SmsNotifier

log = logging.getLogger("dreamapp.otp")

Channel = Literal["sms", "email"]

OTP_TTL_SECONDS = 5 * 60          # OTP valid for 5 minutes
RESEND_COOLDOWN_SECONDS = 60      # Don't allow re-sending sooner than 60s
MAX_ATTEMPTS = 5                  # Wrong codes before lockout
LOCKOUT_SECONDS = 15 * 60         # Lockout duration after too many fails


@dataclass
class _OtpRecord:
    code: str
    issued_at: float
    attempts: int = 0
    locked_until: float = 0.0


_store: dict[tuple[str, str], _OtpRecord] = {}
_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


def _generate_code() -> str:
    # 6 digits, zero-padded; use cryptographically random source
    return f"{secrets.randbelow(1_000_000):06d}"


async def _dispatch(channel: Channel, recipient: str, code: str, purpose: str) -> bool:
    if channel == "sms":
        return await SmsNotifier.send(
            recipient,
            f"DreamApp verification code: {code}. Expires in 5 min.",
        )
    if channel == "email":
        return await EmailNotifier.send(
            recipient,
            subject=f"DreamApp {purpose} code",
            body=f"Your verification code is {code}. It expires in 5 minutes.",
        )
    return False


async def request_otp(
    recipient: str,
    channel: Channel = "sms",
    purpose: str = "login",
) -> dict:
    """Generate + dispatch a fresh OTP. Returns {sent, expires_in?, retry_after?, locked_for?}.

    `purpose` is informational (used in email subject); the same code can
    be used for either login or password-reset.
    """
    if not recipient:
        raise ValueError("recipient required")
    key = (channel, recipient)
    async with _lock:
        rec = _store.get(key)
        now = _now()
        if rec and rec.locked_until > now:
            return {"sent": False, "locked_for": int(rec.locked_until - now)}
        if rec and (now - rec.issued_at) < RESEND_COOLDOWN_SECONDS:
            return {
                "sent": False,
                "retry_after": int(RESEND_COOLDOWN_SECONDS - (now - rec.issued_at)),
            }
        code = _generate_code()
        _store[key] = _OtpRecord(code=code, issued_at=now, attempts=0)
    await _dispatch(channel, recipient, code, purpose)
    return {"sent": True, "expires_in": OTP_TTL_SECONDS}


async def verify_otp(
    recipient: str, code: str, channel: Channel = "sms"
) -> bool:
    """Returns True if code matches and is unexpired. Consumes on success."""
    if not recipient or not code:
        return False
    key = (channel, recipient)
    async with _lock:
        rec = _store.get(key)
        now = _now()
        if not rec:
            return False
        if rec.locked_until > now:
            return False
        if (now - rec.issued_at) > OTP_TTL_SECONDS:
            _store.pop(key, None)
            return False
        if not secrets.compare_digest(rec.code, code):
            rec.attempts += 1
            if rec.attempts >= MAX_ATTEMPTS:
                rec.locked_until = now + LOCKOUT_SECONDS
            return False
        _store.pop(key, None)
        return True
