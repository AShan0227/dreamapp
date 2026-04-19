"""Semantic knowledge retrieval with Genesis Attribution.

Supplements the keyword-based services/knowledge.py with pgvector lookup
against the seeded L1/L2 knowledge embeddings. Every retrieval increments
use_count and promotes probation → graduated after 3 uses.
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge_embedding import (
    KnowledgeEmbedding,
    KnowledgeStatus,
    KnowledgeTier,
)
from services.embeddings import aembed_text


async def retrieve_knowledge(
    db: AsyncSession,
    query: str,
    sources: Optional[Sequence[str]] = None,
    tiers: Sequence[KnowledgeTier] = (KnowledgeTier.L1, KnowledgeTier.L2),
    limit: int = 8,
    l2_limit: int = 2,
    dedup_key: Optional[str] = None,
) -> list[KnowledgeEmbedding]:
    """Top-K semantic retrieval with Attribution tracking.

    Cross-tier by default: pulls L1 (interpretive) AND a small slice of L2
    (real-dream / paper evidence). The L2 slice is capped at `l2_limit` to
    avoid swamping prompt context with raw corpus.

    `dedup_key` (optional, e.g. dream_id) deduplicates Attribution counting
    across stages of the same dream — without it, a single symbol appearing
    in interview + director + interpreter would count 3× even though it
    produced 1 user experience.

    Filters out quarantined entries.
    """
    if not query or not query.strip():
        return []

    query_embedding = await aembed_text(query)
    if query_embedding is None:
        return []

    base = select(KnowledgeEmbedding).where(
        KnowledgeEmbedding.embedding != None,  # noqa: E711
        KnowledgeEmbedding.status != KnowledgeStatus.quarantined,
    )
    if sources:
        base = base.where(KnowledgeEmbedding.source.in_(list(sources)))

    tier_list = list(tiers)
    has_l1 = KnowledgeTier.L1 in tier_list
    has_l2 = KnowledgeTier.L2 in tier_list

    entries: list[KnowledgeEmbedding] = []
    try:
        if has_l1:
            l1_limit = max(1, limit - (l2_limit if has_l2 else 0))
            l1_stmt = (
                base.where(KnowledgeEmbedding.tier == KnowledgeTier.L1)
                .order_by(KnowledgeEmbedding.embedding.cosine_distance(query_embedding))
                .limit(l1_limit)
            )
            res = await db.execute(l1_stmt)
            entries.extend(res.scalars().all())
        if has_l2:
            l2_stmt = (
                base.where(KnowledgeEmbedding.tier == KnowledgeTier.L2)
                .order_by(KnowledgeEmbedding.embedding.cosine_distance(query_embedding))
                .limit(l2_limit)
            )
            res = await db.execute(l2_stmt)
            entries.extend(res.scalars().all())
    except Exception as e:
        print(f"Semantic retrieval failed: {e}")
        return []

    # Genesis Attribution — count once per dedup_key per entry, not per stage
    if dedup_key:
        already_counted = await _already_counted(db, dedup_key, [e.id for e in entries])
    else:
        already_counted = set()

    now = datetime.utcnow()
    for e in entries:
        if e.id in already_counted:
            # Touch last_used_at but don't double-count use_count
            e.last_used_at = now
            continue
        e.use_count = (e.use_count or 0) + 1
        e.last_used_at = now
        if e.use_count >= 3 and e.status == KnowledgeStatus.probation:
            e.status = KnowledgeStatus.graduated
            e.confidence = min(1.0, (e.confidence or 0.5) + 0.2)

    if dedup_key:
        _record_dedup(dedup_key, [e.id for e in entries])

    try:
        await db.commit()
    except Exception as e:
        print(f"Attribution commit failed: {e}")
        await db.rollback()

    try:
        from services.observability import inc
        inc("dreamapp_knowledge_retrievals_total")
    except Exception:
        pass

    return entries


# ---- per-dream dedup memory ----------------------------------------------
# Lightweight in-process LRU mapping dream_id → set(entry_id) for the lifetime
# of this process. Cross-process dedup would need a shared store (Redis), but
# for typical pipeline use the same worker handles all 3 stages of one dream.

_dedup_cache: "dict[str, set[str]]" = {}
_dedup_order: "list[str]" = []
_DEDUP_MAX_KEYS = 2048


def _record_dedup(key: str, ids: list[str]) -> None:
    bucket = _dedup_cache.setdefault(key, set())
    fresh = not bucket
    bucket.update(ids)
    if fresh:
        _dedup_order.append(key)
        # LRU eviction
        while len(_dedup_order) > _DEDUP_MAX_KEYS:
            old = _dedup_order.pop(0)
            _dedup_cache.pop(old, None)


async def _already_counted(db, key: str, ids: list[str]) -> set[str]:
    """Return subset of ids that have already been counted for this dedup key.

    Falls back to in-process cache; if the key has no cached entries yet,
    consults the dreams.knowledge_citations JSON for persistence across
    restarts.
    """
    cached = _dedup_cache.get(key, set())
    if cached:
        return {i for i in ids if i in cached}

    # Persistence path: load citations from this dream and seed the cache
    try:
        from models.dream import DreamRecord
        dream = await db.get(DreamRecord, key)
        if dream and dream.knowledge_citations:
            seen: set[str] = set()
            for stage_ids in (dream.knowledge_citations or {}).values():
                if isinstance(stage_ids, list):
                    seen.update(stage_ids)
            _dedup_cache[key] = seen
            _dedup_order.append(key)
            return {i for i in ids if i in seen}
    except Exception:
        pass
    return set()


def _group(entries: list[KnowledgeEmbedding]) -> dict[str, list[KnowledgeEmbedding]]:
    out: dict[str, list[KnowledgeEmbedding]] = {}
    for e in entries:
        out.setdefault(e.source, []).append(e)
    return out


def format_interview_context(entries: list[KnowledgeEmbedding]) -> str:
    """Format retrieved entries as interviewer context (symbols, archetypes, corpus examples)."""
    if not entries:
        return ""
    by_source = _group(entries)
    lines: list[str] = []

    if "symbols" in by_source:
        lines.append("[SEMANTIC MATCH — Dream symbols from 55-symbol knowledge base:]")
        for e in by_source["symbols"][:5]:
            meta = e.metadata_json or {}
            follow_ups = meta.get("follow_up_questions", [])
            psych = meta.get("psychological_interpretations", {})
            jungian = psych.get("jungian", "") if isinstance(psych, dict) else ""
            lines.append(f"\n**{e.name}**")
            if follow_ups:
                qs = [str(q) for q in follow_ups[:3]]
                lines.append(f"  Suggested questions: {'; '.join(qs)}")
            if jungian:
                lines.append(f"  Jungian: {str(jungian)[:150]}")

    if "archetypes" in by_source:
        lines.append("\n[ARCHETYPE HINTS:]")
        for e in by_source["archetypes"][:3]:
            lines.append(f"  {e.name}: {e.content_text[:120]}")

    if "corpus" in by_source:
        lines.append("\n[SIMILAR REAL DREAMS (reference patterns, not to quote):]")
        for e in by_source["corpus"][:2]:
            meta = e.metadata_json or {}
            text = str(meta.get("text") or e.content_text)[:160]
            themes = [str(t) for t in (meta.get("themes") or [])[:4]]
            lines.append(f"  — {text}... [{', '.join(themes)}]")

    if lines:
        lines.append(
            "\nUse these patterns to inform follow-up questions. Do NOT quote to user."
        )
    return "\n".join(lines)


def format_interpretation_context(entries: list[KnowledgeEmbedding]) -> str:
    """Format retrieved entries as interpreter context (symbols, archetypes, narratives, TCM, cultural)."""
    if not entries:
        return ""
    by_source = _group(entries)
    lines: list[str] = []

    if "symbols" in by_source:
        lines.append("[SEMANTIC SYMBOLS:]")
        for e in by_source["symbols"][:5]:
            meta = e.metadata_json or {}
            psych = meta.get("psychological_interpretations", {})
            cultural = meta.get("cultural_interpretations", {})
            lines.append(f"\n## {e.name}")
            if isinstance(psych, dict):
                for lens, interp in psych.items():
                    if interp:
                        lines.append(f"  {lens}: {str(interp)[:200]}")
            if isinstance(cultural, dict):
                for culture, interp in cultural.items():
                    if interp:
                        lines.append(f"  {culture}: {str(interp)[:150]}")

    if "archetypes" in by_source:
        lines.append("\n[JUNGIAN ARCHETYPES:]")
        for e in by_source["archetypes"][:3]:
            meta = e.metadata_json or {}
            desc = meta.get("description", e.content_text)
            questions = meta.get("key_questions", [])
            lines.append(f"\n**{e.name}**")
            lines.append(f"  {str(desc)[:200]}")
            if questions:
                qs = [str(q) for q in questions[:2]]
                lines.append(f"  Key questions: {'; '.join(qs)}")

    if "narratives" in by_source:
        lines.append("\n[NARRATIVE ARCHETYPES:]")
        for e in by_source["narratives"][:2]:
            meta = e.metadata_json or {}
            significance = meta.get("psychological_significance", "")
            if isinstance(significance, dict):
                significance = significance.get("primary", "")
            lines.append(f"\n**{e.name}**")
            lines.append(f"  {str(significance)[:200] or e.content_text[:200]}")

    if "tcm" in by_source:
        lines.append("\n[TCM PERSPECTIVE:]")
        for e in by_source["tcm"][:2]:
            meta = e.metadata_json or {}
            element = (
                meta.get("element_zh") or meta.get("element_en") or meta.get("element", "")
            )
            lines.append(f"\n**{e.name}** (element: {element})")
            wellness = meta.get("wellness_recommendations") or meta.get(
                "recommendations", {}
            )
            if isinstance(wellness, dict):
                diet = wellness.get("dietary") or wellness.get("diet", [])
                if isinstance(diet, list) and diet:
                    items = [str(d) for d in diet[:3]]
                    lines.append(f"  Diet: {', '.join(items)}")

    if "cultural" in by_source:
        lines.append("\n[CROSS-CULTURAL ECHOES:]")
        for e in by_source["cultural"][:3]:
            lines.append(f"  {e.content_text[:180]}")

    return "\n".join(lines)


def format_director_context(entries: list[KnowledgeEmbedding]) -> str:
    """Format retrieved entries as director context (film techniques, emotion visuals, styles)."""
    if not entries:
        return ""
    by_source = _group(entries)
    lines: list[str] = []

    if "film_techniques" in by_source:
        lines.append("[SEMANTIC FILM TECHNIQUES:]")
        for e in by_source["film_techniques"][:4]:
            meta = e.metadata_json or {}
            keywords = meta.get("prompt_keywords", "")
            lines.append(f"  {e.name}: {str(keywords)[:120] or e.content_text[:120]}")

    if "emotion_visual" in by_source:
        lines.append("\n[EMOTION → VISUAL MAPPING:]")
        for e in by_source["emotion_visual"][:2]:
            meta = e.metadata_json or {}
            parts = []
            for k in ("camera", "lighting", "color", "motion"):
                v = meta.get(k)
                if v:
                    parts.append(f"{k}: {str(v)[:60]}")
            lines.append(f"  {e.name} — {'; '.join(parts)}")

    if "prompt_styles" in by_source:
        lines.append("\n[STYLE PRESETS:]")
        for e in by_source["prompt_styles"][:2]:
            meta = e.metadata_json or {}
            keywords = meta.get("keywords", [])
            refs = meta.get("reference_films", [])
            if isinstance(keywords, list):
                kw = [str(k) for k in keywords[:6]]
                lines.append(f"  {e.name}: {', '.join(kw)}")
            if isinstance(refs, list) and refs:
                rf = [str(r) for r in refs[:3]]
                lines.append(f"    Reference: {', '.join(rf)}")

    if "dreamcore" in by_source:
        lines.append("\n[DREAMCORE SPACES:]")
        for e in by_source["dreamcore"][:2]:
            lines.append(f"  {e.name}: {e.content_text[:160]}")

    return "\n".join(lines)


# --- High-level helpers used by the pipeline ---

INTERVIEW_SOURCES = ("symbols", "archetypes", "corpus")
INTERPRETATION_SOURCES = ("symbols", "archetypes", "narratives", "tcm", "cultural")
DIRECTOR_SOURCES = (
    "film_techniques",
    "emotion_visual",
    "prompt_styles",
    "dreamcore",
)


async def semantic_interview_context(
    db: AsyncSession, text: str, dream_id: Optional[str] = None
) -> tuple[str, list[str]]:
    """Return (prompt_text, list_of_cited_entry_ids).

    `dream_id` (when supplied) deduplicates Attribution counting across
    interview rounds + downstream director/interpreter stages of the
    same dream.
    """
    entries = await retrieve_knowledge(
        db, text, sources=INTERVIEW_SOURCES, limit=8, dedup_key=dream_id
    )
    return format_interview_context(entries), [e.id for e in entries]


async def semantic_interpretation_context(
    db: AsyncSession, dream_script: dict, dream_id: Optional[str] = None
) -> tuple[str, list[str]]:
    import json

    query = json.dumps(dream_script, ensure_ascii=False)
    entries = await retrieve_knowledge(
        db, query, sources=INTERPRETATION_SOURCES, limit=10, dedup_key=dream_id
    )
    return format_interpretation_context(entries), [e.id for e in entries]


async def semantic_director_context(
    db: AsyncSession, dream_script: dict, dream_id: Optional[str] = None
) -> tuple[str, list[str]]:
    import json

    query = json.dumps(dream_script, ensure_ascii=False)
    entries = await retrieve_knowledge(
        db, query, sources=DIRECTOR_SOURCES, limit=8, dedup_key=dream_id
    )
    return format_director_context(entries), [e.id for e in entries]


async def apply_feedback(
    db: AsyncSession, citation_ids: list[str], helpful: bool
) -> int:
    """Bump success_count or failure_count on a set of cited entries.

    Design note: one feedback event touches ALL cited entries because we
    can't tell which entry actually drove the outcome (diffused responsibility).
    To avoid quarantining innocent entries, the quarantine threshold is
    proportional: an entry only gets quarantined when failure_rate is high
    relative to its total usage, not just on absolute count.
    """
    if not citation_ids:
        return 0

    result = await db.execute(
        select(KnowledgeEmbedding).where(
            KnowledgeEmbedding.id.in_(list(citation_ids))
        )
    )
    entries = list(result.scalars().all())
    # Dampen per-entry delta when many entries share a single feedback signal
    n = max(1, len(entries))
    conf_delta_up = min(0.10, 0.05 + 0.02 * (5 / n))   # more entries → smaller bump
    conf_delta_down = min(0.15, 0.05 + 0.05 * (5 / n)) # more entries → smaller hit

    for e in entries:
        if helpful:
            e.success_count = (e.success_count or 0) + 1
            e.confidence = min(1.0, (e.confidence or 0.5) + conf_delta_up)
        else:
            e.failure_count = (e.failure_count or 0) + 1
            e.confidence = max(0.0, (e.confidence or 0.5) - conf_delta_down)
            # Quarantine only when failure rate is high AND entry has been tested
            # (at least 3 total feedback events, failure ratio > 60%)
            total_fb = (e.failure_count or 0) + (e.success_count or 0)
            if total_fb >= 3 and (e.failure_count or 0) / total_fb > 0.6:
                e.status = KnowledgeStatus.quarantined

    await db.commit()
    return len(entries)
