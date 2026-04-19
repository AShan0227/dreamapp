"""HTTP surface for the Wave F features:

- Cross-temporal correlation     /api/temporal/...
- Deja Reve                      /api/deja-reve/...
- Dream Matching                 /api/matching/...
- Customization                  /api/customize/...
- Remix                          /api/remix/...
- Co-Dreaming                    /api/codream/...
- Vibe Coder v2                  /api/vibe/...   (replaces routers/agents.py vibe stub)

All endpoints are owner-checked through services/auth.require_user.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.dream import DreamRecord
from models.social import (
    PatternKind,
    DreamCustomization,
    DreamRemix,
    RemixKind,
    CoDreamSession,
    CoDreamParticipant,
    DejaReveLink,
)
from models.user import UserRecord
from services.auth import require_user, get_optional_user
from services import recurring_patterns as patterns_svc
from services import deja_reve as dr_svc
from services import dream_matching as match_svc
from services import customization as cz_svc
from services import remix as rx_svc
from services import codream as co_svc
from services.quota import check_and_consume_video_quota


router = APIRouter(tags=["social"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# ---------------- Cross-temporal correlation (§8.3) -------------------------

@router.post("/api/temporal/refresh")
async def refresh_temporal_patterns(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Recompute the user's recurring patterns from current dreams."""
    return await patterns_svc.refresh_patterns(db, user.id)


