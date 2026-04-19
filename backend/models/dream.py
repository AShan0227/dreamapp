import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, Float, String, Text, DateTime, Integer, JSON, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


# --- SQLAlchemy ORM ---

class Base(DeclarativeBase):
    pass


class DreamStatus(str, Enum):
    interviewing = "interviewing"
    scripted = "scripted"
    generating = "generating"
    completed = "completed"
    failed = "failed"


class DreamRecord(Base):
    __tablename__ = "dreams"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(SAEnum(DreamStatus), default=DreamStatus.interviewing)
    user_id = Column(String, nullable=True)  # Owner
    is_public = Column(Boolean, default=False)  # Visible on dream plaza

    # Interview
    chat_history = Column(JSON, default=list)  # [{role, content}]
    user_initial_input = Column(Text, default="")

    # Dream Script (generated after interview)
    dream_script = Column(JSON, nullable=True)  # structured dream narrative

    # Video
    video_prompt = Column(Text, nullable=True)  # JSON string of shot plan
    video_url = Column(String, nullable=True)  # Final video or first completed clip
    video_urls = Column(JSON, default=list)  # All clip URLs in order
    # Stable object name in MinIO (e.g. "dreams/{id}/dream_film.mp4").
    # Source of truth for serving; presigned URLs are derived on read.
    video_object_name = Column(String, nullable=True)
    video_style = Column(String, default="surreal")
    video_task_id = Column(String, nullable=True)  # Legacy single task
    video_task_ids = Column(JSON, default=list)  # Multi-shot task IDs
    video_shot_plan = Column(JSON, nullable=True)  # Full shot plan from director
    video_pending_prompts = Column(JSON, default=list)  # Prompts waiting to be submitted

    # Interpretation
    interpretation = Column(JSON, nullable=True)

    # Genesis Attribution — track which knowledge entries drove each stage
    # {"interviewer": [ids...], "director": [ids...], "interpreter": [ids...]}
    knowledge_citations = Column(JSON, default=dict)

    # User feedback (per aspect)
    # {"interpretation": "helpful"|"unhelpful", ...}
    feedback = Column(JSON, default=dict)

    # Metadata
    emotion_tags = Column(JSON, default=list)
    symbol_tags = Column(JSON, default=list)
    character_tags = Column(JSON, default=list)
    title = Column(String, nullable=True)
    failure_reason = Column(Text, nullable=True)  # Why generation failed
    deleted_at = Column(DateTime, nullable=True)  # Soft-delete (NULL = live)

    # Phase 2: Analysis
    nightmare_flag = Column(Boolean, default=False)
    emotion_valence = Column(Float, nullable=True)   # -1.0 to 1.0
    emotion_arousal = Column(Float, nullable=True)    # 0.0 to 1.0
    theme_tags = Column(JSON, default=list)
    location_tags = Column(JSON, default=list)
    entity_extraction_done = Column(Boolean, default=False)

    # Vector embedding for semantic search
    if HAS_PGVECTOR:
        embedding = Column(Vector(512), nullable=True)


# --- Pydantic Schemas ---

class DreamStartRequest(BaseModel):
    # Cap protects the LLM context budget + storage. 8000 chars ≈ 2-4 minute
    # narration which is plenty for a single dream. Larger payloads are
    # almost always paste-error or abuse.
    initial_input: str = Field(..., min_length=1, max_length=8000, description="User's initial dream description")
    style: str = Field(default="surreal", max_length=40, description="Visual style preference")


class DreamChatRequest(BaseModel):
    dream_id: str
    message: str = Field(..., min_length=1, max_length=4000)


class DreamChatResponse(BaseModel):
    dream_id: str
    ai_message: str
    is_complete: bool = False
    round_number: int


class DreamScriptScene(BaseModel):
    scene_number: int
    description: str
    visual_details: str
    emotion: str
    camera: str = ""
    time_feel: str = ""
    duration_hint: str = ""


class DreamScript(BaseModel):
    title: str
    overall_emotion: str
    scenes: list[DreamScriptScene]
    characters: list[str] = []
    symbols: list[str] = []
    color_palette: list[str] = []
    time_feel: str = ""
    visual_style: str = "surreal"


class DreamGenerateRequest(BaseModel):
    dream_id: str
    style: Optional[str] = None


class DreamInterpretation(BaseModel):
    summary: str
    symbols: list[dict]  # [{symbol, meaning, context}]
    emotion_analysis: str
    psychological_lens: str  # Jungian / evolutionary / narrative
    narrative_archetype: str
    life_insight: str
    tcm_perspective: Optional[str] = None  # Traditional Chinese Medicine


class DreamResponse(BaseModel):
    id: str
    created_at: datetime
    status: DreamStatus
    title: Optional[str] = None
    video_url: Optional[str] = None
    video_urls: list[str] = []
    video_style: str
    video_shot_plan: Optional[dict] = None
    interpretation: Optional[dict] = None
    emotion_tags: list[str] = []
    symbol_tags: list[str] = []
    character_tags: list[str] = []
    chat_history: list[dict] = []
    dream_script: Optional[dict] = None
    is_public: bool = False
    user_id: Optional[str] = None
    failure_reason: Optional[str] = None
    video_object_name: Optional[str] = None

    model_config = {"from_attributes": True}


class DreamUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=120)
    video_style: Optional[str] = Field(None, max_length=40)
