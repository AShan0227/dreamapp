"""Phase 2 models: DreamEntity, DreamCorrelation, DreamHealthSnapshot, IncubationSession, DreamIP."""

import uuid
from datetime import datetime, date
from enum import Enum

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, DateTime, Date, JSON, Enum as SAEnum
from models.dream import Base

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class EntityType(str, Enum):
    character = "character"
    symbol = "symbol"
    location = "location"
    scene = "scene"
    object = "object"


class ProbationStatus(str, Enum):
    probation = "probation"
    graduated = "graduated"
    quarantined = "quarantined"


class DreamEntity(Base):
    __tablename__ = "dream_entities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dream_id = Column(String, nullable=False)
    user_id = Column(String, nullable=True)
    entity_type = Column(SAEnum(EntityType), nullable=False)
    canonical_name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(Text, default="")
    attributes = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Genesis Probation Track
    probation_status = Column(SAEnum(ProbationStatus), default=ProbationStatus.probation)
    probation_uses = Column(Integer, default=0)      # times this entity was referenced
    probation_successes = Column(Integer, default=0)  # user confirmed match
    probation_failures = Column(Integer, default=0)   # user said "not the same"
    confidence = Column(Float, default=0.5)           # 0.0 to 1.0

    # Vector embedding
    if HAS_PGVECTOR:
        embedding = Column(Vector(512), nullable=True)


class CorrelationType(str, Enum):
    # Original types
    recurring_scene = "recurring_scene"
    recurring_character = "recurring_character"
    thematic_link = "thematic_link"
    emotional_echo = "emotional_echo"
    narrative_evolution = "narrative_evolution"
    # Genesis-inspired types
    similar = "similar"          # Dreams share similar content/mood
    causal = "causal"            # One dream seems to cause/trigger another
    contradicts = "contradicts"  # Dreams present opposing narratives
    refines = "refines"          # Same dream evolving over time
    abstracts = "abstracts"      # Multiple dreams → one meta-pattern


class DreamCorrelation(Base):
    __tablename__ = "dream_correlations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    dream_id_a = Column(String, nullable=False)
    dream_id_b = Column(String, nullable=False)
    correlation_type = Column(SAEnum(CorrelationType), nullable=False)
    similarity_score = Column(Float, default=0.0)
    shared_entities = Column(JSON, default=list)
    analysis = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class PeriodType(str, Enum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class DreamHealthSnapshot(Base):
    __tablename__ = "dream_health_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(SAEnum(PeriodType), default=PeriodType.weekly)
    total_dreams = Column(Integer, default=0)
    nightmare_count = Column(Integer, default=0)
    nightmare_frequency = Column(Float, default=0.0)
    dominant_emotions = Column(JSON, default=list)
    emotion_trend = Column(JSON, default=list)
    recurring_symbols = Column(JSON, default=list)
    recurring_characters = Column(JSON, default=list)
    anomalies = Column(JSON, default=list)
    health_score = Column(Float, default=100.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class IncubationStatus(str, Enum):
    active = "active"
    completed = "completed"
    expired = "expired"


class IncubationSession(Base):
    __tablename__ = "incubation_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)
    intention = Column(Text, nullable=False)
    intention_tags = Column(JSON, default=list)
    recommendations = Column(JSON, default=dict)
    started_at = Column(DateTime, default=datetime.utcnow)
    dream_id = Column(String, nullable=True)
    outcome_match = Column(Float, nullable=True)
    outcome_analysis = Column(Text, nullable=True)
    status = Column(SAEnum(IncubationStatus), default=IncubationStatus.active)


class IPType(str, Enum):
    character = "character"
    location = "location"
    motif = "motif"


class DreamIP(Base):
    __tablename__ = "dream_ips"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    ip_type = Column(SAEnum(IPType), default=IPType.character)
    description = Column(Text, default="")
    appearance_count = Column(Integer, default=0)
    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    source_entities = Column(JSON, default=list)
    visual_prompt = Column(Text, default="")
    thumbnail_url = Column(String, nullable=True)
    mythology_text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Vector embedding
    if HAS_PGVECTOR:
        embedding = Column(Vector(512), nullable=True)
