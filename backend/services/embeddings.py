"""Embedding service — generates vector embeddings for semantic search.

Uses BAAI/bge-small-zh-v1.5 (130MB, bilingual zh+en, CPU-friendly).
Loaded once at startup, cached in Docker volume.

Sync vs async:
  - `embed_text` / `embed_texts` are CPU-bound (50-300ms per call) and MUST
    be wrapped with `asyncio.to_thread` when invoked from an async coroutine.
  - Use `aembed_text` / `aembed_texts` from any `async def` — they handle
    the off-loop dispatch for you.
"""

import asyncio
import os
import json
from typing import Optional

from config import settings

# Lazy-loaded model
_model = None


def _get_model():
    """Load embedding model lazily. Thread-safe via GIL."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            cache_dir = settings.embedding_cache_dir
            os.makedirs(cache_dir, exist_ok=True)
            _model = SentenceTransformer(
                settings.embedding_model,
                cache_folder=cache_dir,
            )
            from services.observability import get_logger
            get_logger("embeddings").info("embedding model loaded", extra={"model": settings.embedding_model})
        except Exception as e:
            from services.observability import get_logger
            get_logger("embeddings").exception("embedding model load failed", extra={"err": str(e)})
            _model = "FAILED"
    return _model if _model != "FAILED" else None


def embed_text(text: str) -> Optional[list[float]]:
    """Embed a single text. Returns vector or None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    try:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    except Exception as e:
        from services.observability import get_logger
        get_logger("embeddings").warning("embed_text failed", extra={"err": str(e)})
        return None


def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed multiple texts in batch. More efficient than individual calls."""
    model = _get_model()
    if model is None:
        return [None] * len(texts)
    try:
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [e.tolist() for e in embeddings]
    except Exception as e:
        from services.observability import get_logger
        get_logger("embeddings").warning("embed_texts failed", extra={"err": str(e)})
        return [None] * len(texts)


def embed_dream(dream_script: dict) -> Optional[list[float]]:
    """Generate embedding for a dream from its script."""
    if not dream_script:
        return None

    parts = []
    title = dream_script.get("title", "")
    if title:
        parts.append(title)

    emotion = dream_script.get("overall_emotion", "")
    if emotion:
        parts.append(f"Emotion: {emotion}")

    scenes = dream_script.get("scenes", [])
    for scene in scenes[:5]:
        desc = scene.get("description", "")
        if desc:
            parts.append(desc)

    symbols = dream_script.get("symbols", [])
    if symbols:
        parts.append("Symbols: " + ", ".join(str(s) for s in symbols))

    characters = dream_script.get("characters", [])
    if characters:
        parts.append("Characters: " + ", ".join(str(c) for c in characters))

    text = ". ".join(parts)
    return embed_text(text) if text else None


def embed_entity(canonical_name: str, display_name: str, description: str) -> Optional[list[float]]:
    """Generate embedding for a dream entity."""
    text = f"{canonical_name} {display_name} {description}"
    return embed_text(text) if text.strip() else None


def embed_knowledge_entry(name: str, content: str) -> Optional[list[float]]:
    """Generate embedding for a knowledge base entry."""
    text = f"{name}: {content}"
    return embed_text(text) if text.strip() else None


# ---- Async wrappers — use these from any async def ------------------------

async def aembed_text(text: str) -> Optional[list[float]]:
    """Async-safe wrapper. Off-loads CPU-bound encode to the default
    threadpool so the event loop stays unblocked under concurrency."""
    if not text:
        return None
    return await asyncio.to_thread(embed_text, text)


async def aembed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    if not texts:
        return []
    return await asyncio.to_thread(embed_texts, texts)


async def aembed_dream(dream_script: dict) -> Optional[list[float]]:
    if not dream_script:
        return None
    return await asyncio.to_thread(embed_dream, dream_script)


async def aembed_entity(canonical_name: str, display_name: str, description: str) -> Optional[list[float]]:
    return await asyncio.to_thread(embed_entity, canonical_name, display_name, description)


async def aembed_knowledge_entry(name: str, content: str) -> Optional[list[float]]:
    return await asyncio.to_thread(embed_knowledge_entry, name, content)
