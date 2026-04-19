"""Service layer for the 20 Threads-style social patterns.

All functions take an AsyncSession + caller user_id (or other typed args)
and return either ORM rows or plain dicts. Routes in routers/threads.py
stay thin. Notifications fan out via `notify()` from anywhere.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.user import UserRecord
from models.engagement import (
    DreamComment, DreamReaction, UserFollow,
)
from models.threads import (
    UserProfileExtra, Notification, Mention,
    DreamQuote, HashtagFollow, HashtagUsage,
    DreamBookmark, DreamPoll, PollVote,
    UserMute, UserBlock, ContentReport,
    DirectThread, DirectMessage, DreamSeries,
)


# ---------------- Profiles + handles ----------------------------------------

HANDLE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,24}$")


async def get_or_create_profile(db: AsyncSession, user_id: str) -> UserProfileExtra:
    res = await db.execute(select(UserProfileExtra).where(UserProfileExtra.user_id == user_id))
    p = res.scalar_one_or_none()
    if p:
        return p
    p = UserProfileExtra(user_id=user_id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def update_profile(
    db: AsyncSession, user_id: str,
    handle: Optional[str] = None,
    bio: Optional[str] = None,
    location: Optional[str] = None,
    link: Optional[str] = None,
    private_account: Optional[bool] = None,
    who_can_comment: Optional[str] = None,
    who_can_dm: Optional[str] = None,
    who_can_mention: Optional[str] = None,
) -> UserProfileExtra:
    p = await get_or_create_profile(db, user_id)
    if handle is not None:
        h = handle.strip().lstrip("@")
        if not HANDLE_RE.match(h):
            raise ValueError("Handle must be 3-25 chars, letters/digits/_, starting with a letter")
        # Uniqueness — DB unique index will also catch this; check first for nicer error
        existing = await db.execute(
            select(UserProfileExtra).where(and_(UserProfileExtra.handle == h, UserProfileExtra.user_id != user_id))
        )
        if existing.scalar_one_or_none():
            raise ValueError("Handle taken")
        p.handle = h
    if bio is not None: p.bio = bio[:500]
    if location is not None: p.location = location[:80]
    if link is not None: p.link = link[:300]
    if private_account is not None: p.private_account = bool(private_account)
    for k, v in (("who_can_comment", who_can_comment), ("who_can_dm", who_can_dm), ("who_can_mention", who_can_mention)):
        if v is not None:
            if v not in ("anyone", "following", "mutual", "nobody"):
                raise ValueError(f"Invalid {k}: {v}")
            setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return p


async def resolve_handle(db: AsyncSession, handle: str) -> Optional[UserProfileExtra]:
    h = handle.strip().lstrip("@").lower()
    res = await db.execute(select(UserProfileExtra).where(UserProfileExtra.handle == h))
    return res.scalar_one_or_none()


async def public_profile(db: AsyncSession, user_id: str, viewer_user_id: Optional[str] = None) -> dict:
    """Profile page payload — used by the @handle route + UI."""
    user = await db.get(UserRecord, user_id)
    if not user:
        raise LookupError("User not found")
    profile = await get_or_create_profile(db, user_id)

    fol_res = await db.execute(select(func.count(UserFollow.id)).where(UserFollow.followee_id == user_id))
    foling_res = await db.execute(select(func.count(UserFollow.id)).where(UserFollow.follower_id == user_id))
    dream_res = await db.execute(
        select(func.count(DreamRecord.id)).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.deleted_at.is_(None),
        ))
    )
    pub_res = await db.execute(
        select(func.count(DreamRecord.id)).where(and_(
            DreamRecord.user_id == user_id,
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.deleted_at.is_(None),
        ))
    )

    is_following = False
    is_self = bool(viewer_user_id and viewer_user_id == user_id)
    if viewer_user_id and not is_self:
        f = await db.execute(select(UserFollow).where(and_(
            UserFollow.follower_id == viewer_user_id,
            UserFollow.followee_id == user_id,
        )))
        is_following = f.scalar_one_or_none() is not None

    return {
        "id": user.id,
        "nickname": user.nickname,
        "handle": profile.handle,
        "bio": profile.bio,
        "location": profile.location,
        "link": profile.link,
        "is_verified": profile.is_verified,
        "verified_kind": profile.verified_kind,
        "private_account": profile.private_account,
        "pinned_dream_ids": profile.pinned_dream_ids or [],
        "follower_count": int(fol_res.scalar() or 0),
        "following_count": int(foling_res.scalar() or 0),
        "dream_count": int(dream_res.scalar() or 0),
        "public_dream_count": int(pub_res.scalar() or 0),
        "is_following": is_following,
        "is_self": is_self,
    }


async def pin_dreams(db: AsyncSession, user_id: str, dream_ids: list[str]) -> UserProfileExtra:
    if len(dream_ids) > 3:
        raise ValueError("Max 3 pinned dreams")
    # Validate ownership
    for did in dream_ids:
        d = await db.get(DreamRecord, did)
        if not d or d.user_id != user_id:
            raise PermissionError(f"Dream {did} not yours")
    p = await get_or_create_profile(db, user_id)
    p.pinned_dream_ids = dream_ids
    await db.commit()
    await db.refresh(p)
    return p


# ---------------- Notifications --------------------------------------------

async def notify(
    db: AsyncSession, user_id: str, kind: str,
    actor_user_id: Optional[str] = None,
    target_kind: Optional[str] = None, target_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Notification:
    """Create one notification row + fire out-of-app channels (push/wechat).

    In-app row is authoritative; push/wechat are fire-and-forget. Skips
    self-notifications + blocked pairs.
    """
    if actor_user_id and actor_user_id == user_id:
        return None  # don't notify yourself
    if actor_user_id:
        b = await db.execute(select(UserBlock).where(or_(
            and_(UserBlock.blocker_user_id == user_id, UserBlock.blocked_user_id == actor_user_id),
            and_(UserBlock.blocker_user_id == actor_user_id, UserBlock.blocked_user_id == user_id),
        )))
        if b.scalar_one_or_none():
            return None
    n = Notification(
        user_id=user_id, kind=kind, actor_user_id=actor_user_id,
        target_kind=target_kind, target_id=target_id, payload=payload or {},
    )
    db.add(n)
    await db.commit()

    # Best-effort out-of-app fanout. Look up the recipient ONCE on the
    # caller's existing session rather than opening a new pool connection
    # per notification (previously a pool-exhaustion footgun under load).
    try:
        from models.user import UserRecord
        recipient = await db.get(UserRecord, user_id)
    except Exception:
        recipient = None

    if recipient is not None and not getattr(recipient, "is_banned", False):
        ptoken = getattr(recipient, "push_token", None)
        openid = getattr(recipient, "wechat_openid", None)
        if ptoken or openid:
            try:
                import asyncio
                task = asyncio.ensure_future(
                    _dispatch_push(
                        ptoken=ptoken,
                        openid=openid,
                        locale=getattr(recipient, "locale", "zh-CN") or "zh-CN",
                        kind=kind,
                        payload=payload or {},
                    )
                )
                # Keep reference so GC doesn't cancel mid-flight (Python asyncio
                # holds only weakrefs to scheduled tasks).
                _pending_push_tasks.add(task)
                task.add_done_callback(_pending_push_tasks.discard)
            except Exception:
                pass
    return n


# Module-level set of pending fire-and-forget push tasks — prevents GC from
# cancelling them before they complete. Bounded by natural task lifetime.
_pending_push_tasks: set = set()


async def _dispatch_push(
    *,
    ptoken: Optional[str],
    openid: Optional[str],
    locale: str,
    kind: str,
    payload: dict,
) -> None:
    """Inner — already has recipient creds, just dispatches to providers."""
    try:
        from services import push as _push
        title, body = _render_push_copy(kind, payload, locale)
        tpl_data = _render_wechat_template_data(kind, payload)
        await _push.dispatch(
            user_push_token=ptoken,
            user_wechat_openid=openid,
            kind=kind,
            title=title,
            body=body,
            data={"kind": kind, **{k: str(v) for k, v in payload.items() if isinstance(v, (str, int, float, bool))}},
            wechat_template_data=tpl_data,
            wechat_page=payload.get("page"),
        )
    except Exception as e:
        from services.observability import get_logger
        get_logger("notifier").exception("push fanout failed", extra={"kind": kind, "err": str(e)})


def _render_push_copy(kind: str, payload: dict, locale: str) -> tuple[str, str]:
    """Short push title + body, locale-aware."""
    zh = locale.startswith("zh")
    actor = payload.get("actor_nickname", "有人" if zh else "Someone")
    dream_title = payload.get("dream_title", "")
    copy = {
        "comment": (f"{actor} 评论了你的梦" if zh else f"{actor} commented on your dream",
                    f"「{dream_title}」" if dream_title else ""),
        "reaction": (f"{actor} 点了反应" if zh else f"{actor} reacted",
                     f"「{dream_title}」" if dream_title else ""),
        "follow": (f"{actor} 关注了你" if zh else f"{actor} followed you", ""),
        "mention": (f"{actor} @ 了你" if zh else f"{actor} mentioned you", ""),
        "dm": (f"{actor} 发来新消息" if zh else f"New message from {actor}", ""),
        "quote": (f"{actor} 引用了你的梦" if zh else f"{actor} quoted your dream", ""),
        "video_ready": ("你的梦视频好了" if zh else "Your dream video is ready", dream_title),
        "payment_success": ("支付成功" if zh else "Payment complete", payload.get("purpose", "")),
    }
    return copy.get(kind, (f"DreamApp: {kind}", ""))


def _render_wechat_template_data(kind: str, payload: dict) -> dict:
    """Build WeChat subscribe-message data dict. Template shape depends on
    registered template — this is a best-effort generic shape. Ops tunes
    per template.
    """
    dream_title = payload.get("dream_title", "")[:20]
    actor = payload.get("actor_nickname", "")[:20]
    return {
        "thing1": {"value": (actor or "DreamApp")[:20]},
        "thing2": {"value": (dream_title or kind)[:20]},
    }


async def list_notifications(db: AsyncSession, user_id: str, unread_only: bool = False, limit: int = 50) -> list[dict]:
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.is_read == False)  # noqa: E712
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = list(res.scalars().all())

    actor_ids = sorted({r.actor_user_id for r in rows if r.actor_user_id})
    nicks: dict[str, str] = {}
    if actor_ids:
        u_res = await db.execute(select(UserRecord).where(UserRecord.id.in_(actor_ids)))
        nicks = {u.id: u.nickname for u in u_res.scalars().all()}

    return [
        {
            "id": r.id, "kind": r.kind, "actor_user_id": r.actor_user_id,
            "actor_nickname": nicks.get(r.actor_user_id) if r.actor_user_id else None,
            "target_kind": r.target_kind, "target_id": r.target_id,
            "payload": r.payload or {}, "is_read": r.is_read,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def unread_count(db: AsyncSession, user_id: str) -> int:
    res = await db.execute(
        select(func.count(Notification.id)).where(and_(
            Notification.user_id == user_id, Notification.is_read == False,  # noqa: E712
        ))
    )
    return int(res.scalar() or 0)


async def mark_read(db: AsyncSession, user_id: str, notification_ids: Optional[list[str]] = None) -> int:
    """Mark one/many/all notifications read. Returns count updated."""
    from sqlalchemy import update as _update
    stmt = _update(Notification).where(Notification.user_id == user_id).values(is_read=True)
    if notification_ids:
        stmt = stmt.where(Notification.id.in_(notification_ids))
    else:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
    r = await db.execute(stmt)
    await db.commit()
    return r.rowcount or 0


# ---------------- @-mentions -----------------------------------------------

MENTION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{2,24})")


async def parse_and_record_mentions(
    db: AsyncSession, body: str, mentioner_user_id: str,
    source_kind: str, source_id: str,
) -> list[str]:
    """Find @handles in the body, resolve to user_ids, persist Mention rows,
    and dispatch notifications. Returns the list of mentioned user_ids.

    Idempotent on (source_kind, source_id, mentioned) — re-parsing the same
    edited body won't double-fire notifications.
    """
    handles = list(set(MENTION_RE.findall(body or "")))
    if not handles:
        return []

    res = await db.execute(
        select(UserProfileExtra).where(UserProfileExtra.handle.in_([h.lower() for h in handles]))
    )
    found = {p.handle: p.user_id for p in res.scalars().all()}
    mentioned_ids: list[str] = []
    for h in handles:
        uid = found.get(h.lower())
        if not uid or uid == mentioner_user_id:
            continue
        # Dedupe: skip if already recorded for this source
        existing = await db.execute(
            select(Mention).where(and_(
                Mention.source_kind == source_kind,
                Mention.source_id == source_id,
                Mention.mentioned_user_id == uid,
            ))
        )
        if existing.scalar_one_or_none():
            continue
        db.add(Mention(
            mentioner_user_id=mentioner_user_id, mentioned_user_id=uid,
            source_kind=source_kind, source_id=source_id,
        ))
        mentioned_ids.append(uid)
    await db.commit()
    # Notifications
    for uid in mentioned_ids:
        await notify(
            db, uid, "mention", actor_user_id=mentioner_user_id,
            target_kind=source_kind, target_id=source_id,
            payload={"preview": (body or "")[:120]},
        )
    return mentioned_ids


# ---------------- Hashtags --------------------------------------------------

HASHTAG_RE = re.compile(r"#([\w\u4e00-\u9fff]{1,40})")  # alnum + Chinese


async def index_hashtags_for_dream(db: AsyncSession, dream_id: str, user_id: str, body: str) -> list[str]:
    """Extract #tags from a dream body / title, write HashtagUsage rows."""
    tags = list({t.lower() for t in HASHTAG_RE.findall(body or "")})
    for tag in tags:
        # Idempotent via composite UQ
        existing = await db.execute(
            select(HashtagUsage).where(and_(
                HashtagUsage.tag == tag, HashtagUsage.dream_id == dream_id,
            ))
        )
        if existing.scalar_one_or_none():
            continue
        db.add(HashtagUsage(tag=tag, dream_id=dream_id, user_id=user_id))
    await db.commit()
    return tags


