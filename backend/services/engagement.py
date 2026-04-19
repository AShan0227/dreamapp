"""Engagement primitives — comments, reactions, follows, daily picks,
challenges, referrals, sleep records.

Routes live in routers/engagement.py. This module owns the business logic
+ DB writes; routers stay thin.
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord, DreamStatus
from models.engagement import (
    DreamComment, DreamReaction, UserFollow,
    DailyPick, DreamChallenge, ChallengeSubmission,
    ReferralCode, ReferralRedemption, SleepRecord, CoinLedger,
)
from models.user import UserRecord


# ---------------- Comments / reactions --------------------------------------

ALLOWED_REACTIONS = {"like", "scary", "curious", "moon", "heart", "wow", "sad"}


async def _ensure_dream_visible(db: AsyncSession, dream_id: str, viewer_user_id: Optional[str]) -> DreamRecord:
    dream = await db.get(DreamRecord, dream_id)
    if not dream or dream.deleted_at is not None:
        raise LookupError("Dream not found")
    is_owner = viewer_user_id and dream.user_id == viewer_user_id
    if not dream.is_public and not is_owner:
        raise PermissionError("Dream is private")
    return dream


async def add_comment(
    db: AsyncSession, user_id: str, dream_id: str, body: str,
    parent_id: Optional[str] = None,
) -> DreamComment:
    """Add a top-level or threaded comment.

    Body is auto-scored for warmth via LLM (services/llm). Very negative
    scores (< 0.2) get auto-hidden pending review.
    """
    body = (body or "").strip()
    if not body:
        raise ValueError("Comment body required")
    if len(body) > 1000:
        raise ValueError("Comment too long (max 1000)")

    await _ensure_dream_visible(db, dream_id, user_id)

    warmth = await _score_warmth(body)

    c = DreamComment(
        dream_id=dream_id,
        user_id=user_id,
        body=body,
        parent_id=parent_id,
        warmth_score=warmth,
        is_hidden=warmth is not None and warmth < 0.2,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)

    # Side effects (best effort — failures don't break the comment write):
    # 1. Notify dream owner (different from commenter)
    # 2. Notify parent comment author on a reply
    # 3. Parse @mentions and notify each mentioned user
    try:
        from services.threads import notify, parse_and_record_mentions
        dream = await db.get(DreamRecord, dream_id)
        if dream and dream.user_id and dream.user_id != user_id:
            await notify(
                db, dream.user_id, "comment", actor_user_id=user_id,
                target_kind="dream", target_id=dream_id,
                payload={"comment_id": c.id, "preview": body[:120]},
            )
        if parent_id:
            parent = await db.get(DreamComment, parent_id)
            if parent and parent.user_id != user_id:
                await notify(
                    db, parent.user_id, "reply", actor_user_id=user_id,
                    target_kind="comment", target_id=parent_id,
                    payload={"comment_id": c.id, "preview": body[:120]},
                )
        await parse_and_record_mentions(db, body, user_id, "comment", c.id)
    except Exception as e:
        from services.observability import get_logger
        get_logger("engagement").warning("comment side-effects failed", extra={"dream_id": dream_id, "err": str(e)})
    return c


async def _score_warmth(body: str) -> Optional[float]:
    """LLM-scored warmth 0..1. Returns None on failure (defaults to visible)."""
    try:
        from services.llm import chat_completion
        raw = await chat_completion(
            messages=[{"role": "user", "content": (
                f"Rate the WARMTH of this comment from 0.0 (toxic, attacking) to 1.0 "
                f"(warm, supportive, curious). A neutral or factual comment is around 0.5. "
                f"Respond with ONLY the number.\n\nComment: {body[:500]}"
            )}],
            system="You are a content-moderation classifier. Output a single decimal number 0.0-1.0.",
            max_tokens=10,
            # Deterministic classifier — keep cache eligibility (temp <= 0.2 cutoff).
            temperature=0.0,
            timeout_s=15.0,  # short call; don't hold the comment-write request
        )
        s = raw.strip().split()[0]
        return max(0.0, min(1.0, float(s)))
    except Exception:
        return None


async def list_comments(db: AsyncSession, dream_id: str, viewer_user_id: Optional[str]) -> list[dict]:
    await _ensure_dream_visible(db, dream_id, viewer_user_id)
    res = await db.execute(
        select(DreamComment)
        .where(and_(DreamComment.dream_id == dream_id, DreamComment.is_hidden == False))  # noqa: E712
        .order_by(DreamComment.created_at.asc())
    )
    rows = list(res.scalars().all())

    # Hydrate nicknames (small N — no need to optimize)
    user_ids = sorted({r.user_id for r in rows})
    nicks: dict[str, str] = {}
    if user_ids:
        u_res = await db.execute(select(UserRecord).where(UserRecord.id.in_(user_ids)))
        nicks = {u.id: u.nickname for u in u_res.scalars().all()}

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "nickname": nicks.get(r.user_id, "Anonymous"),
            "body": r.body,
            "parent_id": r.parent_id,
            "warmth_score": r.warmth_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def toggle_reaction(
    db: AsyncSession, user_id: str, dream_id: str, kind: str,
) -> dict:
    """Toggle the (user, dream, kind) reaction on/off. Returns counts."""
    if kind not in ALLOWED_REACTIONS:
        raise ValueError(f"Unknown reaction kind: {kind}")
    await _ensure_dream_visible(db, dream_id, user_id)

    existing = await db.execute(
        select(DreamReaction).where(and_(
            DreamReaction.dream_id == dream_id,
            DreamReaction.user_id == user_id,
            DreamReaction.kind == kind,
        ))
    )
    row = existing.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
        added = False
    else:
        db.add(DreamReaction(dream_id=dream_id, user_id=user_id, kind=kind))
        await db.commit()
        added = True
        # Reward the OWNER + notify them
        dream = await db.get(DreamRecord, dream_id)
        if dream and dream.user_id and dream.user_id != user_id:
            await credit_coins(db, dream.user_id, 1, "earn_reaction_received", ref=dream_id)
            try:
                from services.threads import notify
                await notify(
                    db, dream.user_id, "reaction", actor_user_id=user_id,
                    target_kind="dream", target_id=dream_id,
                    payload={"kind": kind},
                )
            except Exception as e:
                from services.observability import get_logger
                get_logger("engagement").warning("reaction notify failed", extra={"err": str(e)})

    counts = await reaction_counts(db, dream_id)
    return {"added": added, "counts": counts}


async def reaction_counts(db: AsyncSession, dream_id: str) -> dict[str, int]:
    res = await db.execute(
        select(DreamReaction.kind, func.count(DreamReaction.id))
        .where(DreamReaction.dream_id == dream_id)
        .group_by(DreamReaction.kind)
    )
    return {kind: count for kind, count in res.all()}


# ---------------- Follow graph ----------------------------------------------

async def follow_user(db: AsyncSession, follower_id: str, followee_id: str) -> bool:
    if follower_id == followee_id:
        raise ValueError("Cannot follow yourself")
    target = await db.get(UserRecord, followee_id)
    if not target:
        raise LookupError("User not found")

    # Idempotent
    existing = await db.execute(
        select(UserFollow).where(and_(
            UserFollow.follower_id == follower_id,
            UserFollow.followee_id == followee_id,
        ))
    )
    if existing.scalar_one_or_none():
        return False
    db.add(UserFollow(follower_id=follower_id, followee_id=followee_id))
    await db.commit()
    # Notify the followee
    try:
        from services.threads import notify
        await notify(
            db, followee_id, "follow", actor_user_id=follower_id,
            target_kind="user", target_id=follower_id,
        )
    except Exception as e:
        from services.observability import get_logger
        get_logger("engagement").warning("follow notify failed", extra={"err": str(e)})
    return True


async def unfollow_user(db: AsyncSession, follower_id: str, followee_id: str) -> bool:
    res = await db.execute(
        select(UserFollow).where(and_(
            UserFollow.follower_id == follower_id,
            UserFollow.followee_id == followee_id,
        ))
    )
    row = res.scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def following_feed(db: AsyncSession, user_id: str, limit: int = 30) -> list[DreamRecord]:
    """Public dreams from people the user follows, newest first."""
    follow_res = await db.execute(
        select(UserFollow.followee_id).where(UserFollow.follower_id == user_id)
    )
    followee_ids = [r[0] for r in follow_res.all()]
    if not followee_ids:
        return []
    res = await db.execute(
        select(DreamRecord)
        .where(and_(
            DreamRecord.user_id.in_(followee_ids),
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.deleted_at.is_(None),
        ))
        .order_by(DreamRecord.created_at.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def follow_counts(db: AsyncSession, user_id: str) -> dict[str, int]:
    f_res = await db.execute(
        select(func.count(UserFollow.id)).where(UserFollow.followee_id == user_id)
    )
    fo_res = await db.execute(
        select(func.count(UserFollow.id)).where(UserFollow.follower_id == user_id)
    )
    return {
        "followers": int(f_res.scalar() or 0),
        "following": int(fo_res.scalar() or 0),
    }


# ---------------- Daily picks -----------------------------------------------

def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def auto_pick_today(db: AsyncSession) -> Optional[DailyPick]:
    """Pick the most-engaging public dream from the last 24h.

    Single aggregated SQL (was N+1: 1 candidate-fetch + 2 per-dream counts).
    For 50 candidates that was 101 round-trips; now it's 1.
    """
    cutoff = datetime.utcnow() - timedelta(hours=24)

    # LEFT JOIN counts of reactions + comments in one trip, ranked server-side.
    # Score = reactions + 2*non-hidden comments (comments worth more).
    reactions_subq = (
        select(
            DreamReaction.dream_id.label("d_id"),
            func.count(DreamReaction.id).label("rc"),
        )
        .group_by(DreamReaction.dream_id)
        .subquery()
    )
    comments_subq = (
        select(
            DreamComment.dream_id.label("d_id"),
            func.count(DreamComment.id).label("cc"),
        )
        .where(DreamComment.is_hidden == False)  # noqa: E712
        .group_by(DreamComment.dream_id)
        .subquery()
    )

    score_expr = (
        func.coalesce(reactions_subq.c.rc, 0)
        + func.coalesce(comments_subq.c.cc, 0) * 2
    ).label("score")

    stmt = (
        select(DreamRecord, score_expr)
        .outerjoin(reactions_subq, reactions_subq.c.d_id == DreamRecord.id)
        .outerjoin(comments_subq, comments_subq.c.d_id == DreamRecord.id)
        .where(and_(
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.status == DreamStatus.completed,
            DreamRecord.created_at >= cutoff,
            DreamRecord.deleted_at.is_(None),
        ))
        .order_by(score_expr.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        return None

    top, top_score = row[0], int(row[1] or 0)
    today = _today_key()

    # Idempotent — don't double-pick for the same day
    existing = await db.execute(
        select(DailyPick).where(and_(DailyPick.date_key == today, DailyPick.slot == "featured"))
    )
    pick = existing.scalar_one_or_none()
    if pick:
        pick.dream_id = top.id
        pick.pick_reason = {"score": top_score, "reactions": top_score}
    else:
        pick = DailyPick(
            date_key=today,
            slot="featured",
            dream_id=top.id,
            pick_reason={"score": top_score},
        )
        db.add(pick)
    await db.commit()
    return pick


async def get_today_picks(db: AsyncSession) -> list[dict]:
    today = _today_key()
    res = await db.execute(
        select(DailyPick).where(DailyPick.date_key == today)
    )
    picks = list(res.scalars().all())
    out = []
    for p in picks:
        d = await db.get(DreamRecord, p.dream_id)
        if not d or d.deleted_at is not None:
            continue
        out.append({
            "slot": p.slot,
            "dream_id": p.dream_id,
            "title": d.title,
            "blurb": p.blurb,
            "video_url": d.video_url,
            "pick_reason": p.pick_reason,
        })
    return out


# ---------------- Challenges ------------------------------------------------

async def list_active_challenges(db: AsyncSession) -> list[DreamChallenge]:
    res = await db.execute(
        select(DreamChallenge).where(DreamChallenge.is_active == True)  # noqa: E712
        .order_by(DreamChallenge.created_at.desc())
    )
    return list(res.scalars().all())


async def submit_to_challenge(
    db: AsyncSession, user_id: str, challenge_id: str, dream_id: str,
) -> ChallengeSubmission:
    challenge = await db.get(DreamChallenge, challenge_id)
    if not challenge or not challenge.is_active:
        raise LookupError("Challenge not active")
    dream = await db.get(DreamRecord, dream_id)
    if not dream or dream.user_id != user_id:
        raise PermissionError("Dream must be yours")
    if not dream.is_public:
        # Auto-publish on challenge entry — challenges are public by nature
        dream.is_public = True

    # Idempotent — one submission per (challenge, user)
    existing = await db.execute(
        select(ChallengeSubmission).where(and_(
            ChallengeSubmission.challenge_id == challenge_id,
            ChallengeSubmission.user_id == user_id,
        ))
    )
    sub = existing.scalar_one_or_none()
    if sub:
        sub.dream_id = dream_id  # allow swapping
    else:
        sub = ChallengeSubmission(
            challenge_id=challenge_id, user_id=user_id, dream_id=dream_id,
        )
        db.add(sub)
        challenge.submission_count = (challenge.submission_count or 0) + 1
    await db.commit()
    await db.refresh(sub)
    return sub


async def challenge_leaderboard(db: AsyncSession, challenge_id: str, limit: int = 30) -> list[dict]:
    res = await db.execute(
        select(ChallengeSubmission)
        .where(ChallengeSubmission.challenge_id == challenge_id)
        .order_by(ChallengeSubmission.vote_count.desc())
        .limit(limit)
    )
    rows = list(res.scalars().all())
    out = []
    for r in rows:
        d = await db.get(DreamRecord, r.dream_id)
        u = await db.get(UserRecord, r.user_id)
        if not d or d.deleted_at is not None:
            continue
        out.append({
            "submission_id": r.id,
            "dream_id": r.dream_id,
            "title": d.title,
            "video_url": d.video_url,
            "user_nickname": u.nickname if u else "Anonymous",
            "vote_count": r.vote_count,
        })
    return out


# ---------------- Referrals -------------------------------------------------

REFERRER_REWARD = 100  # coins
REFERRED_REWARD = 50


def _new_referral_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def get_or_create_referral_code(db: AsyncSession, user_id: str) -> ReferralCode:
    res = await db.execute(select(ReferralCode).where(ReferralCode.user_id == user_id))
    code = res.scalar_one_or_none()
    if code:
        return code

    # Try a few times in case of (extremely unlikely) collision
    for _ in range(5):
        candidate = _new_referral_code()
        dup = await db.execute(select(ReferralCode).where(ReferralCode.code == candidate))
        if not dup.scalar_one_or_none():
            break
    code = ReferralCode(user_id=user_id, code=candidate)
    db.add(code)
    await db.commit()
    await db.refresh(code)
    return code


async def redeem_referral(db: AsyncSession, referred_user_id: str, code: str) -> dict:
    """Called once per new user (right after first login). Idempotent."""
    code = (code or "").strip().upper()
    if not code:
        raise ValueError("Code required")

    # Already redeemed?
    existing = await db.execute(
        select(ReferralRedemption).where(ReferralRedemption.referred_user_id == referred_user_id)
    )
    if existing.scalar_one_or_none():
        return {"redeemed": False, "reason": "Already redeemed"}

    code_row = await db.execute(select(ReferralCode).where(ReferralCode.code == code))
    rc = code_row.scalar_one_or_none()
    if not rc:
        raise LookupError("Invalid code")
    if rc.user_id == referred_user_id:
        raise ValueError("Cannot redeem your own code")

    rd = ReferralRedemption(
        code=code,
        referrer_user_id=rc.user_id,
        referred_user_id=referred_user_id,
        referrer_reward_coins=REFERRER_REWARD,
        referred_reward_coins=REFERRED_REWARD,
    )
    db.add(rd)
    rc.use_count = (rc.use_count or 0) + 1
    await db.commit()

    # Credit both sides
    await credit_coins(db, rc.user_id, REFERRER_REWARD, "earn_referral", ref=referred_user_id)
    await credit_coins(db, referred_user_id, REFERRED_REWARD, "earn_referral", ref=rc.user_id)

    return {
        "redeemed": True,
        "referrer_reward": REFERRER_REWARD,
        "referred_reward": REFERRED_REWARD,
    }


# ---------------- Sleep records ---------------------------------------------

async def record_sleep(db: AsyncSession, user_id: str, payload: dict) -> SleepRecord:
    """Manual or imported sleep record. payload accepts the keys on
    SleepRecord plus an arbitrary `raw_payload`.
    """
    night_of_str = payload.get("night_of")
    if not night_of_str:
        raise ValueError("night_of required")
    if isinstance(night_of_str, str):
        try:
            night_of = datetime.fromisoformat(night_of_str.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("night_of must be ISO 8601")
    else:
        night_of = night_of_str

    rec = SleepRecord(
        user_id=user_id,
        night_of=night_of,
        duration_minutes=int(payload.get("duration_minutes", 0)),
        rem_minutes=payload.get("rem_minutes"),
        deep_minutes=payload.get("deep_minutes"),
        light_minutes=payload.get("light_minutes"),
        awake_minutes=payload.get("awake_minutes"),
        avg_hr=payload.get("avg_hr"),
        source=payload.get("source", "manual"),
        raw_payload=payload.get("raw_payload") or {},
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_sleep(db: AsyncSession, user_id: str, days: int = 30) -> list[dict]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    res = await db.execute(
        select(SleepRecord)
        .where(and_(SleepRecord.user_id == user_id, SleepRecord.night_of >= cutoff))
        .order_by(SleepRecord.night_of.desc())
    )
    return [
        {
            "id": r.id,
            "night_of": r.night_of.isoformat(),
            "duration_minutes": r.duration_minutes,
            "rem_minutes": r.rem_minutes,
            "deep_minutes": r.deep_minutes,
            "source": r.source,
        }
        for r in res.scalars().all()
    ]


# ---------------- Coin ledger -----------------------------------------------

# --- Coin balance denormalization ------------------------------------------
#
# Each credit/debit was doing O(ledger rows) SUM on every call — linear
# cost in user lifetime activity. We now cache the running balance on
# `users.coin_balance` (new column, migration 0009) and update it in the
# SAME transaction as the ledger insert. The ledger stays append-only as
# source of truth for audit + reconcile.
#
# On race: we use FOR UPDATE on the users row for debits so two concurrent
# spend attempts serialize (prevents double-spend). Credits don't need a
# lock — they can race safely since they only increase.
#
# Reconcile: `reconcile_coin_balance(user_id)` recomputes from ledger —
# run on demand + scheduled nightly. If a direct DB edit ever skews the
# cache, reconcile brings it back.

async def credit_coins(
    db: AsyncSession, user_id: str, amount: int,
    reason: str, ref: Optional[str] = None, note: Optional[str] = None,
) -> int:
    """Append a coin entry + update cached balance in the same transaction.
    Returns the new balance. Positive for earn, negative for spend.
    """
    if amount == 0:
        return await coin_balance(db, user_id)

    # Append-only ledger (always wins over any cache — source of truth)
    db.add(CoinLedger(
        user_id=user_id, delta=amount, reason=reason, ref=ref, note=note,
    ))

    # Update the cached balance on users row
    from models.user import UserRecord
    user = await db.get(UserRecord, user_id)
    if user is not None and hasattr(user, "coin_balance"):
        current = int(user.coin_balance or 0)
        user.coin_balance = current + amount
        new_balance = user.coin_balance
    else:
        new_balance = None

    await db.commit()

    # Fallback for any user row that doesn't have the column yet or is missing
    if new_balance is None:
        return await _coin_balance_from_ledger(db, user_id)
    return int(new_balance)


async def debit_coins(
    db: AsyncSession, user_id: str, amount: int,
    reason: str, ref: Optional[str] = None,
) -> int:
    """Spend coins with race-free balance check (SELECT FOR UPDATE).

    Two concurrent /gift calls with the same user can no longer push balance
    negative — the second one blocks until the first commits, then reads the
    updated balance and correctly rejects if insufficient.
    """
    if amount <= 0:
        raise ValueError("Debit amount must be positive")

    from models.user import UserRecord
    # Lock the user row so concurrent debits serialize.
    is_pg = _is_postgres(db)
    stmt = select(UserRecord).where(UserRecord.id == user_id)
    if is_pg:
        stmt = stmt.with_for_update()
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        raise ValueError("User not found")

    bal = int(getattr(user, "coin_balance", None) or 0)
    # If the column is unpopulated/NULL, fall back to ledger sum once to repair
    if bal == 0 and hasattr(user, "coin_balance") and user.coin_balance is None:
        bal = await _coin_balance_from_ledger(db, user_id)
        user.coin_balance = bal

    if bal < amount:
        # Release the lock by rolling back any pending state on this row
        await db.rollback()
        raise ValueError(f"Insufficient coins (have {bal}, need {amount})")

    # Now atomically append ledger + decrement cached balance
    db.add(CoinLedger(
        user_id=user_id, delta=-amount, reason=reason, ref=ref,
    ))
    user.coin_balance = bal - amount
    await db.commit()
    return int(user.coin_balance)


def _is_postgres(db: AsyncSession) -> bool:
    try:
        return (db.bind.dialect.name if db.bind else "") == "postgresql"
    except Exception:
        return False


async def coin_balance(db: AsyncSession, user_id: str) -> int:
    """Read cached balance from users.coin_balance. Falls back to ledger
    SUM if the column is NULL (fresh user hasn't transacted yet)."""
    from models.user import UserRecord
    user = await db.get(UserRecord, user_id)
    if user is None:
        return 0
    cached = getattr(user, "coin_balance", None)
    if cached is not None:
        return int(cached)
    # Repair-on-read: recompute + persist
    total = await _coin_balance_from_ledger(db, user_id)
    if hasattr(user, "coin_balance"):
        user.coin_balance = total
        await db.commit()
    return total


async def _coin_balance_from_ledger(db: AsyncSession, user_id: str) -> int:
    """Source-of-truth: sum of all ledger entries. Called by fallback paths
    + reconcile_coin_balance + startup migration."""
    res = await db.execute(
        select(func.coalesce(func.sum(CoinLedger.delta), 0)).where(CoinLedger.user_id == user_id)
    )
    return int(res.scalar() or 0)


async def reconcile_coin_balance(db: AsyncSession, user_id: str) -> tuple[int, int]:
    """Recompute cached balance from ledger for one user. Returns (before, after).
    Safe to call any time — idempotent. Useful for admin tools / nightly job.
    """
    from models.user import UserRecord
    user = await db.get(UserRecord, user_id)
    if user is None or not hasattr(user, "coin_balance"):
        return (0, 0)
    before = int(user.coin_balance or 0)
    after = await _coin_balance_from_ledger(db, user_id)
    if before != after:
        user.coin_balance = after
        await db.commit()
    return (before, after)


async def coin_history(db: AsyncSession, user_id: str, limit: int = 50) -> list[dict]:
    res = await db.execute(
        select(CoinLedger)
        .where(CoinLedger.user_id == user_id)
        .order_by(CoinLedger.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id,
            "delta": r.delta,
            "reason": r.reason,
            "ref": r.ref,
            "note": r.note,
            "created_at": r.created_at.isoformat(),
        }
        for r in res.scalars().all()
    ]
