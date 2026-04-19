"""Co-Dreaming sessions (PRODUCT_DOC §6.3).

Session lifecycle:
  open → recording → completed/abandoned

  - Creator opens with a theme + max_participants
  - Up to N users join via invite_code
  - Each records a dream tied to session_id
  - When all submit (or creator closes), we render a combined script + video

Renderer combines participants' dreams into a single multi-perspective
narrative — each user's contribution becomes a scene block in the
combined script, marked with the contributor's nickname.
"""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.social import CoDreamSession, CoDreamParticipant, CoDreamStatus
from models.user import UserRecord
from services.llm import chat_completion
from services.interpreter import _repair_json


def _gen_invite_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


async def create_session(
    db: AsyncSession,
    creator_user_id: str,
    title: str,
    theme: str,
    max_participants: int = 4,
    is_public: bool = False,
) -> CoDreamSession:
    """Open a new co-dream session. Auto-adds the creator as a participant.

    `is_public=True` makes the lobby discoverable in the public lobby feed
    (anyone can join without an invite code).
    """
    code = _gen_invite_code()
    # Best-effort uniqueness — collision is astronomically unlikely
    for _ in range(5):
        existing = await db.execute(
            select(CoDreamSession).where(CoDreamSession.invite_code == code)
        )
        if not existing.scalar_one_or_none():
            break
        code = _gen_invite_code()

    session = CoDreamSession(
        creator_user_id=creator_user_id,
        title=title,
        theme=theme,
        max_participants=max(2, min(max_participants, 8)),
        invite_code=code,
        status="open",
        is_public=is_public,
    )
    db.add(session)
    await db.flush()

    db.add(CoDreamParticipant(
        session_id=session.id,
        user_id=creator_user_id,
    ))
    await db.commit()
    await db.refresh(session)
    return session


async def join_by_code(
    db: AsyncSession, user_id: str, invite_code: str
) -> tuple[CoDreamSession, CoDreamParticipant]:
    result = await db.execute(
        select(CoDreamSession).where(CoDreamSession.invite_code == invite_code.upper().strip())
    )
    session = result.scalar_one_or_none()
    if not session:
        raise ValueError("Invalid invite code")
    if session.status != "open" and session.status != "recording":
        raise ValueError(f"Session is {session.status}")

    # Already a participant?
    existing = await db.execute(
        select(CoDreamParticipant).where(
            and_(
                CoDreamParticipant.session_id == session.id,
                CoDreamParticipant.user_id == user_id,
            )
        )
    )
    p = existing.scalar_one_or_none()
    if p:
        return session, p

    # Capacity check
    count_result = await db.execute(
        select(func.count(CoDreamParticipant.id))
        .where(CoDreamParticipant.session_id == session.id)
    )
    if (count_result.scalar() or 0) >= session.max_participants:
        raise ValueError("Session full")

    p = CoDreamParticipant(session_id=session.id, user_id=user_id)
    db.add(p)
    if session.status == "open":
        session.status = "recording"
    await db.commit()
    await db.refresh(p)
    return session, p