async def follow_hashtag(db: AsyncSession, user_id: str, tag: str) -> bool:
    tag = tag.strip().lstrip("#").lower()
    if not tag:
        raise ValueError("Tag required")
    existing = await db.execute(
        select(HashtagFollow).where(and_(HashtagFollow.user_id == user_id, HashtagFollow.tag == tag))
    )
    if existing.scalar_one_or_none():
        return False
    db.add(HashtagFollow(user_id=user_id, tag=tag))
    await db.commit()
    return True


async def unfollow_hashtag(db: AsyncSession, user_id: str, tag: str) -> bool:
    tag = tag.strip().lstrip("#").lower()
    res = await db.execute(
        select(HashtagFollow).where(and_(HashtagFollow.user_id == user_id, HashtagFollow.tag == tag))
    )
    row = res.scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def list_followed_hashtags(db: AsyncSession, user_id: str) -> list[str]:
    res = await db.execute(select(HashtagFollow.tag).where(HashtagFollow.user_id == user_id))
    return [r[0] for r in res.all()]


async def hashtag_dreams(db: AsyncSession, tag: str, limit: int = 30) -> list[dict]:
    """Public dreams under a tag, newest first."""
    tag = tag.strip().lstrip("#").lower()
    res = await db.execute(
        select(HashtagUsage, DreamRecord)
        .join(DreamRecord, DreamRecord.id == HashtagUsage.dream_id)
        .where(and_(
            HashtagUsage.tag == tag,
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.deleted_at.is_(None),
        ))
        .order_by(HashtagUsage.created_at.desc())
        .limit(limit)
    )
    out = []
    for usage, d in res.all():
        out.append({
            "dream_id": d.id, "title": d.title, "video_url": d.video_url,
            "user_id": d.user_id, "created_at": d.created_at.isoformat(),
        })
    return out


