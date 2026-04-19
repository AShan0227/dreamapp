"""Crisis detection + routing for mental-health-adjacent product.

Triggers when user dream/chat content suggests acute distress, suicidal
ideation, self-harm, abuse, or psychosis. On trigger:
  1. Returns a crisis_response payload (hotlines, gentle copy)
  2. Suppresses video generation for the affected dream
  3. Logs to CrisisFlag table for human review queue
  4. Does NOT block dream recording — user must still be able to express;
     it's the AI's RESPONSE that changes, not the user's freedom to write.

Two detection layers:
  - L1 keyword/phrase match (fast, no LLM call) — high precision triggers
  - L2 (optional) LLM zero-shot classifier on borderline content

Localized for zh + en. Hotlines are jurisdiction-aware (best-effort by
locale; user can override in profile).

Design principle: false positives are OK (we offer a hotline), false
negatives are not. Tune toward sensitive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


# ---------------- Trigger lexicon -------------------------------------------
# Categorized by severity. ANY HIGH match → crisis. MEDIUM matches need 2+ to
# trigger. LOW are tracked but don't trigger on their own.
#
# IMPORTANT — reviewing this list:
# - "Dream about" framing softens but does not eliminate signal. A user who
#   repeatedly dreams of suicide is still in distress; the dream is the
#   excuse to surface what they don't yet have words for.
# - 中文部分包括口语和书面语两种,以及网络隐语(如"上路了"、"想躺平到底")。
# - Pure metaphor will sometimes trigger ("kill it at work"). The response
#   we give is gentle enough that this is acceptable cost.

HIGH_EN = [
    r"\bsuicid", r"\bkill myself", r"\bend(ing)? my life", r"\bend it all",
    r"\bending (my|this|it all)\b",                # "ending my life" / "ending it all"
    r"\btake my (own )?life", r"\bdon'?t want to (live|be alive|exist|wake up)",
    r"\bbetter off (dead|without me)", r"\bno reason to (live|continue|go on)",
    r"\b(jump|jumping) off (a |the )?(bridge|building|roof)",
    r"\boverdose on", r"\bhang myself", r"\bshoot myself",
    r"\b(self[- ]?harm|cutting myself|burning myself)",
    r"\b(rape|raped|sexual(ly)? assault)",
    r"\bbeing abused\b", r"\bdomestic violence",
]
HIGH_ZH = [
    r"自杀", r"想死", r"不想活", r"不想活了", r"活不下去",
    r"结束(自己的|我的)?生命", r"了结(自己|生命)",
    r"跳楼", r"上吊", r"割腕", r"自残", r"自伤", r"吞药",
    r"被强奸", r"被强暴", r"被性侵", r"被家暴", r"家庭暴力",
    r"我想消失", r"消失算了", r"撑不下去", r"撑不住了",
    r"想躺平到底", r"上路了",  # 网络隐语
]

MEDIUM_EN = [
    r"\bcan'?t (do|take) (this|it) anymore", r"\bgive up\b",
    r"\bnothing matters\b", r"\bworthless\b", r"\bhopeless\b",
    r"\bnobody (would|will) (miss|care)\b",
    r"\bplan(ning)? to hurt", r"\bafraid I'?ll hurt",
]
MEDIUM_ZH = [
    r"撑不住", r"放弃了", r"没有意义", r"没人会想我",
    r"觉得自己没用", r"觉得活着没意思",
    r"很痛苦", r"想伤害自己", r"想伤害(他|她|TA)",
]

# Acute psychosis signals — different routing (urgent care, not hotline)
PSYCHOSIS_EN = [
    r"\bvoices? (telling|told) me", r"\bthe voices",
    r"\bbeing (followed|watched|tracked) (constantly|all the time)",
    r"\bgovernment is (in my|reading my) (mind|head)",
    r"\bplanted (a chip|a device) in (me|my)",
]
PSYCHOSIS_ZH = [
    r"有声音叫我", r"听到声音让我",
    r"政府在监控我", r"被(跟踪|监视)了很久",
    r"(芯片|设备)被植入",
]


# ---------------- Hotline directory -----------------------------------------

HOTLINES = {
    "zh-CN": {
        "primary": {
            "name": "北京心理危机研究与干预中心",
            "phone": "010-82951332",
            "available": "24小时",
        },
        "secondary": {
            "name": "希望24热线 / 全国心理援助",
            "phone": "400-161-9995",
            "available": "24小时",
        },
        "text": "向晚上10点-早上6点可加微信公众号「树洞救援团」",
    },
    "en": {
        "primary": {
            "name": "988 Suicide & Crisis Lifeline (US)",
            "phone": "988",
            "available": "24/7",
        },
        "secondary": {
            "name": "Crisis Text Line",
            "phone": "Text HOME to 741741 (US/CA/UK/IE)",
            "available": "24/7",
        },
        "text": "If you are not in the US: https://findahelpline.com",
    },
    "default": {
        "primary": {
            "name": "International Association for Suicide Prevention",
            "phone": "https://www.iasp.info/resources/Crisis_Centres/",
            "available": "Directory by country",
        },
    },
}


@dataclass
class CrisisDetection:
    triggered: bool
    severity: str  # "none" | "watch" | "crisis" | "psychosis"
    matched: list[str]   # the regex labels matched (for audit/QA)
    locale: str
    message: str         # gentle message to show user
    hotlines: dict       # the hotline directory entry for their locale
    suppress_ai: bool    # interpreter / video should be paused

    @property
    def should_block_video(self) -> bool:
        return self.suppress_ai


def _scan(text: str, patterns: list[str]) -> list[str]:
    matches = []
    if not text:
        return matches
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE | re.UNICODE):
            matches.append(pat)
    return matches


def detect(
    text: str,
    locale: str = "zh-CN",
) -> CrisisDetection:
    """Run synchronous keyword detection on the provided text.

    `text` should be the COMBINED user input — initial input + chat history
    user-side messages + any narrative the user wrote. Don't pass the AI's
    own output (false positives from interpreted symbolism).
    """
    high = _scan(text, HIGH_EN + HIGH_ZH)
    med = _scan(text, MEDIUM_EN + MEDIUM_ZH)
    psy = _scan(text, PSYCHOSIS_EN + PSYCHOSIS_ZH)

    severity = "none"
    if high or len(med) >= 2:
        severity = "crisis"
    elif med:
        severity = "watch"
    if psy:
        severity = "psychosis"

    triggered = severity in ("crisis", "psychosis")
    hotlines = HOTLINES.get(locale, HOTLINES.get("zh-CN" if locale.startswith("zh") else "en", HOTLINES["default"]))

    if severity == "psychosis":
        message = _psychosis_message(locale)
        suppress = True
    elif severity == "crisis":
        message = _crisis_message(locale)
        suppress = True
    elif severity == "watch":
        message = _watch_message(locale)
        suppress = False  # let AI continue but log
    else:
        message = ""
        suppress = False

    return CrisisDetection(
        triggered=triggered,
        severity=severity,
        matched=high + med + psy,
        locale=locale,
        message=message,
        hotlines=hotlines,
        suppress_ai=suppress,
    )


def _crisis_message(locale: str) -> str:
    if locale.startswith("zh"):
        return (
            "你写的内容让我有点担心你。我没有办法在这里替代专业的支持,"
            "但你愿意打一个电话吗?下面这个号码 24 小时都有人接听。"
            "你的梦我先不解读,先把你照顾好。"
        )
    return (
        "What you wrote makes me concerned for you. I'm not the right "
        "support for this moment — but the line below has a person who "
        "can listen, 24/7. Your dream can wait. You can't."
    )


def _psychosis_message(locale: str) -> str:
    if locale.startswith("zh"):
        return (
            "听起来你最近经历了一些非常强烈、非常压迫的体验。"
            "这些感受是真实的,但它们也可能在告诉你身体或大脑需要被照顾。"
            "请考虑联系下面的热线或就近的精神科。我会在你身边,但我不替代医生。"
        )
    return (
        "What you're describing sounds intense and heavy. These experiences "
        "are real to you, and they may also be a signal that your mind or "
        "body needs care that goes beyond what I can offer. Please consider "
        "reaching out to the line below or your nearest psychiatric service."
    )


def _watch_message(locale: str) -> str:
    if locale.startswith("zh"):
        return "我注意到你最近不太轻松。如果你想找个人说话,这里有 24 小时的热线。"
    return "It sounds like you're carrying a lot right now. If you ever want a person to talk to, this line is open 24/7."


# ---------------- Persistence ----------------------------------------------

async def log_crisis_flag(
    db: AsyncSession,
    user_id: Optional[str],
    dream_id: Optional[str],
    detection: CrisisDetection,
    surface: str,  # "interview" | "interpretation" | "narrative" | "thread" | "dm"
) -> None:
    """Append-only flag for human review queue. Failure to log is logged
    but does not raise — never block the user response on a logging error.
    """
    if detection.severity == "none":
        return
    try:
        from models.engagement import CrisisFlag
        flag = CrisisFlag(
            user_id=user_id,
            dream_id=dream_id,
            severity=detection.severity,
            surface=surface,
            matched_patterns=detection.matched,
            locale=detection.locale,
        )
        db.add(flag)
        await db.commit()
    except Exception as e:
        # Best-effort: don't break the user-facing response.
        import logging
        logging.getLogger(__name__).exception("Failed to log crisis flag: %s", e)


def crisis_response_payload(detection: CrisisDetection) -> dict:
    """Shape for the API response when crisis is triggered. Frontend
    is expected to render this with care — overlay, large hotline button,
    not buried in interpretation copy.
    """
    return {
        "crisis": True,
        "severity": detection.severity,
        "message": detection.message,
        "hotlines": detection.hotlines,
        "interpretation_paused": detection.suppress_ai,
    }
