"""Analytics endpoints.

User-facing:
  POST /api/analytics/track — fire a client-side event (session start,
    page view, CTA click). Authenticated so we can tie to user_id.

Staff-only:
  GET /api/analytics/funnel — compute a funnel across steps
  GET /api/analytics/events — raw event stream for debugging
  GET /api/analytics/overview — KPI dashboard snapshot
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import require_user, get_optional_user
from models.user import UserRecord
from services import analytics as _analytics

router = APIRouter()


async def get_db():
    from main import async_session
    async with async_session() as db:
        yield db


class TrackRequest(BaseModel):
    event: str = Field(..., max_length=80)
    props: Optional[dict] = None
    session_id: Optional[str] = Field(None, max_length=80)


@router.post("/api/analytics/track")
async def track_event(
    req: TrackRequest,
    user: Optional[UserRecord] = Depends(get_optional_user),
):
    """Client-initiated tracking. Authenticated users get attribution;
    anonymous events are still recorded but distinct_id is session-bound.
    """
    # Only allow a client-safe subset of events from the frontend
    ALLOWED_CLIENT_EVENTS = {
        "session_started", "page_viewed", "cta_clicked",
        "onboarding_step", "share_button_clicked",
        "subscription_viewed", "paywall_shown",
        "record_started", "record_finished",
        "dream_shared_external",
        "app_opened", "app_backgrounded",
    }
    if req.event not in ALLOWED_CLIENT_EVENTS:
        raise HTTPException(status_code=400, detail=f"event '{req.event}' not allowed from client")
    await _analytics.track(
        req.event,
        user_id=(user.id if user else None),
        props=req.props,
        session_id=req.session_id,
    )
    return {"ok": True}


async def require_staff(
    user: UserRecord = Depends(require_user),
) -> UserRecord:
    if not getattr(user, "is_staff", False):
        raise HTTPException(status_code=403, detail="staff only")
    return user


@router.get("/api/analytics/funnel")
async def get_funnel(
    steps: str = Query(default=",".join(_analytics.DEFAULT_REVENUE_FUNNEL)),
    days: int = Query(30, ge=1, le=180),
    staff: UserRecord = Depends(require_staff),
):
    """Return ordered funnel with per-step dropoff + conversion %."""
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    if not step_list:
        raise HTTPException(status_code=400, detail="no steps provided")
    result = await _analytics.funnel(step_list, days=days)
    return {"steps": result, "window_days": days}


@router.get("/api/analytics/events")
async def list_events(
    event: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from models.engagement import AnalyticsEvent
    q = select(AnalyticsEvent)
    if event:
        q = q.where(AnalyticsEvent.event == event)
    if user_id:
        q = q.where(AnalyticsEvent.user_id == user_id)
    q = q.order_by(AnalyticsEvent.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "event": r.event,
            "user_id": r.user_id,
            "session_id": r.session_id,
            "props": r.props,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/api/analytics/overview")
async def overview(
    days: int = Query(7, ge=1, le=90),
    staff: UserRecord = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """High-signal KPI dashboard. All metrics are per-window.

    Intentionally opinionated about what matters:
      - DAU, new registrations, dream-completion rate, video-gen rate
      - Paying users delta, MRR estimate, churn signals
      - Crisis flags + open moderation reports (safety health)
    """
    from models.engagement import (
        AnalyticsEvent, Payment, Subscription, CrisisFlag,
    )
    from models.threads import ContentReport
    cutoff = datetime.utcnow() - timedelta(days=days)

    # DAU-ish: distinct users with any event in the window
    dau_res = await db.execute(
        select(func.count(func.distinct(AnalyticsEvent.user_id))).where(
            and_(AnalyticsEvent.created_at >= cutoff, AnalyticsEvent.user_id.isnot(None))
        )
    )
    dau = int(dau_res.scalar() or 0)

    def _count(q):
        return int(q.scalar() or 0)

    def _count_event(ev):
        return select(func.count(AnalyticsEvent.id)).where(
            and_(AnalyticsEvent.event == ev, AnalyticsEvent.created_at >= cutoff)
        )

    new_users = _count(await db.execute(_count_event("user_registered")))
    dreams_started = _count(await db.execute(_count_event("dream_started")))
    dreams_interpreted = _count(await db.execute(_count_event("dream_interpreted")))
    videos_generated = _count(await db.execute(_count_event("dream_video_generated")))
    payments_ok = _count(await db.execute(_count_event("payment_succeeded")))
    payments_fail = _count(await db.execute(_count_event("payment_failed")))

    # Revenue (completed payments in window)
    rev_res = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            and_(Payment.status == "completed", Payment.completed_at >= cutoff)
        )
    )
    revenue_cents = int(rev_res.scalar() or 0)

    # Paid-tier users at this moment
    paid_res = await db.execute(
        select(func.count(Subscription.id)).where(
            and_(Subscription.tier.in_(["pro", "premium"]), Subscription.status == "active")
        )
    )
    paid_count = int(paid_res.scalar() or 0)

    # Safety: open crisis flags + unresolved reports
    crisis_res = await db.execute(
        select(func.count(CrisisFlag.id)).where(CrisisFlag.reviewed == False)  # noqa: E712
    )
    open_crisis = int(crisis_res.scalar() or 0)

    reports_res = await db.execute(
        select(func.count(ContentReport.id)).where(ContentReport.resolved_at.is_(None))
    )
    open_reports = int(reports_res.scalar() or 0)

    return {
        "window_days": days,
        "dau": dau,
        "new_users": new_users,
        "dreams_started": dreams_started,
        "dreams_interpreted": dreams_interpreted,
        "dreams_completion_rate": (dreams_interpreted / dreams_started) if dreams_started else 0,
        "videos_generated": videos_generated,
        "payments_succeeded": payments_ok,
        "payments_failed": payments_fail,
        "payment_success_rate": payments_ok / (payments_ok + payments_fail) if (payments_ok + payments_fail) else 0,
        "revenue_cents": revenue_cents,
        "paid_subscribers": paid_count,
        "safety": {
            "open_crisis_flags": open_crisis,
            "open_content_reports": open_reports,
        },
    }
