"""Wave I — 16 new tables for Threads-style social features.

Revision ID: 0006_threads
Revises: 0005_engagement
Create Date: 2026-04-17 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_threads"
down_revision = "0005_engagement"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "user_profile_extras"):
        op.create_table(
            "user_profile_extras",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("handle", sa.String(), unique=True, index=True),
            sa.Column("bio", sa.Text()),
            sa.Column("location", sa.String()),
            sa.Column("link", sa.String()),
            sa.Column("is_verified", sa.Boolean(), server_default="false"),
            sa.Column("verified_kind", sa.String()),
            sa.Column("private_account", sa.Boolean(), server_default="false"),
            sa.Column("who_can_comment", sa.String(), server_default="anyone"),
            sa.Column("who_can_dm", sa.String(), server_default="mutual"),
            sa.Column("who_can_mention", sa.String(), server_default="anyone"),
            sa.Column("pinned_dream_ids", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("kind", sa.String(), nullable=False, index=True),
            sa.Column("actor_user_id", sa.String(), index=True),
            sa.Column("target_kind", sa.String()),
            sa.Column("target_id", sa.String(), index=True),
            sa.Column("payload", sa.JSON()),
            sa.Column("is_read", sa.Boolean(), server_default="false", index=True),
            sa.Column("created_at", sa.DateTime(), index=True),
        )

    if not _has_table(bind, "mentions"):
        op.create_table(
            "mentions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("mentioner_user_id", sa.String(), nullable=False, index=True),
            sa.Column("mentioned_user_id", sa.String(), nullable=False, index=True),
            sa.Column("source_kind", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_quotes"):
        op.create_table(
            "dream_quotes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("quoted_dream_id", sa.String(), nullable=False, index=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_repost_only", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime(), index=True),
        )

    if not _has_table(bind, "hashtag_follows"):
        op.create_table(
            "hashtag_follows",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("tag", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("user_id", "tag", name="uq_hashtag_follow"),
        )

    if not _has_table(bind, "hashtag_usages"):
        op.create_table(
            "hashtag_usages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("tag", sa.String(), nullable=False, index=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(), index=True),
            sa.UniqueConstraint("tag", "dream_id", name="uq_hashtag_dream"),
        )

    if not _has_table(bind, "dream_bookmarks"):
        op.create_table(
            "dream_bookmarks",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("folder", sa.String(), server_default="default"),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("user_id", "dream_id", name="uq_user_bookmark"),
        )

    if not _has_table(bind, "dream_polls"):
        op.create_table(
            "dream_polls",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("creator_user_id", sa.String(), nullable=False, index=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("options", sa.JSON()),
            sa.Column("closes_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "poll_votes"):
        op.create_table(
            "poll_votes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("poll_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("option_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("poll_id", "user_id", name="uq_poll_vote"),
        )

    if not _has_table(bind, "user_mutes"):
        op.create_table(
            "user_mutes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("muter_user_id", sa.String(), nullable=False, index=True),
            sa.Column("muted_user_id", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("muter_user_id", "muted_user_id", name="uq_user_mute"),
        )

    if not _has_table(bind, "user_blocks"):
        op.create_table(
            "user_blocks",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("blocker_user_id", sa.String(), nullable=False, index=True),
            sa.Column("blocked_user_id", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("blocker_user_id", "blocked_user_id", name="uq_user_block"),
        )

    if not _has_table(bind, "content_reports"):
        op.create_table(
            "content_reports",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("reporter_user_id", sa.String(), nullable=False, index=True),
            sa.Column("target_kind", sa.String(), nullable=False),
            sa.Column("target_id", sa.String(), nullable=False, index=True),
            sa.Column("reason", sa.String(), nullable=False),
            sa.Column("detail", sa.Text()),
            sa.Column("status", sa.String(), server_default="open"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "direct_threads"):
        op.create_table(
            "direct_threads",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_a_id", sa.String(), nullable=False, index=True),
            sa.Column("user_b_id", sa.String(), nullable=False, index=True),
            sa.Column("last_message_at", sa.DateTime(), index=True),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("user_a_id", "user_b_id", name="uq_dm_pair"),
        )

    if not _has_table(bind, "direct_messages"):
        op.create_table(
            "direct_messages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("thread_id", sa.String(), nullable=False, index=True),
            sa.Column("sender_user_id", sa.String(), nullable=False, index=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_read", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime(), index=True),
        )

    if not _has_table(bind, "dream_series"):
        op.create_table(
            "dream_series",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("is_public", sa.Boolean(), server_default="false"),
            sa.Column("dream_ids", sa.JSON()),
            sa.Column("cover_dream_id", sa.String()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for t in (
        "dream_series", "direct_messages", "direct_threads",
        "content_reports", "user_blocks", "user_mutes",
        "poll_votes", "dream_polls", "dream_bookmarks",
        "hashtag_usages", "hashtag_follows", "dream_quotes",
        "mentions", "notifications", "user_profile_extras",
    ):
        if _has_table(bind, t):
            op.drop_table(t)
