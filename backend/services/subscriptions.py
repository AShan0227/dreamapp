"""Subscription tiers + entitlement checks.

Free / Pro / Premium model. Entitlements are computed from the active
Subscription row; quota functions in services/quota.py call this to
decide effective caps per user.

Pricing (cents):
  Pro       2900 / month   (¥29)
  Premium   9900 / month   (¥99)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.engagement import Subscription, SubscriptionTier


# Pricing + quotas. Edit here, all entitlement logic flows from this dict.
PLAN_CATALOG: dict[str, dict] = {
    "free": {
        "monthly_price_cents": 0,
        "video_quota_daily": 5,
        "premium_styles": False,
        "priority_queue": False,
        "max_follows": 50,
        "therapy_credits_monthly": 0,
        "watermark_free_share": False,
    },
    "pro": {
        "monthly_price_cents": 2900,
        "video_quota_daily": 30,
        "premium_styles": True,
        "priority_queue": True,
        "max_follows": 1000,
        "therapy_credits_monthly": 0,
        "watermark_free_share": False,
    },
    "premium": {
        "monthly_price_cents": 9900,
        "video_quota_daily": 999,  # effectively unlimited
        "premium_styles": True,
        "priority_queue": True,
        "max_follows": 99999,
        "therapy_credits_monthly": 1,
        "watermark_free_share": True,
    },
}


async def get_active_subscription(db: AsyncSession, user_id: str) -> Subscription:
    """Return the user's active subscription, defaulting to a free row.

    Free-tier users always have an entitlement object so callsites don't
    have to special-case missing rows.
    """
    res = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.updated_at.desc())
        .limit(1)
    )
    sub = res.scalar_one_or_none()
    if sub:
        # Treat expired paid subs as free
        if sub.tier != "free" and sub.current_period_end and sub.current_period_end < datetime.utcnow():
            sub.tier = "free"
            sub.status = "expired"
            await db.commit()
        return sub
    # Synthesize a free row (don't persist — keeps DB clean for read-only flows)
    return Subscription(user_id=user_id, tier="free", status="active")


async def get_entitlements(db: AsyncSession, user_id: str) -> dict:
    """The effective feature/quota set for the caller right now."""
    sub = await get_active_subscription(db, user_id)
    plan = PLAN_CATALOG[sub.tier]
    return {
        "tier": sub.tier if isinstance(sub.tier, str) else sub.tier.value,
        "status": sub.status,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        **plan,
    }


async def upgrade_subscription(
    db: AsyncSession, user_id: str, tier: SubscriptionTier,
    payment_id: Optional[str], months: int = 1,
) -> Subscription:
    """Activate or extend the user's subscription. Called from payment webhook.

    If the user already has an active sub of the SAME tier, extend its
    current_period_end. If different tier (upgrade/downgrade), supersede.
    """
    sub = await get_active_subscription(db, user_id)
    now = datetime.utcnow()
    new_end_base = sub.current_period_end if (
        sub.tier == tier and sub.current_period_end and sub.current_period_end > now
    ) else now
    new_end = new_end_base + timedelta(days=30 * months)

    # If we returned a synthesized free Subscription, persist a real one now
    if sub.id is None or sub not in db:
        sub = Subscription(user_id=user_id, tier=tier)
        db.add(sub)

    sub.tier = tier
    sub.status = "active"
    sub.current_period_end = new_end
    sub.last_payment_id = payment_id
    sub.updated_at = now
    await db.commit()
    await db.refresh(sub)
    return sub


async def cancel_subscription(db: AsyncSession, user_id: str) -> Subscription:
    sub = await get_active_subscription(db, user_id)
    if sub.id is None:
        return sub  # already free
    sub.auto_renew = False
    sub.status = "cancelled"  # period still runs to current_period_end
    await db.commit()
    return sub
