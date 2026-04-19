"""Auth, quota, soft-delete, failure_reason, embedding model fingerprint.

Revision ID: 0002_auth_quota_failure
Revises: 0001_baseline
Create Date: 2026-04-16 18:00:00.000000

Adds:
- users.email / phone / password_hash / video_quota_date / video_quota_used
- dreams.failure_reason / deleted_at
- knowledge_embeddings.embedding_model
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_auth_quota_failure"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _has_column(conn, table: str, col: str) -> bool:
    insp = sa.inspect(conn)
    return col in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # users
    if not _has_column(bind, "users", "email"):
        op.add_column("users", sa.Column("email", sa.String(), nullable=True))
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if not _has_column(bind, "users", "phone"):
        op.add_column("users", sa.Column("phone", sa.String(), nullable=True))
        op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    if not _has_column(bind, "users", "password_hash"):
        op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    if not _has_column(bind, "users", "video_quota_date"):
        op.add_column("users", sa.Column("video_quota_date", sa.DateTime(), nullable=True))
    if not _has_column(bind, "users", "video_quota_used"):
        op.add_column(
            "users",
            sa.Column("video_quota_used", sa.Integer(), nullable=True, server_default="0"),
        )

    # dreams
    if not _has_column(bind, "dreams", "failure_reason"):
        op.add_column("dreams", sa.Column("failure_reason", sa.Text(), nullable=True))
    if not _has_column(bind, "dreams", "deleted_at"):
        op.add_column("dreams", sa.Column("deleted_at", sa.DateTime(), nullable=True))
        op.create_index("ix_dreams_deleted_at", "dreams", ["deleted_at"])

    # knowledge_embeddings
    if not _has_column(bind, "knowledge_embeddings", "embedding_model"):
        op.add_column(
            "knowledge_embeddings",
            sa.Column("embedding_model", sa.String(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, "knowledge_embeddings", "embedding_model"):
        op.drop_column("knowledge_embeddings", "embedding_model")

    if _has_column(bind, "dreams", "deleted_at"):
        try:
            op.drop_index("ix_dreams_deleted_at", table_name="dreams")
        except Exception:
            pass
        op.drop_column("dreams", "deleted_at")
    if _has_column(bind, "dreams", "failure_reason"):
        op.drop_column("dreams", "failure_reason")

    for col in ("video_quota_used", "video_quota_date", "password_hash"):
        if _has_column(bind, "users", col):
            op.drop_column("users", col)
    for col, idx in (("phone", "ix_users_phone"), ("email", "ix_users_email")):
        if _has_column(bind, "users", col):
            try:
                op.drop_index(idx, table_name="users")
            except Exception:
                pass
            op.drop_column("users", col)
