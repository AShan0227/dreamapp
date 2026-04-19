"""Cross-temporal correlation: detect recurring patterns across a user's dreams.

PRODUCT_DOC §8.3 — the killer feature. We look for:
  - scene recurrence (same setting/place returning)
  - character recurrence (same person/entity)
  - theme recurrence (same emotional/topical concern)
  - narrative evolution (same story arc, different ending)
  - symbol recurrence (same symbol across multiple dreams)
  - emotion recurrence (consistent emotional pattern)

Run on demand from /api/temporal/refresh, or auto after each new dream
script is generated. Idempotent — upserts by (user_id, kind, canonical_name).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.entities import DreamEntity
from models.social import RecurringPattern, PatternKind


MIN_OCCURRENCES = 2  # below this, not "recurring"


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


async def _user_dreams(db: AsyncSession, user_id: str) -> list[DreamRecord]:
    """All of a user's non-deleted, scripted dreams in chronological order."""
    result = await db.execute(
        select(DreamRecord)
        .where(
            and_(
                DreamRecord.user_id == user_id,
                DreamRecord.deleted_at.is_(None),
                DreamRecord.dream_script.isnot(None),
            )
        )
        .order_by(DreamRecord.created_at.asc())
    )
    return list(result.scalars().all())


def _patterns_from_dreams(dreams: list[DreamRecord]) -> list[dict]:
    """Aggregate dreams into pattern candidates.

    Returns a list of {kind, canonical_name, dream_ids, first_seen, last_seen,
    metadata} dicts ready to upsert.
    """
    sym_index: dict[str, list[DreamRecord]] = defaultdict(list)
    char_index: dict[str, list[DreamRecord]] = defaultdict(list)
    loc_index: dict[str, list[DreamRecord]] = defaultdict(list)
    theme_index: dict[str, list[DreamRecord]] = defaultdict(list)
    emotion_index: dict[str, list[DreamRecord]] = defaultdict(list)

    for d in dreams:
        for s in (d.symbol_tags or []):
            n = _normalize(str(s))
            if n:
                sym_index[n].append(d)
        for c in (d.character_tags or []):
            n = _normalize(str(c))
            if n:
                char_index[n].append(d)
        for loc in (d.location_tags or []):
            n = _normalize(str(loc))
            if n:
                loc_index[n].append(d)
        for theme in (d.theme_tags or []):
            n = _normalize(str(theme))
            if n:
                theme_index[n].append(d)
        for em in (d.emotion_tags or []):
            n = _normalize(str(em))
            if n:
                emotion_index[n].append(d)

    out: list[dict] = []

    def _emit(kind: PatternKind, index: dict[str, list[DreamRecord]]):
        for name, ds in index.items():
            if len(ds) < MIN_OCCURRENCES:
                continue
            out.append({
                "kind": kind,
                "canonical_name": name,
                "dream_ids": [d.id for d in ds],
                "first_seen_at": ds[0].created_at,
                "last_seen_at": ds[-1].created_at,
                "metadata": {
                    "occurrence_count": len(ds),
                    "spans_days": (ds[-1].created_at - ds[0].created_at).days if len(ds) > 1 else 0,
                },
            })

    _emit(PatternKind.symbol, sym_index)
    _emit(PatternKind.character, char_index)
    _emit(PatternKind.scene, loc_index)
    _emit(PatternKind.theme, theme_index)
    _emit(PatternKind.emotion, emotion_index)

    # Narrative evolution: same title prefix, different scripts
    title_groups: dict[str, list[DreamRecord]] = defaultdict(list)
    for d in dreams:
        if not d.title:
            continue
        # Use first 4 chars as a coarse "is this the same dream"
        key = _normalize(d.title)[:6]
        if key:
            title_groups[key].append(d)
    for key, ds in title_groups.items():
        if len(ds) >= MIN_OCCURRENCES:
            out.append({
                "kind": PatternKind.narrative,
                "canonical_name": ds[0].title or key,
                "dream_ids": [d.id for d in ds],
                "first_seen_at": ds[0].created_at,
                "last_seen_at": ds[-1].created_at,
                "metadata": {
                    "occurrence_count": len(ds),
                    "title_variants": list({d.title for d in ds if d.title}),
                },
            })

    return out


async def refresh_patterns(db: AsyncSession, user_id: str) -> dict:
    """Recompute the user's recurring_patterns rows. Returns counts.

    Strategy: compute the full set of patterns from current dreams, then
    upsert by (user_id, kind, canonical_name). Patterns that no longer
    apply (dream deleted) get removed.
    """
    dreams = await _user_dreams(db, user_id)
    if len(dreams) < MIN_OCCURRENCES:
        return {"computed": 0, "upserted": 0, "removed": 0}

    candidates = _patterns_from_dreams(dreams)

    # Index existing rows by (kind, canonical_name)
    result = await db.execute(
        select(RecurringPattern).where(RecurringPattern.user_id == user_id)
    )
    existing_rows = list(result.scalars().all())
    existing_by_key = {(r.kind, r.canonical_name): r for r in existing_rows}

    seen_keys: set = set()
    upserted = 0

    for cand in candidates:
        key = (cand["kind"], cand["canonical_name"])
        seen_keys.add(key)
        row = existing_by_key.get(key)
        if row:
            row.occurrence_count = len(cand["dream_ids"])
            row.dream_ids = cand["dream_ids"]
            row.first_seen_at = cand["first_seen_at"]
            row.last_seen_at = cand["last_seen_at"]
            row.metadata_json = cand["metadata"]
        else:
            db.add(RecurringPattern(
                user_id=user_id,
                kind=cand["kind"],
                canonical_name=cand["canonical_name"],
                occurrence_count=len(cand["dream_ids"]),
                dream_ids=cand["dream_ids"],
                first_seen_at=cand["first_seen_at"],
                last_seen_at=cand["last_seen_at"],
                metadata_json=cand["metadata"],
            ))
        upserted += 1

    # Prune patterns that no longer apply
    removed = 0
    for key, row in existing_by_key.items():
        if key not in seen_keys:
            await db.delete(row)
            removed += 1

    await db.commit()
    return {"computed": len(candidates), "upserted": upserted, "removed": removed}


async def list_patterns(
    db: AsyncSession, user_id: str, kind: PatternKind | None = None
) -> list[dict]:
    """Read patterns for display in the timeline view."""
    stmt = select(RecurringPattern).where(RecurringPattern.user_id == user_id)
    if kind:
        stmt = stmt.where(RecurringPattern.kind == kind)
    stmt = stmt.order_by(RecurringPattern.occurrence_count.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
            "canonical_name": r.canonical_name,
            "occurrence_count": r.occurrence_count,
            "dream_ids": r.dream_ids or [],
            "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            "spans_days": (r.metadata_json or {}).get("spans_days"),
        }
        for r in rows
    ]
