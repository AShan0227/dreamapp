"""Event tracking for the revenue funnel.

Events land in two places:
  1. Local append-only `analytics_events` table — always on. Used for
     funnel queries, retention cohorts, and offline analysis.
  2. Optional PostHog forwarder — if DREAM_POSTHOG_API_KEY is set, fire
     the event there too. The local table is the source of truth; PostHog
     is a convenience for dashboards until we build our own.

Design:
  - Track on the server side (client events are unreliable — ad blockers,
    mobile webviews without JS).
  - Fire-and-forget (never block the user request).
  - Event names follow `<domain>_<verb>` snake_case. Properties are
    JSON-serializable primitives.

Canonical event taxonomy (add more but don't rename existing):

  # Acquisition / onboarding
  user_registered                 {method, utm_source?}
  user_onboarded                  {steps_completed, seconds_elapsed}

  # Dream journey
  dream_started                   {method}
  dream_script_ready              {dream_id, interview_rounds}
  dream_interpreted               {dream_id, nightmare: bool}
  dream_video_generated           {dream_id, priority: bool, quota_remaining}
  dream_video_failed              {dream_id, reason}
  dream_published                 {dream_id, auto_flagged: bool}
  dream_shared                    {dream_id, target}

  # Social
  comment_posted                  {target_dream_id}
  reaction_added                  {target_dream_id, kind}
  follow_added                    {target_user_id}

  # Monetization (the north-star funnel)
  subscription_viewed             {plan}
  payment_initiated               {provider, purpose, amount_cents}
  payment_succeeded               {provider, purpose, amount_cents}
  payment_failed                  {provider, purpose, reason}
  subscription_activated          {plan, months}
  subscription_cancelled          {plan}
  coins_purchased                 {amount_cents, coin_count}
  skip_queue_used                 {dream_id, method: coin|subscription}

  # Safety
  crisis_triggered                {severity, surface}
  content_reported                {target_type, reason}
  content_blocked                 {categories, surface}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

log = logging.getLogger("dreamapp.analytics")


async def track(
    event: str,
    user_id: Optional[str] = None,
    props: Optional[dict] = None,
    *,
    session_id: Optional[str] = None,
) -> None:
    """Fire-and-forget event tracking. Always safe to call; never raises."""
    try:
        await _track_local(event, user_id, props or {}, session_id)
    except Exception as e:
        log.exception("analytics local write failed: %s", e)

    if os.getenv("DREAM_POSTHOG_API_KEY"):
        try:
            asyncio.ensure_future(_track_posthog(event, user_id, props or {}))
        except Exception as e:
            log.exception("analytics posthog dispatch failed: %s", e)


async def _track_local(
    event: str,
    user_id: Optional[str],
    props: dict,
    session_id: Optional[str],
) -> None:
    """Append to analytics_events. Opens its own session so caller's
    commit/rollback is never affected."""
    from main import async_session
    from models.engagement import AnalyticsEvent
    async with async_session() as db:
        db.add(AnalyticsEvent(
            id=str(uuid.uuid4()),
            event=event[:80],
            user_id=user_id,
            session_id=session_id,
            props=_safe_props(props),
            created_at=datetime.utcnow(),
        ))
        await db.commit()


def _safe_props(props: dict) -> dict:
    """Strip non-JSON-serializable values, truncate strings."""
    clean = {}
    for k, v in (props or {}).items():
        key = str(k)[:80]
        if isinstance(v, (str, int, float, bool)) or v is None:
            if isinstance(v, str) and len(v) > 500:
                v = v[:500]
            clean[key] = v
        elif isinstance(v, (list, dict)):
            try:
                clean[key] = json.loads(json.dumps(v, default=str))[:10] if isinstance(v, list) else json.loads(json.dumps(v, default=str))
            except Exception:
                clean[key] = str(v)[:200]
        else:
            clean[key] = str(v)[:200]
    return clean


async def _track_posthog(event: str, user_id: Optional[str], props: dict) -> None:
    """Optional forward to PostHog. Requires DREAM_POSTHOG_API_KEY."""
    import httpx
    api_key = os.getenv("DREAM_POSTHOG_API_KEY", "")
    host = os.getenv("DREAM_POSTHOG_HOST", "https://us.posthog.com")
    if not api_key:
        return
    payload = {
        "api_key": api_key,
        "event": event,
        "distinct_id": user_id or "anonymous",
        "properties": _safe_props(props),
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{host}/capture/", json=payload)
    except Exception as e:
        log.warning("PostHog capture failed: %s", e)


# ---------------- Funnel query helpers --------------------------------------

async def funnel(
    steps: list[str],
    days: int = 30,
    *,
    cohort_user_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Return per-step conversion counts for an ordered list of events.

    Each user must have event[i] before event[i+1] (first occurrence wins)
    to count at step i+1. Dropoff = step[i] - step[i+1].

    Used by /api/analytics/funnel in the admin dashboard.
    """
    from main import async_session
    from sqlalchemy import text
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    async with async_session() as db:
        # For each step, pull (user_id, min(created_at)) within window
        step_counts: list[dict] = []
        prior_users_with_times: dict[str, datetime] = {}

        for i, event in enumerate(steps):
            conds = "event = :event AND created_at >= :cutoff"
            params = {"event": event, "cutoff": cutoff}
            if cohort_user_ids:
                # Limit cohort for small lists — not safe for huge lists
                if len(cohort_user_ids) <= 1000:
                    conds += " AND user_id = ANY(:uids)"
                    params["uids"] = cohort_user_ids
            sql = text(f"""
                SELECT user_id, MIN(created_at) AS ts
                FROM analytics_events
                WHERE {conds} AND user_id IS NOT NULL
                GROUP BY user_id
            """)
            res = await db.execute(sql, params)
            rows = res.mappings().all()

            if i == 0:
                # Everyone who ever did step[0] counts
                prior_users_with_times = {r["user_id"]: r["ts"] for r in rows}
                step_counts.append({"event": event, "users": len(rows), "dropoff": 0})
            else:
                # Only users who did step[i] AFTER their step[i-1] timestamp count
                these = {r["user_id"]: r["ts"] for r in rows}
                converted = {
                    uid for uid, ts in these.items()
                    if uid in prior_users_with_times and ts >= prior_users_with_times[uid]
                }
                prev_n = step_counts[-1]["users"]
                step_counts.append({
                    "event": event,
                    "users": len(converted),
                    "dropoff": prev_n - len(converted),
                    "conversion_from_prev": (len(converted) / prev_n) if prev_n else 0,
                })
                # Advance timestamps to the new step
                prior_users_with_times = {
                    uid: these[uid] for uid in converted if uid in these
                }

    return step_counts


DEFAULT_REVENUE_FUNNEL = [
    "user_registered",
    "dream_started",
    "dream_script_ready",
    "dream_interpreted",
    "dream_video_generated",
    "subscription_viewed",
    "payment_initiated",
    "payment_succeeded",
]
