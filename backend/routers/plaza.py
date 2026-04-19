"""Dream Plaza — browse and discover public dreams."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional

from models.dream import DreamRecord, DreamStatus
from models.user import UserRecord
from services.auth import require_user, assert_dream_mutable_by
from services.video_url import serve_video_url
from services.pii import redact

router = APIRouter(prefix="/api/plaza", tags=["plaza"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Banned-user exclusion helper. Public-facing plaza listings must NEVER leak
# content from banned users. Wrapping queries with this helper gives us a
# single place to enforce it — was previously per-endpoint (and a soft-deleted
# banned user's still-public dream slipped through until the moderation
# cascade ran).
# ---------------------------------------------------------------------------
def _not_banned_user_subq():
    """Subquery selecting user_ids that are NOT banned."""
    return select(UserRecord.id).where(
        UserRecord.is_banned == False  # noqa: E712
    ).subquery()


def _public_visible_where():
    """Base predicate for any plaza / feed query. Applies:
      - is_public
      - not soft-deleted
      - owner not banned (even if content wasn't moderation-hidden yet)
    """
    banned_ok = _not_banned_user_subq()
    return and_(
        DreamRecord.is_public == True,  # noqa: E712
        DreamRecord.deleted_at.is_(None),
        DreamRecord.user_id.in_(select(banned_ok.c.id)),
    )


@router.get("/dreams")
async def browse_plaza(
    skip: int = 0,
    limit: int = 20,
    emotion: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Browse public dreams on the plaza. Anonymous-readable (by design).

    Banned-user content is filtered out via _public_visible_where — applied
    uniformly across all plaza surfaces.
    """
    query = (
        select(DreamRecord)
        .where(
            and_(
                _public_visible_where(),
                DreamRecord.status == DreamStatus.completed,
                DreamRecord.video_url != None,
            )
        )
        .order_by(DreamRecord.created_at.desc())
    )

    if emotion:
        query = query.where(DreamRecord.emotion_tags.contains(emotion))

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    dreams = result.scalars().all()

    return [
        {
            "id": d.id,
            "title": redact(d.title or ""),
            "video_url": serve_video_url(d, public=True),
            "video_urls": d.video_urls or [],
            "emotion_tags": d.emotion_tags or [],
            "symbol_tags": d.symbol_tags or [],
            "created_at": d.created_at.isoformat(),
            "video_style": d.video_style,
            # Don't expose owner user_id on public listings — match_id is enough
            # for any downstream "find similar dreamers" feature.
            "user_id": None,
        }
        for d in dreams
    ]


@router.get("/trending")
async def trending_themes(db: AsyncSession = Depends(get_db)):
    """Get trending dream themes from recent public dreams.

    Uses Postgres `jsonb_array_elements_text` to group/count tags in SQL.
    Previous implementation fetched all tag arrays into Python and counted
    there — fine at 100 candidates, 10× faster once the table grows.
    Falls back to the old path on non-PG backends (dev SQLite).
    """
    from sqlalchemy import text

    dialect = db.bind.dialect.name if db.bind else ""
    if dialect == "postgresql":
        try:
            # Limit candidate set to the 500 most-recent public completed dreams
            # — keeps the `unnest` bounded, plenty of signal for trending.
            emo_rows = await db.execute(text(
                "SELECT tag, COUNT(*) AS n FROM ( "
                "  SELECT jsonb_array_elements_text(emotion_tags::jsonb) AS tag "
                "  FROM dreams "
                "  WHERE is_public = true AND status = 'completed' "
                "        AND deleted_at IS NULL "
                "  ORDER BY created_at DESC LIMIT 500 "
                ") t WHERE tag IS NOT NULL AND tag <> '' "
                "GROUP BY tag ORDER BY n DESC LIMIT 10"
            ))
            sym_rows = await db.execute(text(
                "SELECT tag, COUNT(*) AS n FROM ( "
                "  SELECT jsonb_array_elements_text(symbol_tags::jsonb) AS tag "
                "  FROM dreams "
                "  WHERE is_public = true AND status = 'completed' "
                "        AND deleted_at IS NULL "
                "  ORDER BY created_at DESC LIMIT 500 "
                ") t WHERE tag IS NOT NULL AND tag <> '' "
                "GROUP BY tag ORDER BY n DESC LIMIT 10"
            ))
            total_res = await db.execute(text(
                "SELECT COUNT(*) FROM dreams WHERE is_public = true "
                "AND status = 'completed' AND deleted_at IS NULL"
            ))
            return {
                "top_emotions": [{"name": r[0], "count": int(r[1])} for r in emo_rows.all()],
                "top_symbols": [{"name": r[0], "count": int(r[1])} for r in sym_rows.all()],
                "total_public_dreams": int(total_res.scalar() or 0),
            }
        except Exception:
            # Fall through to the Python path on any SQL error
            pass

    # Non-PG / fallback path
    result = await db.execute(
        select(DreamRecord.emotion_tags, DreamRecord.symbol_tags)
        .where(and_(
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.status == DreamStatus.completed,
        ))
        .order_by(DreamRecord.created_at.desc())
        .limit(100)
    )
    rows = result.all()
    symbol_count: dict[str, int] = {}
    emotion_count: dict[str, int] = {}
    for emotion_tags, symbol_tags in rows:
        for tag in (emotion_tags or []):
            if isinstance(tag, str) and tag:
                emotion_count[tag] = emotion_count.get(tag, 0) + 1
        for tag in (symbol_tags or []):
            if isinstance(tag, str) and tag:
                symbol_count[tag] = symbol_count.get(tag, 0) + 1
    top_emotions = sorted(emotion_count.items(), key=lambda x: x[1], reverse=True)[:10]
    top_symbols = sorted(symbol_count.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "top_emotions": [{"name": k, "count": v} for k, v in top_emotions],
        "top_symbols": [{"name": k, "count": v} for k, v in top_symbols],
        "total_public_dreams": len(rows),
    }


@router.post("/dreams/{dream_id}/publish")
async def publish_dream(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Make a dream public on the plaza. Owner only.

    Pre-publish moderation gate: hard-block zero-tolerance content (CSAM,
    direct threats); soft-flag + allow for NSFW/slurs/spam (will accumulate
    user reports). Banned users cannot publish anything.
    """
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="account suspended")

    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)

    # Moderate the publicly-visible surface: title + narrative + chat
    from services import moderation as _mod
    script = dream.dream_script or {}
    candidate = " ".join([
        dream.title or "",
        str(script.get("narrative", "")),
        str(script.get("one_line_summary", "")),
        " ".join(m.get("content", "") for m in (dream.chat_history or []) if m.get("role") == "user"),
    ])
    result = _mod.moderate(candidate, surface="public")
    if result.is_blocked:
        raise HTTPException(status_code=451, detail={
            "blocked": True,
            "categories": result.categories,
            "message": "This content violates our publishing policy (CSAM / direct threats / terror). It remains visible only to you.",
        })
    # Soft-flag: allow publish, auto-file a silent report for staff review
    if result.needs_review:
        try:
            from models.threads import ContentReport
            db.add(ContentReport(
                reporter_user_id="__auto__",
                target_kind="dream",
                target_id=dream.id,
                reason="nsfw" if "nsfw" in result.categories else ("hate" if "slur" in result.categories else "spam"),
                detail=f"Auto-flagged on publish. Categories: {result.categories}",
            ))
        except Exception:
            pass  # never fail publish on audit-log write

    dream.is_public = True
    await db.commit()
    return {"dream_id": dream_id, "is_public": True, "auto_flagged": result.needs_review}


@router.post("/dreams/{dream_id}/unpublish")
async def unpublish_dream(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a dream from the plaza. Owner only."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)

    dream.is_public = False
    await db.commit()
    return {"dream_id": dream_id, "is_public": False}


@router.get("/dreams/{dream_id}/similar")
async def find_similar_dreams(dream_id: str, db: AsyncSession = Depends(get_db)):
    """Find dreams with similar symbols/emotions."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")

    # Find dreams with overlapping symbols or emotions
    my_symbols = set(dream.symbol_tags or [])
    my_emotions = set(dream.emotion_tags or [])

    result = await db.execute(
        select(DreamRecord)
        .where(
            and_(
                DreamRecord.is_public == True,
                DreamRecord.status == DreamStatus.completed,
                DreamRecord.id != dream_id,
            )
        )
        .order_by(DreamRecord.created_at.desc())
        .limit(100)
    )
    candidates = result.scalars().all()

    # Score by overlap
    scored = []
    for d in candidates:
        d_symbols = set(d.symbol_tags or [])
        d_emotions = set(d.emotion_tags or [])
        score = len(my_symbols & d_symbols) * 2 + len(my_emotions & d_emotions)
        if score > 0:
            scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "id": d.id,
            "title": d.title,
            "video_url": serve_video_url(d, public=True),
            "emotion_tags": d.emotion_tags or [],
            "symbol_tags": d.symbol_tags or [],
            "similarity_score": score,
            "created_at": d.created_at.isoformat(),
        }
        for score, d in scored[:10]
    ]


