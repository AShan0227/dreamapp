"""Wave H: comments, reactions, follows, daily picks, challenges, referrals,
sleep records, therapist marketplace, payments, subscriptions, coin ledger,
B2B api keys.

Revision ID: 0005_engagement
Revises: 0004_social_models
Create Date: 2026-04-17 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_engagement"
down_revision = "0004_social_models"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "dream_comments"):
        op.create_table(
            "dream_comments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("parent_id", sa.String()),
            sa.Column("warmth_score", sa.Float()),
            sa.Column("is_hidden", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_reactions"):
        op.create_table(
            "dream_reactions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("dream_id", "user_id", "kind", name="uq_dream_reaction"),
        )

    if not _has_table(bind, "user_follows"):
        op.create_table(
            "user_follows",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("follower_id", sa.String(), nullable=False, index=True),
            sa.Column("followee_id", sa.String(), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("follower_id", "followee_id", name="uq_user_follow"),
        )

    if not _has_table(bind, "daily_picks"):
        op.create_table(
            "daily_picks",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("date_key", sa.String(), nullable=False, index=True),
            sa.Column("slot", sa.String(), server_default="featured"),
            sa.Column("dream_id", sa.String(), nullable=False),
            sa.Column("blurb", sa.Text()),
            sa.Column("pick_reason", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_challenges"):
        op.create_table(
            "dream_challenges",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("keyword", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("starts_at", sa.DateTime()),
            sa.Column("ends_at", sa.DateTime()),
            sa.Column("is_active", sa.Boolean(), server_default="true"),
            sa.Column("submission_count", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "challenge_submissions"):
        op.create_table(
            "challenge_submissions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("challenge_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("vote_count", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_user"),
        )

    if not _has_table(bind, "referral_codes"):
        op.create_table(
            "referral_codes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("code", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("use_count", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "referral_redemptions"):
        op.create_table(
            "referral_redemptions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("code", sa.String(), nullable=False, index=True),
            sa.Column("referrer_user_id", sa.String(), nullable=False, index=True),
            sa.Column("referred_user_id", sa.String(), nullable=False, unique=True),
            sa.Column("referrer_reward_coins", sa.Integer(), server_default="0"),
            sa.Column("referred_reward_coins", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "sleep_records"):
        op.create_table(
            "sleep_records",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("night_of", sa.DateTime(), nullable=False, index=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("rem_minutes", sa.Integer()),
            sa.Column("deep_minutes", sa.Integer()),
            sa.Column("light_minutes", sa.Integer()),
            sa.Column("awake_minutes", sa.Integer()),
            sa.Column("avg_hr", sa.Float()),
            sa.Column("source", sa.String(), server_default="manual"),
            sa.Column("raw_payload", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "therapist_profiles"):
        op.create_table(
            "therapist_profiles",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("bio", sa.Text()),
            sa.Column("credentials", sa.JSON()),
            sa.Column("specialties", sa.JSON()),
            sa.Column("languages", sa.JSON()),
            sa.Column("hourly_rate_cents", sa.Integer(), server_default="0"),
            sa.Column("currency", sa.String(), server_default="CNY"),
            sa.Column("rating_avg", sa.Float()),
            sa.Column("rating_count", sa.Integer(), server_default="0"),
            sa.Column("verification_status", sa.String(), server_default="pending"),
            sa.Column("is_active", sa.Boolean(), server_default="true"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "therapy_bookings"):
        op.create_table(
            "therapy_bookings",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("client_user_id", sa.String(), nullable=False, index=True),
            sa.Column("therapist_id", sa.String(), nullable=False, index=True),
            sa.Column("scheduled_for", sa.DateTime(), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), server_default="50"),
            sa.Column("status", sa.String(), server_default="requested"),
            sa.Column("shared_dream_ids", sa.JSON()),
            sa.Column("client_intake_notes", sa.Text()),
            sa.Column("price_cents", sa.Integer(), server_default="0"),
            sa.Column("currency", sa.String(), server_default="CNY"),
            sa.Column("payment_id", sa.String(), index=True),
            sa.Column("platform_fee_cents", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("out_trade_no", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("provider_payment_id", sa.String(), index=True),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(), server_default="CNY"),
            sa.Column("purpose", sa.String(), nullable=False, index=True),
            sa.Column("purpose_ref", sa.String()),
            sa.Column("status", sa.String(), server_default="pending"),
            sa.Column("failure_reason", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
        )

    if not _has_table(bind, "subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("tier", sa.String(), server_default="free"),
            sa.Column("status", sa.String(), server_default="active"),
            sa.Column("current_period_end", sa.DateTime()),
            sa.Column("auto_renew", sa.Boolean(), server_default="true"),
            sa.Column("last_payment_id", sa.String()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "coin_ledger"):
        op.create_table(
            "coin_ledger",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(), nullable=False, index=True),
            sa.Column("ref", sa.String()),
            sa.Column("note", sa.String()),
            sa.Column("created_at", sa.DateTime(), index=True),
        )

    if not _has_table(bind, "api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_user_id", sa.String(), nullable=False, index=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("key_hash", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("scopes", sa.JSON()),
            sa.Column("monthly_request_quota", sa.Integer(), server_default="10000"),
            sa.Column("requests_this_period", sa.Integer(), server_default="0"),
            sa.Column("period_start", sa.DateTime()),
            sa.Column("is_revoked", sa.Boolean(), server_default="false"),
            sa.Column("last_used_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
        )

    # Add is_public column to existing codream_sessions for public lobby
    insp = sa.inspect(bind)
    if "codream_sessions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("codream_sessions")}
        if "is_public" not in cols:
            op.add_column("codream_sessions", sa.Column("is_public", sa.Boolean(), server_default="false"))


def downgrade() -> None:
    bind = op.get_bind()
    for t in (
        "api_keys", "coin_ledger", "subscriptions", "payments",
        "therapy_bookings", "therapist_profiles", "sleep_records",
        "referral_redemptions", "referral_codes",
        "challenge_submissions", "dream_challenges", "daily_picks",
        "user_follows", "dream_reactions", "dream_comments",
    ):
        if _has_table(bind, t):
            op.drop_table(t)
