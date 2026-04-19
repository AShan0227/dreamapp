"""Knowledge embedding model — Genesis-inspired L0/L1/L2 tiered storage."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, Float, Integer, String, Text, DateTime, JSON, Enum as SAEnum
from models.dream import Base

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class KnowledgeTier(str, Enum):
    """Genesis-inspired knowledge tiers."""
    L0 = "L0"  # Index: id, tags, score — for fast filtering (50 tokens)
    L1 = "L1"  # Knowledge: full interpretation, injected into context (200-500 tokens)
    L2 = "L2"  # Evidence: raw papers, corpus, audit trail (unlimited, not injected)


class KnowledgeStatus(str, Enum):
    """Genesis probation system for knowledge entries."""
    probation = "probation"    # New, unvalidated
    graduated = "graduated"    # Proven useful (3+ successful uses)
    quarantined = "quarantined"  # Low quality or contradicted


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Classification
    source = Column(String, nullable=False)     # "symbols", "archetypes", "narratives", etc.
    source_id = Column(String, nullable=False)   # id or name within the source
    tier = Column(SAEnum(KnowledgeTier), default=KnowledgeTier.L1)  # Genesis tier

    # Content
    name = Column(String, nullable=False)        # display name
    content_text = Column(Text, nullable=False)  # the text that was embedded
    metadata_json = Column(JSON, default=dict)   # original full entry

    # Genesis probation tracking
    status = Column(SAEnum(KnowledgeStatus), default=KnowledgeStatus.probation)
    use_count = Column(Integer, default=0)       # times retrieved and used
    success_count = Column(Integer, default=0)   # times user confirmed helpful
    failure_count = Column(Integer, default=0)   # times user said unhelpful
    confidence = Column(Float, default=0.5)      # 0.0 to 1.0
    impact_score = Column(Float, default=0.5)    # how impactful this knowledge is

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # Embedding model fingerprint — guards against silently mixing vectors
    # produced by different models. Validated at startup.
    embedding_model = Column(String, nullable=True)

    # Vector column
    if HAS_PGVECTOR:
        embedding = Column(Vector(512), nullable=True)
