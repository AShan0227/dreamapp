"""Streak + daily prompt system (Wave M).

Design:
  - On every `start_dream`, we call `bump_streak(user)`:
      * same day as last → no-op
      * consecutive day → increment current_streak_days
      * gap → reset to 1
  - Milestones (7 / 30 / 100 days) award coins + notification.
  - Daily prompt is a scheduled item stored in `daily_prompts` table,
    one row per (date, locale). `get_today_prompt()` returns today's.
  - Frontend calls `/api/streak/me` + `/api/streak/today-prompt`.

Timezone: streak uses YYYY-MM-DD from UTC right now. A later iteration
could use user.locale → timezone, but UTC is fine for v1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserRecord


# Coin rewards at each milestone (positive values)
_MILESTONES: dict[int, int] = {
    3: 20,       # "3 日"
    7: 50,       # "1 week"
    14: 100,     # "2 weeks"
    30: 300,     # "1 month"
    100: 1000,   # "100 day dreamer"
    365: 3000,   # "1 year"
}


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _yesterday_utc() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


async def bump_streak(db: AsyncSession, user: UserRecord) -> dict:
    """Advance a user's streak after recording a dream today.

    IMPORTANT: the `user` passed by route handlers is usually attached to
    a different session (from `require_user`). Mutating it here would not
    persist in the route's `db`. We re-fetch by id inside this session.

    Returns a summary dict:
      {
        "current": int,           # current streak after bump
        "longest": int,           # personal best
        "changed": bool,          # True if this call advanced the streak
        "milestone": int | None,  # which milestone was just hit (e.g. 7)
        "coins_awarded": int,     # rewarded this call, if any
      }
    """
    # Re-fetch user in the CURRENT session so mutations persist on db.commit()
    user = await db.get(UserRecord, user.id)
    if user is None:
        return {"current": 0, "longest": 0, "changed": False, "milestone": None, "coins_awarded": 0}

    today = _today_utc()
    last = getattr(user, "last_streak_date", None)
    current = int(getattr(user, "current_streak_days", 0) or 0)
    longest = int(getattr(user, "longest_streak_days", 0) or 0)

    result = {
        "current": current,
        "longest": longest,
        "changed": False,
        "milestone": None,
        "coins_awarded": 0,
    }

    if last == today:
        # Already counted for today — idempotent. No new bump.
        return result

    # Advance logic
    if last == _yesterday_utc():
        current += 1
    else:
        current = 1  # either gap or first-ever dream

    longest = max(longest, current)

    user.current_streak_days = current
    user.longest_streak_days = longest
    user.last_streak_date = today

    milestone = _MILESTONES.get(current)
    coins = 0
    if milestone:
        # Reward + log to coin ledger
        try:
            from services.engagement import credit_coins
            await credit_coins(
                db, user.id, milestone,
                reason=f"earn_streak_{current}",
                note=f"{current}-day dream streak",
            )
            coins = milestone
        except Exception:
            # Never break the dream flow because of a reward failure
            coins = 0

    await db.commit()

    result.update({
        "current": current,
        "longest": longest,
        "changed": True,
        "milestone": current if milestone else None,
        "coins_awarded": coins,
    })
    return result


async def streak_summary(user: UserRecord) -> dict:
    """Read-only summary for UI display."""
    current = int(getattr(user, "current_streak_days", 0) or 0)
    longest = int(getattr(user, "longest_streak_days", 0) or 0)
    last = getattr(user, "last_streak_date", None)
    # Alive today if we've recorded today; still-counting if yesterday.
    today = _today_utc()
    yesterday = _yesterday_utc()
    status = "inactive"
    if last == today:
        status = "done_today"
    elif last == yesterday:
        status = "continue_today"
    elif last and last < yesterday:
        status = "broken"
    next_m = next((m for m in sorted(_MILESTONES.keys()) if m > current), None)
    return {
        "current": current,
        "longest": longest,
        "status": status,
        "last_streak_date": last,
        "next_milestone": next_m,
        "next_milestone_reward": _MILESTONES.get(next_m, 0) if next_m else 0,
    }


# ---------------- Daily prompt -------------------------------------------

# Curated rotating pool — picked deterministically by (date, locale). Real
# deployment should seed these into the `daily_prompts` table via ops so
# the list stays editorial / on-brand.
_PROMPT_POOL_ZH = [
    ("symbol", "今晚试着梦到一扇从未开过的门"),
    ("symbol", "今晚试着梦到水 —— 海、湖、雨,都可以"),
    ("character", "今晚试着梦到一个童年时的朋友"),
    ("emotion", "今晚试着梦到一种你白天不常感受的情绪"),
    ("narrative", "今晚试着梦到一段你以为会发生的人生"),
    ("place", "今晚试着梦到一个你没去过、但好像认识的地方"),
    ("lucid", "今晚试着做一个清醒梦 —— 在梦里问自己:'我在梦里吗?'"),
]
_PROMPT_POOL_EN = [
    ("symbol", "Tonight try to dream of a door that's never been opened."),
    ("symbol", "Tonight try to dream of water — ocean, lake, rain."),
    ("character", "Tonight try to dream of a childhood friend."),
    ("emotion", "Tonight try to dream in a feeling you don't usually get in waking life."),
    ("narrative", "Tonight try to dream of a life you thought would happen."),
    ("place", "Tonight try to dream of a place you've never been but somehow know."),
    ("lucid", "Tonight try for a lucid dream — ask yourself: 'am I dreaming?'"),
]


async def get_today_prompt(db: AsyncSession, locale: str = "zh-CN") -> dict:
    """Return today's daily prompt for the given locale. Falls back to
    deterministic pick from the pool if no DB row is seeded for today."""
    from models.engagement import DailyPrompt  # defined in this module
    today = _today_utc()
    is_zh = (locale or "").lower().startswith("zh")
    locale_key = "zh-CN" if is_zh else "en"

    # Look for an ops-seeded prompt first
    res = await db.execute(
        select(DailyPrompt).where(
            DailyPrompt.date_key == today,
            DailyPrompt.locale == locale_key,
        ).limit(1)
    )
    row = res.scalar_one_or_none()
    if row:
        return {
            "date": today,
            "locale": locale_key,
            "prompt": row.prompt_text,
            "category": row.category,
            "source": "seeded",
        }

    # Deterministic fallback: pool[date_index % len]
    pool = _PROMPT_POOL_ZH if is_zh else _PROMPT_POOL_EN
    # Hash today string → stable index per day
    h = sum(ord(c) for c in today)
    cat, txt = pool[h % len(pool)]
    return {
        "date": today,
        "locale": locale_key,
        "prompt": txt,
        "category": cat,
        "source": "pool",
    }