@router.get("/search")
async def semantic_search(
    q: str = Query(..., description="Natural language dream search", max_length=300),
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across public dreams using vector similarity. Anonymous-readable.

    Query length capped to 300 chars to prevent embedding-DoS via giant input.
    """
    from services.embeddings import aembed_text

    query_embedding = await aembed_text(q)
    if query_embedding is None:
        # Fallback to title search
        result = await db.execute(
            select(DreamRecord)
            .where(
                and_(
                    DreamRecord.is_public == True,
                    DreamRecord.status == DreamStatus.completed,
                    DreamRecord.title != None,
                )
            )
            .order_by(DreamRecord.created_at.desc())
            .limit(limit)
        )
        dreams = result.scalars().all()
    else:
        # Vector search if pgvector available and dreams have embeddings
        try:
            result = await db.execute(
                select(DreamRecord)
                .where(
                    and_(
                        DreamRecord.is_public == True,
                        DreamRecord.status == DreamStatus.completed,
                        DreamRecord.embedding != None,
                    )
                )
                .order_by(DreamRecord.embedding.cosine_distance(query_embedding))
                .limit(limit)
            )
            dreams = result.scalars().all()
        except Exception:
            # Fallback if pgvector not available
            result = await db.execute(
                select(DreamRecord)
                .where(
                    and_(
                        DreamRecord.is_public == True,
                        DreamRecord.status == DreamStatus.completed,
                    )
                )
                .order_by(DreamRecord.created_at.desc())
                .limit(limit)
            )
            dreams = result.scalars().all()

    return [
        {
            "id": d.id,
            "title": d.title,
            "video_url": serve_video_url(d, public=True),
            "emotion_tags": d.emotion_tags or [],
            "symbol_tags": d.symbol_tags or [],
            "created_at": d.created_at.isoformat(),
        }
        for d in dreams
    ]


@router.post("/knowledge/sleep-cycle")
async def run_knowledge_sleep_cycle(
    decay_days: int = 14,
    skip_merge: bool = False,
    user: UserRecord = Depends(require_user),  # gated — destructive action
    db: AsyncSession = Depends(get_db),
):
    """Run Genesis-style distillation on the knowledge embeddings.

    Decays unused entries, promotes high-use L2 to L1, merges duplicates,
    quarantines low-confidence entries.
    """
    from services.sleep_cycle_knowledge import run_sleep_cycle

    return await run_sleep_cycle(db, decay_days=decay_days, skip_merge=skip_merge)


@router.get("/knowledge/scheduler")
async def scheduler_status():
    """Status of the background Sleep Cycle scheduler."""
    import services.scheduler as _sched

    if _sched.scheduler is None:
        return {"running": False, "reason": "not initialized"}
    return _sched.scheduler.status()


@router.get("/knowledge/top")
async def top_entries(
    by: str = "use_count",
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Top knowledge entries by usage, success, or failure.

    `by`: "use_count" (default) | "success" | "failure" | "confidence"
    """
    from models.knowledge_embedding import KnowledgeEmbedding

    ord_col = {
        "use_count": KnowledgeEmbedding.use_count,
        "success": KnowledgeEmbedding.success_count,
        "failure": KnowledgeEmbedding.failure_count,
        "confidence": KnowledgeEmbedding.confidence,
    }.get(by, KnowledgeEmbedding.use_count)

    result = await db.execute(
        select(KnowledgeEmbedding).order_by(ord_col.desc()).limit(limit)
    )
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "source": e.source,
            "name": e.name,
            "tier": e.tier.value if hasattr(e.tier, "value") else str(e.tier),
            "status": e.status.value if hasattr(e.status, "value") else str(e.status),
            "confidence": e.confidence,
            "use_count": e.use_count,
            "success_count": e.success_count,
            "failure_count": e.failure_count,
            "last_used_at": e.last_used_at.isoformat() if e.last_used_at else None,
        }
        for e in entries
    ]


