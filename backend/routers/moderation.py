"""Moderation endpoints — user-facing report intake + staff review queue."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import require_user
from models.user import UserRecord
from services import moderation as mod
from services.moderation import REPORT_REASONS

router = APIRouter()


async def get_db():
    from main import async_session
    async with async_session() as db:
        yield db


# ---------------- User-facing: submit a report -----------------------------

class ReportRequest(BaseModel):
    target_type: str = Field(..., pattern="^(dream|thread|comment|user|dm)$")
    target_id: str
    reason: str
    detail: Optional[str] = Field(None, max_length=1000)


@router.post("/api/moderation/report")
async def submit_report(
    body: ReportRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Any authenticated user can report any content. Idempotent per
    (reporter, target, reason). Crosses AUTO_HIDE_THRESHOLD → auto-hide.
    """
    if body.reason not in REPORT_REASONS:
        raise HTTPException(status_code=400, detail=f"unknown reason; valid: {list(REPORT_REASONS.keys())}")
    if body.target_id == user.id and body.target_type == "user":
        raise HTTPException(status_code=400, detail="cannot report yourself")
    auto_hidden, total = await mod.submit_report(
        db, user.id, body.target_type, body.target_id, body.reason, body.detail,
    )
    return {
        "ok": True,
        "auto_hidden": auto_hidden,
        "total_reports": total,
    }


@router.get("/api/moderation/report/reasons")
async def list_reasons():
    """Exposed to frontend so the report modal can populate its picker."""
    return {"reasons": REPORT_REASONS}


# ---------------- Staff-only: review queue ---------------------------------

async def require_staff(
    user: UserRecord = Depends(require_user),
) -> UserRecord:
    if not getattr(user, "is_staff", False):
        raise HTTPException(status_code=403, detail="staff only")
    return user


@router.get("/api/moderation/queue")
async def list_queue(
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    limit: int = Query(50, ge=1, le=200),
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    return await mod.list_review_queue(db, limit=limit, status=status)


class ResolveRequest(BaseModel):
    action: str = Field(..., pattern="^(allow|hide|delete|ban_user)$")
    note: Optional[str] = Field(None, max_length=500)


@router.post("/api/moderation/resolve/{report_id}")
async def resolve(
    report_id: str,
    body: ResolveRequest,
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await mod.resolve_report(db, report_id, body.action, staff.id, body.note)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "not found"))
    return result


# ---------------- Staff-only: crisis flags review --------------------------

@router.get("/api/moderation/crisis")
async def list_crisis_flags(
    reviewed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Human-review queue for crisis flags (K2 output)."""
    from sqlalchemy import select
    from models.engagement import CrisisFlag
    q = select(CrisisFlag).where(CrisisFlag.reviewed == reviewed).order_by(CrisisFlag.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "dream_id": r.dream_id,
            "severity": r.severity,
            "surface": r.surface,
            "matched_patterns": r.matched_patterns,
            "locale": r.locale,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "action_taken": r.action_taken,
        }
        for r in rows
    ]


class CrisisResolveRequest(BaseModel):
    action_taken: str = Field(..., max_length=500)


@router.post("/api/moderation/crisis/{flag_id}/resolve")
async def resolve_crisis(
    flag_id: str,
    body: CrisisResolveRequest,
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    from models.engagement import CrisisFlag
    f = await db.get(CrisisFlag, flag_id)
    if not f:
        raise HTTPException(status_code=404, detail="flag not found")
    f.reviewed = True
    f.reviewed_at = datetime.utcnow()
    f.action_taken = body.action_taken
    await db.commit()
    return {"ok": True}
