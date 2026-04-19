"""Dream Matching — find users with semantically similar dreams.

PRODUCT_DOC §6.2: "147 people had a similar dream to yours last night".
Privacy stance: we never expose other users' dream content directly via
matching — only counts + thematic overlap. The user can opt-in to
publish a dream (is_public=True), which then becomes discoverable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord, DreamStatus
from models.social import DreamMatch


async def count_similar_recent(
    db: AsyncSession,
    dream_id: str,
    window_hours: int = 48,
    similarity_threshold: float = 0.75,
) -> dict:
    """For a given dream, count how many other users had similar dreams recently.

    Uses pgvector cosine. Only considers dreams from OTHER users (not own).
    Returns a non-PII summary suitable for surfacing to the dreamer.
    """
    dream = await db.get(DreamRecord, dream_id)
    if not dream or dream.embedding is None:
        return {"matches": 0, "shared_themes": [], "window_hours": window_hours}

    cutoff = datetime.utcnow() - timedelta(hours=window_hours)

    try:
        # Cosine-distance threshold is pushed to SQL so Postgres filters on
        # the index instead of returning 500 rows to Python for re-scoring.
        # `<=> :vec` returns cosine distance (0..2). Threshold 1 - sim.
        cutoff_distance = 1.0 - similarity_threshold
        distance = DreamRecord.embedding.cosine_distance(dream.embedding)
        result = await db.execute(
            select(DreamRecord)
            .where(
                and_(
                    DreamRecord.user_id != dream.user_id,
                    DreamRecord.deleted_at.is_(None),
                    DreamRecord.embedding.isnot(None),
                    DreamRecord.created_at >= cutoff,
                    distance <= cutoff_distance,
                )
            )
            .order_by(distance)
            .limit(100)   # was 500 — now pre-filtered, so we need far fewer
        )
        matches: list[DreamRecord] = list(result.scalars().all())
    except Exception:
        return {"matches": 0, "shared_themes": [], "window_hours": window_hours}

    # Aggregate shared themes/symbols WITHOUT exposing individual dreams
    theme_counter: dict[str, int] = {}
    for m in matches:
        for tag in (m.symbol_tags or []) + (m.theme_tags or []):
            if tag:
                theme_counter[tag] = theme_counter.get(tag, 0) + 1
    shared = sorted(
        ({"theme": k, "count": v} for k, v in theme_counter.items()),
        key=lambda x: -x["count"],
    )[:8]

    return {
        "matches": len(matches),
        "shared_themes": shared,
        "window_hours": window_hours,
        "similarity_threshold": similarity_threshold,
    }


async def find_compatible_users(
    db: AsyncSession,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    """Find users whose dream patterns most overlap with the caller's.

    Approach: aggregate this user's symbol/theme tags into a signature,
    score every other user's signature against it, return top N.

    Privacy: we surface only nickname + similarity + shared theme list,
    never raw dream content.
    """
    # Caller's signature — only fetch the columns we need (tag arrays),
    # not the full DreamRecord. Big row memory win on users with lots of dreams.
    own_result = await db.execute(
        select(
            DreamRecord.symbol_tags,
            DreamRecord.theme_tags,
            DreamRecord.emotion_tags,
        ).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.deleted_at.is_(None),
        ))
    )
    own_rows = list(own_result.all())
    if not own_rows:
        return []

    own_tags: dict[str, int] = {}
    for syms, themes, emotions in own_rows:
        for tag in (syms or []) + (themes or []) + (emotions or []):
            if tag:
                own_tags[tag] = own_tags.get(tag, 0) + 1

    if not own_tags:
        return []

    # Other users' tag aggregates — only fetch recent candidates (14d, was 30d)
    # and cap to 3000 to bound memory. Lightweight columns only.
    cutoff = datetime.utcnow() - timedelta(days=14)
    others_result = await db.execute(
        select(
            DreamRecord.user_id,
            DreamRecord.symbol_tags,
            DreamRecord.theme_tags,
            DreamRecord.emotion_tags,
        ).where(and_(
            DreamRecord.user_id != user_id,
            DreamRecord.user_id.isnot(None),
            DreamRecord.deleted_at.is_(None),
            DreamRecord.created_at >= cutoff,
        ))
        .limit(3000)
    )

    by_user: dict[str, dict[str, int]] = {}
    for uid, syms, themes, emotions in others_result.all():
        sig = by_user.setdefault(uid, {})
        for tag in (syms or []) + (themes or []) + (emotions or []):
            if tag:
                sig[tag] = sig.get(tag, 0) + 1

    # Cosine similarity between tag-frequency vectors
    import math
    own_norm = math.sqrt(sum(v * v for v in own_tags.values())) or 1.0

    scored = []
    for other_uid, sig in by_user.items():
        shared = set(own_tags) & set(sig)
        if not shared:
            continue
        dot = sum(own_tags[t] * sig[t] for t in shared)
        other_norm = math.sqrt(sum(v * v for v in sig.values())) or 1.0
        sim = dot / (own_norm * other_norm)
        if sim < 0.1:
            continue
        scored.append({
            "user_id": other_uid,
            "similarity": round(sim, 3),
            "shared_themes": sorted(shared)[:8],
            "shared_count": len(shared),
        })

    scored.sort(key=lambda x: -x["similarity"])

    # Hydrate nicknames (still no PII beyond nickname/avatar)
    from models.user import UserRecord
    user_ids = [s["user_id"] for s in scored[:limit]]
    if user_ids:
        users_result = await db.execute(
            select(UserRecord).where(UserRecord.id.in_(user_ids))
        )
        nick_by_id = {u.id: u.nickname for u in users_result.scalars().all()}
        for s in scored[:limit]:
            s["nickname"] = nick_by_id.get(s["user_id"], "Anonymous Dreamer")
            # Don't leak the user_id in the response — the matching ID is
            # enough for follow-up actions like "send a dream invitation".
            s["match_id"] = s.pop("user_id")[:8]
    return scored[:limit]
