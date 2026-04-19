"""Social, remix, customization, co-dreaming, recurring patterns, deja-reve.

Revision ID: 0004_social_models
Revises: 0003_video_object_name
Create Date: 2026-04-16 23:30:00.000000

Adds 6 new tables for the Wave F features. Each is independent (no FK
constraints across them) so they can be added/dropped cleanly.
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_social_models"
down_revision = "0003_video_object_name"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "recurring_patterns"):
        op.create_table(
            "recurring_patterns",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("kind", sa.String(), nullable=False, index=True),
            sa.Column("canonical_name", sa.String(), nullable=False),
            sa.Column("occurrence_count", sa.Integer(), server_default="2"),
            sa.Column("dream_ids", sa.JSON()),
            sa.Column("first_seen_at", sa.DateTime()),
            sa.Column("last_seen_at", sa.DateTime()),
            sa.Column("metadata_json", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "deja_reve_links"):
        op.create_table(
            "deja_reve_links",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("dream_id", sa.String(), nullable=False, index=True),
            sa.Column("waking_event", sa.Text(), nullable=False),
            sa.Column("waking_event_at", sa.DateTime()),
            sa.Column("similarity", sa.Float()),
            sa.Column("source", sa.String(), server_default="user"),
            sa.Column("confirmed", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_customizations"):
        op.create_table(
            "dream_customizations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("source_dream_id", sa.String(), nullable=False, index=True),
            sa.Column("kinds", sa.JSON()),
            sa.Column("parameters", sa.JSON()),
            sa.Column("user_completion_text", sa.Text()),
            sa.Column("video_url", sa.String()),
            sa.Column("video_object_name", sa.String()),
            sa.Column("video_urls", sa.JSON()),
            sa.Column("status", sa.String(), server_default="pending"),
            sa.Column("failure_reason", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_remixes"):
        op.create_table(
            "dream_remixes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("kind", sa.String(), nullable=False, index=True),
            sa.Column("source_dream_ids", sa.JSON()),
            sa.Column("user_prompt", sa.Text()),
            sa.Column("challenge_keyword", sa.String(), index=True),
            sa.Column("remixed_script", sa.JSON()),
            sa.Column("remixed_interpretation", sa.JSON()),
            sa.Column("video_url", sa.String()),
            sa.Column("video_object_name", sa.String()),
            sa.Column("title", sa.String()),
            sa.Column("status", sa.String(), server_default="pending"),
            sa.Column("failure_reason", sa.Text()),
            sa.Column("is_public", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )

    if not _has_table(bind, "codream_sessions"):
        op.create_table(
            "codream_sessions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("creator_user_id", sa.String(), nullable=False, index=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("theme", sa.Text(), nullable=False),
            sa.Column("max_participants", sa.Integer(), server_default="4"),
            sa.Column("invite_code", sa.String(), unique=True, nullable=False, index=True),
            sa.Column("status", sa.String(), server_default="open"),
            sa.Column("starts_at", sa.DateTime()),
            sa.Column("ends_at", sa.DateTime()),
            sa.Column("combined_script", sa.JSON()),
            sa.Column("combined_video_url", sa.String()),
            sa.Column("combined_video_object_name", sa.String()),
            sa.Column("created_at", sa.DateTime()),
        )

    if not _has_table(bind, "codream_participants"):
        op.create_table(
            "codream_participants",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("session_id", sa.String(), nullable=False, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("dream_id", sa.String(), index=True),
            sa.Column("joined_at", sa.DateTime()),
            sa.Column("submitted_at", sa.DateTime()),
        )

    if not _has_table(bind, "dream_matches"):
        op.create_table(
            "dream_matches",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("dream_id_a", sa.String(), nullable=False, index=True),
            sa.Column("dream_id_b", sa.String(), nullable=False, index=True),
            sa.Column("user_id_a", sa.String(), nullable=False),
            sa.Column("user_id_b", sa.String(), nullable=False),
            sa.Column("similarity", sa.Float(), nullable=False),
            sa.Column("shared_themes", sa.JSON()),
            sa.Column("computed_at", sa.DateTime()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for t in (
        "dream_matches",
        "codream_participants",
        "codream_sessions",
        "dream_remixes",
        "dream_customizations",
        "deja_reve_links",
        "recurring_patterns",
    ):
        if _has_table(bind, t):
            op.drop_table(t)
