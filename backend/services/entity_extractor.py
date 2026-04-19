"""Extract structured entities from dream scripts for cross-temporal analysis."""

import json
from difflib import SequenceMatcher

from services.llm import chat_completion

EXTRACTION_PROMPT = """Analyze this dream and extract ALL entities into structured JSON.

For each entity, provide:
- entity_type: "character", "symbol", "location", "scene", or "object"
- canonical_name: a short snake_case identifier for grouping across dreams (e.g., "faceless_figure", "dark_ocean", "floating_staircase")
- display_name: human-readable name
- description: visual/emotional description from this dream
- attributes: {appearance, behavior, emotional_tone, role_in_dream}

CRITICAL: canonical_name must be NORMALIZED. "a shadowy man", "the dark figure", "man with no face" should ALL be "faceless_figure". Use the most generic, reusable form.

Output JSON array:
```json
[
  {
    "entity_type": "character",
    "canonical_name": "faceless_figure",
    "display_name": "The Faceless Figure",
    "description": "A tall dark figure with no discernible face...",
    "attributes": {"appearance": "tall, dark", "behavior": "watching silently", "emotional_tone": "menacing", "role_in_dream": "pursuer"}
  }
]
```

Output ONLY the JSON array. Extract at least 3 entities. Include characters, key locations, and significant objects/symbols."""


async def extract_entities(dream_script: dict, chat_history: list[dict] = None) -> list[dict]:
    """Extract entities from a dream script. Returns list of entity dicts."""
    script_text = json.dumps(dream_script, ensure_ascii=False)

    # Add interview context for richer extraction
    context = ""
    if chat_history:
        user_msgs = [m["content"] for m in chat_history if m["role"] == "user"]
        context = f"\n\nOriginal dream descriptions:\n" + "\n".join(user_msgs[:5])

    raw = await chat_completion(
        messages=[{"role": "user", "content": f"Dream script:\n{script_text}{context}"}],
        system=EXTRACTION_PROMPT,
        max_tokens=2000,
    )

    # Parse JSON
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]

    try:
        entities = json.loads(raw.strip())
        if isinstance(entities, list):
            return entities
    except json.JSONDecodeError:
        pass

    return []


def canonicalize_against_existing(
    new_entity: dict, existing_entities: list[dict], threshold: float = 0.6
) -> str:
    """Check if a new entity matches any existing one. Returns canonical_name."""
    new_name = new_entity.get("canonical_name", "").lower()
    new_desc = new_entity.get("description", "").lower()
    new_type = new_entity.get("entity_type", "")

    for existing in existing_entities:
        if existing.get("entity_type") != new_type:
            continue

        existing_name = existing.get("canonical_name", "").lower()

        # Exact match
        if new_name == existing_name:
            return existing_name

        # Fuzzy name match
        name_sim = SequenceMatcher(None, new_name, existing_name).ratio()
        if name_sim >= threshold:
            return existing_name

        # Description similarity (for ambiguous cases)
        existing_desc = existing.get("description", "").lower()
        if existing_desc and new_desc:
            desc_sim = SequenceMatcher(None, new_desc[:100], existing_desc[:100]).ratio()
            if desc_sim >= 0.7:
                return existing_name

    return new_name


async def extract_emotion_scores(interpretation: dict) -> tuple[float, float]:
    """Extract valence (-1 to 1) and arousal (0 to 1) from interpretation."""
    emotion_text = interpretation.get("emotion_analysis", "")
    summary = interpretation.get("summary", "")

    raw = await chat_completion(
        messages=[{"role": "user", "content": f"Based on this dream interpretation, score the emotional content.\n\nEmotion analysis: {emotion_text}\nSummary: {summary}\n\nOutput ONLY two numbers separated by comma:\nvalence (from -1.0 very negative to 1.0 very positive),arousal (from 0.0 very calm to 1.0 very intense)\n\nExample: -0.3,0.7"}],
        system="You are an emotion scoring system. Output only two decimal numbers separated by a comma. No other text.",
        max_tokens=20,
    )

    try:
        parts = raw.strip().split(",")
        valence = max(-1.0, min(1.0, float(parts[0].strip())))
        arousal = max(0.0, min(1.0, float(parts[1].strip())))
        return valence, arousal
    except (ValueError, IndexError):
        return 0.0, 0.5


def is_nightmare(dream_script: dict, interpretation: dict) -> bool:
    """Detect if a dream is a nightmare based on content analysis."""
    emotion = (dream_script.get("overall_emotion") or "").lower()
    summary = (interpretation.get("summary") or "").lower()
    emotion_analysis = (interpretation.get("emotion_analysis") or "").lower()

    nightmare_keywords = [
        "fear", "terror", "horror", "nightmare", "dread", "panic", "anxiety",
        "chase", "attack", "death", "dying", "scream", "trapped", "suffocate",
        "恐惧", "惊恐", "噩梦", "害怕", "恐怖", "追赶", "死亡", "窒息", "困住",
    ]

    all_text = f"{emotion} {summary} {emotion_analysis}"
    hit_count = sum(1 for kw in nightmare_keywords if kw in all_text)

    return hit_count >= 3
