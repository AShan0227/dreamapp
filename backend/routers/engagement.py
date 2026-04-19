"""HTTP surface for Wave H engagement features.

Routes mounted under several path prefixes for clarity:
  /api/dreams/{id}/comments    + /reactions
  /api/follows/{user_id}
  /api/feed/following
  /api/picks/today
  /api/challenges
  /api/referrals
  /api/sleep
  /api/therapists + /api/bookings
  /api/payments
  /api/subscription
  /api/coins
  /api/share
  /api/api-keys
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.user import UserRecord
from models.engagement import (
    PaymentProvider, SubscriptionTier,
    TherapistProfile, TherapistVerificationStatus,
)
from services.auth import require_user, get_optional_user
from services import engagement as eng
from services import payments as pay
from services import subscriptions as subs
from services import therapists as ther
from services import api_keys as akeys
from services import share as share_svc


router = APIRouter(tags=["engagement"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# ---------------- Comments + reactions --------------------------------------

class CommentBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[str] = None


@router.post("/api/dreams/{dream_id}/comments")
async def post_comment(
    dream_id: str,
    body: CommentBody,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="account suspended")

    # Moderation gate — public surface
    from services import moderation as _mod
    result = _mod.moderate(body.body, surface="public")
    if result.is_blocked:
        raise HTTPException(status_code=451, detail={
            "blocked": True,
            "categories": result.categories,
            "message": "Comment blocked by content policy.",
        })

    try:
        c = await eng.add_comment(db, user.id, dream_id, body.body, body.parent_id)
    except (LookupError, ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Soft-flag comment: set warmth low + auto-hide if slur/nsfw detected
    if result.needs_review and result.categories:
        if "slur" in result.categories or "nsfw" in result.categories:
            c.is_hidden = True
            await db.commit()
    return {"id": c.id, "body": c.body, "warmth": c.warmth_score, "is_hidden": c.is_hidden, "auto_flagged": result.needs_review}


@router.get("/api/dreams/{dream_id}/comments")
async def list_comments(
    dream_id: str,
    user: Optional[UserRecord] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await eng.list_comments(db, dream_id, user.id if user else None)
    except (LookupError, PermissionError) as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 403, detail=str(e))


class ReactionBody(BaseModel):
    kind: str = Field(..., min_length=1, max_length=20)


@router.post("/api/dreams/{dream_id}/reactions")
async def toggle_reaction(
    dream_id: str,
    body: ReactionBody,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await eng.toggle_reaction(db, user.id, dream_id, body.kind)
    except (LookupError, ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/dreams/{dream_id}/reactions")
async def get_reactions(
    dream_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await eng.reaction_counts(db, dream_id)


# ---------------- Follow graph + Following feed -----------------------------

@router.post("/api/follows/{followee_id}")
async def follow(
    followee_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        added = await eng.follow_user(db, user.id, followee_id)
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"following": True, "added": added}


@router.delete("/api/follows/{followee_id}")
async def unfollow(
    followee_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await eng.unfollow_user(db, user.id, followee_id)
    return {"following": False, "removed": removed}


@router.get("/api/follows/counts")
async def my_follow_counts(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await eng.follow_counts(db, user.id)


@router.get("/api/feed/following")
async def following_feed(
    limit: int = 30,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await eng.following_feed(db, user.id, limit=limit)
    from services.video_url import serve_video_url
    return [
        {
            "id": d.id,
            "user_id": d.user_id,
            "title": d.title,
            "video_url": serve_video_url(d, public=True),
            "emotion_tags": d.emotion_tags or [],
            "symbol_tags": d.symbol_tags or [],
            "created_at": d.created_at.isoformat(),
        }
        for d in rows
    ]


# ---------------- Daily picks ----------------------------------------------

@router.get("/api/picks/today")
async def picks_today(db: AsyncSession = Depends(get_db)):
    return await eng.get_today_picks(db)


@router.post("/api/picks/refresh")
async def picks_refresh(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Force a re-pick. Anyone can trigger; idempotent for the day."""
    pick = await eng.auto_pick_today(db)
    if not pick:
        return {"pick": None, "reason": "No public dreams in last 24h"}
    return {"pick": {"dream_id": pick.dream_id, "reason": pick.pick_reason}}


