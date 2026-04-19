"""Dream Wrapped (Wave N) — year / quarter / month in dreams.

Strongest self-propagating content on the platform. Computed once per
(user, period), cached, shared via opaque slug.

Period support:
  "2026"          — calendar year
  "2026-Q2"       — Q1/Q2/Q3/Q4
  "month-2026-04" — single calendar month

Output shape is stable — frontend Wrapped page consumes it directly.
"""

from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord, DreamStatus
from models.engagement import DreamWrappedSnapshot


# ---- Period parsing -------------------------------------------------------

def _period_range(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for the period string. Raises
    ValueError on malformed input — caller should surface 400.
    """
    period = period.strip()
    if len(period) == 4 and period.isdigit():
        year = int(period)
        return datetime(year, 1, 1), datetime(year + 1, 1, 1)
    if "-Q" in period:
        year_s, q_s = period.split("-Q")
        year = int(year_s)
        q = int(q_s)
        if q < 1 or q > 4:
            raise ValueError("quarter must be 1-4")
        start = datetime(year, 3 * (q - 1) + 1, 1)
        end = datetime(year + (1 if q == 4 else 0), (3 * q) % 12 + 1 if q < 4 else 1, 1) \
            if q < 4 else datetime(year + 1, 1, 1)
        return start, end
    if period.startswith("month-"):
        _, ym = period.split("-", 1)
        year_s, month_s = ym.split("-")
        year, month = int(year_s), int(month_s)
        start = datetime(year, month, 1)
        end = datetime(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        return start, end
    raise ValueError(f"Unknown period format: {period!r}")


# ---- Compute Wrapped ------------------------------------------------------

async def compute_wrapped(
    db: AsyncSession, user_id: str, period: str, force: bool = False,
) -> dict:
    """Return a Wrapped report. Caches result in dream_wrapped_snapshots.

    Pass force=True to recompute + overwrite (admin tool / debug).
    """
    if not force:
        cached = await db.execute(
            select(DreamWrappedSnapshot).where(
                DreamWrappedSnapshot.user_id == user_id,
                DreamWrappedSnapshot.period == period,
            ).limit(1)
        )
        snap = cached.scalar_one_or_none()
        if snap and snap.payload:
            payload = dict(snap.payload)
            payload["share_slug"] = snap.share_slug
            payload["cached"] = True
            return payload

    start, end = _period_range(period)
    res = await db.execute(
        select(DreamRecord).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.created_at >= start,
            DreamRecord.created_at < end,
            DreamRecord.status == DreamStatus.completed,
            DreamRecord.deleted_at.is_(None),
        )).order_by(DreamRecord.created_at)
    )
    dreams = list(res.scalars().all())

    payload = _build_payload(period, start, end, dreams)

    # Persist snapshot + mint share slug
    slug = secrets.token_urlsafe(9)   # ~12 chars, URL-safe
    existing = await db.execute(
        select(DreamWrappedSnapshot).where(
            DreamWrappedSnapshot.user_id == user_id,
            DreamWrappedSnapshot.period == period,
        ).limit(1)
    )
    snap = existing.scalar_one_or_none()
    if snap:
        snap.payload = payload
        if not snap.share_slug:
            snap.share_slug = slug
    else:
        snap = DreamWrappedSnapshot(
            user_id=user_id,
            period=period,
            payload=payload,
            share_slug=slug,
        )
        db.add(snap)
    await db.commit()
    await db.refresh(snap)

    payload["share_slug"] = snap.share_slug
    payload["cached"] = False
    return payload


def _build_payload(period: str, start: datetime, end: datetime, dreams: list) -> dict:
    """Shape the Wrapped data. Stable schema — frontend page binds directly.

    Fields:
      period, start, end, total_dreams, nightmare_count, nightmare_rate
      top_symbols, top_emotions, top_characters
      emotion_arc (by month), first_dream_title, most_intense_dream_title
      dream_aesthetic (variant name — solaris / shinkai / moonrise / ...)
      streak_peak (longest consecutive-day run in this period)
      headline_number (the hero number for the share card — "87 dreams")
    """
    total = len(dreams)
    if total == 0:
        return {
            "period": period,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "empty": True,
            "total_dreams": 0,
            "headline_number": 0,
            "headline_label_zh": "这段时间没有梦",
            "headline_label_en": "No dreams this period",
        }

    syms: Counter = Counter()
    emos: Counter = Counter()
    chars: Counter = Counter()
    nightmares = 0
    emotion_arc: dict[str, list[float]] = {}

    for d in dreams:
        for s in d.symbol_tags or []:
            if s: syms[s] += 1
        for e in d.emotion_tags or []:
            if e: emos[e] += 1
        for c in d.character_tags or []:
            if c: chars[c] += 1
        if d.nightmare_flag:
            nightmares += 1
        month = d.created_at.strftime("%Y-%m")
        if d.emotion_valence is not None:
            emotion_arc.setdefault(month, []).append(float(d.emotion_valence))

    # Reduce emotion_arc to monthly averages
    arc = [
        {"month": m, "valence": round(sum(v) / len(v), 3), "count": len(v)}
        for m, v in sorted(emotion_arc.items())
    ]

    # Streak peak within this period — scan date sequence
    date_set = sorted({d.created_at.strftime("%Y-%m-%d") for d in dreams})
    streak_peak = 0
    cur = 0
    prev = None
    for dstr in date_set:
        if prev is None:
            cur = 1
        else:
            d_prev = datetime.strptime(prev, "%Y-%m-%d")
            d_cur = datetime.strptime(dstr, "%Y-%m-%d")
            cur = cur + 1 if (d_cur - d_prev).days == 1 else 1
        streak_peak = max(streak_peak, cur)
        prev = dstr

    # Dream aesthetic — majority vote from emotion/nightmare tags
    aesthetic = _dominant_aesthetic(emos, nightmares, total)

    # Most intense dream = max abs(valence) or the earliest nightmare
    most_intense = None
    if dreams:
        candidates = [d for d in dreams if d.emotion_valence is not None]
        if candidates:
            hero = max(candidates, key=lambda d: abs(d.emotion_valence or 0))
            most_intense = hero.title or "Untitled"
        elif nightmares:
            first_nm = next((d for d in dreams if d.nightmare_flag), None)
            most_intense = (first_nm.title if first_nm else None) or "Untitled"

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "empty": False,
        "total_dreams": total,
        "nightmare_count": nightmares,
        "nightmare_rate": round(nightmares / total, 3),
        "top_symbols": [{"name": n, "count": c} for n, c in syms.most_common(5)],
        "top_emotions": [{"name": n, "count": c} for n, c in emos.most_common(5)],
        "top_characters": [{"name": n, "count": c} for n, c in chars.most_common(5)],
        "emotion_arc": arc,
        "first_dream_title": (dreams[0].title or "Untitled") if dreams else None,
        "most_intense_dream_title": most_intense,
        "dream_aesthetic": aesthetic,
        "streak_peak": streak_peak,
        "headline_number": total,
        "headline_label_zh": f"你做了 {total} 个梦",
        "headline_label_en": f"You dreamt {total} times",
    }


def _dominant_aesthetic(emos: Counter, nightmares: int, total: int) -> str:
    """Very rough — delegate to frontend's richer dream-aesthetic.ts for
    actual visualization. This is just the headline label for the Wrapped
    share card.
    """
    if total and nightmares / total > 0.3:
        return "Mulholland"
    top = emos.most_common(1)
    if not top:
        return "Moonrise"
    word = top[0][0].lower()
    if any(k in word for k in ("joy", "love", "warm", "爱", "喜", "快乐", "怀旧")):
        return "Spirited"
    if any(k in word for k in ("long", "sad", "missing", "想", "念", "悲")):
        return "Shinkai"
    if any(k in word for k in ("quiet", "reflect", "water", "静", "水", "忆")):
        return "Solaris"
    return "Moonrise"


async def wrapped_by_slug(db: AsyncSession, slug: str) -> Optional[dict]:
    """Anonymous-readable lookup for the share page. Returns the Wrapped
    payload or None if slug unknown. Does NOT reveal user_id.
    """
    res = await db.execute(
        select(DreamWrappedSnapshot).where(
            DreamWrappedSnapshot.share_slug == slug
        ).limit(1)
    )
    snap = res.scalar_one_or_none()
    if not snap or not snap.payload:
        return None
    payload = dict(snap.payload)
    payload["share_slug"] = snap.share_slug
    return payload