async def trending_hashtags(db: AsyncSession, hours: int = 24, limit: int = 20) -> list[dict]:
    """Most-used tags in the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    res = await db.execute(
        select(HashtagUsage.tag, func.count(HashtagUsage.id).label("n"))
        .where(HashtagUsage.created_at >= cutoff)
        .group_by(HashtagUsage.tag)
        .order_by(func.count(HashtagUsage.id).desc())
        .limit(limit)
    )
    return [{"tag": t, "count": int(n)} for t, n in res.all()]


# ---------------- For You feed ---------------------------------------------

async def for_you_feed(db: AsyncSession, user_id: str, limit: int = 30) -> list[dict]:
    """Algorithmic ranking: shared tags + reaction count + recency.

    Cheap implementation: pull user's own symbol_tags + theme_tags signature,
    score recent public dreams by overlap, weight by reaction count, drop
    blocked / muted users.
    """
    own_res = await db.execute(
        select(DreamRecord).where(DreamRecord.user_id == user_id)
    )
    own = list(own_res.scalars().all())
    own_tags: set[str] = set()
    for d in own:
        for t in (d.symbol_tags or []) + (d.theme_tags or []):
            if t: own_tags.add(t.lower())

    # Excluded users (block both ways + mute one way)
    excluded: set[str] = set()
    for query in (
        select(UserBlock.blocked_user_id).where(UserBlock.blocker_user_id == user_id),
        select(UserBlock.blocker_user_id).where(UserBlock.blocked_user_id == user_id),
        select(UserMute.muted_user_id).where(UserMute.muter_user_id == user_id),
    ):
        r = await db.execute(query)
        for row in r.all():
            excluded.add(row[0])
    excluded.add(user_id)  # never recommend my own dreams in FYP

    cutoff = datetime.utcnow() - timedelta(days=14)

    # Single SQL: candidate dreams LEFT JOIN reaction counts. Previously one
    # extra `count(*)` query per candidate dream (up to 300 × round-trip);
    # this turns it into a single aggregated query.
    reactions_subq = (
        select(
            DreamReaction.dream_id.label("d_id"),
            func.count(DreamReaction.id).label("rc"),
        )
        .group_by(DreamReaction.dream_id)
        .subquery()
    )
    stmt = (
        select(DreamRecord, func.coalesce(reactions_subq.c.rc, 0).label("reactions"))
        .outerjoin(reactions_subq, reactions_subq.c.d_id == DreamRecord.id)
        .where(and_(
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.deleted_at.is_(None),
            DreamRecord.created_at >= cutoff,
            DreamRecord.user_id.notin_(list(excluded)) if excluded else True,
        ))
        .limit(300)
    )
    pool_res = await db.execute(stmt)
    rows = pool_res.all()
    if not rows:
        return []

    scored = []
    now = datetime.utcnow()
    for d, reactions in rows:
        reactions = int(reactions or 0)
        d_tags = {(t or "").lower() for t in (d.symbol_tags or []) + (d.theme_tags or []) if t}
        overlap = len(own_tags & d_tags) if own_tags else 0
        age_days = max(0, (now - d.created_at).days)
        recency = max(0.5, 1.0 - age_days / 28.0)
        score = (overlap * 5 + reactions * 2 + 1) * recency
        scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [
        {
            "dream_id": d.id, "title": d.title, "video_url": d.video_url,
            "user_id": d.user_id, "score": round(score, 2),
            "created_at": d.created_at.isoformat(),
        }
        for score, d in scored[:limit]
    ]


# ---------------- Bookmarks -------------------------------------------------

async def bookmark(db: AsyncSession, user_id: str, dream_id: str, folder: str = "default") -> bool:
    existing = await db.execute(
        select(DreamBookmark).where(and_(
            DreamBookmark.user_id == user_id, DreamBookmark.dream_id == dream_id,
        ))
    )
    if existing.scalar_one_or_none():
        return False
    db.add(DreamBookmark(user_id=user_id, dream_id=dream_id, folder=folder))
    await db.commit()
    return True


async def unbookmark(db: AsyncSession, user_id: str, dream_id: str) -> bool:
    res = await db.execute(
        select(DreamBookmark).where(and_(
            DreamBookmark.user_id == user_id, DreamBookmark.dream_id == dream_id,
        ))
    )
    row = res.scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def list_bookmarks(db: AsyncSession, user_id: str, folder: Optional[str] = None) -> list[dict]:
    q = select(DreamBookmark, DreamRecord).join(
        DreamRecord, DreamRecord.id == DreamBookmark.dream_id
    ).where(DreamBookmark.user_id == user_id)
    if folder:
        q = q.where(DreamBookmark.folder == folder)
    q = q.order_by(DreamBookmark.created_at.desc())
    res = await db.execute(q)
    return [
        {
            "bookmark_id": b.id, "folder": b.folder,
            "dream_id": d.id, "title": d.title, "video_url": d.video_url,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b, d in res.all()
    ]


# ---------------- Polls -----------------------------------------------------

async def create_poll(
    db: AsyncSession, user_id: str, dream_id: str, question: str, options: list[str],
    closes_in_hours: Optional[int] = 72,
) -> DreamPoll:
    if len(options) < 2 or len(options) > 6:
        raise ValueError("2-6 options required")
    closes_at = datetime.utcnow() + timedelta(hours=closes_in_hours) if closes_in_hours else None
    structured = [{"id": f"opt{i}", "text": (o or "")[:120]} for i, o in enumerate(options)]
    p = DreamPoll(
        dream_id=dream_id, creator_user_id=user_id,
        question=question[:500], options=structured, closes_at=closes_at,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def vote_poll(db: AsyncSession, user_id: str, poll_id: str, option_id: str) -> dict:
    poll = await db.get(DreamPoll, poll_id)
    if not poll:
        raise LookupError("Poll not found")
    if poll.closes_at and poll.closes_at < datetime.utcnow():
        raise ValueError("Poll closed")
    if option_id not in {o.get("id") for o in (poll.options or [])}:
        raise ValueError("Unknown option")
    # Replace existing vote
    existing = await db.execute(
        select(PollVote).where(and_(PollVote.poll_id == poll_id, PollVote.user_id == user_id))
    )
    row = existing.scalar_one_or_none()
    if row:
        row.option_id = option_id
    else:
        db.add(PollVote(poll_id=poll_id, user_id=user_id, option_id=option_id))
    await db.commit()
    return await poll_results(db, poll_id)


async def poll_results(db: AsyncSession, poll_id: str) -> dict:
    poll = await db.get(DreamPoll, poll_id)
    if not poll:
        raise LookupError("Poll not found")
    res = await db.execute(
        select(PollVote.option_id, func.count(PollVote.id))
        .where(PollVote.poll_id == poll_id)
        .group_by(PollVote.option_id)
    )
    counts = {oid: int(n) for oid, n in res.all()}
    total = sum(counts.values()) or 1
    return {
        "poll_id": poll_id,
        "question": poll.question,
        "options": [
            {**o, "votes": counts.get(o["id"], 0), "pct": round(counts.get(o["id"], 0) * 100 / total, 1)}
            for o in (poll.options or [])
        ],
        "total_votes": sum(counts.values()),
        "closes_at": poll.closes_at.isoformat() if poll.closes_at else None,
    }


# ---------------- Mute / Block / Report ------------------------------------

async def toggle_mute(db: AsyncSession, muter: str, target: str) -> dict:
    if muter == target:
        raise ValueError("Cannot mute yourself")
    res = await db.execute(select(UserMute).where(and_(
        UserMute.muter_user_id == muter, UserMute.muted_user_id == target,
    )))
    row = res.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
        return {"muted": False}
    db.add(UserMute(muter_user_id=muter, muted_user_id=target))
    await db.commit()
    return {"muted": True}


async def toggle_block(db: AsyncSession, blocker: str, target: str) -> dict:
    if blocker == target:
        raise ValueError("Cannot block yourself")
    res = await db.execute(select(UserBlock).where(and_(
        UserBlock.blocker_user_id == blocker, UserBlock.blocked_user_id == target,
    )))
    row = res.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
        return {"blocked": False}
    # Blocking auto-unfollows both ways
    await db.execute(delete(UserFollow).where(or_(
        and_(UserFollow.follower_id == blocker, UserFollow.followee_id == target),
        and_(UserFollow.follower_id == target, UserFollow.followee_id == blocker),
    )))
    db.add(UserBlock(blocker_user_id=blocker, blocked_user_id=target))
    await db.commit()
    return {"blocked": True}


async def report_content(
    db: AsyncSession, reporter: str, target_kind: str, target_id: str,
    reason: str, detail: str = "",
) -> ContentReport:
    if reason not in ("spam", "harassment", "graphic", "self_harm", "misinformation", "other"):
        raise ValueError(f"Invalid reason: {reason}")
    r = ContentReport(
        reporter_user_id=reporter, target_kind=target_kind, target_id=target_id,
        reason=reason, detail=detail[:1000] if detail else None,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


# ---------------- DMs (mutual-follow gated) --------------------------------

def _dm_pair(a: str, b: str) -> tuple[str, str]:
    """Always return user_a < user_b alphabetically — single canonical thread."""
    return (a, b) if a < b else (b, a)


async def _are_mutual(db: AsyncSession, a: str, b: str) -> bool:
    if a == b:
        return False
    r1 = await db.execute(select(UserFollow).where(and_(
        UserFollow.follower_id == a, UserFollow.followee_id == b,
    )))
    if not r1.scalar_one_or_none():
        return False
    r2 = await db.execute(select(UserFollow).where(and_(
        UserFollow.follower_id == b, UserFollow.followee_id == a,
    )))
    return r2.scalar_one_or_none() is not None


async def get_or_create_thread(db: AsyncSession, sender: str, recipient: str) -> DirectThread:
    """Open a 1-1 thread. Recipient's privacy settings + mutual-follow gate."""
    if sender == recipient:
        raise ValueError("Cannot DM yourself")
    # Recipient privacy
    rp = await get_or_create_profile(db, recipient)
    if rp.who_can_dm == "nobody":
        raise PermissionError("Recipient does not accept DMs")
    if rp.who_can_dm == "mutual" and not await _are_mutual(db, sender, recipient):
        raise PermissionError("Recipient only accepts DMs from mutual follows")
    if rp.who_can_dm == "following":
        # they must follow me
        f = await db.execute(select(UserFollow).where(and_(
            UserFollow.follower_id == recipient, UserFollow.followee_id == sender,
        )))
        if not f.scalar_one_or_none():
            raise PermissionError("Recipient only accepts DMs from people they follow")
    # Block check
    b = await db.execute(select(UserBlock).where(or_(
        and_(UserBlock.blocker_user_id == sender, UserBlock.blocked_user_id == recipient),
        and_(UserBlock.blocker_user_id == recipient, UserBlock.blocked_user_id == sender),
    )))
    if b.scalar_one_or_none():
        raise PermissionError("Cannot DM this user")

    a, c = _dm_pair(sender, recipient)
    res = await db.execute(select(DirectThread).where(and_(
        DirectThread.user_a_id == a, DirectThread.user_b_id == c,
    )))
    th = res.scalar_one_or_none()
    if th:
        return th
    th = DirectThread(user_a_id=a, user_b_id=c)
    db.add(th)
    await db.commit()
    await db.refresh(th)
    return th


