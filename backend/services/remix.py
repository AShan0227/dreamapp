"""Dream Remix (PRODUCT_DOC §7.2).

Five remix kinds:
  - self_splice    user combines two of own dreams into one narrative
  - remix_other    re-render a public plaza dream in caller's style
  - chain          A's ending = B's beginning (community co-creation)
  - dialogue       two dreams analyzed side-by-side, AI finds connections
  - challenge      same keyword/prompt, multiple users compete

Most remixes produce a NEW DreamRemix row (not a DreamRecord) so they're
discoverable separately and don't pollute the dreamer's archive.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.social import DreamRemix, RemixKind
from services.llm import chat_completion
from services.interpreter import _repair_json


SPLICE_PROMPT = """You are weaving two of the user's separate dreams into one
coherent narrative dream. Preserve the most vivid imagery from each. The new
dream should feel like the dreamer's subconscious bridged them in a single night.

DREAM A:
{a}

DREAM B:
{b}

USER GUIDANCE (optional):
{guidance}

Output the spliced dream as a SCRIPT in this JSON schema:
{{
  "title": "...",
  "overall_emotion": "...",
  "scenes": [{{"scene_number": 1, "description": "...", "visual_details": "...", "emotion": "..."}}, ...],
  "characters": [...],
  "symbols": [...],
  "color_palette": [...],
  "visual_style": "..."
}}
Output ONLY JSON."""


REMIX_OTHER_PROMPT = """You are re-rendering someone else's dream in YOUR
style preferences. Keep the original narrative bones. Apply the new style/mood.

ORIGINAL DREAM SCRIPT:
{src}

USER'S RE-RENDER REQUEST:
{guidance}

Output the re-rendered dream script in the same schema. Output ONLY JSON."""


CHAIN_PROMPT = """You are continuing a chain dream. The PREVIOUS dream's final
scene becomes the OPENING of this new dream. Develop a fresh narrative from there.

PREVIOUS DREAM ENDING:
{prev_ending}

USER GUIDANCE:
{guidance}

Output the new dream script. Output ONLY JSON."""


DIALOGUE_PROMPT = """You are a dream analyst comparing two dreams. Identify
hidden connections, shared symbols, complementary themes. Be concrete and concise.

DREAM A: {a}

DREAM B: {b}

