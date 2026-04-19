"""Wave M — coin_balance denormalization + streak columns + streak events.

Revision ID: 0009_wave_m
Revises: 0008_perf_indexes
Create Date: 2026-04-19 10:00:00.000000

Adds:
  - users.coin_balance                  — denormalized cache of SUM(coin_ledger.delta)
  - users.current_streak_days           — consecutive-day dream-record streak
  - users.longest_streak_days           — personal best
  - users.last_streak_date              — YYYY-MM-DD of last streak-counted day
  - daily_prompts                       — table of pushed "tonight try to dream of X"
  - dream_remix_links                   — Wave O: user→user derivative attribution
  - dream_wrapped_snapshots             — Wave N: cached year-in-dreams reports

Also backfills users.coin_balance from coin_ledger SUM so existing users
don't start at 0.
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_wave_m"
down_revision = "0008_perf_indexes"
branch_labels = None
depends_on = None


def _has_column(conn, table: str, col: str) -> bool:
    if table not in sa.inspect(conn).get_table_names():
        return False
    return col in {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ---- users: coin_balance + streak ----------------------------------
    for col, ddl in [
        ("coin_balance", sa.Column("coin_balance", sa.Integer(), server_default="0")),
        ("current_streak_days", sa.Column("current_streak_days", sa.Integer(), server_default="0")),
        ("longest_streak_days", sa.Column("longest_streak_days", sa.Integer(), server_default="0")),
        ("last_streak_date", sa.Column("last_streak_date", sa.String())),
    ]:
        if not _has_column(bind, "users", col):
            op.add_column("users", ddl)

    # ---- Backfill coin_balance from ledger -----------------------------
    if _has_table(bind, "coin_ledger"):
        try:
            op.execute(
                "UPDATE users SET coin_balance = COALESCE(( "
                "  SELECT SUM(delta) FROM coin_ledger "
                "  WHERE coin_ledger.user_id = users.id "
                "), 0) "
                "WHERE coin_balance IS NULL OR coin_balance = 0"
            )
        except Exception:
            # Non-fatal: repair-on-read in service will catch any stragglers
            pass

    # ---- daily_prompts (Wave M) ----------------------------------------
    if not _has_table(bind, "daily_prompts"):
        op.create_table(
            "daily_prompts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("date_key", sa.String(), nullable=False, index=True),   # YYYY-MM-DD (UTC)
            sa.Column("locale", sa.String(), nullable=False, index=True),     # zh-CN | en
            sa.Column("prompt_text", sa.Text(), nullable=False),
            sa.Column("category", sa.String()),        # e.g. "symbol" | "emotion" | "narrative"
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_daily_prompts_date_locale",
            "daily_prompts",
            ["date_key", "locale"],
            unique=True,
        )

    # ---- dream_remix_links (Wave O) -----------------------------------
    # NOTE: does NOT collide with `dream_remixes` from earlier migration
    # (that's the AI-assisted remix pipeline from models.social). This is
    # the lightweight user-to-user attribution link for duets.
    if not _has_table(bind, "dream_remix_links"):
        op.create_table(
            "dream_remix_links",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("source_dream_id", sa.String(), nullable=False, index=True),
            sa.Column("remix_dream_id", sa.String(), nullable=False, index=True, unique=True),
            sa.Column("remixer_user_id", sa.String(), nullable=False, index=True),
            sa.Column("remix_kind", sa.String(), nullable=False),  # "duet" | "cover" | "continuation"
            sa.Column("note", sa.Text()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        )

    # ---- dream_wrapped_snapshots (Wave N) ------------------------------
    if not _has_table(bind, "dream_wrapped_snapshots"):
        op.create_table(
            "dream_wrapped_snapshots",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("period", sa.String(), nullable=False),     # "2026" | "2026-Q2" | "month-2026-04"
            sa.Column("payload", sa.JSON()),                      # full wrapped report
            sa.Column("share_slug", sa.String(), unique=True, index=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
        )
        op.create_index(
            "ix_wrapped_user_period",
            "dream_wrapped_snapshots",
            ["user_id", "period"],
            unique=True,
        )


def downgrade() -> None:
    for tbl in ("dream_wrapped_snapshots", "dream_remix_links", "daily_prompts"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
    for col in ("last_streak_date", "longest_streak_days", "current_streak_days", "coin_balance"):
        try:
            op.drop_column("users", col)
        except Exception:
            pass
