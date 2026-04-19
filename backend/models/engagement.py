"""Social engagement, monetization, mental-health, B2B models.

Wave H — single migration adds everything needed for Phase 1 (UX) + Phase 2
(monetization). Each table is independent (no cross-table FK constraints)
so partial rollback is trivial.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, JSON, String, Text,
    Enum as SAEnum,
)

from models.dream import Base


# ---------------- Social: comments + reactions + follows --------------------

class DreamComment(Base):
    __tablename__ = "dream_comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dream_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    body = Column(Text, nullable=False)
    parent_id = Column(String, nullable=True)  # threaded replies
    # LLM-scored "warmth" 0..1; very low = auto-hide pending review
    warmth_score = Column(Float, nullable=True)
    is_hidden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DreamReaction(Base):
    """One row per (user, dream, kind). Unique constraint by composite."""
    __tablename__ = "dream_reactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dream_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    # 👍 / 😨 / 🤔 / 🌙 / ❤️ — full emoji whitelist enforced at the API layer
    kind = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    follower_id = Column(String, nullable=False, index=True)
    followee_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Daily curation + challenges -------------------------------

class DailyPick(Base):
    """A dream surfaced as 'dream of the day'. Auto-picked by service or
    manually set by an admin. Deduped to one entry per (date, slot).
    """
    __tablename__ = "daily_picks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date_key = Column(String, nullable=False, index=True)  # "YYYY-MM-DD"
    slot = Column(String, default="featured")  # "featured" | "trending" | "editor"
    dream_id = Column(String, nullable=False)
    blurb = Column(Text, nullable=True)
    pick_reason = Column(JSON, default=dict)  # {top_emotion, reaction_count, ...}
    created_at = Column(DateTime, default=datetime.utcnow)


class DreamChallenge(Base):
    """Weekly themed challenge. Submissions are DreamRecord rows tagged
    with `challenge_keyword` (already on the dream model? no — stored in
    `challenge_submissions` instead to keep DreamRecord clean)."""
    __tablename__ = "dream_challenges"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    keyword = Column(String, nullable=False, unique=True, index=True)  # e.g. "geting-chased"
    title = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    starts_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    submission_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChallengeSubmission(Base):
    __tablename__ = "challenge_submissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    challenge_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    dream_id = Column(String, nullable=False, index=True)
    vote_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Referral / virality ---------------------------------------

class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True, index=True)
    code = Column(String, nullable=False, unique=True, index=True)  # short shareable
    use_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralRedemption(Base):
    __tablename__ = "referral_redemptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, nullable=False, index=True)
    referrer_user_id = Column(String, nullable=False, index=True)
    referred_user_id = Column(String, nullable=False, unique=True)  # one-time
    referrer_reward_coins = Column(Integer, default=0)
    referred_reward_coins = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Sleep tracker integration ---------------------------------

class SleepRecord(Base):
    """A single nightly sleep record imported from Apple Health / Mi Band /
    other tracker. We store the minimum fields needed to cross-correlate
    with dream content."""
    __tablename__ = "sleep_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    night_of = Column(DateTime, nullable=False, index=True)  # date the sleep started
    duration_minutes = Column(Integer, nullable=False)
    rem_minutes = Column(Integer, nullable=True)
    deep_minutes = Column(Integer, nullable=True)
    light_minutes = Column(Integer, nullable=True)
    awake_minutes = Column(Integer, nullable=True)
    avg_hr = Column(Float, nullable=True)
    source = Column(String, default="manual")  # apple_health | mi_band | manual
    raw_payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Therapist marketplace -------------------------------------

class TherapistVerificationStatus(str, Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class TherapistProfile(Base):
    __tablename__ = "therapist_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True, index=True)
    display_name = Column(String, nullable=False)
    bio = Column(Text, nullable=True)
    credentials = Column(JSON, default=list)  # ["PsyD", "registered with X board"]
    specialties = Column(JSON, default=list)  # ["nightmare", "trauma", "lucid"]
    languages = Column(JSON, default=list)
    hourly_rate_cents = Column(Integer, default=0)  # display in user's currency
    currency = Column(String, default="CNY")
    rating_avg = Column(Float, nullable=True)
    rating_count = Column(Integer, default=0)
    # Stored as VARCHAR; using SAEnum here triggers PG asyncpg "missing enum
    # type" errors since the migration didn't create a pg enum type.
    verification_status = Column(String, default="pending")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TherapyBookingStatus(str, Enum):
    requested = "requested"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    refunded = "refunded"


class TherapyBooking(Base):
    __tablename__ = "therapy_bookings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    client_user_id = Column(String, nullable=False, index=True)
    therapist_id = Column(String, nullable=False, index=True)
    scheduled_for = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=50)
    status = Column(String, default="requested")  # see TherapyBookingStatus enum

    # Material the client opted to share with the therapist
    shared_dream_ids = Column(JSON, default=list)
    client_intake_notes = Column(Text, nullable=True)

    price_cents = Column(Integer, default=0)
    currency = Column(String, default="CNY")
    payment_id = Column(String, nullable=True, index=True)
    platform_fee_cents = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------- Payments + subscriptions + entitlements -------------------

class PaymentProvider(str, Enum):
    wechat = "wechat"
    alipay = "alipay"
    stripe = "stripe"
    free = "free"  # internal grant (referral reward, promo)


class PaymentStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"
    cancelled = "cancelled"


class Payment(Base):
    """A single financial transaction. Webhook from provider flips
    status → completed. payment_id is what the provider returns; out_trade_no
    is what we sent (invoice id).
    """
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    out_trade_no = Column(String, nullable=False, unique=True, index=True)
    provider = Column(String, nullable=False)  # see PaymentProvider enum
    provider_payment_id = Column(String, nullable=True, index=True)

    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, default="CNY")

    # What is being paid for? "subscription" | "skip_queue" | "therapy_booking" |
    # "dream_coins" | "agent_install"
    purpose = Column(String, nullable=False, index=True)
    purpose_ref = Column(String, nullable=True)  # e.g. booking id, plan code

    status = Column(String, default="pending")  # see PaymentStatus enum
    failure_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class DailyPrompt(Base):
    """Ops-seeded "tonight try to dream of X" prompts (Wave M).

    One row per (date_key, locale). If no row exists for today, the streak
    service falls back to a deterministic pick from a built-in pool.
    """
    __tablename__ = "daily_prompts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date_key = Column(String, nullable=False, index=True)  # YYYY-MM-DD (UTC)
    locale = Column(String, nullable=False, index=True)    # zh-CN | en
    prompt_text = Column(Text, nullable=False)
    category = Column(String, nullable=True)               # symbol | emotion | narrative | ...
    created_at = Column(DateTime, default=datetime.utcnow)


class DreamRemixLink(Base):
    """Wave O — user-to-user derivative dream attribution.

    Distinct from `DreamRemix` in models.social (AI-assisted recombination
    pipeline). This table only LINKS two existing DreamRecord rows so the
    feed / share page can show "N remixes" of a source dream.

    remix_kind taxonomy:
      "duet"        — side-by-side reaction (user reshoots same script w/ their style)
      "cover"       — user takes original narrative, produces their own visual
      "continuation"— user's dream continues the source's narrative
    """
    __tablename__ = "dream_remix_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_dream_id = Column(String, nullable=False, index=True)
    remix_dream_id = Column(String, nullable=False, index=True, unique=True)
    remixer_user_id = Column(String, nullable=False, index=True)
    remix_kind = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DreamWrappedSnapshot(Base):
    """Wave N — cached year/quarter/month in dreams report.

    Expensive to compute (aggregates all user's dreams + cultural/knowledge
    context), so we cache + expose as shareable via `share_slug`.

    period:  "2026" | "2026-Q2" | "month-2026-04"
    payload: full Wrapped JSON (themes, emotion arc, dominant symbols, etc.)
    """
    __tablename__ = "dream_wrapped_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    period = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    share_slug = Column(String, nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class AnalyticsEvent(Base):
    """Append-only event log for funnel / retention / A-B analysis.

    Kept lightweight: no foreign keys, no cascades, no joins-by-default.
    The canonical event taxonomy is in services/analytics.py.

    Retention: keep 180 days online, archive older to cold storage.
    """
    __tablename__ = "analytics_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    session_id = Column(String, nullable=True, index=True)
    props = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CrisisFlag(Base):
    """Append-only crisis detection log. Human-reviewed downstream.

    severity:  watch | crisis | psychosis
    surface:   where in the product the trigger fired (interview /
               interpretation / narrative / thread / dm / comment)
    matched_patterns: the regex labels that matched (not the raw content,
               for privacy; full content is in the original dream/message).
    reviewed:  set to true once a human (support / on-call) has looked.
    action_taken: free text, e.g. "DM'd user", "called hotline", "muted".
    """
    __tablename__ = "crisis_flags"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True, index=True)
    dream_id = Column(String, nullable=True, index=True)
    severity = Column(String, nullable=False, index=True)
    surface = Column(String, nullable=False)
    matched_patterns = Column(JSON, default=list)
    locale = Column(String, default="zh-CN")
    reviewed = Column(Boolean, default=False, index=True)
    action_taken = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    reviewed_at = Column(DateTime, nullable=True)


class PaymentWebhookEvent(Base):
    """Audit log of all incoming payment webhooks. Two purposes:

    1. **Replay protection** — provider event_id is unique-per-provider; a
       second arrival with the same id is silently dropped before fulfilment.
    2. **Forensics** — when a payment looks wrong, you can trace exactly
       which webhooks arrived, in what order, signed or not.

    Rows are append-only. Verified failures are kept too (verified=False) so
    we can detect attack attempts.
    """
    __tablename__ = "payment_webhook_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=True, index=True)  # provider's unique notify id
    out_trade_no = Column(String, nullable=True, index=True)
    verified = Column(Boolean, default=False, index=True)
    raw_summary = Column(Text, nullable=True)  # truncated body for debugging
    received_at = Column(DateTime, default=datetime.utcnow, index=True)


class SubscriptionTier(str, Enum):
    free = "free"
    pro = "pro"
    premium = "premium"


class Subscription(Base):
    """A user's current subscription. One row per user (the active one);
    cancelled subscriptions stay for history with status='cancelled' and a
    new row is added on resubscribe.
    """
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    tier = Column(String, default="free")  # see SubscriptionTier enum
    status = Column(String, default="active")  # active | cancelled | expired

    # When the current paid period ends. Null for free tier.
    current_period_end = Column(DateTime, nullable=True)
    auto_renew = Column(Boolean, default=True)

    # Last successful payment that grants this period
    last_payment_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------- Dream coins (virtual currency) ----------------------------

class CoinLedger(Base):
    """Append-only ledger. Balance = SUM(delta) WHERE user_id=?.

    Reasons we credit/debit:
      - earn_referral / earn_share / earn_reaction_received / earn_challenge_win
      - earn_purchase (1 RMB = 100 coins)
      - spend_premium_style / spend_skip_queue / spend_gift / spend_therapy
      - admin_grant / admin_clawback
    """
    __tablename__ = "coin_ledger"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    delta = Column(Integer, nullable=False)  # negative for spend
    reason = Column(String, nullable=False, index=True)
    ref = Column(String, nullable=True)  # related dream/booking/payment id
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------- B2B API keys ----------------------------------------------

class APIKey(Base):
    """Long-lived API token for B2B (researchers, therapy clinics, partners).
    Scopes are JSON like ["knowledge:read", "research:read"].
    """
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    key_prefix = Column(String, nullable=False)  # display first 6 chars for ID
    scopes = Column(JSON, default=list)
    monthly_request_quota = Column(Integer, default=10000)
    requests_this_period = Column(Integer, default=0)
    period_start = Column(DateTime, default=datetime.utcnow)
    is_revoked = Column(Boolean, default=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