Output JSON: {{
  "hidden_connections": ["..."],
  "shared_symbols": ["..."],
  "complementary_themes": ["..."],
  "synthesis": "2-3 sentence interpretation of the dialogue"
}}
Output ONLY JSON."""


async def _load(db: AsyncSession, dream_id: str) -> DreamRecord | None:
    d = await db.get(DreamRecord, dream_id)
    if not d or d.deleted_at is not None:
        return None
    return d


async def create_self_splice(
    db: AsyncSession,
    user_id: str,
    dream_id_a: str,
    dream_id_b: str,
    user_prompt: str = "",
) -> DreamRemix:
    a = await _load(db, dream_id_a)
    b = await _load(db, dream_id_b)
    if not a or not b:
        raise ValueError("Source dream(s) not found")
    if a.user_id != user_id or b.user_id != user_id:
        raise PermissionError("Both dreams must be owned by caller")
    if not a.dream_script or not b.dream_script:
        raise ValueError("Both dreams must be scripted")

    raw = await chat_completion(
        messages=[{
            "role": "user",
            "content": SPLICE_PROMPT.format(
                a=json.dumps(a.dream_script, ensure_ascii=False),
                b=json.dumps(b.dream_script, ensure_ascii=False),
                guidance=user_prompt or "(no extra guidance)",
            ),
        }],
        system="Dream-script weaver. Combines two dreams into one coherent narrative.",
        max_tokens=4000,
    )
    spliced = _repair_json(raw)

    rx = DreamRemix(
        user_id=user_id,
        kind=RemixKind.self_splice,
        source_dream_ids=[dream_id_a, dream_id_b],
        user_prompt=user_prompt,
        remixed_script=spliced,
        title=(spliced or {}).get("title") if isinstance(spliced, dict) else None,
        status="completed",
    )
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    return rx


async def create_remix_other(
    db: AsyncSession,
    user_id: str,
    source_dream_id: str,
    user_prompt: str,
) -> DreamRemix:
    src = await _load(db, source_dream_id)
    if not src or not src.dream_script:
        raise ValueError("Source dream not found or not scripted")
    if not src.is_public and src.user_id != user_id:
        raise PermissionError("Source dream must be public to remix")

    raw = await chat_completion(
        messages=[{
            "role": "user",
            "content": REMIX_OTHER_PROMPT.format(
                src=json.dumps(src.dream_script, ensure_ascii=False),
                guidance=user_prompt or "Re-render in a fresh style.",
            ),
        }],
        system="Dream re-renderer. Keep the bones, change the skin.",
        max_tokens=4000,
    )
    remixed = _repair_json(raw)

    rx = DreamRemix(
        user_id=user_id,
        kind=RemixKind.remix_other,
        source_dream_ids=[source_dream_id],
        user_prompt=user_prompt,
        remixed_script=remixed,
        title=(remixed or {}).get("title") if isinstance(remixed, dict) else None,
        status="completed",
    )
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    return rx


async def create_chain(
    db: AsyncSession,
    user_id: str,
    previous_remix_id: str | None,
    previous_dream_id: str | None,
    user_prompt: str = "",
) -> DreamRemix:
    """Continue an existing chain (or start one from a dream)."""
    prev_ending = ""
    source_ids: list[str] = []
    if previous_remix_id:
        prev = await db.get(DreamRemix, previous_remix_id)
        if not prev or not prev.remixed_script:
            raise ValueError("Previous chain link not found")
        prev_ending = json.dumps(
            (prev.remixed_script or {}).get("scenes", [])[-1] or {},
            ensure_ascii=False,
        )
        source_ids = [previous_remix_id]
    elif previous_dream_id:
        d = await _load(db, previous_dream_id)
        if not d or not d.dream_script:
            raise ValueError("Previous dream not found")
        prev_ending = json.dumps(
            (d.dream_script or {}).get("scenes", [])[-1] or {},
            ensure_ascii=False,
        )
        source_ids = [previous_dream_id]
    else:
        raise ValueError("Either previous_remix_id or previous_dream_id required")

    raw = await chat_completion(
        messages=[{
            "role": "user",
            "content": CHAIN_PROMPT.format(prev_ending=prev_ending, guidance=user_prompt),
        }],
        system="Chain-dream continuator.",
        max_tokens=4000,
    )
    new_dream = _repair_json(raw)

    rx = DreamRemix(
        user_id=user_id,
        kind=RemixKind.chain,
        source_dream_ids=source_ids,
        user_prompt=user_prompt,
        remixed_script=new_dream,
        title=(new_dream or {}).get("title") if isinstance(new_dream, dict) else None,
        status="completed",
        is_public=True,  # chains are inherently social
    )
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    return rx


async def create_dialogue(
    db: AsyncSession,
    user_id: str,
    dream_id_a: str,
    dream_id_b: str,
) -> DreamRemix:
    a = await _load(db, dream_id_a)
    b = await _load(db, dream_id_b)
    if not a or not b or not a.dream_script or not b.dream_script:
        raise ValueError("Both source dreams must exist + be scripted")
    # Either-public OR both-owned-by-caller
    if a.user_id != user_id and not a.is_public:
        raise PermissionError("Dream A is private")
    if b.user_id != user_id and not b.is_public:
        raise PermissionError("Dream B is private")

    raw = await chat_completion(
        messages=[{
            "role": "user",
            "content": DIALOGUE_PROMPT.format(
                a=json.dumps(a.dream_script, ensure_ascii=False),
                b=json.dumps(b.dream_script, ensure_ascii=False),
            ),
        }],
        system="Dream dialogue analyst.",
        max_tokens=2000,
    )
    interp = _repair_json(raw)

    rx = DreamRemix(
        user_id=user_id,
        kind=RemixKind.dialogue,
        source_dream_ids=[dream_id_a, dream_id_b],
        remixed_interpretation=interp,
        title=f"Dialogue: {(a.title or 'Dream A')[:30]} ↔ {(b.title or 'Dream B')[:30]}",
        status="completed",
    )
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    return rx


async def list_chain(db: AsyncSession, root_id: str, max_depth: int = 20) -> list[dict]:
    """Walk a chain forward from a starting remix or dream id."""
    out: list[dict] = []
    visited: set = set()
    cursor = root_id
    for _ in range(max_depth):
        if cursor in visited:
            break
        visited.add(cursor)
        # Find next link whose source includes `cursor`
        result = await db.execute(
            select(DreamRemix).where(
                and_(
                    DreamRemix.kind == RemixKind.chain,
                    # Postgres JSON contains check via .contains
                )
            )
        )
        # Manual filter — JSON containment varies by driver; safer to scan
        next_links = [r for r in result.scalars().all() if cursor in (r.source_dream_ids or [])]
        if not next_links:
            break
        nxt = next_links[0]
        out.append({
            "id": nxt.id,
            "user_id": nxt.user_id,
            "title": nxt.title,
            "user_prompt": nxt.user_prompt,
            "created_at": nxt.created_at.isoformat() if nxt.created_at else None,
        })
        cursor = nxt.id
    return out


async def list_challenge_entries(
    db: AsyncSession, keyword: str, limit: int = 30
) -> list[dict]:
    keyword = keyword.strip().lower()
    result = await db.execute(
        select(DreamRemix)
        .where(
            and_(
                DreamRemix.kind == RemixKind.challenge,
                DreamRemix.challenge_keyword == keyword,
                DreamRemix.is_public == True,
            )
        )
        .order_by(DreamRemix.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "title": r.title,
            "challenge_keyword": r.challenge_keyword,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