@router.get("/api/temporal/patterns")
async def list_temporal_patterns(
    kind: Optional[str] = None,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the user's recurring patterns. Optional kind filter."""
    pk = None
    if kind:
        try: pk = PatternKind(kind)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown kind: {kind}")
    return await patterns_svc.list_patterns(db, user.id, pk)


# ---------------- Deja Reve (§8.4) ------------------------------------------

class DejaReveSearchRequest(BaseModel):
    waking_event: str = Field(..., min_length=3, max_length=2000)


class DejaReveConfirmRequest(BaseModel):
    dream_id: str
    waking_event: str
    similarity: Optional[float] = None


@router.post("/api/deja-reve/search")
async def deja_reve_search(
    body: DejaReveSearchRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Find dreams that semantically match the waking-life event."""
    return await dr_svc.search_dreams_for_event(db, user.id, body.waking_event)


@router.post("/api/deja-reve/confirm")
async def deja_reve_confirm(
    body: DejaReveConfirmRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """User confirms a dream-reality match — persist it."""
    # Verify the dream is the user's
    d = await db.get(DreamRecord, body.dream_id)
    if not d or d.user_id != user.id:
        raise HTTPException(status_code=404, detail="Dream not found")
    link = await dr_svc.confirm_link(db, user.id, body.dream_id, body.waking_event, body.similarity)
    return {"id": link.id, "dream_id": link.dream_id, "similarity": link.similarity}


@router.get("/api/deja-reve/")
async def deja_reve_list(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await dr_svc.list_links(db, user.id)


# ---------------- Dream Matching (§6.2) -------------------------------------

@router.get("/api/matching/dream/{dream_id}/similar-count")
async def matching_similar_count(
    dream_id: str,
    window_hours: int = 48,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """'147 people had a similar dream to yours last night' surface."""
    d = await db.get(DreamRecord, dream_id)
    if not d:
        raise HTTPException(status_code=404, detail="Dream not found")
    if d.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your dream")
    return await match_svc.count_similar_recent(db, dream_id, window_hours=window_hours)


@router.get("/api/matching/users")
async def matching_compatible_users(
    limit: int = 10,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Top compatible dreamers for the caller."""
    return await match_svc.find_compatible_users(db, user.id, limit=limit)


# ---------------- Customization (§7.1) --------------------------------------

class CustomizeRequest(BaseModel):
    source_dream_id: str
    kinds: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    user_completion_text: Optional[str] = None


@router.post("/api/customize/")
async def create_customize(
    body: CustomizeRequest,
    bg: BackgroundTasks,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Create + schedule a customization. Quota-checked (counts as a video gen)."""
    src = await db.get(DreamRecord, body.source_dream_id)
    if not src or src.user_id != user.id:
        raise HTTPException(status_code=404, detail="Source dream not found")
    await check_and_consume_video_quota(db, user)

    cz = await cz_svc.create_customization(
        db, user.id, body.source_dream_id, body.kinds, body.parameters,
        body.user_completion_text,
    )
    # Render in the background — caller polls
    bg.add_task(_render_in_thread, cz.id)
    return {"id": cz.id, "status": cz.status}


from services.observability import track_bg_task


@track_bg_task("customization_render")
async def _render_in_thread(customization_id: str):
    """Background task entry — needs its own DB session."""
    from main import async_session
    async with async_session() as db:
        await cz_svc.render_customization(db, customization_id)


@router.get("/api/customize/{cz_id}")
async def get_customize(
    cz_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    cz = await db.get(DreamCustomization, cz_id)
    if not cz or cz.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    from services.video_url import serve_video_url
    return {
        "id": cz.id,
        "source_dream_id": cz.source_dream_id,
        "kinds": cz.kinds or [],
        "parameters": cz.parameters or {},
        "status": cz.status,
        "video_url": serve_video_url(cz),
        "failure_reason": cz.failure_reason,
        "created_at": cz.created_at.isoformat() if cz.created_at else None,
    }


@router.get("/api/customize/")
async def list_customize(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DreamCustomization)
        .where(DreamCustomization.user_id == user.id)
        .order_by(DreamCustomization.created_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    from services.video_url import serve_video_url
    return [
        {
            "id": r.id,
            "source_dream_id": r.source_dream_id,
            "status": r.status,
            "kinds": r.kinds or [],
            "parameters": r.parameters or {},
            "video_url": serve_video_url(r),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------- Remix (§7.2) ----------------------------------------------

class SpliceRequest(BaseModel):
    dream_id_a: str
    dream_id_b: str
    user_prompt: str = ""


class RemixOtherRequest(BaseModel):
    source_dream_id: str
    user_prompt: str = ""


class ChainRequest(BaseModel):
    previous_remix_id: Optional[str] = None
    previous_dream_id: Optional[str] = None
    user_prompt: str = ""


class DialogueRequest(BaseModel):
    dream_id_a: str
    dream_id_b: str


@router.post("/api/remix/splice")
async def remix_splice(
    body: SpliceRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rx = await rx_svc.create_self_splice(db, user.id, body.dream_id_a, body.dream_id_b, body.user_prompt)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_remix(rx)


@router.post("/api/remix/other")
async def remix_other(
    body: RemixOtherRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rx = await rx_svc.create_remix_other(db, user.id, body.source_dream_id, body.user_prompt)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_remix(rx)


@router.post("/api/remix/chain")
async def remix_chain(
    body: ChainRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rx = await rx_svc.create_chain(db, user.id, body.previous_remix_id, body.previous_dream_id, body.user_prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_remix(rx)


@router.post("/api/remix/dialogue")
async def remix_dialogue(
    body: DialogueRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rx = await rx_svc.create_dialogue(db, user.id, body.dream_id_a, body.dream_id_b)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_remix(rx)


@router.get("/api/remix/chain/{root_id}")
async def remix_chain_walk(
    root_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await rx_svc.list_chain(db, root_id)


@router.get("/api/remix/challenge/{keyword}")
async def remix_challenge_entries(
    keyword: str,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    return await rx_svc.list_challenge_entries(db, keyword, limit=limit)


@router.get("/api/remix/")
async def list_remixes(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DreamRemix)
        .where(DreamRemix.user_id == user.id)
        .order_by(DreamRemix.created_at.desc())
        .limit(50)
    )
    return [_serialize_remix(r) for r in result.scalars().all()]


def _serialize_remix(rx: DreamRemix) -> dict:
    return {
        "id": rx.id,
        "kind": rx.kind.value if hasattr(rx.kind, "value") else str(rx.kind),
        "source_dream_ids": rx.source_dream_ids or [],
        "user_prompt": rx.user_prompt,
        "title": rx.title,
        "remixed_script": rx.remixed_script,
        "remixed_interpretation": rx.remixed_interpretation,
        "video_url": rx.video_url,
        "status": rx.status,
        "is_public": rx.is_public,
        "created_at": rx.created_at.isoformat() if rx.created_at else None,
    }


# ---------------- Co-Dreaming (§6.3) ----------------------------------------

class CoDreamCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    theme: str = Field(..., min_length=3, max_length=2000)
    max_participants: int = 4
    is_public: bool = False


class CoDreamJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=20)


class CoDreamSubmitRequest(BaseModel):
    session_id: str
    dream_id: str


@router.post("/api/codream/")
async def create_codream(
    body: CoDreamCreateRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    s = await co_svc.create_session(
        db, user.id, body.title, body.theme, body.max_participants,
        is_public=body.is_public,
    )
    return await co_svc.session_status(db, s.id)


@router.get("/api/codream/lobby")
async def codream_public_lobby(
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Public lobby — discover open sessions anyone can join."""
    return await co_svc.list_public_lobbies(db, limit=limit)


@router.post("/api/codream/join")
async def join_codream(
    body: CoDreamJoinRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        s, _p = await co_svc.join_by_code(db, user.id, body.invite_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await co_svc.session_status(db, s.id)


@router.post("/api/codream/submit")
async def submit_codream(
    body: CoDreamSubmitRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify dream ownership
    d = await db.get(DreamRecord, body.dream_id)
    if not d or d.user_id != user.id:
        raise HTTPException(status_code=404, detail="Dream not found")
    try:
        await co_svc.submit_dream(db, user.id, body.session_id, body.dream_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return await co_svc.session_status(db, body.session_id)


@router.post("/api/codream/{session_id}/render")
async def render_codream(
    session_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate the combined script. Caller (creator) triggers when ready."""
    s = await db.get(CoDreamSession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.creator_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only creator can render")
    try:
        await co_svc.render_combined(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await co_svc.session_status(db, session_id)


@router.get("/api/codream/{session_id}")
async def get_codream(
    session_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session detail. Must be a participant."""
    parts = await db.execute(
        select(CoDreamParticipant).where(
            CoDreamParticipant.session_id == session_id,
            CoDreamParticipant.user_id == user.id,
        )
    )
    if not parts.scalar_one_or_none():
        # Allow creator inspection too
        s = await db.get(CoDreamSession, session_id)
        if not s or s.creator_user_id != user.id:
            raise HTTPException(status_code=403, detail="Not a participant")
    return await co_svc.session_status(db, session_id)


@router.get("/api/codream/")
async def list_my_codreams(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    parts = await db.execute(
        select(CoDreamParticipant).where(CoDreamParticipant.user_id == user.id)
    )
    session_ids = [p.session_id for p in parts.scalars().all()]
    if not session_ids:
        return []
    result = await db.execute(
        select(CoDreamSession)
        .where(CoDreamSession.id.in_(session_ids))
        .order_by(CoDreamSession.created_at.desc())
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "theme": s.theme,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "invite_code": s.invite_code,
            "is_creator": s.creator_user_id == user.id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in result.scalars().all()
    ]
