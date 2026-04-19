"""Dream Duet / Remix (Wave O).

Semantic layer: when you start a new dream in "duet" mode, the source
dream's narrative + optional style hint get seeded into your interview
interviewer as the initial input. A `dream_remixes` row links the two
so we can:
  - Show "N remixes" on the source
  - Build a remix feed
  - Let original authors see their viral moments
  - Surface on the hashtag / For You feeds as a thread

Endpoints:
  POST /api/duet/start       — create a new dream seeded from a public source
  GET  /api/duet/of/{dream_id} — list remixes of a dream
  GET  /api/duet/by-me       — list my remixes
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth import require_user
from models.user import UserRecord
from models.dream import DreamRecord, DreamStatus
from models.engagement import DreamRemixLink as DreamRemix

router = APIRouter(prefix="/api/duet", tags=["duet"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# ---- Schemas --------------------------------------------------------------

class DuetStartRequest(BaseModel):
    source_dream_id: str
    kind: str = Field("duet", pattern="^(duet|cover|continuation)$")
    style: Optional[str] = None
    note: Optional[str] = Field(None, max_length=300)


# ---- Handlers -------------------------------------------------------------

@router.post("/start")
async def start_duet(
    body: DuetStartRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a remix dream. The source MUST be public.

    Flow:
      1. Fetch source + verify is_public, not deleted, owner not banned.
      2. Craft an initial_input that references the source (without copying
         it verbatim — copyright/IP respect).
      3. Delegate to DreamInterviewer.start_interview just like a normal
         /api/dreams/start.
      4. Persist DreamRemix row linking the two.
      5. Notify source owner that their dream was remixed.
    """
    source = await db.get(DreamRecord, body.source_dream_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source dream not found")
    if not source.is_public or source.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Source dream is not public")
    # Also block if the source owner is banned
    if source.user_id:
        from models.user import UserRecord as U
        owner = await db.get(U, source.user_id)
        if owner and getattr(owner, "is_banned", False):
            raise HTTPException(status_code=403, detail="Source unavailable")

    # Seed the interview with a respectful reference — not a copy.
    src_title = (source.title or "another dreamer's dream")[:80]
    summary = ((source.dream_script or {}).get("one_line_summary", "")
               if source.dream_script else "")[:200]
    if body.kind == "continuation":
        seed = f"[Continuing the dream titled '{src_title}'] {summary}"
    elif body.kind == "cover":
        seed = f"[Re-dreaming '{src_title}' in my own aesthetic] {summary}"
    else:  # duet
        seed = f"[Duet with '{src_title}'] {summary}"
    if body.note:
        seed += f" — {body.note[:200]}"

    # Delegate to the existing interviewer start path
    from services.interviewer import DreamInterviewer
    interviewer = DreamInterviewer()
    ai_message, chat_history, cited = await interviewer.start_interview(seed, db=db)

    new_dream = DreamRecord(
        user_id=user.id,
        user_initial_input=seed,
        chat_history=chat_history,
        video_style=body.style or source.video_style,
        status=DreamStatus.interviewing,
        knowledge_citations={"interviewer": cited} if cited else {},
    )
    db.add(new_dream)
    await db.commit()
    await db.refresh(new_dream)

    # Link the remix
    db.add(DreamRemix(
        source_dream_id=source.id,
        remix_dream_id=new_dream.id,
        remixer_user_id=user.id,
        remix_kind=body.kind,
        note=body.note,
    ))
    await db.commit()

    # Notify source owner (if different from remixer)
    try:
        from services.threads import notify
        if source.user_id and source.user_id != user.id:
            await notify(
                db,
                user_id=source.user_id,
                kind="remix",
                actor_user_id=user.id,
                target_kind="dream",
                target_id=source.id,
                payload={
                    "remix_dream_id": new_dream.id,
                    "remix_kind": body.kind,
                    "dream_title": source.title,
                },
            )
    except Exception:
        pass

    # Analytics
    try:
        from services import analytics as _an
        await _an.track("dream_remix_started", user_id=user.id, props={
            "source_dream_id": source.id,
            "remix_dream_id": new_dream.id,
            "kind": body.kind,
        })
    except Exception:
        pass

    return {
        "dream_id": new_dream.id,
        "source_dream_id": source.id,
        "kind": body.kind,
        "ai_message": ai_message,
        "round_number": 1,
        "is_complete": False,
    }


@router.get("/of/{dream_id}")
async def list_remixes_of(dream_id: str, db: AsyncSession = Depends(get_db)):
    """Public: list remixes of a dream. Anonymous-readable so the share
    page can show "N remixes" without login.
    """
    # Source must be public to expose remix list
    src = await db.get(DreamRecord, dream_id)
    if not src or not src.is_public or src.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Dream not found")

    res = await db.execute(
        select(DreamRemix, DreamRecord)
        .join(DreamRecord, DreamRemix.remix_dream_id == DreamRecord.id)
        .where(and_(
            DreamRemix.source_dream_id == dream_id,
            DreamRecord.is_public == True,  # noqa: E712
            DreamRecord.deleted_at.is_(None),
        ))
        .order_by(DreamRemix.created_at.desc())
        .limit(50)
    )
    rows = res.all()
    return {
        "source_dream_id": dream_id,
        "count": len(rows),
        "remixes": [
            {
                "dream_id": d.id,
                "title": d.title,
                "kind": rx.remix_kind,
                "video_url": d.video_url,
                "created_at": rx.created_at.isoformat() if rx.created_at else None,
            }
            for rx, d in rows
        ],
    }


@router.get("/by-me")
async def my_remixes(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """My own remix history — the dreams I've derived from others."""
    res = await db.execute(
        select(DreamRemix, DreamRecord)
        .join(DreamRecord, DreamRemix.remix_dream_id == DreamRecord.id)
        .where(DreamRemix.remixer_user_id == user.id)
        .order_by(DreamRemix.created_at.desc())
        .limit(100)
    )
    rows = res.all()
    return [
        {
            "dream_id": d.id,
            "title": d.title,
            "source_dream_id": rx.source_dream_id,
            "kind": rx.remix_kind,
            "created_at": rx.created_at.isoformat() if rx.created_at else None,
        }
        for rx, d in rows
    ]
