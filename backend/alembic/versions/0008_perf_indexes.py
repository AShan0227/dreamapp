"""Wave L1 — performance indexes.

Revision ID: 0008_perf_indexes
Revises: 0007_wave_k
Create Date: 2026-04-18 10:00:00.000000

Adds:
  - HNSW indexes on both pgvector embedding columns (dreams.embedding,
    knowledge_embeddings.embedding). Without these, every retrieval is a
    sequential scan over every row. cosine_ops is the right opclass — both
    the model (BAAI/bge) and our queries use cosine similarity.
  - Composite + btree indexes on hot WHERE clauses identified in audit:
      dreams (user_id), (is_public, created_at DESC), (nightmare_flag),
      coin_ledger (user_id, created_at DESC),
      analytics_events (event, created_at DESC).
  - Drop the redundant single-column event_id index from
    payment_webhook_events (the composite (provider, event_id) covers it).

Notes on HNSW build:
  - HNSW is the right choice over ivfflat at our scale (small datasets
    today, room to grow): no required pre-build sample size, lower recall
    sensitivity to k, and faster query time.
  - `CONCURRENTLY` not used because alembic runs in a transaction; switch
    to op.execute_outside_txn pattern if these tables grow huge before
    deployment.
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_perf_indexes"
down_revision = "0007_wave_k"
branch_labels = None
depends_on = None


def _has_index(conn, table: str, name: str) -> bool:
    rows = sa.inspect(conn).get_indexes(table)
    return any(r["name"] == name for r in rows)


def _has_table(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ---- pgvector HNSW on dreams.embedding -------------------------------
    if _has_table(bind, "dreams") and not _has_index(bind, "dreams", "ix_dreams_embedding_hnsw"):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_dreams_embedding_hnsw "
            "ON dreams USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # ---- pgvector HNSW on knowledge_embeddings.embedding -----------------
    if _has_table(bind, "knowledge_embeddings") and not _has_index(
        bind, "knowledge_embeddings", "ix_knowledge_embeddings_hnsw"
    ):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_embeddings_hnsw "
            "ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # ---- pgvector HNSW on dream_entities.embedding (if column exists) ----
    if _has_table(bind, "dream_entities"):
        cols = {c["name"] for c in sa.inspect(bind).get_columns("dream_entities")}
        if "embedding" in cols and not _has_index(bind, "dream_entities", "ix_dream_entities_embedding_hnsw"):
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_dream_entities_embedding_hnsw "
                "ON dream_entities USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64)"
            )

    # ---- dreams composite + btree --------------------------------------
    if _has_table(bind, "dreams"):
        if not _has_index(bind, "dreams", "ix_dreams_user_id"):
            op.create_index("ix_dreams_user_id", "dreams", ["user_id"])
        # Plaza queries always filter is_public + order by created_at desc
        if not _has_index(bind, "dreams", "ix_dreams_public_created"):
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_dreams_public_created "
                "ON dreams (is_public, created_at DESC) "
                "WHERE is_public = true AND deleted_at IS NULL"
            )
        if not _has_index(bind, "dreams", "ix_dreams_nightmare"):
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_dreams_nightmare "
                "ON dreams (user_id, created_at DESC) "
                "WHERE nightmare_flag = true AND deleted_at IS NULL"
            )

    # ---- coin_ledger user feed ------------------------------------------
    if _has_table(bind, "coin_ledger") and not _has_index(
        bind, "coin_ledger", "ix_coin_ledger_user_time"
    ):
        op.create_index(
            "ix_coin_ledger_user_time", "coin_ledger", ["user_id", "created_at"],
            postgresql_using="btree",
        )

    # ---- analytics_events funnel queries --------------------------------
    if _has_table(bind, "analytics_events") and not _has_index(
        bind, "analytics_events", "ix_analytics_events_funnel"
    ):
        op.create_index(
            "ix_analytics_events_funnel",
            "analytics_events",
            ["event", "created_at"],
        )

    # ---- Drop redundant single-col index left by 0007 -------------------
    if _has_table(bind, "payment_webhook_events") and _has_index(
        bind, "payment_webhook_events", "ix_payment_webhook_events_event_id"
    ):
        # The composite ix_pwhk_provider_event covers single-column lookups.
        op.drop_index("ix_payment_webhook_events_event_id", table_name="payment_webhook_events")


def downgrade() -> None:
    bind = op.get_bind()
    for tbl, idx in [
        ("dreams", "ix_dreams_embedding_hnsw"),
        ("knowledge_embeddings", "ix_knowledge_embeddings_hnsw"),
        ("dream_entities", "ix_dream_entities_embedding_hnsw"),
        ("dreams", "ix_dreams_user_id"),
        ("dreams", "ix_dreams_public_created"),
        ("dreams", "ix_dreams_nightmare"),
        ("coin_ledger", "ix_coin_ledger_user_time"),
        ("analytics_events", "ix_analytics_events_funnel"),
    ]:
        try:
            op.drop_index(idx, table_name=tbl)
        except Exception:
            pass
    if _has_table(bind, "payment_webhook_events") and not _has_index(
        bind, "payment_webhook_events", "ix_payment_webhook_events_event_id"
    ):
        op.create_index(
            "ix_payment_webhook_events_event_id",
            "payment_webhook_events",
            ["event_id"],
        )