async def send_dm(db: AsyncSession, sender: str, recipient: str, body: str) -> DirectMessage:
    body = (body or "").strip()
    if not body:
        raise ValueError("Empty message")
    if len(body) > 2000:
        raise ValueError("Message too long (max 2000)")
    th = await get_or_create_thread(db, sender, recipient)
    msg = DirectMessage(thread_id=th.id, sender_user_id=sender, body=body)
    db.add(msg)
    th.last_message_at = datetime.utcnow()
    await db.commit()
    await db.refresh(msg)
    # Notify recipient
    await notify(db, recipient, "dm", actor_user_id=sender,
                 target_kind="thread", target_id=th.id,
                 payload={"preview": body[:120]})
    return msg


async def list_dm_threads(db: AsyncSession, user_id: str) -> list[dict]:
    res = await db.execute(
        select(DirectThread).where(or_(
            DirectThread.user_a_id == user_id, DirectThread.user_b_id == user_id,
        )).order_by(DirectThread.last_message_at.desc().nullslast())
    )
    threads = list(res.scalars().all())
    out = []
    for t in threads:
        other_id = t.user_b_id if t.user_a_id == user_id else t.user_a_id
        other = await db.get(UserRecord, other_id)
        # Last message preview + unread count
        m = await db.execute(
            select(DirectMessage).where(DirectMessage.thread_id == t.id)
            .order_by(DirectMessage.created_at.desc()).limit(1)
        )
        last = m.scalar_one_or_none()
        u_res = await db.execute(
            select(func.count(DirectMessage.id)).where(and_(
                DirectMessage.thread_id == t.id,
                DirectMessage.sender_user_id != user_id,
                DirectMessage.is_read == False,  # noqa: E712
            ))
        )
        out.append({
            "thread_id": t.id,
            "other_user_id": other_id,
            "other_nickname": other.nickname if other else "Anonymous",
            "last_message_preview": last.body[:120] if last else None,
            "last_message_at": (last.created_at.isoformat() if last and last.created_at else None),
            "unread_count": int(u_res.scalar() or 0),
        })
    return out