@router.get("/knowledge/quarantined")
async def quarantined_entries(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Entries that have been quarantined — useful for audit and recovery."""
    from models.knowledge_embedding import KnowledgeEmbedding, KnowledgeStatus

    result = await db.execute(
        select(KnowledgeEmbedding)
        .where(KnowledgeEmbedding.status == KnowledgeStatus.quarantined)
        .order_by(KnowledgeEmbedding.last_used_at.desc().nullslast())
        .limit(limit)
    )
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "source": e.source,
            "name": e.name,
            "tier": e.tier.value if hasattr(e.tier, "value") else str(e.tier),
            "confidence": e.confidence,
            "failure_count": e.failure_count,
            "success_count": e.success_count,
            "use_count": e.use_count,
            "content": e.content_text[:200],
        }
        for e in entries
    ]


@router.post("/knowledge/{entry_id}/restore")
async def restore_entry(
    entry_id: str,
    user: UserRecord = Depends(require_user),  # gated — mutates state
    db: AsyncSession = Depends(get_db),
):
    """Bring a quarantined entry back to probation — manual override."""
    from models.knowledge_embedding import KnowledgeEmbedding, KnowledgeStatus

    entry = await db.get(KnowledgeEmbedding, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry.status = KnowledgeStatus.probation
    entry.confidence = max(0.5, entry.confidence or 0.5)
    entry.failure_count = 0
    await db.commit()
    return {"id": entry_id, "status": "probation", "confidence": entry.confidence}


# ---------------- Research dashboard endpoints ------------------------------
#
# Aggregate views over the corpus of dreams + entities + knowledge for
# researchers and product owners. All read-only. Public for now since none
# of these expose individual user data — only counts/distributions.

@router.get("/research/symbol-frequency")
async def research_symbol_frequency(
    limit: int = 30,
    public_only: bool = False,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """How often does each symbol appear across the dream corpus?"""
    from sqlalchemy import func as _func
    from models.entities import DreamEntity
    base = select(
        DreamEntity.canonical_name,
        _func.count(DreamEntity.id).label("count"),
    ).group_by(DreamEntity.canonical_name)
    if public_only:
        # join dreams to filter
        base = (
            select(
                DreamEntity.canonical_name,
                _func.count(DreamEntity.id).label("count"),
            )
            .join(DreamRecord, DreamRecord.id == DreamEntity.dream_id)
            .where(DreamRecord.is_public == True)
            .group_by(DreamEntity.canonical_name)
        )
    base = base.order_by(_func.count(DreamEntity.id).desc()).limit(limit)
    result = await db.execute(base)
    return [{"symbol": name, "count": int(c)} for name, c in result.all()]


@router.get("/research/emotion-distribution")
async def research_emotion_distribution(db: AsyncSession = Depends(get_db)):
    """Distribution of emotion tags + valence/arousal histograms."""
    result = await db.execute(
        select(DreamRecord.emotion_tags, DreamRecord.emotion_valence, DreamRecord.emotion_arousal)
        .where(DreamRecord.dream_script != None)  # noqa: E711
    )
    emotion_counts: dict[str, int] = {}
    valence_buckets: dict[str, int] = {f"{i/10:.1f}": 0 for i in range(-10, 11, 2)}
    arousal_buckets: dict[str, int] = {f"{i/10:.1f}": 0 for i in range(0, 11, 2)}

    def _bucket(v: float, lo: float, hi: float, step: float) -> str:
        v = max(lo, min(hi, v))
        return f"{round(v / step) * step:.1f}"

    total = 0
    for tags, val, ar in result.all():
        total += 1
        for t in (tags or []):
            if isinstance(t, str) and t:
                emotion_counts[t] = emotion_counts.get(t, 0) + 1
        if val is not None:
            valence_buckets[_bucket(val, -1.0, 1.0, 0.2)] = valence_buckets.get(_bucket(val, -1.0, 1.0, 0.2), 0) + 1
        if ar is not None:
            arousal_buckets[_bucket(ar, 0.0, 1.0, 0.2)] = arousal_buckets.get(_bucket(ar, 0.0, 1.0, 0.2), 0) + 1

    return {
        "total_dreams_with_script": total,
        "top_emotions": sorted(
            ({"emotion": k, "count": v} for k, v in emotion_counts.items()),
            key=lambda x: -x["count"],
        )[:25],
        "valence_histogram": [{"bucket": k, "count": v} for k, v in valence_buckets.items()],
        "arousal_histogram": [{"bucket": k, "count": v} for k, v in arousal_buckets.items()],
    }


@router.get("/research/cultural-breakdown")
async def research_cultural_breakdown(db: AsyncSession = Depends(get_db)):
    """Which cultural knowledge entries get cited most? Maps audience interest."""
    from models.knowledge_embedding import KnowledgeEmbedding
    result = await db.execute(
        select(KnowledgeEmbedding)
        .where(KnowledgeEmbedding.source == "cultural")
        .order_by(KnowledgeEmbedding.use_count.desc())
        .limit(50)
    )
    out = []
    for e in result.scalars().all():
        meta = e.metadata_json or {}
        out.append({
            "name": e.name,
            "culture": meta.get("culture") or meta.get("name_native") or "?",
            "use_count": e.use_count or 0,
            "success_count": e.success_count or 0,
            "failure_count": e.failure_count or 0,
            "confidence": e.confidence,
        })
    return out


@router.get("/research/papers-cited")
async def research_papers_cited(db: AsyncSession = Depends(get_db)):
    """Which research papers does the system actually lean on most?"""
    from models.knowledge_embedding import KnowledgeEmbedding
    result = await db.execute(
        select(KnowledgeEmbedding)
        .where(KnowledgeEmbedding.source == "papers")
        .order_by(KnowledgeEmbedding.use_count.desc())
    )
    out = []
    for e in result.scalars().all():
        meta = e.metadata_json or {}
        out.append({
            "id": meta.get("id"),
            "title": meta.get("title") or e.name,
            "authors": meta.get("authors") or [],
            "year": meta.get("year"),
            "journal": meta.get("journal"),
            "category": meta.get("category"),
            "use_count": e.use_count or 0,
            "success_count": e.success_count or 0,
        })
    return {
        "total_papers": len(out),
        "papers": out,
    }


@router.get("/research/export.csv")
async def research_export_csv(
    kind: str = Query("symbols", description="symbols | emotions | papers | cultural"),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """CSV export for offline analysis. ``kind`` selects the dataset.

    Opens in Excel/Sheets. Uses RFC 4180 quoting — values with commas or
    newlines get wrapped + escaped.
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    buf = io.StringIO()
    writer = csv.writer(buf)

    if kind == "symbols":
        data = await research_symbol_frequency(limit=500, public_only=False, db=db)
        writer.writerow(["symbol", "count"])
        for row in data:
            writer.writerow([row["symbol"], row["count"]])
    elif kind == "emotions":
        d = await research_emotion_distribution(db=db)
        writer.writerow(["emotion", "count"])
        for row in d["top_emotions"]:
            writer.writerow([row["emotion"], row["count"]])
    elif kind == "papers":
        d = await research_papers_cited(db=db)
        writer.writerow(["id", "title", "authors", "year", "journal", "category", "use_count", "success_count"])
        for p in d["papers"]:
            writer.writerow([
                p.get("id") or "",
                p.get("title") or "",
                "; ".join(p.get("authors") or []),
                p.get("year") or "",
                p.get("journal") or "",
                p.get("category") or "",
                p.get("use_count", 0),
                p.get("success_count", 0),
            ])
    elif kind == "cultural":
        rows = await research_cultural_breakdown(db=db)
        writer.writerow(["name", "culture", "use_count", "success_count", "failure_count", "confidence"])
        for r in rows:
            writer.writerow([r["name"], r["culture"], r["use_count"], r["success_count"], r["failure_count"], r["confidence"]])
    else:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="dreamapp-{kind}.csv"'},
    )


