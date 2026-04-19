"""Add dreams.video_object_name (stable MinIO key for resigning).

Revision ID: 0003_video_object_name
Revises: 0002_auth_quota_failure
Create Date: 2026-04-16 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_video_object_name"
down_revision = "0002_auth_quota_failure"
branch_labels = None
depends_on = None


def _has_column(conn, table: str, col: str) -> bool:
    insp = sa.inspect(conn)
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "dreams", "video_object_name"):
        op.add_column("dreams", sa.Column("video_object_name", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "dreams", "video_object_name"):
        op.drop_column("dreams", "video_object_name")
