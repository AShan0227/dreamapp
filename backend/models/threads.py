"""Threads-style social primitives.

20 patterns adapted from Meta's Threads for the dream domain. All tables
keyed by user_id (string FK to users) with no hard FK constraints —
rebuilds + drops are trivial.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, JSON, String, Text,
)

from models.dream import Base


# ---------------- Profile extensions ---------------------------------------
# Most profile data already lives on UserRecord. We add a small extension
# table to avoid migrating users for optional bio/handle/badges/privacy.

class UserProfileExtra(Base):
    """One row per user. Created on first profile-page hit if missing."""
    __tablename__ = "user_profile_extras"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True, index=True)
    handle = Column(String, unique=True, nullable=True, index=True)  # @username
    bio = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    link = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)  # therapist / researcher / staff
    verified_kind = Column(String, nullable=True)  # "therapist" | "researcher" | "staff"

    # Privacy
    private_account = Column(Boolean, default=False)  # follows require approval
    who_can_comment = Column(String, default="anyone")  # anyone | following | mutual
    who_can_dm = Column(String, default="mutual")      # anyone | following | mutual | nobody
    who_can_mention = Column(String, default="anyone")

    # Pinned dream IDs (max 3, ordered by index)
    pinned_dream_ids = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------- Activity / notifications ---------------------------------

class Notification(Base):
    """A user-facing event for the inbox bell.

    `kind` taxonomy:
      reaction / comment / reply / follow / mention / quote /
      pick_of_day / challenge_win / therapist_response / system
    """
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    actor_user_id = Column(String, nullable=True, index=True)
    target_kind = Column(String, nullable=True)  # "dream" | "comment" | "user"
    target_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, default=dict)  # arbitrary extras (preview text, etc.)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------- Mentions -------------------------------------------------

class Mention(Base):
    """Materialized @-mention edges. Created when a comment / dream body
    contains @handle that resolves to a user. Source-of-truth is the body
    text; this table is the cached index for "who mentioned me?" queries.
    """
    __tablename__ = "mentions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mentioner_user_id = Column(String, nullable=False, index=True)
    mentioned_user_id = Column(String, nullable=False, index=True)
    source_kind = Column(String, nullable=False)  # "comment" | "dream"
    source_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Quote / repost -------------------------------------------

class DreamQuote(Base):
    """A user's "quote" of someone else's dream — their own commentary
    attached on top, surfaced in followers' feed.
    """
    __tablename__ = "dream_quotes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    quoted_dream_id = Column(String, nullable=False, index=True)
    body = Column(Text, nullable=False)
    is_repost_only = Column(Boolean, default=False)  # repost without commentary
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------- Hashtags & topic following -------------------------------

class HashtagFollow(Base):
    __tablename__ = "hashtag_follows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    tag = Column(String, nullable=False, index=True)  # lowercase, no #
    created_at = Column(DateTime, default=datetime.utcnow)


class HashtagUsage(Base):
    """Materialized index of which dreams contain which hashtags. Refreshed
    on dream save; used for trending + topic feed queries.
    """
    __tablename__ = "hashtag_usages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tag = Column(String, nullable=False, index=True)
    dream_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------- Bookmarks ------------------------------------------------

class DreamBookmark(Base):
    """Private save of someone else's (or own) dream."""
    __tablename__ = "dream_bookmarks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    dream_id = Column(String, nullable=False, index=True)
    folder = Column(String, default="default")  # user-named folders
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Polls ----------------------------------------------------

class DreamPoll(Base):
    """A poll attached to a dream (e.g. "what does this symbol mean?")."""
    __tablename__ = "dream_polls"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dream_id = Column(String, nullable=False, index=True)
    creator_user_id = Column(String, nullable=False, index=True)
    question = Column(Text, nullable=False)
    options = Column(JSON, default=list)  # [{id, text}]
    closes_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PollVote(Base):
    __tablename__ = "poll_votes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    poll_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    option_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------- Mute / Block / Report ------------------------------------

class UserMute(Base):
    __tablename__ = "user_mutes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    muter_user_id = Column(String, nullable=False, index=True)
    muted_user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserBlock(Base):
    __tablename__ = "user_blocks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    blocker_user_id = Column(String, nullable=False, index=True)
    blocked_user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentReport(Base):
    """User-submitted abuse / TOS report. Routes to moderation queue.

    Auto-hide: 3+ distinct reporters on same (target_kind, target_id) while
    status='open' trips automatic soft-hide pending human review.
    """
    __tablename__ = "content_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reporter_user_id = Column(String, nullable=False, index=True)
    target_kind = Column(String, nullable=False, index=True)  # "dream" | "thread" | "comment" | "user" | "dm"
    target_id = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=True)
    status = Column(String, default="open", index=True)  # open | reviewing | actioned | dismissed
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Resolution state
    resolved_at = Column(DateTime, nullable=True, index=True)
    action_taken = Column(String, nullable=True)  # allow | hide | delete | ban_user
    moderator_id = Column(String, nullable=True)
    moderator_note = Column(Text, nullable=True)


# ---------------- Direct messages ------------------------------------------

class DirectThread(Base):
    """A 1-1 conversation between two users. user_a < user_b alphabetically
    so we can dedupe on the (a, b) pair regardless of who created it.
    """
    __tablename__ = "direct_threads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_a_id = Column(String, nullable=False, index=True)
    user_b_id = Column(String, nullable=False, index=True)
    last_message_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String, nullable=False, index=True)
    sender_user_id = Column(String, nullable=False, index=True)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------- Dream chain / series -------------------------------------

class DreamSeries(Base):
    """A user-curated sequence of their own dreams telling one ongoing
    story (e.g. "Year of the Faceless Man — 12 dreams over 6 months").
    """
    __tablename__ = "dream_series"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)
    dream_ids = Column(JSON, default=list)  # ordered
    cover_dream_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
