"""LinUCB-inspired contextual style selector.

Given dream content features (emotions, symbols, narrative type),
recommends the best visual style based on historical outcomes.
"""

import math
import json
from collections import defaultdict
from pathlib import Path

STYLES = [
    "surreal", "ethereal", "noir", "cyberpunk_dream",
    "tarkovsky_poetic", "studio_ghibli_dream", "david_lynch_uncanny",
    "gothic_romantic", "vaporwave_dream", "ancient_mythic",
]

# Feature extractors: map dream content to feature vector
EMOTION_FEATURES = {
    "fear": [1, 0, 0, 0, 0, 0],
    "peace": [0, 1, 0, 0, 0, 0],
    "wonder": [0, 0, 1, 0, 0, 0],
    "sadness": [0, 0, 0, 1, 0, 0],
    "joy": [0, 0, 0, 0, 1, 0],
    "anxiety": [0.7, 0, 0, 0, 0, 0.3],
    "nostalgia": [0, 0.3, 0, 0.5, 0, 0.2],
    "confusion": [0.3, 0, 0.3, 0, 0, 0.4],
}

SYMBOL_FEATURES = {
    "water": [0, 1, 0, 0],
    "fire": [1, 0, 0, 0],
    "flying": [0, 0, 1, 0],
    "chase": [1, 0, 0, 0],
    "mirror": [0, 0, 0, 1],
    "forest": [0, 1, 0, 0],
    "city": [0, 0, 0, 1],
    "death": [0.5, 0, 0, 0.5],
}

# Style-to-feature affinity (manually initialized, updated by feedback)
STYLE_PRIORS = {
    "surreal": {"emotion": [0.5, 0.3, 0.8, 0.3, 0.2, 0.5], "symbol": [0.5, 0.5, 0.7, 0.8]},
    "ethereal": {"emotion": [0, 0.9, 0.7, 0.4, 0.5, 0], "symbol": [0.3, 0.8, 0.6, 0.2]},
    "noir": {"emotion": [0.8, 0, 0.2, 0.6, 0, 0.7], "symbol": [0.3, 0.2, 0.1, 0.9]},
    "cyberpunk_dream": {"emotion": [0.6, 0, 0.5, 0.3, 0.3, 0.6], "symbol": [0.4, 0.2, 0.3, 0.9]},
    "tarkovsky_poetic": {"emotion": [0.2, 0.8, 0.5, 0.7, 0.2, 0.1], "symbol": [0.5, 0.9, 0.3, 0.3]},
    "studio_ghibli_dream": {"emotion": [0.1, 0.7, 0.8, 0.3, 0.8, 0.1], "symbol": [0.3, 0.8, 0.7, 0.2]},
    "david_lynch_uncanny": {"emotion": [0.9, 0.1, 0.4, 0.4, 0, 0.8], "symbol": [0.4, 0.3, 0.2, 0.9]},
    "gothic_romantic": {"emotion": [0.6, 0.2, 0.3, 0.8, 0.1, 0.5], "symbol": [0.5, 0.4, 0.2, 0.6]},
    "vaporwave_dream": {"emotion": [0.2, 0.4, 0.6, 0.5, 0.4, 0.3], "symbol": [0.3, 0.5, 0.5, 0.7]},
    "ancient_mythic": {"emotion": [0.3, 0.5, 0.7, 0.4, 0.3, 0.2], "symbol": [0.6, 0.7, 0.5, 0.4]},
}

# Exploration parameter (Genesis LinUCB alpha)
ALPHA = 0.3


def extract_features(dream_script: dict) -> list[float]:
    """Extract feature vector from dream content."""
    emotion = (dream_script.get("overall_emotion") or "").lower()
    symbols = dream_script.get("symbols", [])

    # Emotion features (6-dim)
    emotion_vec = [0.0] * 6
    for key, vec in EMOTION_FEATURES.items():
        if key in emotion:
            emotion_vec = [max(a, b) for a, b in zip(emotion_vec, vec)]

    # Symbol features (4-dim)
    symbol_vec = [0.0] * 4
    for sym in symbols:
        sym_lower = sym.lower() if isinstance(sym, str) else ""
        for key, vec in SYMBOL_FEATURES.items():
            if key in sym_lower:
                symbol_vec = [max(a, b) for a, b in zip(symbol_vec, vec)]

    return emotion_vec + symbol_vec


def recommend_style(dream_script: dict, exploration: bool = True) -> tuple[str, float]:
    """Recommend best visual style for a dream. Returns (style, confidence)."""
    features = extract_features(dream_script)

    scores = {}
    for style in STYLES:
        prior = STYLE_PRIORS.get(style, {})
        emotion_affinity = prior.get("emotion", [0.5] * 6)
        symbol_affinity = prior.get("symbol", [0.5] * 4)

        # Dot product: feature alignment with style affinity
        affinity = sum(f * a for f, a in zip(features[:6], emotion_affinity))
        affinity += sum(f * a for f, a in zip(features[6:], symbol_affinity))

        # Exploration bonus (UCB-style)
        if exploration:
            affinity += ALPHA * (1.0 / (1 + len(features)))  # Simple UCB bonus

        scores[style] = affinity

    # Pick best
    best_style = max(scores, key=scores.get)
    best_score = scores[best_style]

    # Normalize confidence to 0-1
    max_possible = sum(max(v) for v in [list(EMOTION_FEATURES.values())[0]] * 6) + 4
    confidence = min(1.0, best_score / max(1, max_possible))

    return best_style, round(confidence, 3)


def get_style_ranking(dream_script: dict) -> list[dict]:
    """Get all styles ranked by affinity. For UI display."""
    features = extract_features(dream_script)

    results = []
    for style in STYLES:
        prior = STYLE_PRIORS.get(style, {})
        emotion_affinity = prior.get("emotion", [0.5] * 6)
        symbol_affinity = prior.get("symbol", [0.5] * 4)

        score = sum(f * a for f, a in zip(features[:6], emotion_affinity))
        score += sum(f * a for f, a in zip(features[6:], symbol_affinity))

        results.append({"style": style, "score": round(score, 3)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
