"""Dream Health Index endpoints."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.health_index import compute_health_index, detect_anomalies
from services.sleep_cycle import run_sleep_cycle, should_sleep
from services.style_selector import recommend_style, get_style_ranking
from services.auth import require_user
from models.user import UserRecord

router = APIRouter(prefix="/api/health", tags=["health"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


@router.get("/current")
async def current_health(
    user: UserRecord = Depends(require_user),
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Compute current health metrics for a user."""
    end = date.today()
    start = end - timedelta(days=days)
    return await compute_health_index(user.id, start, end, db)


@router.get("/anomalies")
async def get_anomalies(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect anomalies in recent dream patterns."""
    return {"anomalies": await detect_anomalies(user.id, db)}


@router.post("/generate-report")
async def generate_report(
    user: UserRecord = Depends(require_user),
    period: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Generate and store a health snapshot."""
    from models.entities import DreamHealthSnapshot, PeriodType

    end = date.today()
    days = {"weekly": 7, "monthly": 30, "quarterly": 90}.get(period, 30)
    start = end - timedelta(days=days)

    result = await compute_health_index(user.id, start, end, db)

    snapshot = DreamHealthSnapshot(
        user_id=user.id,
        period_start=start,
        period_end=end,
        period_type=PeriodType(period) if period in PeriodType.__members__ else PeriodType.monthly,
        total_dreams=result.get("total_dreams", 0),
        nightmare_count=result.get("nightmare_count", 0),
        nightmare_frequency=result.get("nightmare_frequency", 0),
        dominant_emotions=result.get("dominant_emotions", []),
        emotion_trend=result.get("emotion_trend", []),
        recurring_symbols=result.get("recurring_symbols", []),
        recurring_characters=result.get("recurring_characters", []),
        anomalies=result.get("anomalies", []),
        health_score=result.get("health_score", 100),
    )
    db.add(snapshot)
    await db.commit()

    return result


@router.post("/sleep-cycle")
async def trigger_sleep_cycle(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Run Genesis-inspired sleep cycle: decay → prune → distill → promote."""
    summary = await run_sleep_cycle(user.id, db)
    return {"status": "completed", "summary": summary}


@router.get("/should-sleep")
async def check_should_sleep(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if sleep cycle should trigger (5+ new entities in 24h)."""
    should = await should_sleep(user.id, db)
    return {"should_sleep": should}


@router.post("/recommend-style")
async def recommend_dream_style(
    dream_script: dict = None,
    db: AsyncSession = Depends(get_db),
):
    """LinUCB-inspired auto style recommendation based on dream content."""
    if not dream_script:
        from fastapi import Body
        return {"error": "Provide dream_script in body"}

    style, confidence = recommend_style(dream_script)
    ranking = get_style_ranking(dream_script)

    return {
        "recommended_style": style,
        "confidence": confidence,
        "ranking": ranking[:5],
    }
