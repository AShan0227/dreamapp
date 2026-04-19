"""HTTP surface for the 20 Threads-style social patterns."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserRecord
from services.auth import require_user, get_optional_user
from services import threads as ts


router = APIRouter(tags=["threads"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# ---------------- Profile ---------------------------------------------------

class ProfileUpdateRequest(BaseModel):
    handle: Optional[str] = Field(None, max_length=30)
    bio: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=80)
    link: Optional[str] = Field(None, max_length=300)
    private_account: Optional[bool] = None
    who_can_comment: Optional[str] = None
    who_can_dm: Optional[str] = None
    who_can_mention: Optional[str] = None


@router.get("/api/profile/{handle_or_id}")
async def get_profile(
    handle_or_id: str,
    user: Optional[UserRecord] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve by @handle (with prefix) OR by raw user id."""
    target_id: Optional[str] = None
    h = handle_or_id.lstrip("@")
    if not h:
        raise HTTPException(status_code=400, detail="handle required")
    p = await ts.resolve_handle(db, h)
    if p:
        target_id = p.user_id
    else:
        # treat as user_id
        target_id = handle_or_id

    try:
        return await ts.public_profile(db, target_id, viewer_user_id=user.id if user else None)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/api/profile/me")
async def update_my_profile(
    body: ProfileUpdateRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        p = await ts.update_profile(
            db, user.id,
            handle=body.handle, bio=body.bio, location=body.location, link=body.link,
            private_account=body.private_account,
            who_can_comment=body.who_can_comment, who_can_dm=body.who_can_dm,
            who_can_mention=body.who_can_mention,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ts.public_profile(db, user.id, viewer_user_id=user.id)


class PinRequest(BaseModel):
    dream_ids: list[str] = Field(..., max_length=3)


@router.post("/api/profile/me/pin")
async def pin_dreams(
    body: PinRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        p = await ts.pin_dreams(db, user.id, body.dream_ids)
    except (PermissionError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pinned_dream_ids": p.pinned_dream_ids or []}


# ---------------- Notifications --------------------------------------------

@router.get("/api/notifications/")
async def list_notifications(
    unread_only: bool = False, limit: int = 50,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.list_notifications(db, user.id, unread_only=unread_only, limit=limit)


@router.get("/api/notifications/unread-count")
async def unread_count(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return {"count": await ts.unread_count(db, user.id)}


class MarkReadRequest(BaseModel):
    notification_ids: Optional[list[str]] = None  # null = mark all


@router.post("/api/notifications/mark-read")
async def mark_read(
    body: MarkReadRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    n = await ts.mark_read(db, user.id, body.notification_ids)
    return {"marked": n}


# ---------------- Hashtags --------------------------------------------------

@router.post("/api/hashtags/{tag}/follow")
async def follow_tag(tag: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    try:
        added = await ts.follow_hashtag(db, user.id, tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"following": True, "added": added}


@router.delete("/api/hashtags/{tag}/follow")
async def unfollow_tag(tag: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    removed = await ts.unfollow_hashtag(db, user.id, tag)
    return {"following": False, "removed": removed}


@router.get("/api/hashtags/me")
async def my_followed_tags(user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    return await ts.list_followed_hashtags(db, user.id)


@router.get("/api/hashtags/{tag}")
async def tag_dreams(tag: str, limit: int = 30, db: AsyncSession = Depends(get_db)):
    return await ts.hashtag_dreams(db, tag, limit=limit)


@router.get("/api/hashtags/trending/")
async def trending(hours: int = 24, limit: int = 20, db: AsyncSession = Depends(get_db)):
    return await ts.trending_hashtags(db, hours=hours, limit=limit)


# ---------------- For You feed ---------------------------------------------

@router.get("/api/feed/for-you")
async def for_you(
    limit: int = 30,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.for_you_feed(db, user.id, limit=limit)


# ---------------- Bookmarks -------------------------------------------------

@router.post("/api/dreams/{dream_id}/bookmark")
async def add_bookmark(
    dream_id: str, folder: str = "default",
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    added = await ts.bookmark(db, user.id, dream_id, folder=folder)
    return {"bookmarked": True, "added": added}


@router.delete("/api/dreams/{dream_id}/bookmark")
async def remove_bookmark(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await ts.unbookmark(db, user.id, dream_id)
    return {"bookmarked": False, "removed": removed}


@router.get("/api/bookmarks/")
async def list_bookmarks(
    folder: Optional[str] = None,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.list_bookmarks(db, user.id, folder=folder)


# ---------------- Polls -----------------------------------------------------

class PollCreate(BaseModel):
    dream_id: str
    question: str = Field(..., min_length=3, max_length=500)
    options: list[str] = Field(..., min_length=2, max_length=6)
    closes_in_hours: Optional[int] = 72


@router.post("/api/polls/")
async def create_poll(
    body: PollCreate,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        p = await ts.create_poll(
            db, user.id, body.dream_id, body.question, body.options,
            closes_in_hours=body.closes_in_hours,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ts.poll_results(db, p.id)


class PollVoteRequest(BaseModel):
    option_id: str


@router.post("/api/polls/{poll_id}/vote")
async def vote_poll(
    poll_id: str, body: PollVoteRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ts.vote_poll(db, user.id, poll_id, body.option_id)
    except (LookupError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/polls/{poll_id}")
async def poll_results(poll_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await ts.poll_results(db, poll_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Poll not found")


# ---------------- Mute / Block / Report ------------------------------------

@router.post("/api/users/{target_id}/mute")
async def toggle_mute(
    target_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ts.toggle_mute(db, user.id, target_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/users/{target_id}/block")
async def toggle_block(
    target_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ts.toggle_block(db, user.id, target_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ReportBody(BaseModel):
    target_kind: str
    target_id: str
    reason: str
    detail: str = ""


@router.post("/api/reports/")
async def report_content(
    body: ReportBody,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        r = await ts.report_content(db, user.id, body.target_kind, body.target_id, body.reason, body.detail)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": r.id, "status": r.status}


# ---------------- DMs ------------------------------------------------------

class DMSendRequest(BaseModel):
    recipient_id: str
    body: str = Field(..., min_length=1, max_length=2000)


@router.post("/api/dm/send")
async def send_dm(
    body: DMSendRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        m = await ts.send_dm(db, user.id, body.recipient_id, body.body)
    except (PermissionError, ValueError) as e:
        raise HTTPException(status_code=403 if isinstance(e, PermissionError) else 400, detail=str(e))
    return {"id": m.id, "thread_id": m.thread_id}


@router.get("/api/dm/threads")
async def list_threads(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.list_dm_threads(db, user.id)


@router.get("/api/dm/threads/{thread_id}/messages")
async def list_messages(
    thread_id: str, limit: int = 100,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ts.list_dm_messages(db, user.id, thread_id, limit=limit)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------------- Quote / Repost -------------------------------------------

class QuoteRequest(BaseModel):
    quoted_dream_id: str
    body: str = Field("", max_length=1000)
    repost_only: bool = False


@router.post("/api/quotes/")
async def quote(
    body: QuoteRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        q = await ts.quote_dream(db, user.id, body.quoted_dream_id, body.body, repost_only=body.repost_only)
    except (LookupError, PermissionError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": q.id, "user_id": q.user_id, "quoted_dream_id": q.quoted_dream_id,
        "body": q.body, "is_repost_only": q.is_repost_only,
    }


@router.get("/api/dreams/{dream_id}/quotes")
async def list_quotes(dream_id: str, limit: int = 30, db: AsyncSession = Depends(get_db)):
    return await ts.list_quotes_of(db, dream_id, limit=limit)


# ---------------- Threaded comment tree ------------------------------------

@router.get("/api/dreams/{dream_id}/comments-tree")
async def comments_tree(
    dream_id: str,
    user: Optional[UserRecord] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.comment_tree(db, dream_id)


# ---------------- Series ---------------------------------------------------

class SeriesCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    dream_ids: list[str] = Field(default_factory=list)
    is_public: bool = False


@router.post("/api/series/")
async def create_series(
    body: SeriesCreate,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    s = await ts.create_series(db, user.id, body.title, body.description, body.dream_ids, body.is_public)
    return ts._serialize_series(s)


class SeriesUpdate(BaseModel):
    add_dream_id: Optional[str] = None
    remove_dream_id: Optional[str] = None
    title: Optional[str] = None
    is_public: Optional[bool] = None


@router.patch("/api/series/{series_id}")
async def update_series(
    series_id: str, body: SeriesUpdate,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        s = await ts.update_series(
            db, user.id, series_id,
            add_dream_id=body.add_dream_id, remove_dream_id=body.remove_dream_id,
            title=body.title, is_public=body.is_public,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return ts._serialize_series(s)


@router.get("/api/series/")
async def list_my_series(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await ts.list_my_series(db, user.id)
