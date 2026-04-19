"""Cross-temporal dream correlation — find recurring patterns across dreams."""

from collections import defaultdict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import DreamEntity, DreamCorrelation, CorrelationType
from models.dream import DreamRecord, DreamStatus
from services.llm import chat_completion


async def correlate_dreams(user_id: str, db: AsyncSession) -> list[dict]:
    """Find cross-dream correlations for a user. Returns new correlation records."""
    # Fetch all entities for user
    result = await db.execute(
        select(DreamEntity).where(DreamEntity.user_id == user_id)
    )
    entities = result.scalars().all()

    # Group by canonical_name
    entity_groups: dict[str, list[DreamEntity]] = defaultdict(list)
    for e in entities:
        entity_groups[e.canonical_name].append(e)

    # Find entities appearing in 2+ dreams
    recurring = {name: ents for name, ents in entity_groups.items() if len(set(e.dream_id for e in ents)) >= 2}

    # Build dream-pair scores
    pair_scores: dict[tuple, dict] = {}

    for name, ents in recurring.items():
        dream_ids = list(set(e.dream_id for e in ents))
        entity_type = ents[0].entity_type.value

        # Weight by entity type
        weight = {"character": 3, "location": 2, "scene": 1.5, "symbol": 1, "object": 0.5}.get(entity_type, 1)

        for i in range(len(dream_ids)):
            for j in range(i + 1, len(dream_ids)):
                pair = (min(dream_ids[i], dream_ids[j]), max(dream_ids[i], dream_ids[j]))
                if pair not in pair_scores:
                    pair_scores[pair] = {"score": 0, "shared": [], "types": []}
                pair_scores[pair]["score"] += weight
                pair_scores[pair]["shared"].append(name)
                pair_scores[pair]["types"].append(entity_type)

    # Create correlation records for significant pairs
    new_correlations = []
    for (did_a, did_b), data in pair_scores.items():
        if data["score"] < 2:
            continue

        # Determine correlation type
        if "character" in data["types"]:
            corr_type = CorrelationType.recurring_character
        elif "scene" in data["types"] or "location" in data["types"]:
            corr_type = CorrelationType.recurring_scene
        else:
            corr_type = CorrelationType.thematic_link

        # Check if correlation already exists
        existing = await db.execute(
            select(DreamCorrelation).where(
                and_(
                    DreamCorrelation.dream_id_a == did_a,
                    DreamCorrelation.dream_id_b == did_b,
                    DreamCorrelation.user_id == user_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Normalize score to 0-1
        max_possible = 10
        norm_score = min(1.0, data["score"] / max_possible)

        corr = DreamCorrelation(
            user_id=user_id,
            dream_id_a=did_a,
            dream_id_b=did_b,
            correlation_type=corr_type,
            similarity_score=norm_score,
            shared_entities=data["shared"],
        )
        db.add(corr)
        new_correlations.append({
            "dream_a": did_a,
            "dream_b": did_b,
            "type": corr_type.value,
            "score": norm_score,
            "shared": data["shared"],
        })

    await db.commit()
    return new_correlations


async def get_entity_timeline(user_id: str, canonical_name: str, db: AsyncSession) -> list[dict]:
    """Get timeline of appearances for a specific entity across all dreams."""
    result = await db.execute(
        select(DreamEntity, DreamRecord)
        .join(DreamRecord, DreamEntity.dream_id == DreamRecord.id)
        .where(
            and_(
                DreamEntity.user_id == user_id,
                DreamEntity.canonical_name == canonical_name,
            )
        )
        .order_by(DreamRecord.created_at)
    )
    rows = result.all()

    return [
        {
            "dream_id": entity.dream_id,
            "dream_title": dream.title,
            "date": dream.created_at.isoformat(),
            "description": entity.description,
            "attributes": entity.attributes,
            "emotion": dream.emotion_tags[0] if dream.emotion_tags else None,
        }
        for entity, dream in rows
    ]
