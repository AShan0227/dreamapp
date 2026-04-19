"""Dream Incubation / Active Dreaming endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import IncubationSession, IncubationStatus
from models.dream import DreamRecord
from models.user import UserRecord
from services.incubation import create_incubation, evaluate_outcome
from services.auth import require_user

router = APIRouter(prefix="/api/incubation", tags=["incubation"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


class IncubationRequest(BaseModel):
    intention: str


@router.post("/start")
async def start_incubation(
    req: IncubationRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a dream incubation session with pre-sleep recommendations."""
    result = await create_incubation(req.intention)

    session = IncubationSession(
        user_id=user.id,
        intention=req.intention,
        intention_tags=result.get("intention_tags", []),
        recommendations=result.get("recommendations", {}),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "intention": req.intention,
        "intention_tags": result.get("intention_tags", []),
        "recommendations": result.get("recommendations", {}),
        "matched_symbols": result.get("matched_symbols", []),
    }


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get incubation session details."""
    session = await db.get(IncubationSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    return {
        "session_id": session.id,
        "intention": session.intention,
        "recommendations": session.recommendations,
        "status": session.status.value,
        "dream_id": session.dream_id,
        "outcome_match": session.outcome_match,
        "outcome_analysis": session.outcome_analysis,
    }


@router.post("/{session_id}/link-dream")
async def link_dream(
    session_id: str,
    dream_id: str = Query(...),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Link a recorded dream to the incubation session and evaluate outcome."""
    session = await db.get(IncubationSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    dream = await db.get(DreamRecord, dream_id)
    if not dream or not dream.dream_script:
        raise HTTPException(status_code=404, detail="Dream not found or not scripted")
    if dream.user_id and dream.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your dream")

    # Evaluate match
    outcome = await evaluate_outcome(session.intention, dream.dream_script)

    session.dream_id = dream_id
    session.outcome_match = outcome.get("match_score", 0)
    session.outcome_analysis = outcome.get("analysis", "")
    session.status = IncubationStatus.completed
    await db.commit()

    return {
        "session_id": session_id,
        "dream_id": dream_id,
        "match_score": session.outcome_match,
        "analysis": session.outcome_analysis,
    }


@router.get("/")
async def list_sessions(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated user's incubation sessions."""
    query = (
        select(IncubationSession)
        .where(IncubationSession.user_id == user.id)
        .order_by(IncubationSession.started_at.desc())
    )
    result = await db.execute(query.limit(20))
    sessions = result.scalars().all()

    return [
        {
            "session_id": s.id,
            "intention": s.intention,
            "status": s.status.value,
            "outcome_match": s.outcome_match,
            "started_at": s.started_at.isoformat(),
        }
        for s in sessions
    ]
