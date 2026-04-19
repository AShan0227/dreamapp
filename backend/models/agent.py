"""Agent system models."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, DateTime, JSON, Enum as SAEnum
from models.dream import Base


class AgentStatus(str, Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"


class AgentRecord(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    trigger = Column(JSON, default=dict)  # {type: schedule|event|manual, config}
    steps = Column(JSON, default=list)    # [{action, params, conditions}]
    is_public = Column(Boolean, default=False)
    is_published = Column(Boolean, default=False)
    price = Column(Float, nullable=True)
    install_count = Column(Integer, default=0)
    rating = Column(Float, nullable=True)
    status = Column(SAEnum(AgentStatus), default=AgentStatus.draft)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    trigger_event = Column(JSON, default=dict)
    steps_log = Column(JSON, default=list)
    status = Column(SAEnum(RunStatus), default=RunStatus.running)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)


class AgentInstall(Base):
    __tablename__ = "agent_installs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)
    config_overrides = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)


class UserLayout(Base):
    __tablename__ = "user_layouts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, unique=True)
    layout_config = Column(JSON, default=dict)
    theme = Column(JSON, default=dict)
    prompt_history = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# Schemas
class AgentCreate(BaseModel):
    name: str
    description: str = ""
    trigger: dict = Field(default_factory=lambda: {"type": "manual"})
    steps: list[dict] = Field(default_factory=list)


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    trigger: dict
    steps: list[dict]
    status: str
    install_count: int = 0
    rating: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