@router.get("/knowledge/stats")
async def knowledge_stats(db: AsyncSession = Depends(get_db)):
    """Distribution of knowledge entries by tier, status, and source."""
    from sqlalchemy import func
    from models.knowledge_embedding import KnowledgeEmbedding

    by_tier_status = await db.execute(
        select(
            KnowledgeEmbedding.tier,
            KnowledgeEmbedding.status,
            func.count(KnowledgeEmbedding.id),
        ).group_by(KnowledgeEmbedding.tier, KnowledgeEmbedding.status)
    )
    by_source = await db.execute(
        select(
            KnowledgeEmbedding.source,
            func.count(KnowledgeEmbedding.id),
            func.avg(KnowledgeEmbedding.confidence),
            func.sum(KnowledgeEmbedding.use_count),
        ).group_by(KnowledgeEmbedding.source)
    )
    total_row = await db.execute(select(func.count(KnowledgeEmbedding.id)))

    return {
        "total_entries": total_row.scalar() or 0,
        "by_tier_status": [
            {
                "tier": r[0].value if hasattr(r[0], "value") else str(r[0]),
                "status": r[1].value if hasattr(r[1], "value") else str(r[1]),
                "count": r[2],
            }
            for r in by_tier_status.all()
        ],
        "by_source": [
            {
                "source": r[0],
                "count": r[1],
                "avg_confidence": round(float(r[2] or 0), 3),
                "total_uses": int(r[3] or 0),
            }
            for r in by_source.all()
        ],
    }


