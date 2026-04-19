import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, JSON
from models.dream import Base


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    nickname = Column(String, default="Dreamer")
    avatar_url = Column(String, nullable=True)
    token = Column(String, unique=True, default=lambda: uuid.uuid4().hex)
    is_public = Column(Boolean, default=True)

    # Phase 2
    dream_count = Column(Integer, default=0)
    last_dream_at = Column(DateTime, nullable=True)
    health_score = Column(Float, nullable=True)
    active_incubation_id = Column(String, nullable=True)
    preferences = Column(JSON, default=dict)

    # Quota tracking — resets daily, used to throttle expensive video gen
    video_quota_date = Column(DateTime, nullable=True)
    video_quota_used = Column(Integer, default=0)

    # Auth (optional — supplements bare token)
    email = Column(String, unique=True, nullable=True, index=True)
    phone = Column(String, unique=True, nullable=True, index=True)
    password_hash = Column(String, nullable=True)

    # Moderation / trust
    is_banned = Column(Boolean, default=False, index=True)
    is_staff = Column(Boolean, default=False)
    ban_reason = Column(String, nullable=True)
    banned_at = Column(DateTime, nullable=True)

    # Locale (zh-CN | en | ...). Used for crisis-hotline localization.
    locale = Column(String, default="zh-CN")

    # Push notification tokens (FCM / APNs / WeChat OpenID)
    push_token = Column(String, nullable=True)
    wechat_openid = Column(String, nullable=True, index=True)

    # Denormalized coin balance — kept in sync with coin_ledger by
    # services.engagement.{credit,debit}_coins. Source of truth is still the
    # ledger (append-only); this column is a cache for O(1) balance reads.
    # If ever out of sync, reconcile_coin_balance(user_id) recomputes.
    coin_balance = Column(Integer, nullable=True, default=0)

    # Streak / daily prompt (Wave M)
    current_streak_days = Column(Integer, default=0)
    longest_streak_days = Column(Integer, default=0)
    last_streak_date = Column(String, nullable=True)  # YYYY-MM-DD, user-local


# Schemas
class UserCreate(BaseModel):
    nickname: str = Field(default="Dreamer", max_length=30)


class UserResponse(BaseModel):
    id: str
    nickname: str
    avatar_url: str | None = None
    token: str
    created_at: datetime
    dream_count: int = 0
    health_score: float | None = None
    email: str | None = None
    phone: str | None = None
    has_password: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # Promote password_hash → has_password without leaking the hash
        if hasattr(obj, "password_hash"):
            data = {
                "id": obj.id,
                "nickname": obj.nickname,
                "avatar_url": getattr(obj, "avatar_url", None),
                "token": obj.token,
                "created_at": obj.created_at,
                "dream_count": getattr(obj, "dream_count", 0) or 0,
                "health_score": getattr(obj, "health_score", None),
                "email": getattr(obj, "email", None),
                "phone": getattr(obj, "phone", None),
                "has_password": bool(getattr(obj, "password_hash", None)),
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)
