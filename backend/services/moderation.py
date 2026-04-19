"""Content moderation — blocklist + heuristics + report intake + review queue.

Three layers:
  1. **Pre-publish gate** — auto-run on anything that becomes public
     (plaza dream, thread post, comment, profile bio). Blocks hard hits
     before they land; flags soft hits for review but allows publish.
  2. **Report intake** — any user can flag any public content. Reports go
     into `ContentReport` table with reason + reporter id. A single report
     doesn't remove content; a 3rd report on the same target auto-hides
     pending review.
  3. **Moderator queue** — admin endpoints to review flagged content and
     apply actions (allow / soft-hide / delete / ban user).

Signals:
  - Zero-tolerance lexicon (CSAM, racial slurs, explicit threats, doxxing)
  - NSFW-leaning lexicon (soft block + review)
  - Spam signals (URL shorteners, repeated promotional phrases)
  - Prompt-injection signals (for content flowing back into LLM context)

This module is deliberately boring and lexicon-based. The real policy
work lives in the lists. An LLM classifier can be added later as a
second stage once we have labeled data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------- Policy lexicon --------------------------------------------
# HARD = auto-block + hide + human review
# SOFT = allow but flag for review; accumulate signals
# SPAM = different treatment — block/soft depending on user reputation

# Explicitly illegal / zero-tolerance (CSAM indicators, terror, direct threats)
HARD_PATTERNS = [
    # CSAM indicators — any literal mention of sexualized minors
    r"\b(child|children|kid|minor|teen|toddler)s?\s+(porn|nude|naked|sex|fuck)",
    r"\b(porn|nude|sex)\s+(child|children|kid|minor|teen|toddler)",
    r"儿童色情", r"幼儿色情", r"萝莉色情", r"未成年.*(裸|性爱|色情)",
    # Direct violent threats with specific target
    r"\bI'?ll (kill|murder|behead|stab) (you|him|her|them)\b",
    r"我要(杀|宰|砍)(死|了)?(你|他|她)",
    # Doxxing attempts (address + name pattern is weak heuristic; err on review)
    r"\baddress is \d+\s+\w+\s+(street|st\.|avenue|ave|road|rd\.|lane)",
    # Terror / mass-event specific phrases
    r"\b(bomb|attack) (at|on) the\b.*(school|mall|church|mosque|synagogue|temple)",
]

# NSFW — allowed in private dream journaling, flagged in public surfaces
NSFW_PATTERNS = [
    r"\b(porn|pornography|xxx|nsfw|explicit sex(ual)?)\b",
    r"\b(blow ?job|hand ?job|cum ?shot|gang ?bang)\b",
    r"裸(照|露|体).*(发|卖|买|求)", r"色情(图|视频|直播)",
    r"露[点骨肉]", r"(黄|色)图",
]

# Hate speech — racial/ethnic slurs (deliberately partial; the real list is
# kept in an ops-only file that's not committed). Matches trigger review.
SLUR_PATTERNS = [
    # Keep this list intentionally short here; an ops-managed additional
    # list can be loaded from env var DREAM_SLUR_EXTRA (comma-separated).
    r"\bn[i1]gg[ae]r\b", r"\bf[a4]gg?[oe]?t\b", r"\bch[i1]nk\b",
    r"\btr[a4]nn[iy]\b",
]

# Spam — promotional patterns that shouldn't live in a dream plaza
SPAM_PATTERNS = [
    r"(https?://|www\.)[^\s]{6,}",  # any URL — review for new/low-rep users
    r"加我?微信[:： ]?\w+", r"加我?v[xX][:： ]?\w+",
    r"\b(join|buy|visit|check out)\b.*\b(telegram|discord|channel|group)\b",
    r"(usdt|btc|eth|crypto|airdrop|免费领取|福利|裙号)",
]

# Prompt injection — content that will likely be re-ingested into an LLM
# prompt (comments on dreams, shared narratives). Strip or flag.
INJECTION_PATTERNS = [
    r"(?i)ignore (all )?(previous|above) (instructions|prompts)",
    r"(?i)you are now (dan|an uncensored)",
    r"(?i)system prompt[:：]",
    r"(?i)</?s>", r"(?i)<\|im_(start|end)\|>",
    r"忽略(以上|之前)的(指令|提示)",
]


@dataclass
class ModerationResult:
    action: str  # "allow" | "soft_flag" | "hard_block"
    reasons: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sanitized_text: Optional[str] = None  # with injection attempts removed

    @property
    def is_blocked(self) -> bool:
        return self.action == "hard_block"

    @property
    def needs_review(self) -> bool:
        return self.action in ("soft_flag", "hard_block")


def _scan(text: str, patterns: list[str], label: str) -> list[str]:
    hits = []
    for pat in patterns:
        if re.search(pat, text or "", flags=re.IGNORECASE | re.UNICODE):
            hits.append(f"{label}:{pat[:40]}")
    return hits


def moderate(text: str, *, surface: str = "public") -> ModerationResult:
    """Synchronous moderation scan.

    surface:
      "public"  — plaza dream, public thread, comment. Full policy.
      "private" — personal dream journal. Only injection + hard patterns.
                  NSFW/slurs/spam are the user's own business in their own
                  journal. Protection only from CSAM / mass-threat content
                  and from prompt injection into our own AI.
    """
    hard = _scan(text, HARD_PATTERNS, "hard")
    inj = _scan(text, INJECTION_PATTERNS, "injection")

    if surface == "private":
        # Private journaling: minimally paternalistic.
        if hard:
            return ModerationResult(action="hard_block", reasons=hard, categories=["hard"])
        sanitized = _strip_injection(text) if inj else None
        if inj:
            return ModerationResult(
                action="soft_flag",
                reasons=inj,
                categories=["injection"],
                sanitized_text=sanitized,
            )
        return ModerationResult(action="allow")

    # Public surface: full policy
    nsfw = _scan(text, NSFW_PATTERNS, "nsfw")
    slurs = _scan(text, SLUR_PATTERNS, "slur")
    spam = _scan(text, SPAM_PATTERNS, "spam")

    if hard:
        return ModerationResult(
            action="hard_block",
            reasons=hard,
            categories=["hard"],
        )

    reasons = nsfw + slurs + inj + spam
    categories = []
    if nsfw: categories.append("nsfw")
    if slurs: categories.append("slur")
    if inj: categories.append("injection")
    if spam: categories.append("spam")

    if reasons:
        return ModerationResult(
            action="soft_flag",
            reasons=reasons,
            categories=categories,
            sanitized_text=_strip_injection(text) if inj else None,
        )
    return ModerationResult(action="allow")


def _strip_injection(text: str) -> str:
    """Best-effort removal of prompt-injection strings before the content is
    fed back into any LLM prompt. Does NOT modify what the user sees —
    callers decide whether to store the sanitized version or keep both.
    """
    out = text
    for pat in INJECTION_PATTERNS:
        out = re.sub(pat, "[removed]", out, flags=re.IGNORECASE | re.UNICODE)
    return out


# ---------------- Report intake ---------------------------------------------

AUTO_HIDE_THRESHOLD = 3  # independent reports on the same target → auto-hide

REPORT_REASONS = {
    "spam": "Spam / promotional / external link",
    "nsfw": "Sexual / explicit content",
    "harassment": "Harassment or bullying",
    "hate": "Hate speech / slurs",
    "violence": "Graphic violence / threats",
    "minor_safety": "Content involving a minor",
    "self_harm": "Self-harm glorification (NOT for crisis — crisis is auto-detected)",
    "misinformation": "Medical / health misinformation",
    "other": "Other",
}


async def submit_report(
    db: AsyncSession,
    reporter_id: str,
    target_type: str,  # "dream" | "thread" | "comment" | "user" | "dm"
    target_id: str,
    reason: str,
    detail: Optional[str] = None,
) -> tuple[bool, int]:
    """Insert a ContentReport row (using models.threads.ContentReport).

    Returns (auto_hidden, total_reports_on_target). auto_hidden=True if this
    report caused the target to cross AUTO_HIDE_THRESHOLD.
    """
    from models.threads import ContentReport
    if reason not in REPORT_REASONS:
        reason = "other"

    # Idempotency — same user reporting same target same reason: overwrite,
    # don't stack
    existing = await db.execute(
        select(ContentReport).where(
            ContentReport.reporter_user_id == reporter_id,
            ContentReport.target_kind == target_type,
            ContentReport.target_id == target_id,
            ContentReport.reason == reason,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.detail = (detail or "")[:1000]
        await db.commit()
    else:
        db.add(ContentReport(
            reporter_user_id=reporter_id,
            target_kind=target_type,
            target_id=target_id,
            reason=reason,
            detail=(detail or "")[:1000],
        ))
        await db.commit()

    # Count distinct reporters on this target (open only)
    count_res = await db.execute(
        select(func.count(func.distinct(ContentReport.reporter_user_id))).where(
            ContentReport.target_kind == target_type,
            ContentReport.target_id == target_id,
            ContentReport.resolved_at.is_(None),
        )
    )
    n = int(count_res.scalar() or 0)

    auto_hidden = False
    if n >= AUTO_HIDE_THRESHOLD:
        auto_hidden = await _auto_hide(db, target_type, target_id)
    return auto_hidden, n


async def _auto_hide(db: AsyncSession, target_type: str, target_id: str) -> bool:
    """Soft-hide the target pending moderator review. Returns True if hidden."""
    if target_type in ("dream", "thread"):  # "thread" is an alias for dream in this product
        from models.dream import DreamRecord
        d = await db.get(DreamRecord, target_id)
        if d and getattr(d, "is_public", False):
            d.is_public = False
            await db.commit()
            return True
    elif target_type == "comment":
        from models.engagement import DreamComment
        c = await db.get(DreamComment, target_id)
        if c and not getattr(c, "is_hidden", False):
            c.is_hidden = True
            await db.commit()
            return True
    elif target_type == "dm":
        # DMs don't have is_hidden; soft-delete by clearing body
        from models.threads import DirectMessage
        m = await db.get(DirectMessage, target_id)
        if m:
            m.body = "[hidden by moderation]"
            await db.commit()
            return True
    return False


# ---------------- Mod queue -------------------------------------------------

async def list_review_queue(
    db: AsyncSession,
    limit: int = 50,
    status: str = "open",  # "open" | "resolved" | "all"
) -> list[dict]:
    """Return items awaiting moderator action, newest first."""
    from models.threads import ContentReport
    q = select(ContentReport)
    if status == "open":
        q = q.where(ContentReport.resolved_at.is_(None))
    elif status == "resolved":
        q = q.where(ContentReport.resolved_at.is_not(None))
    q = q.order_by(ContentReport.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "reporter_id": r.reporter_user_id,
            "target_type": r.target_kind,
            "target_id": r.target_id,
            "reason": r.reason,
            "reason_label": REPORT_REASONS.get(r.reason, r.reason),
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "action_taken": r.action_taken,
            "status": r.status,
        }
        for r in rows
    ]


async def resolve_report(
    db: AsyncSession,
    report_id: str,
    action: str,  # "allow" | "hide" | "delete" | "ban_user"
    moderator_id: str,
    note: Optional[str] = None,
) -> dict:
    from models.threads import ContentReport
    from datetime import datetime
    rep = await db.get(ContentReport, report_id)
    if not rep:
        return {"ok": False, "error": "report not found"}

    if action == "allow":
        await _restore_target(db, rep.target_kind, rep.target_id)
    elif action == "hide":
        await _auto_hide(db, rep.target_kind, rep.target_id)
    elif action == "delete":
        await _soft_delete(db, rep.target_kind, rep.target_id)
    elif action == "ban_user":
        await _ban_target_owner(db, rep.target_kind, rep.target_id)

    rep.resolved_at = datetime.utcnow()
    rep.status = "actioned" if action != "allow" else "dismissed"
    rep.action_taken = action
    rep.moderator_id = moderator_id
    rep.moderator_note = (note or "")[:500]
    await db.commit()
    return {"ok": True, "action": action}


async def _restore_target(db: AsyncSession, target_type: str, target_id: str) -> None:
    if target_type in ("dream", "thread"):
        from models.dream import DreamRecord
        d = await db.get(DreamRecord, target_id)
        if d:
            d.is_public = True
            await db.commit()
    elif target_type == "comment":
        from models.engagement import DreamComment
        c = await db.get(DreamComment, target_id)
        if c:
            c.is_hidden = False
            await db.commit()


async def _soft_delete(db: AsyncSession, target_type: str, target_id: str) -> None:
    from datetime import datetime
    if target_type in ("dream", "thread"):
        from models.dream import DreamRecord
        d = await db.get(DreamRecord, target_id)
        if d and d.deleted_at is None:
            d.deleted_at = datetime.utcnow()
            d.is_public = False
            await db.commit()
    elif target_type == "comment":
        from models.engagement import DreamComment
        c = await db.get(DreamComment, target_id)
        if c:
            c.is_hidden = True
            await db.commit()
    elif target_type == "dm":
        from models.threads import DirectMessage
        m = await db.get(DirectMessage, target_id)
        if m:
            m.body = "[deleted by moderation]"
            await db.commit()


async def _ban_target_owner(db: AsyncSession, target_type: str, target_id: str) -> None:
    """Flip user.is_banned. All content becomes inaccessible to non-staff."""
    from datetime import datetime
    from models.user import UserRecord
    owner_id = None
    if target_type in ("dream", "thread"):
        from models.dream import DreamRecord
        d = await db.get(DreamRecord, target_id)
        if d: owner_id = d.user_id
    elif target_type == "comment":
        from models.engagement import DreamComment
        c = await db.get(DreamComment, target_id)
        if c: owner_id = c.user_id
    elif target_type == "user":
        owner_id = target_id
    if owner_id:
        u = await db.get(UserRecord, owner_id)
        if u and hasattr(u, "is_banned"):
            u.is_banned = True
            if hasattr(u, "banned_at"):
                u.banned_at = datetime.utcnow()
            if hasattr(u, "ban_reason"):
                u.ban_reason = f"moderation:{target_type}:{target_id}"
            await db.commit()