async def submit_dream(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    dream_id: str,
) -> CoDreamParticipant:
    """Link a recorded dream to the user's participant slot."""
    result = await db.execute(
        select(CoDreamParticipant).where(
            and_(
                CoDreamParticipant.session_id == session_id,
                CoDreamParticipant.user_id == user_id,
            )
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise PermissionError("Not a participant in this session")
    p.dream_id = dream_id
    p.submitted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(p)
    return p


async def list_public_lobbies(db: AsyncSession, limit: int = 30) -> list[dict]:
    """Discover open public lobbies — for the 'tonight's themes' feed."""
    # Status column is plain VARCHAR (existing migration didn't create the
    # enum type), so compare against string literals not enum members.
    res = await db.execute(
        select(CoDreamSession)
        .where(and_(
            CoDreamSession.is_public == True,  # noqa: E712
            CoDreamSession.status.in_(["open", "recording"]),
        ))
        .order_by(CoDreamSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(res.scalars().all())
    out = []
    for s in sessions:
        count = await db.execute(
            select(func.count(CoDreamParticipant.id)).where(CoDreamParticipant.session_id == s.id)
        )
        out.append({
            "id": s.id,
            "title": s.title,
            "theme": s.theme,
            "invite_code": s.invite_code,
            "max_participants": s.max_participants,
            "current_participants": int(count.scalar() or 0),
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return out


async def session_status(
    db: AsyncSession, session_id: str
) -> dict:
    """Detailed session status for participants."""
    session = await db.get(CoDreamSession, session_id)
    if not session:
        raise ValueError("Session not found")

    parts_result = await db.execute(
        select(CoDreamParticipant).where(CoDreamParticipant.session_id == session_id)
    )
    parts = list(parts_result.scalars().all())
    user_ids = [p.user_id for p in parts]

    nick_by_id: dict[str, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(UserRecord).where(UserRecord.id.in_(user_ids))
        )
        nick_by_id = {u.id: u.nickname for u in users_result.scalars().all()}

    return {
        "id": session.id,
        "title": session.title,
        "theme": session.theme,
        "invite_code": session.invite_code,
        "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        "creator_user_id": session.creator_user_id,
        "max_participants": session.max_participants,
        "combined_video_url": session.combined_video_url,
        "combined_script": session.combined_script,
        "participants": [
            {
                "user_id": p.user_id,
                "nickname": nick_by_id.get(p.user_id, "Anonymous"),
                "submitted": bool(p.dream_id),
                "joined_at": p.joined_at.isoformat() if p.joined_at else None,
            }
            for p in parts
        ],
    }


COMBINE_PROMPT = """You are weaving multiple dreamers' separate dreams about the
same theme into ONE braided narrative. Each contributor's dream becomes a chapter
of a shared meta-dream. Preserve each dreamer's voice + most vivid imagery.

THEME: {theme}

CONTRIBUTIONS:
{contributions}

Output a combined script JSON:
{{
  "title": "...",
  "overall_emotion": "...",
  "scenes": [...],   // Each scene tagged with "contributor": "<nickname>"
  "characters": [...],
  "symbols": [...],
  "color_palette": [...],
  "visual_style": "...",
  "synthesis": "1-2 sentence reflection on what the group's subconscious shared"
}}
Output ONLY JSON."""


async def render_combined(
    db: AsyncSession, session_id: str
) -> CoDreamSession:
    """Build the combined script when all participants have submitted.

    Does NOT generate video here — caller decides. (Video gen is heavy
    + needs quota deduction; surface it as a separate action.)
    """
    session = await db.get(CoDreamSession, session_id)
    if not session:
        raise ValueError("Session not found")

    parts_result = await db.execute(
        select(CoDreamParticipant).where(
            and_(
                CoDreamParticipant.session_id == session_id,
                CoDreamParticipant.dream_id.isnot(None),
            )
        )
    )
    parts = list(parts_result.scalars().all())
    if len(parts) < 2:
        raise ValueError("Need ≥2 submitted dreams")

    dreams_result = await db.execute(
        select(DreamRecord).where(DreamRecord.id.in_([p.dream_id for p in parts]))
    )
    dreams = {d.id: d for d in dreams_result.scalars().all()}

    users_result = await db.execute(
        select(UserRecord).where(UserRecord.id.in_([p.user_id for p in parts]))
    )
    nick_by_id = {u.id: u.nickname for u in users_result.scalars().all()}

    contribs = []
    for p in parts:
        d = dreams.get(p.dream_id)
        if d and d.dream_script:
            contribs.append({
                "contributor": nick_by_id.get(p.user_id, "Anonymous"),
                "script": d.dream_script,
            })

    if not contribs:
        raise ValueError("No scripted contributions")

    raw = await chat_completion(
        messages=[{
            "role": "user",
            "content": COMBINE_PROMPT.format(
                theme=session.theme,
                contributions=json.dumps(contribs, ensure_ascii=False, indent=2),
            ),
        }],
        system="Co-dream weaver. Multiple dreamers, one shared meta-dream.",
        max_tokens=6000,
    )
    combined = _repair_json(raw)
    if isinstance(combined, dict):
        session.combined_script = combined
        session.status = "completed"
        session.ends_at = datetime.utcnow()
        await db.commit()
        await db.refresh(session)
    return session