# ---------------- Challenges -----------------------------------------------

@router.get("/api/challenges/")
async def list_challenges(db: AsyncSession = Depends(get_db)):
    rows = await eng.list_active_challenges(db)
    return [
        {
            "id": c.id,
            "keyword": c.keyword,
            "title": c.title,
            "prompt": c.prompt,
            "submission_count": c.submission_count,
            "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        }
        for c in rows
    ]


class ChallengeSubmissionRequest(BaseModel):
    challenge_id: str
    dream_id: str


@router.post("/api/challenges/submit")
async def submit_challenge(
    body: ChallengeSubmissionRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        s = await eng.submit_to_challenge(db, user.id, body.challenge_id, body.dream_id)
    except (LookupError, PermissionError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": s.id, "vote_count": s.vote_count}


@router.get("/api/challenges/{challenge_id}/leaderboard")
async def leaderboard(
    challenge_id: str, limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return await eng.challenge_leaderboard(db, challenge_id, limit=limit)


# ---------------- Referrals ------------------------------------------------

@router.get("/api/referrals/me")
async def my_referral_code(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    code = await eng.get_or_create_referral_code(db, user.id)
    return {"code": code.code, "use_count": code.use_count}


class RedeemBody(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)


@router.post("/api/referrals/redeem")
async def redeem(
    body: RedeemBody,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await eng.redeem_referral(db, user.id, body.code)
    except (LookupError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------- Sleep records --------------------------------------------

@router.post("/api/sleep/")
async def add_sleep(
    payload: dict,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rec = await eng.record_sleep(db, user.id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": rec.id, "night_of": rec.night_of.isoformat()}


@router.get("/api/sleep/")
async def list_sleep(
    days: int = 30,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await eng.list_sleep(db, user.id, days=days)


# ---------------- Therapist marketplace ------------------------------------

@router.get("/api/therapists/")
async def list_therapists(
    specialty: Optional[str] = None, language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    return await ther.list_therapists(db, specialty=specialty, language=language)


@router.get("/api/therapists/suggest")
async def suggest_therapists(
    limit: int = 5,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ther.suggest_for_user(db, user.id, limit=limit)


class BookingRequest(BaseModel):
    therapist_id: str
    scheduled_for: datetime
    duration_minutes: int = 50
    shared_dream_ids: list[str] = Field(default_factory=list)
    notes: str = ""


@router.post("/api/bookings/")
async def request_booking(
    body: BookingRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        bk = await ther.request_booking(
            db, user.id, body.therapist_id, body.scheduled_for,
            body.duration_minutes, body.shared_dream_ids, body.notes,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": bk.id,
        "status": bk.status.value if hasattr(bk.status, "value") else str(bk.status),
        "price_cents": bk.price_cents,
        "currency": bk.currency,
    }


@router.get("/api/bookings/")
async def list_bookings(
    as_therapist: bool = False,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ther.list_my_bookings(db, user.id, as_therapist=as_therapist)


# ---------------- Subscriptions + payments + coins -------------------------

@router.get("/api/subscription/me")
async def my_subscription(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await subs.get_entitlements(db, user.id)


@router.get("/api/subscription/plans")
async def list_plans():
    # tier is now a plain string key in PLAN_CATALOG (was SubscriptionTier enum)
    return [
        {"tier": tier, **{k: v for k, v in plan.items()}}
        for tier, plan in subs.PLAN_CATALOG.items()
    ]


class PurchaseRequest(BaseModel):
    purpose: str  # subscription_pro | subscription_premium | skip_queue | dream_coins | therapy_booking
    provider: str  # wechat | alipay | stripe | free
    purpose_ref: Optional[str] = None
    amount_cents: Optional[int] = None  # required for dream_coins, optional otherwise


# Centralized pricing table — single source of truth.
PRICE_CATALOG = {
    "subscription_pro": 2900,
    "subscription_premium": 9900,
    "skip_queue": 300,  # ¥3
    # dream_coins amount is dynamic — caller specifies
}


@router.post("/api/payments/create")
async def create_payment(
    body: PurchaseRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an order. Returns provider-specific launch params."""
    try:
        provider_enum = PaymentProvider(body.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")

    if body.purpose in PRICE_CATALOG:
        amount = PRICE_CATALOG[body.purpose]
    elif body.purpose == "dream_coins":
        if not body.amount_cents or body.amount_cents <= 0:
            raise HTTPException(status_code=400, detail="amount_cents required for dream_coins")
        amount = body.amount_cents
    elif body.purpose == "therapy_booking":
        if not body.purpose_ref:
            raise HTTPException(status_code=400, detail="purpose_ref (booking_id) required")
        from models.engagement import TherapyBooking
        bk = await db.get(TherapyBooking, body.purpose_ref)
        if not bk or bk.client_user_id != user.id:
            raise HTTPException(status_code=404, detail="Booking not found")
        amount = bk.price_cents
    else:
        raise HTTPException(status_code=400, detail=f"Unknown purpose: {body.purpose}")

    payment, payload = await pay.create_payment(
        db, user.id, provider_enum, amount, body.purpose, body.purpose_ref,
    )
    try:
        from services import analytics as _an
        await _an.track("payment_initiated", user_id=user.id, props={
            "provider": body.provider,
            "purpose": body.purpose,
            "amount_cents": amount,
            "out_trade_no": payment.out_trade_no,
        })
    except Exception:
        pass
    return {
        "payment_id": payment.id,
        "out_trade_no": payment.out_trade_no,
        "amount_cents": amount,
        "status": payment.status.value if hasattr(payment.status, "value") else str(payment.status),
        "provider_payload": payload,
    }


@router.post("/api/payments/sandbox-complete")
async def sandbox_complete(
    out_trade_no: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Dev-only: mark a sandbox-mode payment as completed.

    Production webhooks (WeChat/Alipay/Stripe) call separate endpoints.
    This is the local-dev path so you can test the full purchase flow
    without a real wallet.
    """
    p = await pay.mark_payment_completed(db, out_trade_no, provider_payment_id="sandbox")
    if not p:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"completed": True, "id": p.id}


# ---------------- Webhooks (signature-verified) -----------------------------
# Each handler:
#   1. Reads raw body + headers (Stripe/WeChat both sign over raw bytes)
#   2. Calls provider verifier — RETURNS None on bad sig, expired ts, replay
#   3. Records the webhook event (idempotency check by provider event_id)
#   4. Only on verified-fresh: marks payment completed
# Always returns the provider's expected ack body so they don't retry.

@router.post("/api/payments/webhook/wechat")
async def webhook_wechat(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    verified = pay.verify_wechat_webhook(headers, raw)
    if not verified:
        # WeChat-recommended response for failed verification: still 200 + FAIL
        # so they retry — but we log the attempt for forensic trail.
        await pay.record_webhook_event(
            db, "wechat", event_id=None, out_trade_no=None,
            verified=False, raw_summary=raw[:500].decode("utf-8", errors="replace"),
        )
        return {"code": "FAIL", "message": "verification failed"}

    fresh = await pay.record_webhook_event(
        db, "wechat",
        event_id=verified.get("event_id"),
        out_trade_no=verified.get("out_trade_no"),
        verified=True,
    )
    if not fresh:
        # Duplicate event id — already processed. WeChat will stop retrying.
        return {"code": "SUCCESS"}

    p = await pay.mark_payment_completed(
        db, verified["out_trade_no"],
        provider_payment_id=verified.get("transaction_id"),
    )
    return {"code": "SUCCESS" if p else "NOT_FOUND"}


@router.post("/api/payments/webhook/alipay")
async def webhook_alipay(request: Request, db: AsyncSession = Depends(get_db)):
    form_raw = await request.form()
    form = {k: str(v) for k, v in form_raw.items()}
    verified = pay.verify_alipay_webhook(form)
    if not verified:
        await pay.record_webhook_event(
            db, "alipay", event_id=form.get("notify_id"),
            out_trade_no=form.get("out_trade_no"),
            verified=False,
            raw_summary=str(form)[:500],
        )
        return "fail"

    fresh = await pay.record_webhook_event(
        db, "alipay",
        event_id=verified.get("event_id"),
        out_trade_no=verified.get("out_trade_no"),
        verified=True,
    )
    if not fresh:
        return "success"

    p = await pay.mark_payment_completed(
        db, verified["out_trade_no"],
        provider_payment_id=verified.get("transaction_id"),
    )
    return "success" if p else "fail"


@router.post("/api/payments/webhook/stripe")
async def webhook_stripe(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    verified = pay.verify_stripe_webhook(headers, raw)
    if not verified:
        await pay.record_webhook_event(
            db, "stripe", event_id=None, out_trade_no=None,
            verified=False, raw_summary=raw[:500].decode("utf-8", errors="replace"),
        )
        # Stripe expects 400 on bad signature so they don't retry indefinitely
        raise HTTPException(status_code=400, detail="signature verification failed")

    fresh = await pay.record_webhook_event(
        db, "stripe",
        event_id=verified.get("event_id"),
        out_trade_no=verified.get("out_trade_no"),
        verified=True,
    )
    if not fresh:
        return {"received": True, "duplicate": True}

    if not verified.get("out_trade_no"):
        return {"received": True, "fulfilled": False}
    p = await pay.mark_payment_completed(
        db, verified["out_trade_no"],
        provider_payment_id=verified.get("transaction_id"),
    )
    return {"received": True, "fulfilled": bool(p)}


@router.post("/api/subscription/cancel")
async def cancel_subscription(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    s = await subs.cancel_subscription(db, user.id)
    return {"status": s.status, "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None}


# ---------------- Coins -----------------------------------------------------

@router.get("/api/coins/balance")
async def coin_balance(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return {"balance": await eng.coin_balance(db, user.id)}


@router.get("/api/coins/history")
async def coin_history(
    limit: int = 50,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await eng.coin_history(db, user.id, limit=limit)


class GiftRequest(BaseModel):
    to_user_id: str
    amount: int = Field(..., gt=0, le=10000)
    note: Optional[str] = None


@router.post("/api/coins/gift")
async def gift_coins(
    body: GiftRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if body.to_user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot gift to yourself")
    target = await db.get(UserRecord, body.to_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Recipient not found")
    try:
        await eng.debit_coins(db, user.id, body.amount, "spend_gift", ref=body.to_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await eng.credit_coins(db, body.to_user_id, body.amount, "earn_gift", ref=user.id, note=body.note)
    return {"sent": body.amount, "to": body.to_user_id}


# ---------------- Share helpers --------------------------------------------

@router.get("/api/share/{dream_id}")
async def share_card(
    dream_id: str,
    user: Optional[UserRecord] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Build a share payload for native share sheets.

    Owners of Premium subscription get watermark-free download URL.
    """
    from services.video_url import serve_video_url
    d = await db.get(DreamRecord, dream_id)
    if not d or d.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Dream not found")
    is_owner = user is not None and d.user_id == user.id
    if not d.is_public and not is_owner:
        raise HTTPException(status_code=403, detail="Dream is private")

    video_url = serve_video_url(d, public=True)
    payload = share_svc.share_payload(dream_id, video_url or "")

    # Premium opt-out of watermark
    opt_out = False
    if is_owner and user:
        ent = await subs.get_entitlements(db, user.id)
        opt_out = bool(ent.get("watermark_free_share"))

    payload["opt_out_watermark"] = opt_out
    return payload


# ---------------- B2B API keys ---------------------------------------------

class IssueKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["knowledge:read"])
    monthly_quota: int = 10000


@router.post("/api/api-keys/")
async def issue_api_key(
    body: IssueKeyRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a new key. Plaintext is shown ONCE in the response;
    we store only the hash. Premium-tier required for now (cheap gate).
    """
    ent = await subs.get_entitlements(db, user.id)
    if ent["tier"] == "free":
        raise HTTPException(status_code=402, detail="API access requires Pro or Premium subscription")
    row, plaintext = await akeys.issue_key(
        db, user.id, body.name, body.scopes, monthly_quota=body.monthly_quota,
    )
    return {
        "id": row.id,
        "name": row.name,
        "key": plaintext,  # show once
        "scopes": row.scopes,
        "monthly_request_quota": row.monthly_request_quota,
    }


@router.get("/api/api-keys/")
async def list_api_keys(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await akeys.list_keys(db, user.id)


@router.delete("/api/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await akeys.revoke_key(db, user.id, key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"revoked": True}
