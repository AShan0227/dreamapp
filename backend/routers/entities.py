"""Entity extraction, correlation, and timeline endpoints."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import DreamEntity, DreamCorrelation
from models.user import UserRecord
from services.correlator import correlate_dreams, get_entity_timeline
from services.entity_extractor import extract_entities
from services.auth import require_user

router = APIRouter(prefix="/api/entities", tags=["entities"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = None,
    min_count: int = 1,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated user's entities with occurrence counts."""
    query = select(
        DreamEntity.canonical_name,
        DreamEntity.entity_type,
        DreamEntity.display_name,
        func.count(DreamEntity.id).label("count"),
    ).group_by(DreamEntity.canonical_name, DreamEntity.entity_type, DreamEntity.display_name)
    query = query.where(DreamEntity.user_id == user.id)
    if entity_type:
        query = query.where(DreamEntity.entity_type == entity_type)

    query = query.having(func.count(DreamEntity.id) >= min_count)
    query = query.order_by(func.count(DreamEntity.id).desc())

    result = await db.execute(query)
    return [
        {"canonical_name": n, "type": t.value if hasattr(t, 'value') else t, "display_name": d, "count": c}
        for n, t, d, c in result.all()
    ]


@router.get("/correlations")
async def list_correlations(
    correlation_type: Optional[str] = None,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated user's cross-dream correlations."""
    query = (
        select(DreamCorrelation)
        .where(DreamCorrelation.user_id == user.id)
        .order_by(DreamCorrelation.similarity_score.desc())
    )

    if correlation_type:
        query = query.where(DreamCorrelation.correlation_type == correlation_type)

    result = await db.execute(query.limit(50))
    correlations = result.scalars().all()

    return [
        {
            "id": c.id,
            "dream_a": c.dream_id_a,
            "dream_b": c.dream_id_b,
            "type": c.correlation_type.value,
            "score": c.similarity_score,
            "shared_entities": c.shared_entities,
            "analysis": c.analysis,
        }
        for c in correlations
    ]


@router.get("/timeline")
async def entity_timeline(
    entity: str = Query(..., description="Canonical name of entity"),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get timeline of a specific entity across the user's dreams."""
    return await get_entity_timeline(user.id, entity, db)


@router.post("/{dream_id}/extract-entities")
async def trigger_extraction(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger entity extraction for a dream. Owner only."""
    from models.dream import DreamRecord
    dream = await db.get(DreamRecord, dream_id)
    if not dream or not dream.dream_script:
        raise HTTPException(status_code=404, detail="Dream not found or not scripted")
    if dream.user_id and dream.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your dream")

    entities = await extract_entities(dream.dream_script, dream.chat_history or [])

    for ent in entities:
        entity = DreamEntity(
            dream_id=dream_id,
            user_id=dream.user_id,
            entity_type=ent.get("entity_type", "symbol"),
            canonical_name=ent.get("canonical_name", "unknown"),
            display_name=ent.get("display_name", "Unknown"),
            description=ent.get("description", ""),
            attributes=ent.get("attributes", {}),
        )
        db.add(entity)

    dream.entity_extraction_done = True
    await db.commit()

    return {"dream_id": dream_id, "entities_extracted": len(entities)}


@router.post("/correlate")
async def trigger_correlation(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Run correlation analysis for the authenticated user."""
    new_correlations = await correlate_dreams(user.id, db)
    return {"new_correlations": len(new_correlations), "correlations": new_correlations}
