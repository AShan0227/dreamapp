"""Wave K — safety + payments integrity + analytics + user trust.

Revision ID: 0007_wave_k
Revises: 0006_threads
Create Date: 2026-04-17 22:00:00.000000

Adds:
  - payment_webhook_events      — signed webhook audit trail (K1)
  - crisis_flags                — human-review queue for crisis detection (K2)
  - analytics_events            — funnel / retention tracking (K5)
  - users.is_banned, is_staff, ban_reason, banned_at
  - users.locale, push_token, wechat_openid
  - content_reports new cols    — resolved_at, action_taken, moderator_id,
                                  moderator_note (K3 — extends existing table)
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_wave_k"
down_revision = "0006_threads"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def _has_column(conn, table: str, col: str) -> bool:
    if not _has_table(conn, table):
        return False
    cols = {c["name"] for c in sa.inspect(conn).get_columns(table)}
    return col in cols


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------- payment_webhook_events ------------------------------
    if not _has_table(bind, "payment_webhook_events"):
        op.create_table(
            "payment_webhook_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("provider", sa.String(), nullable=False, index=True),
            sa.Column("event_id", sa.String(), index=True),
            sa.Column("out_trade_no", sa.String(), index=True),
            sa.Column("verified", sa.Boolean(), server_default="false", index=True),
            sa.Column("raw_summary", sa.Text()),
            sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        )
        op.create_index(
            "ix_pwhk_provider_event",
            "payment_webhook_events",
            ["provider", "event_id"],
        )

    # ---------------- crisis_flags ----------------------------------------
    if not _has_table(bind, "crisis_flags"):
        op.create_table(
            "crisis_flags",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), index=True),
            sa.Column("dream_id", sa.String(), index=True),
            sa.Column("severity", sa.String(), nullable=False, index=True),
            sa.Column("surface", sa.String(), nullable=False),
            sa.Column("matched_patterns", sa.JSON()),
            sa.Column("locale", sa.String(), server_default="zh-CN"),
            sa.Column("reviewed", sa.Boolean(), server_default="false", index=True),
            sa.Column("action_taken", sa.Text()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
            sa.Column("reviewed_at", sa.DateTime()),
        )

    # ---------------- analytics_events ------------------------------------
    if not _has_table(bind, "analytics_events"):
        op.create_table(
            "analytics_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("event", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), index=True),
            sa.Column("session_id", sa.String(), index=True),
            sa.Column("props", sa.JSON()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        )

    # ---------------- users: moderation + locale + push -------------------
    for col, ddl in [
        ("is_banned", sa.Column("is_banned", sa.Boolean(), server_default="false", index=True)),
        ("is_staff", sa.Column("is_staff", sa.Boolean(), server_default="false")),
        ("ban_reason", sa.Column("ban_reason", sa.String())),
        ("banned_at", sa.Column("banned_at", sa.DateTime())),
        ("locale", sa.Column("locale", sa.String(), server_default="zh-CN")),
        ("push_token", sa.Column("push_token", sa.String())),
        ("wechat_openid", sa.Column("wechat_openid", sa.String(), index=True)),
    ]:
        if not _has_column(bind, "users", col):
            op.add_column("users", ddl)

    # ---------------- content_reports: moderation resolution cols ---------
    if _has_table(bind, "content_reports"):
        for col, ddl in [
            ("resolved_at", sa.Column("resolved_at", sa.DateTime(), index=True)),
            ("action_taken", sa.Column("action_taken", sa.String())),
            ("moderator_id", sa.Column("moderator_id", sa.String())),
            ("moderator_note", sa.Column("moderator_note", sa.Text())),
        ]:
            if not _has_column(bind, "content_reports", col):
                op.add_column("content_reports", ddl)


def downgrade() -> None:
    # Dropping these is destructive (loses audit trail, crisis review history,
    # analytics). Kept as explicit ops-only path; comment out by default.
    op.drop_table("analytics_events")
    op.drop_table("crisis_flags")
    op.drop_table("payment_webhook_events")
    for col in [
        "wechat_openid", "push_token", "locale",
        "banned_at", "ban_reason", "is_staff", "is_banned",
    ]:
        try:
            op.drop_column("users", col)
        except Exception:
            pass
    for col in ["moderator_note", "moderator_id", "action_taken", "resolved_at"]:
        try:
            op.drop_column("content_reports", col)
        except Exception:
            pass
