"""baseline schema — assumes existing prod DB has all tables already created
by ``Base.metadata.create_all`` (lifespan in main.py). This baseline is a
no-op so we can stamp existing DBs without errors. Subsequent migrations
will diff against this point.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op baseline.

    The existing schema was created via SQLAlchemy `create_all` during
    initial deploys (before Alembic existed). This revision marks that
    state. New schema changes go in subsequent migrations.
    """


def downgrade() -> None:
    """No-op baseline."""
