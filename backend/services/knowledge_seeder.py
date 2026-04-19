"""Seed knowledge base entries into pgvector for semantic search."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge_embedding import KnowledgeEmbedding, KnowledgeTier
from services.embeddings import embed_text, embed_texts

# Tier classification: which sources are L0 (index), L1 (knowledge), L2 (evidence)
TIER_MAP = {
    "symbols": KnowledgeTier.L1,          # Core interpretation knowledge — injected into prompts
    "archetypes": KnowledgeTier.L1,       # Core interpretation knowledge
    "narratives": KnowledgeTier.L1,       # Core interpretation knowledge
    "tcm": KnowledgeTier.L1,             # Core interpretation knowledge
    "dreamcore": KnowledgeTier.L1,        # Dreamcore visual knowledge
    "cultural": KnowledgeTier.L1,         # Cultural interpretation
    "film_techniques": KnowledgeTier.L1,  # Video generation knowledge
    "prompt_styles": KnowledgeTier.L1,    # Video generation knowledge
    "emotion_visual": KnowledgeTier.L1,   # Video generation knowledge
    "incubation": KnowledgeTier.L1,       # Active dreaming knowledge
    "papers": KnowledgeTier.L2,           # Evidence — not injected, for reference
    "corpus": KnowledgeTier.L2,           # Evidence — training data, not injected
    # Wave J — subculture + internet content (补齐)
    "aesthetics": KnowledgeTier.L1,       # Internet aesthetics — dreamcore, liminal, y2k, vaporwave...
    "modern_symbols": KnowledgeTier.L1,   # Phone dying, wifi, deepfake, QR, Zoom — modern dream symbols
    "dream_memes": KnowledgeTier.L1,      # X-coded, POV dream, brainrot — register/tone cues
    "shifting": KnowledgeTier.L1,         # Reality-shifting community — DR/CR/WR/void state
    "lucid_tech": KnowledgeTier.L1,       # WILD/MILD/SSILD/WBTB — lucid practitioner context
    "sp_culture": KnowledgeTier.L1,       # Sleep paralysis entities — hat man, old hag, 鬼压床
    "platform_ops": KnowledgeTier.L2,     # 抖音/小红书/B站 platform ops — reference, not interp
    "gen_z_vocab": KnowledgeTier.L1,      # Slang register — bilingual vocabulary
    "wellness": KnowledgeTier.L1,         # Sleepmaxxing/bedrotting/CBT-I — user wellness frame
}

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _extract_entries() -> list[dict]:
    """Extract all knowledge entries from JSON files into flat list."""
    entries = []

    # Symbols
    data = _load("symbols.json")
    for sym in (data.get("symbols", []) if isinstance(data, dict) else data if isinstance(data, list) else []):
        name = sym.get("name_en") or sym.get("name") or "?"
        name_zh = sym.get("name_zh") or ""
        psych = sym.get("psychological_interpretations", {})
        content = f"{name} ({name_zh}). "
        for k, v in psych.items():
            if v:
                content += f"{k}: {str(v)[:150]}. "
        entries.append({"source": "symbols", "source_id": str(sym.get("id", name)), "name": f"{name} / {name_zh}", "content": content, "meta": sym})

    # Archetypes
    data = _load("archetypes.json")
    for arch in data.get("archetypes", []) if isinstance(data, dict) else []:
        name = arch.get("name_en") or arch.get("name") or "?"
        desc = arch.get("description", "")
        manifestations = arch.get("dream_manifestations", [])
        content = f"{name}. {desc[:200]}. Dream manifestations: {', '.join(str(m)[:50] for m in manifestations[:3])}"
        entries.append({"source": "archetypes", "source_id": name, "name": name, "content": content, "meta": arch})

    # Narratives
    data = _load("narratives.json")
    for nar in data.get("narrative_archetypes", data.get("archetypes", data.get("narratives", []))) if isinstance(data, dict) else []:
        name = nar.get("name") or nar.get("name_en") or "?"
        desc = nar.get("description", "")
        keywords = nar.get("detection_keywords", [])
        content = f"{name}. {desc[:200]}. Keywords: {', '.join(str(k) for k in keywords[:10])}"
        entries.append({"source": "narratives", "source_id": name, "name": name, "content": content, "meta": nar})

    # TCM
    data = _load("tcm_dreams.json")
    for organ in data.get("five_organ_systems", []) if isinstance(data, dict) else []:
        name = organ.get("organ_zh", "") + " " + organ.get("organ_en", "")
        excess = organ.get("excess", {}).get("dream_themes", [])
        deficiency = organ.get("deficiency", {}).get("dream_themes", [])
        content = f"TCM {name}. Excess dreams: {', '.join(str(t)[:50] for t in excess[:3])}. Deficiency dreams: {', '.join(str(t)[:50] for t in deficiency[:3])}"
        entries.append({"source": "tcm", "source_id": name.strip(), "name": name.strip(), "content": content, "meta": organ})

    # Dreamcore spaces
    data = _load("dreamcore_knowledge.json")
    if isinstance(data, dict):
        for space in data.get("spaces", data.get("iconic_spaces", [])):
            name = space.get("name", "?")
            desc = space.get("description", space.get("visual_description", ""))
            content = f"Dreamcore: {name}. {str(desc)[:300]}"
            entries.append({"source": "dreamcore", "source_id": name, "name": name, "content": content, "meta": space})

    # Cultural dreams
    data = _load("cultural_dreams.json")
    if isinstance(data, dict):
        for culture_key in data:
            culture = data[culture_key]
            if isinstance(culture, dict) and "symbols" in culture:
                for sym in culture["symbols"][:10]:
                    name = sym.get("symbol", sym.get("name", "?"))
                    meaning = sym.get("meaning", sym.get("interpretation", ""))
                    culture_name = culture.get("culture", culture_key)
                    content = f"Cultural dream ({culture_name}): {name}. {str(meaning)[:200]}"
                    entries.append({"source": "cultural", "source_id": f"{culture_name}:{name}", "name": name, "content": content, "meta": sym})

    # Film techniques
    data = _load("film_techniques.json")
    if isinstance(data, dict):
        for category, techniques in data.items():
            if isinstance(techniques, dict):
                for key, tech in techniques.items():
                    if isinstance(tech, dict):
                        name = tech.get("name", key)
                        desc = tech.get("description", "")
                        keywords = tech.get("prompt_keywords", "")
                        content = f"Film technique ({category}): {name}. {desc}. Keywords: {keywords}"
                        entries.append({"source": "film_techniques", "source_id": f"{category}:{key}", "name": name, "content": content, "meta": tech})

    # Prompt guide — style presets and emotion mappings
    data = _load("prompt_guide.json")
    if isinstance(data, dict):
        for style, preset in data.get("style_presets", {}).items():
            if isinstance(preset, dict):
                keywords = preset.get("keywords", [])
                refs = preset.get("reference_films", [])
                content = f"Visual style: {style}. Keywords: {', '.join(str(k) for k in keywords[:8])}. Reference: {', '.join(str(r) for r in refs[:3])}"
                entries.append({"source": "prompt_styles", "source_id": style, "name": style, "content": content, "meta": preset})

        for emotion, visual in data.get("emotion_to_visual", {}).items():
            if isinstance(visual, dict):
                content = f"Emotion visual: {emotion}. Camera: {visual.get('camera','')}. Lighting: {visual.get('lighting','')}. Color: {visual.get('color','')}. Motion: {visual.get('motion','')}"
                entries.append({"source": "emotion_visual", "source_id": emotion, "name": emotion, "content": content, "meta": visual})

    # Papers summary
    data = _load("papers_summary.json")
    if isinstance(data, dict):
        for paper in data.get("papers", []):
            if isinstance(paper, dict):
                title = paper.get("title", "?")
                authors = paper.get("authors", "")
                findings = paper.get("key_findings", [])
                content = f"Research: {title} ({authors}). Findings: {'. '.join(str(f)[:80] for f in findings[:3])}"
                entries.append({"source": "papers", "source_id": title, "name": title, "content": content, "meta": paper})

    # Dream corpus — embed representative samples
    data = _load("dream_corpus.json")
    if isinstance(data, dict):
        for dream in data.get("dreams", [])[:50]:  # First 50 for performance
            if isinstance(dream, dict):
                text = dream.get("text", "")
                themes = dream.get("themes", [])
                emotion = dream.get("emotion", "")
                did = dream.get("id", "?")
                content = f"Dream example: {str(text)[:200]}. Themes: {', '.join(str(t) for t in themes)}. Emotion: {emotion}"
                entries.append({"source": "corpus", "source_id": str(did), "name": f"Dream {did}", "content": content, "meta": dream})

    # Incubation themes
    data = _load("incubation.json")
    if isinstance(data, dict):
        for theme in data.get("themes", []):
            if isinstance(theme, dict):
                name = theme.get("name", "?")
                meditation = theme.get("meditation_seed", "")
                scent = theme.get("scent", "")
                content = f"Incubation theme: {name}. Meditation: {meditation}. Scent: {scent}"
                entries.append({"source": "incubation", "source_id": name, "name": name, "content": content, "meta": theme})

    # === Wave J: Subculture / internet content (补齐) ===

    # Internet aesthetics — dreamcore, liminal, weirdcore, y2k, vaporwave...
    data = _load("internet_aesthetics.json")
    if isinstance(data, dict):
        for aes in data.get("aesthetics", []):
            if isinstance(aes, dict):
                aid = aes.get("id", aes.get("name_en", "?"))
                name_en = aes.get("name_en", aid)
                name_zh = aes.get("name_zh", "")
                imagery = aes.get("core_imagery", [])
                tone = aes.get("emotional_tone", "")
                palette = aes.get("color_palette", [])
                relevance = aes.get("dream_relevance", "")
                keywords = aes.get("video_prompt_keywords", [])
                content = (
                    f"Internet aesthetic: {name_en} ({name_zh}). "
                    f"Imagery: {', '.join(str(i)[:60] for i in imagery[:5])}. "
                    f"Tone: {tone}. "
                    f"Palette: {', '.join(str(c) for c in palette[:4])}. "
                    f"Dream relevance: {str(relevance)[:200]}. "
                    f"Video keywords: {', '.join(str(k) for k in keywords[:8])}"
                )
                entries.append({"source": "aesthetics", "source_id": str(aid), "name": f"{name_en} / {name_zh}", "content": content, "meta": aes})

    # Modern dream symbols — phone dying, wifi, deepfake, QR, Zoom
    data = _load("modern_symbols.json")
    if isinstance(data, dict):
        for sym in data.get("symbols", []):
            if isinstance(sym, dict):
                sid = sym.get("id", sym.get("name_en", "?"))
                name_en = sym.get("name_en", sym.get("name", sid))
                name_zh = sym.get("name_zh", "")
                category = sym.get("category", "")
                freq = sym.get("frequency", "")
                interp = sym.get("psychological_interpretations", {})
                modern = interp.get("modern", "") if isinstance(interp, dict) else ""
                follow = sym.get("follow_up_questions", [])
                content = (
                    f"Modern symbol: {name_en} ({name_zh}). "
                    f"Category: {category}. Frequency: {freq}. "
                    f"Modern reading: {str(modern)[:200]}. "
                    f"Follow-ups: {' | '.join(str(q)[:80] for q in follow[:2])}"
                )
                entries.append({"source": "modern_symbols", "source_id": str(sid), "name": f"{name_en} / {name_zh}", "content": content, "meta": sym})

    # Dream memes — viral tweet formats
    data = _load("dream_memes.json")
    if isinstance(data, dict):
        for fmt in data.get("formats", []):
            if isinstance(fmt, dict):
                fid = fmt.get("id", fmt.get("name", "?"))
                name = fmt.get("name", fid)
                pattern = fmt.get("pattern", "")
                hint = fmt.get("interpretation_hint", "")
                examples = fmt.get("examples", [])
                content = (
                    f"Dream meme format: {name}. "
                    f"Pattern: {str(pattern)[:150]}. "
                    f"Example: {str(examples[0])[:150] if examples else ''}. "
                    f"Interpretation hint: {str(hint)[:200]}"
                )
                entries.append({"source": "dream_memes", "source_id": str(fid), "name": name, "content": content, "meta": fmt})
        # Also embed the vocab dict as individual slang entries
        vocab = data.get("vocabulary", {})
        if isinstance(vocab, dict):
            for term, meaning in vocab.items():
                content = f"Dream-adjacent slang: {term}. Meaning: {str(meaning)[:200]}"
                entries.append({"source": "dream_memes", "source_id": f"vocab:{term}", "name": term, "content": content, "meta": {"term": term, "meaning": meaning}})

    # Reality-shifting subculture
    data = _load("shifting_subculture.json")
    if isinstance(data, dict):
        for concept in data.get("concepts", []):
            if isinstance(concept, dict):
                cid = concept.get("id", concept.get("term", "?"))
                term = concept.get("term", cid)
                term_zh = concept.get("term_zh", "")
                definition = concept.get("definition", "")
                category = concept.get("category", "")
                hint = concept.get("interpretation_hint", "")
                content = (
                    f"Shifting concept: {term} ({term_zh}). "
                    f"Category: {category}. "
                    f"Definition: {str(definition)[:250]}. "
                    f"Interpretation hint: {str(hint)[:200]}"
                )
                entries.append({"source": "shifting", "source_id": str(cid), "name": f"{term} / {term_zh}", "content": content, "meta": concept})

    # Lucid dreaming techniques
    data = _load("lucid_techniques.json")
    if isinstance(data, dict):
        for tech in data.get("techniques", []):
            if isinstance(tech, dict):
                tid = tech.get("id", tech.get("term", "?"))
                term = tech.get("term", tid)
                full = tech.get("full", "")
                definition = tech.get("definition", "")
                difficulty = tech.get("difficulty", "")
                hint = tech.get("interpretation_hint", tech.get("ai_application", ""))
                content = (
                    f"Lucid technique: {term}"
                    + (f" ({full})" if full else "")
                    + f". {str(definition)[:250]}. "
                    + (f"Difficulty: {difficulty}. " if difficulty else "")
                    + (f"Hint: {str(hint)[:180]}" if hint else "")
                )
                entries.append({"source": "lucid_tech", "source_id": str(tid), "name": term, "content": content, "meta": tech})

    # Sleep paralysis culture — entities + phenomenology
    data = _load("sleep_paralysis_culture.json")
    if isinstance(data, dict):
        for ent in data.get("entities", []):
            if isinstance(ent, dict):
                eid = ent.get("id", ent.get("name", "?"))
                name = ent.get("name", eid)
                culture = ent.get("culture", "")
                desc = ent.get("description", "")
                hint = ent.get("interpretation_hint", ent.get("ai_application", ""))
                content = (
                    f"SP entity: {name}. "
                    + (f"Culture: {culture}. " if culture else "")
                    + f"{str(desc)[:280]}. "
                    + (f"Hint: {str(hint)[:180]}" if hint else "")
                )
                entries.append({"source": "sp_culture", "source_id": str(eid), "name": name, "content": content, "meta": ent})
        # Co-occurring phenomena (v2.0 schema)
        for phen in data.get("co_occurring_phenomena", []):
            if isinstance(phen, dict):
                pid = phen.get("id", phen.get("name", "?"))
                name = phen.get("name", pid)
                desc = phen.get("description", "")
                content = f"SP-adjacent phenomenon: {name}. {str(desc)[:280]}"
                entries.append({"source": "sp_culture", "source_id": f"phen:{pid}", "name": name, "content": content, "meta": phen})

    # Chinese platform ops — 抖音/小红书/B站 (L2, operational)
    data = _load("douyin_xiaohongshu_bili.json")
    if isinstance(data, dict):
        for plat in data.get("platforms", []):
            if isinstance(plat, dict):
                pid = plat.get("id", "?")
                name = plat.get("name", pid)
                voice = plat.get("user_voice", "")
                content = f"Platform ops: {name}. User voice: {str(voice)[:220]}"
                # Embed each popular_format as its own entry for granular retrieval
                entries.append({"source": "platform_ops", "source_id": str(pid), "name": name, "content": content, "meta": plat})
                for fmt in plat.get("popular_formats", []):
                    if isinstance(fmt, dict):
                        fname = fmt.get("format", "?")
                        hook = fmt.get("hook", fmt.get("structure", ""))
                        fcontent = f"{name} format: {fname}. {str(hook)[:200]}"
                        entries.append({"source": "platform_ops", "source_id": f"{pid}:{fname}", "name": f"{name} — {fname}", "content": fcontent, "meta": fmt})

    # Gen Z bilingual dream vocab — register matching
    data = _load("gen_z_dream_vocab.json")
    if isinstance(data, dict):
        # The file has multiple register buckets; flatten them all
        register_keys = [
            "emotional_register",
            "intensity_and_weirdness",
            "romantic_and_parasocial",
            "spiritual_and_shadow",
            "meta_and_platform",
            "darker_register",
            "zh_native_slang_without_en_equivalent",
        ]
        for reg_key in register_keys:
            for item in data.get(reg_key, []):
                if isinstance(item, dict):
                    term = item.get("term", "?")
                    zh = item.get("zh_equivalent", item.get("literal", ""))
                    usage = item.get("usage", "")
                    dream_ctx = item.get("dream_context", "")
                    hint = item.get("interpretation_hint", "")
                    content = (
                        f"Gen Z slang [{reg_key}]: {term} ({zh}). "
                        f"Usage: {str(usage)[:180]}. "
                        + (f"Dream context: {str(dream_ctx)[:150]}. " if dream_ctx else "")
                        + (f"Hint: {str(hint)[:150]}" if hint else "")
                    )
                    entries.append({"source": "gen_z_vocab", "source_id": f"{reg_key}:{term}", "name": term, "content": content, "meta": item})

    # Wellness + sleep culture — sleepmaxxing, bedrotting, CBT-I...
    data = _load("wellness_sleep_culture.json")
    if isinstance(data, dict):
        for mov in data.get("movements", []):
            if isinstance(mov, dict):
                mid = mov.get("id", mov.get("term", "?"))
                term = mov.get("term", mid)
                desc = mov.get("description", "")
                tone = mov.get("tone", "")
                hint = mov.get("interpretation_hint", mov.get("ai_application", ""))
                evidence = mov.get("evidence_tier", "")
                content = (
                    f"Wellness concept: {term}. "
                    f"{str(desc)[:260]}. "
                    + (f"Tone: {tone}. " if tone else "")
                    + (f"Evidence: {str(evidence)[:100]}. " if evidence else "")
                    + (f"Hint: {str(hint)[:180]}" if hint else "")
                )
                entries.append({"source": "wellness", "source_id": str(mid), "name": term, "content": content, "meta": mov})

    return entries


def _load(filename: str):
    path = KNOWLEDGE_DIR / filename
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


async def seed_knowledge_embeddings(db: AsyncSession) -> int:
    """Upsert knowledge entries into pgvector by (source, source_id).

    Behavior:
    - New (source, source_id) pairs are inserted with embeddings.
    - Existing pairs whose content_text changed are re-embedded and updated
      in-place. Existing pairs whose content_text is unchanged are skipped.
    - Stable counters (use_count, success_count, failure_count, status,
      confidence) are preserved on update — feedback survives re-seeds.
    - Returns the number of rows inserted OR updated.

    This is the "incremental seeder" — adding new entries to a knowledge
    JSON file no longer requires manual DB intervention.
    """
    from config import settings as _settings

    entries = _extract_entries()
    if not entries:
        return 0

    # Index existing rows by (source, source_id) for O(1) lookup
    result = await db.execute(select(KnowledgeEmbedding))
    existing: dict[tuple[str, str], KnowledgeEmbedding] = {
        (r.source, r.source_id): r for r in result.scalars().all()
    }

    # Decide which entries need (re)embedding
    to_embed: list[tuple[int, str]] = []      # (index_in_entries, text)
    insert_targets: list[tuple[int, dict]] = []
    update_targets: list[tuple[int, KnowledgeEmbedding]] = []

    for i, entry in enumerate(entries):
        key = (entry["source"], str(entry["source_id"]))
        text = entry["content"]
        ex = existing.get(key)
        if ex is None:
            insert_targets.append((i, entry))
            to_embed.append((i, text))
        elif (ex.content_text or "") != text or ex.embedding_model != _settings.embedding_model:
            # Re-embed if text changed OR if produced by a different model
            update_targets.append((i, ex))
            to_embed.append((i, text))

    if not to_embed:
        return 0

    embeddings_by_index: dict[int, list[float] | None] = {}
    texts = [t for _, t in to_embed]
    indexes = [i for i, _ in to_embed]
    vecs = embed_texts(texts)
    for idx, vec in zip(indexes, vecs):
        embeddings_by_index[idx] = vec

    count = 0

    # Inserts
    for i, entry in insert_targets:
        emb = embeddings_by_index.get(i)
        if emb is None:
            continue
        tier = TIER_MAP.get(entry["source"], KnowledgeTier.L1)
        ke = KnowledgeEmbedding(
            source=entry["source"],
            source_id=str(entry["source_id"]),
            name=entry["name"],
            content_text=entry["content"],
            metadata_json=entry.get("meta", {}),
            tier=tier,
            confidence=0.8 if tier == KnowledgeTier.L1 else 0.5,
            impact_score=0.7 if tier == KnowledgeTier.L1 else 0.3,
            embedding_model=_settings.embedding_model,
        )
        if hasattr(ke, "embedding"):
            ke.embedding = emb
        db.add(ke)
        count += 1

    # Updates — preserve learned counters
    for i, ex in update_targets:
        entry = entries[i]
        emb = embeddings_by_index.get(i)
        ex.name = entry["name"]
        ex.content_text = entry["content"]
        ex.metadata_json = entry.get("meta", {})
        ex.embedding_model = _settings.embedding_model
        if emb is not None and hasattr(ex, "embedding"):
            ex.embedding = emb
        count += 1

    await db.commit()
    print(
        f"Seeded knowledge: {len(insert_targets)} inserted, "
        f"{len(update_targets)} updated"
    )
    return count
