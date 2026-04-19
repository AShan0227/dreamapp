"""Crisis keyword detection — regression + sensitivity tests.

A false negative is liability. We verify every HIGH_* pattern fires and
that compound MEDIUM patterns escalate correctly. False positives are
acceptable (we offer a hotline, not a diagnosis).

Run:
    pytest tests/test_crisis.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.crisis import detect  # noqa: E402


# ---- High-severity: any HIGH match → severity="crisis", suppress_ai=True --

HIGH_ENGLISH_TRIGGERS = [
    "I want to commit suicide",
    "I'm going to kill myself tonight",
    "ending my life seems right",
    "I don't want to be alive anymore",
    "better off dead",
    "no reason to continue",
    "jumping off a bridge sounds peaceful",
    "I've been cutting myself",
    "domestic violence at home",
    "I was sexually assaulted",
]

HIGH_CHINESE_TRIGGERS = [
    "我想自杀",
    "我不想活了",
    "结束我的生命",
    "想跳楼",
    "我最近在自残",
    "被强奸过",
    "被家暴",
    "我想消失",
    "撑不下去了",
]


def test_high_english_triggers_all_fire():
    for phrase in HIGH_ENGLISH_TRIGGERS:
        d = detect(phrase, locale="en")
        assert d.triggered, f"HIGH en phrase missed: {phrase!r}"
        assert d.severity == "crisis"
        assert d.suppress_ai is True
        assert d.hotlines.get("primary"), f"en must return hotline: {phrase!r}"


def test_high_chinese_triggers_all_fire():
    for phrase in HIGH_CHINESE_TRIGGERS:
        d = detect(phrase, locale="zh-CN")
        assert d.triggered, f"HIGH zh phrase missed: {phrase!r}"
        assert d.severity == "crisis"
        assert d.suppress_ai is True
        assert d.hotlines.get("primary"), f"zh must return hotline: {phrase!r}"


# ---- Psychosis routing — different payload (urgent care, not hotline) ----

def test_psychosis_signals_classified_separately():
    for phrase in [
        "voices telling me to do things",
        "the government is reading my mind",
        "政府在监控我",
        "有声音叫我",
    ]:
        d = detect(phrase)
        assert d.severity == "psychosis"
        assert d.suppress_ai is True


# ---- Medium — single hit should NOT trigger crisis -----------------------

def test_single_medium_does_not_trigger_crisis():
    """One watch-level signal alone is 'concerning but not crisis'.

    Note: detect() escalates to crisis at >=2 medium matches (see module
    docstring), so we construct a phrase with exactly one medium hit.
    """
    d = detect("feeling hopeless this week")   # only "hopeless" matches
    assert d.severity == "watch"
    assert d.suppress_ai is False


def test_two_mediums_escalate_to_crisis():
    """Accumulated medium signals should reach crisis."""
    d = detect("I can't do this anymore, I give up, nothing matters, I'm worthless and hopeless")
    assert d.severity == "crisis"


# ---- Clean text should NOT trigger ---------------------------------------

CLEAN_PHRASES = [
    "I dreamt of flying above a purple ocean",
    "有个黑色的门在走廊里",
    "My cat appeared in a lucid dream",
    "梦到前任,在一个咖啡店里",
    "nightmare",   # bare word "nightmare" is NOT a crisis signal
    "I'm emo today about my job",
]


def test_clean_text_does_not_trigger():
    for phrase in CLEAN_PHRASES:
        d = detect(phrase)
        assert d.severity == "none", f"false positive on: {phrase!r} matched={d.matched}"
        assert d.suppress_ai is False


# ---- Locale routing ------------------------------------------------------

def test_chinese_locale_returns_zh_hotline():
    d = detect("我想自杀", locale="zh-CN")
    assert d.hotlines["primary"]["phone"] == "010-82951332"


def test_english_locale_returns_988():
    d = detect("I want to kill myself", locale="en")
    assert "988" in d.hotlines["primary"]["phone"]
