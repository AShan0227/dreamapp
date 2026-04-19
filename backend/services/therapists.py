"""Therapist marketplace logic — directory + matching + booking.

Matching uses recurring-pattern + emotion data to suggest therapists whose
specialties align. No booking proceeds without a successful payment
(services/payments.py + booking.payment_id link).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.engagement import (
    TherapistProfile, TherapistVerificationStatus,
    TherapyBooking, TherapyBookingStatus,
)
from models.social import RecurringPattern, PatternKind
from models.dream import DreamRecord


PLATFORM_FEE_BPS = 2000  # 20% of price


async def list_therapists(
    db: AsyncSession,
    specialty: Optional[str] = None,
    language: Optional[str] = None,
) -> list[dict]:
    """Browse the verified, active directory."""
    q = select(TherapistProfile).where(and_(
        TherapistProfile.verification_status == "verified",
        TherapistProfile.is_active == True,  # noqa: E712
    ))
    res = await db.execute(q)
    rows = list(res.scalars().all())

    out = []
    for t in rows:
        if specialty and specialty not in (t.specialties or []):
            continue
        if language and language not in (t.languages or []):
            continue
        out.append(_serialize_therapist(t))
    out.sort(key=lambda x: -(x["rating_avg"] or 0))
    return out


def _serialize_therapist(t: TherapistProfile) -> dict:
    return {
        "id": t.id,
        "display_name": t.display_name,
        "bio": t.bio,
        "credentials": t.credentials or [],
        "specialties": t.specialties or [],
        "languages": t.languages or [],
        "hourly_rate_cents": t.hourly_rate_cents,
        "currency": t.currency,
        "rating_avg": t.rating_avg,
        "rating_count": t.rating_count,
    }


async def suggest_for_user(db: AsyncSession, user_id: str, limit: int = 5) -> list[dict]:
    """Recommend therapists based on the user's recurring patterns + dream emotions.

    Matching heuristic:
      - Recurring nightmare-pattern → therapists with "nightmare" / "trauma"
      - High-arousal recurring emotion → "anxiety"
      - Recurring "lostness" / "chase" themes → "trauma"
      - Otherwise → general list ordered by rating
    """
    # Pull user's pattern signature
    p_res = await db.execute(
        select(RecurringPattern).where(RecurringPattern.user_id == user_id)
    )
    patterns = list(p_res.scalars().all())
    needed_specialties: set[str] = set()
    for p in patterns:
        name = (p.canonical_name or "").lower()
        if any(k in name for k in ("nightmare", "scared", "fear", "terror")):
            needed_specialties.add("nightmare")
        if any(k in name for k in ("chase", "trauma", "abuse")):
            needed_specialties.add("trauma")
        if any(k in name for k in ("anxious", "panic", "stress")):
            needed_specialties.add("anxiety")
        if "lucid" in name:
            needed_specialties.add("lucid")

    # Recent nightmare flag also matters
    d_res = await db.execute(
        select(DreamRecord).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.nightmare_flag == True,  # noqa: E712
        )).limit(20)
    )
    if list(d_res.scalars().all()):
        needed_specialties.add("nightmare")

    candidates = await list_therapists(db)

    if needed_specialties:
        scored = []
        for t in candidates:
            overlap = len(needed_specialties & set(t["specialties"]))
            if overlap > 0:
                scored.append((overlap, t))
        scored.sort(key=lambda x: (-x[0], -(x[1]["rating_avg"] or 0)))
        out = [{**t, "match_specialties": list(needed_specialties & set(t["specialties"]))}
               for _, t in scored[:limit]]
        if out:
            return out

    return candidates[:limit]


async def request_booking(
    db: AsyncSession,
    client_user_id: str,
    therapist_id: str,
    scheduled_for: datetime,
    duration_minutes: int = 50,
    shared_dream_ids: Optional[list[str]] = None,
    notes: str = "",
) -> TherapyBooking:
    """Create a booking row in 'requested' state. Caller must then create
    a payment for booking.price_cents — payment fulfillment marks it
    'confirmed'.
    """
    therapist = await db.get(TherapistProfile, therapist_id)
    if not therapist or not therapist.is_active or therapist.verification_status != "verified":
        raise LookupError("Therapist not available")

    price = int(therapist.hourly_rate_cents * (duration_minutes / 60))
    fee = int(price * PLATFORM_FEE_BPS / 10000)
    bk = TherapyBooking(
        client_user_id=client_user_id,
        therapist_id=therapist_id,
        scheduled_for=scheduled_for,
        duration_minutes=duration_minutes,
        status="requested",
        shared_dream_ids=shared_dream_ids or [],
        client_intake_notes=notes[:2000] if notes else None,
        price_cents=price,
        currency=therapist.currency,
        platform_fee_cents=fee,
    )
    db.add(bk)
    await db.commit()
    await db.refresh(bk)
    return bk


async def list_my_bookings(db: AsyncSession, user_id: str, as_therapist: bool = False) -> list[dict]:
    field = TherapyBooking.therapist_id if as_therapist else TherapyBooking.client_user_id
    if as_therapist:
        # therapist_id refers to TherapistProfile.id, look up first
        prof_res = await db.execute(select(TherapistProfile).where(TherapistProfile.user_id == user_id))
        prof = prof_res.scalar_one_or_none()
        if not prof:
            return []
        where = TherapyBooking.therapist_id == prof.id
    else:
        where = TherapyBooking.client_user_id == user_id

    res = await db.execute(
        select(TherapyBooking).where(where).order_by(TherapyBooking.scheduled_for.desc())
    )
    return [
        {
            "id": b.id,
            "therapist_id": b.therapist_id,
            "scheduled_for": b.scheduled_for.isoformat(),
            "duration_minutes": b.duration_minutes,
            "status": b.status.value if hasattr(b.status, "value") else str(b.status),
            "price_cents": b.price_cents,
            "currency": b.currency,
            "shared_dream_ids": b.shared_dream_ids or [],
        }
        for b in res.scalars().all()
    ]
