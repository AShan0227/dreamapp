"""Dream Wrapped (Wave N) API.

Endpoints:
  GET /api/wrapped/me?period=2026           — my own Wrapped (computes if needed)
  GET /api/wrapped/slug/{slug}              — anonymous public Wrapped (share page)
  POST /api/wrapped/me/refresh?period=2026  — force recompute (admin/debug)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import require_user
from models.user import UserRecord

router = APIRouter(prefix="/api/wrapped", tags=["wrapped"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


@router.get("/me")
async def my_wrapped(
    period: str = Query(..., description="2026 | 2026-Q2 | month-2026-04"),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from services.wrapped import compute_wrapped
    try:
        return await compute_wrapped(db, user.id, period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/me/refresh")
async def refresh_my_wrapped(
    period: str = Query(...),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from services.wrapped import compute_wrapped
    try:
        return await compute_wrapped(db, user.id, period, force=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/slug/{slug}")
async def public_wrapped(slug: str, db: AsyncSession = Depends(get_db)):
    from services.wrapped import wrapped_by_slug
    payload = await wrapped_by_slug(db, slug)
    if not payload:
        raise HTTPException(status_code=404, detail="Wrapped not found")
    return payload
