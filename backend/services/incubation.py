"""Dream Incubation — active dreaming / pre-sleep content recommendations."""

import json
from pathlib import Path

from services.llm import chat_completion
from services.knowledge import match_symbols

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _load_incubation_data() -> dict:
    path = KNOWLEDGE_DIR / "incubation.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"themes": []}


_incubation_data = _load_incubation_data()


async def create_incubation(intention: str) -> dict:
    """Parse intention and generate pre-sleep recommendations."""
    # Extract themes via LLM
    raw = await chat_completion(
        messages=[{"role": "user", "content": f"Parse this dream intention into 3-5 key themes/keywords:\n\n\"{intention}\"\n\nOutput JSON: {{\"themes\": [\"theme1\", \"theme2\"], \"emotion\": \"desired emotion\"}}"}],
        system="Extract dream intention themes. Output ONLY JSON.",
        max_tokens=200,
    )

    try:
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0] if "```json" in raw else raw.split("```")[1].split("```")[0]
        parsed = json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError):
        parsed = {"themes": [intention], "emotion": "neutral"}

    themes = parsed.get("themes", [intention])
    emotion = parsed.get("emotion", "neutral")

    # Match against knowledge base
    matched_symbols = match_symbols(" ".join(themes))

    # Generate personalized recommendations
    reco_prompt = f"""Generate pre-sleep recommendations to help someone dream about: {intention}

Themes: {', '.join(themes)}
Desired emotion: {emotion}

Provide:
1. images: 3 visual scenes to meditate on before sleep (vivid descriptions)
2. sounds: soundscape description (specific sounds + frequencies)
3. meditation: a 2-sentence guided relaxation seed
4. scent: aromatherapy suggestion

Output JSON: {{"images": [...], "sounds": "...", "meditation": "...", "scent": "..."}}"""

    raw = await chat_completion(
        messages=[{"role": "user", "content": reco_prompt}],
        system="You are a dream incubation expert. Generate pre-sleep content to influence dream content.",
        max_tokens=800,
    )

    try:
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0] if "```json" in raw else raw.split("```")[1].split("```")[0]
        recommendations = json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError):
        recommendations = {
            "images": [f"Visualize: {intention}"],
            "sounds": "Ambient sounds related to your intention",
            "meditation": f"Close your eyes and picture yourself in a scene about {intention}.",
            "scent": "Lavender for relaxation",
        }

    return {
        "intention_tags": themes,
        "recommendations": recommendations,
        "matched_symbols": [s.get("name_en", s.get("name", "?")) for s in matched_symbols[:5]],
    }


async def evaluate_outcome(intention: str, dream_script: dict) -> dict:
    """Compare incubation intention with actual dream. Returns match score and analysis."""
    script_text = json.dumps(dream_script, ensure_ascii=False)

    raw = await chat_completion(
        messages=[{"role": "user", "content": f"The dreamer wanted to dream about: \"{intention}\"\n\nThey actually dreamed:\n{script_text}\n\nScore how well the incubation worked (0.0 = no match, 1.0 = perfect match). Explain briefly.\n\nOutput JSON: {{\"match_score\": 0.X, \"analysis\": \"...\"}}"}],
        system="Score dream incubation effectiveness. Output ONLY JSON.",
        max_tokens=300,
    )

    try:
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0] if "```json" in raw else raw.split("```")[1].split("```")[0]
        result = json.loads(raw.strip())
        return {
            "match_score": max(0.0, min(1.0, float(result.get("match_score", 0)))),
            "analysis": result.get("analysis", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {"match_score": 0.0, "analysis": "Unable to evaluate"}