async def list_dm_messages(db: AsyncSession, user_id: str, thread_id: str, limit: int = 100) -> list[dict]:
    th = await db.get(DirectThread, thread_id)
    if not th or user_id not in (th.user_a_id, th.user_b_id):
        raise PermissionError("Not a participant")
    res = await db.execute(
        select(DirectMessage).where(DirectMessage.thread_id == thread_id)
        .order_by(DirectMessage.created_at.asc()).limit(limit)
    )
    msgs = list(res.scalars().all())
    # Mark mine as read
    from sqlalchemy import update as _update
    await db.execute(
        _update(DirectMessage).where(and_(
            DirectMessage.thread_id == thread_id,
            DirectMessage.sender_user_id != user_id,
            DirectMessage.is_read == False,  # noqa: E712
        )).values(is_read=True)
    )
    await db.commit()
    return [
        {
            "id": m.id, "sender_user_id": m.sender_user_id,
            "body": m.body, "is_read": m.is_read,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


# ---------------- Quote / repost -------------------------------------------

async def quote_dream(
    db: AsyncSession, user_id: str, quoted_dream_id: str,
    body: str, repost_only: bool = False,
) -> DreamQuote:
    src = await db.get(DreamRecord, quoted_dream_id)
    if not src or src.deleted_at is not None:
        raise LookupError("Source dream not found")
    if not src.is_public and src.user_id != user_id:
        raise PermissionError("Dream is private")
    body = (body or "").strip()
    if not repost_only and not body:
        raise ValueError("Body required (or set repost_only=True)")
    q = DreamQuote(
        user_id=user_id, quoted_dream_id=quoted_dream_id,
        body=body, is_repost_only=repost_only,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    # Parse mentions in the body
    if body:
        await parse_and_record_mentions(db, body, user_id, "quote", q.id)
    # Notify the quoted dream's owner
    if src.user_id and src.user_id != user_id:
        await notify(db, src.user_id, "quote", actor_user_id=user_id,
                     target_kind="quote", target_id=q.id,
                     payload={"dream_id": quoted_dream_id, "preview": body[:120]})
    return q


async def list_quotes_of(db: AsyncSession, dream_id: str, limit: int = 30) -> list[dict]:
    res = await db.execute(
        select(DreamQuote).where(DreamQuote.quoted_dream_id == dream_id)
        .order_by(DreamQuote.created_at.desc()).limit(limit)
    )
    rows = list(res.scalars().all())
    user_ids = sorted({r.user_id for r in rows})
    nicks: dict[str, str] = {}
    if user_ids:
        u_res = await db.execute(select(UserRecord).where(UserRecord.id.in_(user_ids)))
        nicks = {u.id: u.nickname for u in u_res.scalars().all()}
    return [
        {
            "id": r.id, "user_id": r.user_id, "user_nickname": nicks.get(r.user_id, "Anonymous"),
            "body": r.body, "is_repost_only": r.is_repost_only,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------- Dream series ---------------------------------------------

async def create_series(
    db: AsyncSession, user_id: str, title: str, description: str = "",
    dream_ids: Optional[list[str]] = None, is_public: bool = False,
) -> DreamSeries:
    s = DreamSeries(
        user_id=user_id, title=title[:120], description=description[:2000] if description else None,
        dream_ids=dream_ids or [], is_public=is_public,
        cover_dream_id=(dream_ids[0] if dream_ids else None),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def update_series(
    db: AsyncSession, user_id: str, series_id: str,
    add_dream_id: Optional[str] = None, remove_dream_id: Optional[str] = None,
    title: Optional[str] = None, is_public: Optional[bool] = None,
) -> DreamSeries:
    s = await db.get(DreamSeries, series_id)
    if not s or s.user_id != user_id:
        raise PermissionError("Not your series")
    ids = list(s.dream_ids or [])
    if add_dream_id:
        d = await db.get(DreamRecord, add_dream_id)
        if not d or d.user_id != user_id:
            raise PermissionError("Dream must be yours")
        if add_dream_id not in ids:
            ids.append(add_dream_id)
    if remove_dream_id and remove_dream_id in ids:
        ids.remove(remove_dream_id)
    s.dream_ids = ids
    if title is not None: s.title = title[:120]
    if is_public is not None: s.is_public = bool(is_public)
    if not s.cover_dream_id and ids:
        s.cover_dream_id = ids[0]
    await db.commit()
    await db.refresh(s)
    return s


async def list_my_series(db: AsyncSession, user_id: str) -> list[dict]:
    res = await db.execute(
        select(DreamSeries).where(DreamSeries.user_id == user_id)
        .order_by(DreamSeries.updated_at.desc())
    )
    return [_serialize_series(s) for s in res.scalars().all()]


def _serialize_series(s: DreamSeries) -> dict:
    return {
        "id": s.id, "title": s.title, "description": s.description,
        "is_public": s.is_public, "dream_ids": s.dream_ids or [],
        "cover_dream_id": s.cover_dream_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ---------------- Threaded comment helpers ---------------------------------

async def comment_tree(db: AsyncSession, dream_id: str) -> list[dict]:
    """Build a nested comment tree from existing flat DreamComment rows.

    Each entry: {comment, children: [...]} so the frontend can render
    indented replies. Skips hidden comments.
    """
    res = await db.execute(
        select(DreamComment).where(and_(
            DreamComment.dream_id == dream_id,
            DreamComment.is_hidden == False,  # noqa: E712
        )).order_by(DreamComment.created_at.asc())
    )
    rows = list(res.scalars().all())

    # Hydrate nicknames
    user_ids = sorted({r.user_id for r in rows})
    nicks: dict[str, str] = {}
    if user_ids:
        u_res = await db.execute(select(UserRecord).where(UserRecord.id.in_(user_ids)))
        nicks = {u.id: u.nickname for u in u_res.scalars().all()}

    by_id: dict[str, dict] = {}
    roots: list[dict] = []
    for r in rows:
        node = {
            "id": r.id, "user_id": r.user_id, "nickname": nicks.get(r.user_id, "Anonymous"),
            "body": r.body, "parent_id": r.parent_id,
            "warmth_score": r.warmth_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "children": [],
        }
        by_id[r.id] = node
    for r in rows:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            by_id[r.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots
