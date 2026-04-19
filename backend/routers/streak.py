"""Streak + daily prompt (Wave M).

Endpoints:
  GET /api/streak/me              — current + longest + milestone progress
  GET /api/streak/today-prompt    — today's "tonight try to dream of X"

No POST to manually bump — the bump happens implicitly on dream_start so
users can't cheat the streak by calling an endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import require_user
from models.user import UserRecord

router = APIRouter()


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


@router.get("/api/streak/me")
async def my_streak(user: UserRecord = Depends(require_user)):
    from services.streak import streak_summary
    return await streak_summary(user)


@router.get("/api/streak/today-prompt")
async def today_prompt(
    locale: str = Query("zh-CN"),
    db: AsyncSession = Depends(get_db),
):
    from services.streak import get_today_prompt
    return await get_today_prompt(db, locale=locale)
