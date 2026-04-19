"""Deja Reve — dream-reality crossing search.

PRODUCT_DOC §8.4: "I think I dreamed about this" → search dream archive,
return best matches via pgvector cosine on the user's dream embeddings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.social import DejaReveLink
from services.embeddings import aembed_text


async def search_dreams_for_event(
    db: AsyncSession,
    user_id: str,
    waking_event: str,
    limit: int = 5,
) -> list[dict]:
    """Find the user's dreams most semantically similar to a waking-life event.

    Returns ranked dreams with similarity scores. Does NOT create a link
    yet — caller decides when to persist (e.g. on user confirmation).
    """
    if not waking_event.strip():
        return []

    query_emb = await aembed_text(waking_event)
    if query_emb is None:
        return []

    try:
        result = await db.execute(
            select(DreamRecord)
            .where(
                and_(
                    DreamRecord.user_id == user_id,
                    DreamRecord.deleted_at.is_(None),
                    DreamRecord.embedding.isnot(None),
                )
            )
            .order_by(DreamRecord.embedding.cosine_distance(query_emb))
            .limit(limit)
        )
        dreams = list(result.scalars().all())
    except Exception:
        # pgvector unavailable — fall back to recency
        result = await db.execute(
            select(DreamRecord)
            .where(
                and_(
                    DreamRecord.user_id == user_id,
                    DreamRecord.deleted_at.is_(None),
                )
            )
            .order_by(DreamRecord.created_at.desc())
            .limit(limit)
        )
        dreams = list(result.scalars().all())

    out = []
    for d in dreams:
        # Compute proper similarity if both embeddings exist
        sim = None
        if d.embedding is not None and query_emb:
            dot = sum(a * b for a, b in zip(d.embedding, query_emb))
            sim = max(0.0, min(1.0, (dot + 1.0) / 2.0))  # cosine in [-1,1] → [0,1]
        out.append({
            "dream_id": d.id,
            "title": d.title or "Untitled",
            "created_at": d.created_at.isoformat(),
            "similarity": sim,
            "emotion_tags": d.emotion_tags or [],
            "symbol_tags": d.symbol_tags or [],
            "video_url": d.video_url,
        })
    return out


async def confirm_link(
    db: AsyncSession,
    user_id: str,
    dream_id: str,
    waking_event: str,
    similarity: Optional[float] = None,
    source: str = "user",
) -> DejaReveLink:
    """Persist a confirmed deja-reve match."""
    link = DejaReveLink(
        user_id=user_id,
        dream_id=dream_id,
        waking_event=waking_event,
        waking_event_at=datetime.utcnow(),
        similarity=similarity,
        source=source,
        confirmed=True,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def list_links(db: AsyncSession, user_id: str, limit: int = 50) -> list[dict]:
    """List confirmed deja-reve links for the user, newest first."""
    result = await db.execute(
        select(DejaReveLink)
        .where(DejaReveLink.user_id == user_id)
        .order_by(DejaReveLink.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "dream_id": r.dream_id,
            "waking_event": r.waking_event,
            "waking_event_at": r.waking_event_at.isoformat() if r.waking_event_at else None,
            "similarity": r.similarity,
            "source": r.source,
            "confirmed": r.confirmed,
        }
        for r in rows
    ]
