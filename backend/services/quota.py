"""Per-user daily video generation quota.

Why: video generation hits paid APIs (Kling/Seedance), so we need to
prevent any single user (or attacker with a token) from burning through
the entire budget. Resets at UTC midnight.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserRecord

# Default daily cap. Override via DREAM_DAILY_VIDEO_QUOTA env if needed.
DEFAULT_DAILY_VIDEO_QUOTA = 5


def _today_utc() -> datetime:
    """Today as a NAIVE UTC midnight datetime.

    The `users.video_quota_date` column is `DateTime` (timezone-naive). Mixing
    a tz-aware value into a naive column makes asyncpg reject the write with
    "can't subtract offset-naive and offset-aware datetimes". We compare and
    store everything as naive-UTC instead.

    Uses `datetime.now(timezone.utc).replace(tzinfo=None)` rather than the
    deprecated `datetime.utcnow()` (slated for removal post-3.12).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime(now.year, now.month, now.day)


def _quota_day(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Strip tzinfo (assume already UTC); this happens for legacy rows
        # written before this fix.
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime(dt.year, dt.month, dt.day)


def get_daily_quota(entitlements: dict | None = None) -> int:
    """Effective daily video cap. Tier-aware when entitlements provided.

    Falls back to env-configured default for callsites that don't pass
    a user (e.g. legacy / health).
    """
    if entitlements and "video_quota_daily" in entitlements:
        return int(entitlements["video_quota_daily"])
    import os
    try:
        return int(os.getenv("DREAM_DAILY_VIDEO_QUOTA", DEFAULT_DAILY_VIDEO_QUOTA))
    except ValueError:
        return DEFAULT_DAILY_VIDEO_QUOTA


async def check_and_consume_video_quota(db: AsyncSession, user: UserRecord) -> int:
    """Check if user has remaining video quota, consume one, return remaining.

    Tier-aware: Pro/Premium users see their plan's quota, not the free cap.
    TOCTOU-safe: re-fetches the user row with FOR UPDATE so two parallel
    requests can't both see ``used=4`` and both increment to 5 against a
    cap of 5 (they'd burn 6 generations against a 5-cap budget).

    Raises 429 with retry hint if quota exhausted.
    """
    from sqlalchemy import select as _select
    from services.subscriptions import get_entitlements

    ent = await get_entitlements(db, user.id)
    cap = get_daily_quota(ent)
    today = _today_utc()

    # Re-fetch with row lock — only meaningful on PG; SQLite ignores it
    # (single-writer anyway).
    locked_user: UserRecord | None = await db.scalar(
        _select(UserRecord).where(UserRecord.id == user.id).with_for_update()
    )
    if locked_user is None:
        # Caller token was valid microseconds ago; user gone is exotic but
        # still a 401 from the user's perspective.
        raise HTTPException(status_code=401, detail="User not found")

    last = _quota_day(locked_user.video_quota_date)
    if last != today:
        locked_user.video_quota_date = today
        locked_user.video_quota_used = 0

    if (locked_user.video_quota_used or 0) >= cap:
        await db.rollback()
        raise HTTPException(
            status_code=429,
            detail=f"Daily video quota reached ({cap}/day). Resets at UTC midnight.",
            headers={"Retry-After": "3600"},
        )

    locked_user.video_quota_used = (locked_user.video_quota_used or 0) + 1
    await db.commit()
    # Mirror onto the in-session object so the caller's `user` reflects truth
    user.video_quota_used = locked_user.video_quota_used
    user.video_quota_date = locked_user.video_quota_date
    return cap - locked_user.video_quota_used


async def get_video_quota_status(user: UserRecord, db: Optional[AsyncSession] = None) -> dict:
    """Tier-aware quota status. Pass `db` to read entitlements; without it
    falls back to the free-tier env default."""
    ent = None
    if db is not None:
        from services.subscriptions import get_entitlements
        ent = await get_entitlements(db, user.id)
    cap = get_daily_quota(ent)
    today = _today_utc()
    last = _quota_day(user.video_quota_date)
    used = 0 if last != today else (user.video_quota_used or 0)
    return {
        "daily_cap": cap,
        "used_today": used,
        "remaining": max(0, cap - used),
        "resets_at": (today.replace(hour=0) if today else None).isoformat() if today else None,
        "tier": ent.get("tier") if ent else "free",
    }
