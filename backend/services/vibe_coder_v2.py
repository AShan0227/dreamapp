"""Vibe Coder real implementation (PRODUCT_DOC §9).

The user types natural language ("I only care about plaza and recording —
hide everything else, big buttons") → an LLM produces a layout config the
frontend dynamically renders.

Layout config schema:

{
  "version": 2,
  "user_archetype": "creator | health | social | interpreter | balanced",
  "tab_bar": [
    {"id": "record", "label": "Record", "icon": "🎙", "primary": true},
    {"id": "plaza", "label": "Plaza", "icon": "🌌"},
    ...
  ],
  "home_widgets": [
    {"id": "recent_dreams", "size": "lg"},
    {"id": "quick_record", "size": "md"},
    {"id": "trending_themes", "size": "md", "hidden": false},
    ...
  ],
  "feature_flags": {
    "show_health_dashboard": false,
    "show_agent_panel": true,
    "compact_mode": false
  },
  "color_accent": "purple | teal | sunset | aurora",
  "explanation": "Short 1-sentence summary of what changed"
}

The frontend treats this as the source of truth for which tab bar
entries / home widgets to show. Falls back to DEFAULT_CONFIG if Vibe
Coder hasn't been used yet.
"""

from __future__ import annotations

import json
from typing import Any

from services.llm import chat_completion
from services.interpreter import _repair_json


DEFAULT_CONFIG = {
    "version": 2,
    "user_archetype": "balanced",
    "tab_bar": [
        {"id": "index", "label": "Dreams", "icon": "🌙", "primary": False},
        {"id": "record", "label": "Record", "icon": "🎙", "primary": True},
        {"id": "plaza", "label": "Plaza", "icon": "🌌", "primary": False},
        {"id": "archive", "label": "Archive", "icon": "📚", "primary": False},
    ],
    "home_widgets": [
        {"id": "recent_dreams", "size": "lg", "hidden": False},
        {"id": "quick_actions", "size": "md", "hidden": False},
        {"id": "health_score", "size": "md", "hidden": False},
        {"id": "incubation", "size": "sm", "hidden": False},
        {"id": "ips", "size": "sm", "hidden": False},
        {"id": "agents", "size": "sm", "hidden": False},
    ],
    "feature_flags": {
        "show_health_dashboard": True,
        "show_agent_panel": True,
        "compact_mode": False,
    },
    "color_accent": "aurora",
    "explanation": "Default balanced layout.",
}


KNOWN_TABS = {"index", "record", "plaza", "archive", "health", "incubation", "ips", "agents", "knowledge", "profile"}
KNOWN_WIDGETS = {"recent_dreams", "quick_actions", "health_score", "incubation", "ips", "agents", "trending_themes", "matching"}
KNOWN_ARCHETYPES = {"creator", "health", "social", "interpreter", "balanced"}
KNOWN_ACCENTS = {"purple", "teal", "sunset", "aurora"}


SYSTEM_PROMPT = """You configure a dream-app's layout from natural-language requests.

You return ONLY a JSON config matching this exact schema. NEVER deviate.
Hide widgets/tabs the user doesn't want by setting hidden:true (don't omit them).

KNOWN tab IDs: index, record, plaza, archive, health, incubation, ips, agents, knowledge, profile
KNOWN widget IDs: recent_dreams, quick_actions, health_score, incubation, ips, agents, trending_themes, matching
KNOWN archetypes: creator (focused on video output + sharing), health (emotional+sleep tracking),
  social (plaza+matching), interpreter (analysis-heavy for pros), balanced (default).
KNOWN accents: purple, teal, sunset, aurora.

ALWAYS include all known tabs + all known widgets in the output (never skip),
toggling primary/hidden flags as appropriate.

Output ONLY the JSON config — no prose."""


def _validate(cfg: Any) -> dict:
    """Normalize an LLM-produced config to the contract.

    Falls back to DEFAULT_CONFIG fields when the LLM produces invalid output.
    Never raises — the user should always get a usable config.
    """
    out = dict(DEFAULT_CONFIG)
    if not isinstance(cfg, dict):
        out["explanation"] = "LLM returned invalid config; using defaults."
        return out

    if cfg.get("user_archetype") in KNOWN_ARCHETYPES:
        out["user_archetype"] = cfg["user_archetype"]
    if cfg.get("color_accent") in KNOWN_ACCENTS:
        out["color_accent"] = cfg["color_accent"]
    if isinstance(cfg.get("explanation"), str):
        out["explanation"] = cfg["explanation"][:200]

    # Tab bar — keep only known IDs, preserve order
    if isinstance(cfg.get("tab_bar"), list):
        tabs = []
        seen = set()
        for t in cfg["tab_bar"]:
            if isinstance(t, dict) and t.get("id") in KNOWN_TABS and t["id"] not in seen:
                tabs.append({
                    "id": t["id"],
                    "label": str(t.get("label") or t["id"].title())[:20],
                    "icon": str(t.get("icon") or "•")[:4],
                    "primary": bool(t.get("primary", False)),
                    "hidden": bool(t.get("hidden", False)),
                })
                seen.add(t["id"])
        # Add any missing known tabs as hidden
        for known in KNOWN_TABS:
            if known not in seen:
                base = next((b for b in DEFAULT_CONFIG["tab_bar"] if b["id"] == known), None)
                tabs.append({
                    "id": known,
                    "label": (base or {}).get("label", known.title()),
                    "icon": (base or {}).get("icon", "•"),
                    "primary": False,
                    "hidden": True,
                })
        out["tab_bar"] = tabs

    if isinstance(cfg.get("home_widgets"), list):
        widgets = []
        seen = set()
        for w in cfg["home_widgets"]:
            if isinstance(w, dict) and w.get("id") in KNOWN_WIDGETS and w["id"] not in seen:
                size = w.get("size", "md")
                if size not in ("sm", "md", "lg"):
                    size = "md"
                widgets.append({
                    "id": w["id"],
                    "size": size,
                    "hidden": bool(w.get("hidden", False)),
                })
                seen.add(w["id"])
        for known in KNOWN_WIDGETS:
            if known not in seen:
                widgets.append({"id": known, "size": "md", "hidden": True})
        out["home_widgets"] = widgets

    if isinstance(cfg.get("feature_flags"), dict):
        flags = dict(out["feature_flags"])
        for k, v in cfg["feature_flags"].items():
            if isinstance(v, bool):
                flags[k] = v
        out["feature_flags"] = flags

    return out


async def process_vibe_request(prompt: str, current_config: dict | None = None) -> dict:
    """Send the natural-language request + current config to the LLM,
    parse the response, validate, return the new config.
    """
    base = current_config if isinstance(current_config, dict) else DEFAULT_CONFIG

    user_message = f"""CURRENT CONFIG:
{json.dumps(base, ensure_ascii=False, indent=2)}

USER REQUEST:
{prompt}

Output the new config JSON. Same schema. Output ONLY JSON."""

    raw = await chat_completion(
        messages=[{"role": "user", "content": user_message}],
        system=SYSTEM_PROMPT,
        max_tokens=2000,
    )
    new_cfg = _repair_json(raw)
    return _validate(new_cfg)
