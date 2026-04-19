"""Sleep Cycle distillation for the knowledge base — Genesis玄武-inspired.

Periodic memory consolidation over the KnowledgeEmbedding table:
  - Decay:   unused entries lose confidence
  - Prune:   low-confidence entries get quarantined (soft delete)
  - Promote: L2 evidence with sustained usage is promoted to L1
  - Merge:   clusters of near-duplicate embeddings are collapsed

Invoked manually via /api/admin/knowledge/sleep-cycle, or can be wired
to a cron. Separate from the per-user sleep_cycle.py in services/.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge_embedding import (
    KnowledgeEmbedding,
    KnowledgeStatus,
    KnowledgeTier,
)

# Defaults tuned for a ~weekly cadence
DECAY_DAYS = 14
DECAY_AMOUNT = 0.05            # L1 decay (interpretive — meant to be used often)
DECAY_AMOUNT_L2 = 0.005        # L2 decay 10× slower (evidence — fine to sit idle)
PRUNE_MIN_CONFIDENCE = 0.1
PROMOTE_MIN_USES = 5
MERGE_DISTANCE = 0.05  # cosine distance threshold for near-duplicate


async def decay_unused(
    db: AsyncSession, days: int = DECAY_DAYS, amount: float = DECAY_AMOUNT
) -> int:
    """Reduce confidence on L1 entries that haven't been used recently.

    L2 entries (raw evidence — papers, dream corpus) are designed NOT to be
    frequently retrieved; decaying them at the same rate would silently
    quarantine the entire evidence base. L2 uses a 10× slower decay rate.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # L1 — full decay rate
    l1_stmt = (
        update(KnowledgeEmbedding)
        .where(
            or_(
                KnowledgeEmbedding.last_used_at < cutoff,
                KnowledgeEmbedding.last_used_at.is_(None),
            ),
            KnowledgeEmbedding.confidence > PRUNE_MIN_CONFIDENCE,
            KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
            KnowledgeEmbedding.tier == KnowledgeTier.L1,
        )
        .values(confidence=KnowledgeEmbedding.confidence - amount)
    )
    r1 = await db.execute(l1_stmt)

    # L2 — gentle decay only
    l2_stmt = (
        update(KnowledgeEmbedding)
        .where(
            or_(
                KnowledgeEmbedding.last_used_at < cutoff,
                KnowledgeEmbedding.last_used_at.is_(None),
            ),
            KnowledgeEmbedding.confidence > PRUNE_MIN_CONFIDENCE,
            KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
            KnowledgeEmbedding.tier == KnowledgeTier.L2,
        )
        .values(confidence=KnowledgeEmbedding.confidence - DECAY_AMOUNT_L2)
    )
    r2 = await db.execute(l2_stmt)

    return (r1.rowcount or 0) + (r2.rowcount or 0)


async def prune_low_confidence(
    db: AsyncSession, min_confidence: float = PRUNE_MIN_CONFIDENCE
) -> int:
    """Quarantine entries whose confidence has decayed below the floor."""
    stmt = (
        update(KnowledgeEmbedding)
        .where(
            KnowledgeEmbedding.confidence < min_confidence,
            KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
        )
        .values(status=KnowledgeStatus.quarantined)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def promote_l2_to_l1(
    db: AsyncSession, min_uses: int = PROMOTE_MIN_USES
) -> int:
    """Promote L2 evidence that has proven useful in retrieval to L1 knowledge."""
    stmt = (
        update(KnowledgeEmbedding)
        .where(
            KnowledgeEmbedding.tier == KnowledgeTier.L2,
            KnowledgeEmbedding.use_count >= min_uses,
            KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
            KnowledgeEmbedding.failure_count
            <= KnowledgeEmbedding.success_count,
        )
        .values(
            tier=KnowledgeTier.L1,
            status=KnowledgeStatus.graduated,
            confidence=0.8,
        )
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def merge_near_duplicates(
    db: AsyncSession, distance: float = MERGE_DISTANCE
) -> int:
    """Collapse near-duplicate entries inside the same source.

    When two L1 entries in the same source have cosine distance < threshold,
    the lower-confidence one gets quarantined as redundant. Keeps indexing
    economical and prevents prompt bloat.
    """
    # Pull all L1 graduated/probation entries grouped by source
    result = await db.execute(
        select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.tier == KnowledgeTier.L1,
            KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
            KnowledgeEmbedding.embedding.isnot(None),
        )
    )
    entries = list(result.scalars().all())

    # Group by source
    by_source: dict[str, list[KnowledgeEmbedding]] = {}
    for e in entries:
        by_source.setdefault(e.source, []).append(e)

    merged = 0
    for source, items in by_source.items():
        if len(items) < 2:
            continue
        # Compare pairwise within the same source (small N per source)
        keep: list[KnowledgeEmbedding] = []
        for candidate in sorted(items, key=lambda x: -(x.confidence or 0)):
            is_dup = False
            cand_emb = candidate.embedding
            if cand_emb is None:
                continue
            for kept in keep:
                kept_emb = kept.embedding
                if kept_emb is None:
                    continue
                # cosine distance between two normalized vectors
                dot = sum(a * b for a, b in zip(cand_emb, kept_emb))
                dist = 1.0 - dot
                if dist < distance:
                    is_dup = True
                    break
            if is_dup:
                candidate.status = KnowledgeStatus.quarantined
                merged += 1
            else:
                keep.append(candidate)

    return merged


# Min seconds between actual decay applications. Manual "Run now" from
# the dashboard or repeated tests would otherwise stack decay events
# back-to-back and quarantine healthy entries by accident.
MIN_DECAY_INTERVAL_SECONDS = 6 * 3600

_last_decay_at: dict[str, datetime] = {}


async def run_sleep_cycle(
    db: AsyncSession,
    decay_days: int = DECAY_DAYS,
    skip_merge: bool = False,
    force_decay: bool = False,
) -> dict:
    """Full distillation pass. Returns counts for each phase.

    Decay is rate-limited (idempotent within MIN_DECAY_INTERVAL_SECONDS)
    unless ``force_decay=True``. Promote/merge/prune always run — they're
    naturally idempotent and depend on accumulated state.
    """
    now = datetime.utcnow()
    last = _last_decay_at.get("global")
    decayed = 0
    decay_skipped = False
    if force_decay or last is None or (now - last).total_seconds() >= MIN_DECAY_INTERVAL_SECONDS:
        decayed = await decay_unused(db, days=decay_days)
        _last_decay_at["global"] = now
    else:
        decay_skipped = True

    promoted = await promote_l2_to_l1(db)
    merged = 0 if skip_merge else await merge_near_duplicates(db)
    pruned = await prune_low_confidence(db)
    await db.commit()

    # Snapshot current state
    from sqlalchemy import func

    counts_result = await db.execute(
        select(
            KnowledgeEmbedding.tier,
            KnowledgeEmbedding.status,
            func.count(KnowledgeEmbedding.id),
        ).group_by(KnowledgeEmbedding.tier, KnowledgeEmbedding.status)
    )
    distribution = [
        {
            "tier": row[0].value if hasattr(row[0], "value") else str(row[0]),
            "status": row[1].value if hasattr(row[1], "value") else str(row[1]),
            "count": row[2],
        }
        for row in counts_result.all()
    ]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "decayed": decayed,
        "decay_skipped_rate_limit": decay_skipped,
        "promoted_l2_to_l1": promoted,
        "merged_duplicates": merged,
        "pruned_quarantined": pruned,
        "distribution": distribution,
    }
