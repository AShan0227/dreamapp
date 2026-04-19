"""Sleep Cycle Distillation — Genesis-inspired periodic knowledge consolidation.

Runs periodically to:
1. DECAY: Age old entities/correlations, reduce confidence over time
2. PRUNE: Remove quarantined entities, orphan correlations
3. DISTILL: Merge similar entities, discover new patterns
4. PROMOTE: Graduate high-confidence entities to Dream IPs
"""

from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy import select, and_, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import (
    DreamEntity, DreamCorrelation, DreamIP,
    ProbationStatus, CorrelationType, IPType,
)
from services.llm import chat_completion


# Configuration
DECAY_RATE = 0.05          # Confidence decays 5% per cycle
STALE_DAYS = 60            # Entities not seen in 60 days start decaying
GRADUATION_THRESHOLD = 3   # 3 successful uses → graduated
QUARANTINE_THRESHOLD = 2   # 2 failures → quarantined
IP_PROMOTION_COUNT = 3     # 3+ appearances → Dream IP candidate
SIMILARITY_THRESHOLD = 0.6 # Entities with >60% name similarity may merge


async def run_sleep_cycle(user_id: str, db: AsyncSession) -> dict:
    """Run a full sleep cycle for a user. Returns summary of actions taken."""
    summary = {"decayed": 0, "pruned": 0, "merged": 0, "promoted": 0, "contradictions": 0}

    # === Phase 1: DECAY ===
    stale_cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
    result = await db.execute(
        select(DreamEntity).where(
            and_(
                DreamEntity.user_id == user_id,
                DreamEntity.created_at < stale_cutoff,
                DreamEntity.probation_status != ProbationStatus.quarantined,
                DreamEntity.confidence > 0.1,
            )
        )
    )
    stale_entities = result.scalars().all()

    for entity in stale_entities:
        entity.confidence = max(0.1, entity.confidence - DECAY_RATE)
        summary["decayed"] += 1

    # === Phase 2: PRUNE ===
    # Remove quarantined entities
    result = await db.execute(
        select(DreamEntity).where(
            and_(
                DreamEntity.user_id == user_id,
                DreamEntity.probation_status == ProbationStatus.quarantined,
            )
        )
    )
    quarantined = result.scalars().all()
    for q in quarantined:
        await db.delete(q)
        summary["pruned"] += 1

    # === Phase 3: DISTILL — merge similar entities ===
    result = await db.execute(
        select(DreamEntity).where(DreamEntity.user_id == user_id)
    )
    all_entities = result.scalars().all()

    # Group by entity_type
    by_type: dict[str, list] = defaultdict(list)
    for e in all_entities:
        by_type[e.entity_type.value].append(e)

    # Find mergeable pairs within each type
    for entity_type, entities in by_type.items():
        seen_names = {}
        for entity in entities:
            name = entity.canonical_name.lower()
            if name in seen_names:
                # Merge: keep the one with higher confidence
                existing = seen_names[name]
                if entity.confidence > existing.confidence:
                    existing.probation_status = ProbationStatus.quarantined
                    seen_names[name] = entity
                else:
                    entity.probation_status = ProbationStatus.quarantined
                summary["merged"] += 1
            else:
                seen_names[name] = entity

    # === Phase 4: PROMOTE — graduate high-use entities ===
    result = await db.execute(
        select(DreamEntity).where(
            and_(
                DreamEntity.user_id == user_id,
                DreamEntity.probation_status == ProbationStatus.probation,
            )
        )
    )
    probation_entities = result.scalars().all()

    for entity in probation_entities:
        if entity.probation_successes >= GRADUATION_THRESHOLD:
            entity.probation_status = ProbationStatus.graduated
            entity.confidence = min(1.0, entity.confidence + 0.2)
            summary["promoted"] += 1
        elif entity.probation_failures >= QUARANTINE_THRESHOLD:
            entity.probation_status = ProbationStatus.quarantined
            summary["pruned"] += 1

    # === Phase 5: Detect contradictions ===
    # Find entity pairs that appear in conflicting dream contexts
    result = await db.execute(
        select(
            DreamEntity.canonical_name,
            func.count(DreamEntity.id).label("count"),
        )
        .where(DreamEntity.user_id == user_id)
        .group_by(DreamEntity.canonical_name)
        .having(func.count(DreamEntity.id) >= 2)
    )
    recurring = result.all()

    for name, count in recurring:
        # Check if entity descriptions contradict across dreams
        instances = await db.execute(
            select(DreamEntity).where(
                and_(
                    DreamEntity.user_id == user_id,
                    DreamEntity.canonical_name == name,
                )
            )
        )
        entity_list = instances.scalars().all()

        # Simple contradiction detection: if emotional tones diverge significantly
        tones = [e.attributes.get("emotional_tone", "") for e in entity_list if isinstance(e.attributes, dict)]
        unique_tones = set(t for t in tones if t)
        if len(unique_tones) >= 3:
            # This entity appears with very different emotional contexts → possible evolution
            dream_ids = list(set(e.dream_id for e in entity_list))
            if len(dream_ids) >= 2:
                # Create a "refines" correlation
                existing = await db.execute(
                    select(DreamCorrelation).where(
                        and_(
                            DreamCorrelation.user_id == user_id,
                            DreamCorrelation.correlation_type == CorrelationType.refines,
                            DreamCorrelation.shared_entities.contains(name),
                        )
                    )
                )
                if not existing.scalar_one_or_none():
                    corr = DreamCorrelation(
                        user_id=user_id,
                        dream_id_a=dream_ids[0],
                        dream_id_b=dream_ids[-1],
                        correlation_type=CorrelationType.refines,
                        similarity_score=0.7,
                        shared_entities=[name],
                        analysis=f"Entity '{name}' evolves across dreams with changing emotional context: {', '.join(unique_tones)}",
                    )
                    db.add(corr)
                    summary["contradictions"] += 1

    await db.commit()
    return summary


async def should_sleep(user_id: str, db: AsyncSession) -> bool:
    """Check if sleep cycle should trigger (Genesis: 5+ new concrete experiences)."""
    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.count(DreamEntity.id)).where(
            and_(
                DreamEntity.user_id == user_id,
                DreamEntity.created_at >= recent_cutoff,
            )
        )
    )
    recent_count = result.scalar() or 0
    return recent_count >= 5