@router.get("/knowledge-search")
async def knowledge_search(
    q: str = Query(..., description="Search knowledge base semantically", max_length=300),
    source: Optional[str] = None,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across the knowledge base. Anonymous-readable."""
    from services.embeddings import aembed_text
    from models.knowledge_embedding import KnowledgeEmbedding

    query_embedding = await aembed_text(q)
    if query_embedding is None:
        return []

    try:
        query = select(KnowledgeEmbedding).where(KnowledgeEmbedding.embedding != None)
        if source:
            query = query.where(KnowledgeEmbedding.source == source)
        query = query.order_by(KnowledgeEmbedding.embedding.cosine_distance(query_embedding)).limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        # Genesis Attribution: increment use_count for retrieved entries
        from datetime import datetime
        for e in entries:
            e.use_count = (e.use_count or 0) + 1
            e.last_used_at = datetime.utcnow()
            # Graduate after 3 uses
            if e.use_count >= 3 and e.status.value == "probation":
                e.status = "graduated"
                e.confidence = min(1.0, (e.confidence or 0.5) + 0.2)
        await db.commit()

        return [
            {
                "source": e.source,
                "name": e.name,
                "tier": e.tier.value if hasattr(e.tier, 'value') else str(e.tier),
                "content": e.content_text[:200],
                "confidence": e.confidence,
                "use_count": e.use_count,
                "metadata": e.metadata_json,
            }
            for e in entries
        ]
    except Exception as e:
        return {"error": str(e)}
