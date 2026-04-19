"""PII redaction helpers for dream content.

Conservative regex-based approach. Catches obvious patterns
(emails, phone numbers, ID numbers, IP addresses, payment cards) and
replaces them with redaction tokens.

Used as a defense-in-depth layer for two flows:
  1. When a dream is published to the plaza (is_public=True), the
     description / script shown to others is run through `redact()` so
     the dreamer's contacts aren't accidentally exposed.
  2. When research CSV exports include corpus text, redact() runs first.

NOT a substitute for proper named-entity removal — real names slip
through. For real PII protection at scale, use a NER model
(e.g. Microsoft Presidio).
"""

from __future__ import annotations

import re

# Patterns intentionally conservative — false negatives preferable to
# false positives that mangle legitimate dream content.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Email
    (re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[email]"),
    # Chinese phone (11 digits starting with 1)
    (re.compile(r"\b1[3-9]\d{9}\b"), "[phone]"),
    # International E.164-ish (+CC followed by 7-15 digits)
    (re.compile(r"\+\d{1,3}[\s-]?\d{6,14}\b"), "[phone]"),
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[ip]"),
    # Chinese resident ID (15 or 18 digits with optional X check char)
    (re.compile(r"\b\d{15}(?:\d{2}[\dX])?\b"), "[id-number]"),
    # Payment card numbers (13-19 digits with optional separators)
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[card]"),
    # Bank account-ish (16-25 digit runs)
    (re.compile(r"\b\d{16,25}\b"), "[account]"),
]


def redact(text: str) -> str:
    """Return the text with high-confidence PII patterns replaced by tokens.

    Pure function; never raises.
    """
    if not text or not isinstance(text, str):
        return text
    out = text
    for pattern, token in _PATTERNS:
        out = pattern.sub(token, out)
    return out


def redact_dream_script(script: dict | None) -> dict | None:
    """Apply redact() to free-text fields inside a dream-script dict.

    Returns a new dict; doesn't mutate the input. Numeric / structural
    fields are passed through.
    """
    if not isinstance(script, dict):
        return script
    REDACT_KEYS = {"title", "description", "visual_details", "synthesis"}
    out: dict = {}
    for k, v in script.items():
        if k in REDACT_KEYS and isinstance(v, str):
            out[k] = redact(v)
        elif k == "scenes" and isinstance(v, list):
            out[k] = [
                {sk: (redact(sv) if isinstance(sv, str) and sk in REDACT_KEYS else sv)
                 for sk, sv in scene.items()}
                if isinstance(scene, dict) else scene
                for scene in v
            ]
        else:
            out[k] = v
    return out
