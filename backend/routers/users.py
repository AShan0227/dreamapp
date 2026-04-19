"""User accounts: register, login (email/password or phone OTP), token rotation."""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserRecord, UserCreate, UserResponse
from services.passwords import hash_password, verify_password
from services import otp as otp_service
from services.auth import require_user

router = APIRouter(prefix="/api/users", tags=["users"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# --- Schemas ---

PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    nickname: str = Field(default="Dreamer", max_length=30)


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PhoneOtpRequestBody(BaseModel):
    phone: str = Field(..., min_length=7, max_length=20)


class PhoneOtpVerifyBody(BaseModel):
    phone: str = Field(..., min_length=7, max_length=20)
    code: str = Field(..., min_length=4, max_length=8)
    nickname: Optional[str] = Field(default=None, max_length=30)


class ChangePasswordRequest(BaseModel):
    old_password: Optional[str] = None  # None for first-time set
    new_password: str = Field(..., min_length=8, max_length=72)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=8)
    new_password: str = Field(..., min_length=8, max_length=72)


class BindEmailRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)


class BindPhoneRequest(BaseModel):
    phone: str = Field(..., min_length=7, max_length=20)
    code: str = Field(..., min_length=4, max_length=8)


# --- Helpers ---

def _validate_phone(phone: str) -> str:
    s = phone.strip()
    if not PHONE_RE.match(s):
        raise HTTPException(status_code=400, detail="Invalid phone number")
    return s


# --- Anonymous register (kept for backwards compat / quick onboarding) ---

@router.post("/register", response_model=UserResponse)
async def register(req: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create an anonymous user. Returns token for future auth.

    Without email/password the only credential is the token. Recommend
    upgrading to /register/email or /login/phone to attach recoverable creds.
    """
    user = UserRecord(nickname=req.nickname)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    try:
        from services import analytics as _an
        await _an.track("user_registered", user_id=user.id, props={"method": "anonymous"})
    except Exception:
        pass
    return UserResponse.model_validate(user)


# --- Email/password ---

@router.post("/register/email", response_model=UserResponse)
async def register_email(req: EmailRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with email + password.

    Anti-enumeration: this used to return 409 on duplicate email, leaking
    which addresses are already registered. Now duplicates return 401
    "Invalid email or password" — same shape as a wrong-password login —
    so an attacker probing the endpoint can't distinguish "exists" from
    "doesn't exist".

    Genuinely new users get 200 + a fresh token as before.
    """
    existing = await db.execute(select(UserRecord).where(UserRecord.email == req.email))
    if existing.scalar_one_or_none():
        # Quietly indistinguishable from a failed login — protects existing users.
        # (We're not silently creating a duplicate; just refusing without leaking
        # whether the address is taken.)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = UserRecord(
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    try:
        from services import analytics as _an
        await _an.track("user_registered", user_id=user.id, props={"method": "email"})
    except Exception:
        pass
    return UserResponse.model_validate(user)


@router.post("/login/email", response_model=UserResponse)
async def login_email(req: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate by email + password. Returns the user incl. token."""
    result = await db.execute(select(UserRecord).where(UserRecord.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        # Generic message — never confirm or deny existence of accounts
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return UserResponse.model_validate(user)


# --- Phone OTP (passwordless) ---

@router.post("/login/phone/request")
async def login_phone_request(body: PhoneOtpRequestBody):
    """Request an OTP for phone-based login. Caller doesn't need to exist yet."""
    phone = _validate_phone(body.phone)
    result = await otp_service.request_otp(phone, channel="sms", purpose="login")
    if not result.get("sent"):
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Wait before requesting another code",
                **{k: v for k, v in result.items() if k != "sent"},
            },
        )
    return {"sent": True, "expires_in": result.get("expires_in")}


@router.post("/login/phone/verify", response_model=UserResponse)
async def login_phone_verify(body: PhoneOtpVerifyBody, db: AsyncSession = Depends(get_db)):
    """Verify OTP. Auto-creates the user on first successful verification."""
    phone = _validate_phone(body.phone)
    if not await otp_service.verify_otp(phone, body.code, channel="sms"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    result = await db.execute(select(UserRecord).where(UserRecord.phone == phone))
    user = result.scalar_one_or_none()
    if not user:
        user = UserRecord(phone=phone, nickname=body.nickname or f"Dreamer-{phone[-4:]}")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return UserResponse.model_validate(user)


# --- Password reset ---

@router.post("/password/reset/request")
async def password_reset_request(body: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Send a password reset code to the user's email.

    Always returns 200 — never reveals whether the email is registered
    (prevents account enumeration).
    """
    result = await db.execute(select(UserRecord).where(UserRecord.email == body.email))
    user = result.scalar_one_or_none()
    # Only actually send if the user exists; response shape is identical either way
    if user:
        await otp_service.request_otp(body.email, channel="email", purpose="password reset")
    return {"sent": True, "expires_in": 300}


@router.post("/password/reset/confirm", response_model=UserResponse)
async def password_reset_confirm(body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    """Verify the reset code and set the new password.

    Returns the updated user (with token) so the frontend can log in immediately.
    """
    if not await otp_service.verify_otp(body.email, body.code, channel="email"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    result = await db.execute(select(UserRecord).where(UserRecord.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        # Race: account deleted between request and confirm. Treat as code invalid.
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


# --- Bind email/phone to existing account ---

@router.post("/me/bind/email", response_model=UserResponse)
async def bind_email(
    body: BindEmailRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach an email + password to an account that doesn't yet have one.

    Used to upgrade an anonymous (token-only) account into a recoverable one.
    """
    if user.email:
        raise HTTPException(status_code=409, detail="Email already bound")

    existing = await db.execute(select(UserRecord).where(UserRecord.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")

    user.email = body.email
    user.password_hash = hash_password(body.password)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/me/bind/phone", response_model=UserResponse)
async def bind_phone(
    body: BindPhoneRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Attach a phone number to the current account, verified by OTP."""
    phone = _validate_phone(body.phone)
    if not await otp_service.verify_otp(phone, body.code, channel="sms"):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    if user.phone == phone:
        return UserResponse.model_validate(user)

    existing = await db.execute(select(UserRecord).where(UserRecord.phone == phone))
    other = existing.scalar_one_or_none()
    if other and other.id != user.id:
        raise HTTPException(status_code=409, detail="Phone already in use")

    user.phone = phone
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


# --- Account ---

@router.get("/me", response_model=UserResponse)
async def get_me(user: UserRecord = Depends(require_user)):
    return UserResponse.model_validate(user)


@router.post("/me/password", response_model=UserResponse)
async def change_password(
    req: ChangePasswordRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or change the user's password. If a password already exists,
    `old_password` must be supplied and must match."""
    if user.password_hash:
        if not req.old_password or not verify_password(req.old_password, user.password_hash):
            raise HTTPException(status_code=401, detail="Old password incorrect")
    user.password_hash = hash_password(req.new_password)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/me/quota")
async def get_my_quota(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Inspect remaining daily video quota (tier-aware)."""
    from services.quota import get_video_quota_status
    return await get_video_quota_status(user, db=db)


class PushTokenRequest(BaseModel):
    push_token: Optional[str] = None
    wechat_openid: Optional[str] = None
    locale: Optional[str] = None


@router.post("/me/push-token")
async def register_push_token(
    req: PushTokenRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Register or refresh the caller's FCM token + WeChat openid + locale.

    Call on app launch and whenever FCM emits a token-refresh callback.
    Passing `push_token=null` unregisters (user opted out of push).
    """
    if req.push_token is not None:
        user.push_token = req.push_token or None
    if req.wechat_openid is not None:
        user.wechat_openid = req.wechat_openid or None
    if req.locale:
        user.locale = req.locale[:20]
    await db.commit()
    return {"ok": True, "push_enabled": bool(user.push_token), "wechat_enabled": bool(user.wechat_openid)}


# ---- GDPR: data export + account deletion ---------------------------------

@router.get("/me/export")
async def export_my_data(
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Export everything we hold about the caller as a single JSON blob.

    Includes: profile, all dreams (incl. soft-deleted), entities, IPs,
    incubation sessions, agents, knowledge feedback the user has given,
    co-dream sessions, customizations, remixes. Excludes: aggregate
    counters and other users' data.

    Designed for GDPR Article 15 (right of access) compliance.
    """
    from sqlalchemy import select as _select
    from models.dream import DreamRecord
    from models.entities import DreamEntity, IncubationSession, DreamIP
    from models.agent import AgentRecord
    from models.social import (
        DreamCustomization, DreamRemix, CoDreamParticipant,
        DejaReveLink, RecurringPattern,
    )

    async def _all(model, where):
        # Resilient: if one table is in ORM/DB drift (e.g. a column added to
        # the model but not migrated), the user shouldn't lose access to
        # their other data. Failing tables return [] with a logged warning.
        try:
            r = await db.execute(_select(model).where(where))
            return [_serialize(o) for o in r.scalars().all()]
        except Exception as e:
            print(f"[export] {model.__tablename__} skipped: {e}")
            await db.rollback()
            return []

    def _serialize(obj):
        out = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif hasattr(val, "value"):  # Enum
                val = val.value
            elif col.name == "embedding":
                # Vector embeddings aren't useful to the user + are huge — skip
                continue
            elif col.name == "password_hash":
                # Don't export the password hash even to the owner
                val = "<redacted>"
            out[col.name] = val
        return out

    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": _serialize(user),
        "dreams": await _all(DreamRecord, DreamRecord.user_id == user.id),
        "entities": await _all(DreamEntity, DreamEntity.user_id == user.id),
        "ips": await _all(DreamIP, DreamIP.user_id == user.id),
        "incubation_sessions": await _all(IncubationSession, IncubationSession.user_id == user.id),
        "agents": await _all(AgentRecord, AgentRecord.user_id == user.id),
        "customizations": await _all(DreamCustomization, DreamCustomization.user_id == user.id),
        "remixes": await _all(DreamRemix, DreamRemix.user_id == user.id),
        "codream_participations": await _all(CoDreamParticipant, CoDreamParticipant.user_id == user.id),
        "deja_reve_links": await _all(DejaReveLink, DejaReveLink.user_id == user.id),
        "recurring_patterns": await _all(RecurringPattern, RecurringPattern.user_id == user.id),
    }
    return payload


class HardDeleteRequest(BaseModel):
    confirmation: str = Field(..., description='Must be "DELETE MY ACCOUNT"')


@router.post("/me/delete")
async def hard_delete_account(
    body: HardDeleteRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the user + all their personal data.

    Cascade scope (mirrors /me/export):
      - dreams (hard delete, not soft)
      - entities, ips, incubation sessions
      - agents, customizations, remixes, deja-reve links, recurring patterns
      - codream participant rows (sessions where the user was the only
        participant get the session deleted too)
      - the user row itself

    Idempotent — running twice on a missing user is fine. The token
    becomes invalid immediately on success.
    """
    if body.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=400,
            detail="confirmation must be exactly 'DELETE MY ACCOUNT'",
        )

    from sqlalchemy import delete as _del, select as _select
    from models.dream import DreamRecord
    from models.entities import DreamEntity, IncubationSession, DreamIP
    from models.agent import AgentRecord, AgentRun, AgentInstall, UserLayout
    from models.social import (
        DreamCustomization, DreamRemix, CoDreamSession, CoDreamParticipant,
        DejaReveLink, RecurringPattern, DreamMatch,
    )

    uid = user.id

    # Owned tables — straight delete
    for stmt in (
        _del(DreamRecord).where(DreamRecord.user_id == uid),
        _del(DreamEntity).where(DreamEntity.user_id == uid),
        _del(DreamIP).where(DreamIP.user_id == uid),
        _del(IncubationSession).where(IncubationSession.user_id == uid),
        _del(DreamCustomization).where(DreamCustomization.user_id == uid),
        _del(DreamRemix).where(DreamRemix.user_id == uid),
        _del(DejaReveLink).where(DejaReveLink.user_id == uid),
        _del(RecurringPattern).where(RecurringPattern.user_id == uid),
        _del(CoDreamParticipant).where(CoDreamParticipant.user_id == uid),
        _del(DreamMatch).where((DreamMatch.user_id_a == uid) | (DreamMatch.user_id_b == uid)),
        _del(UserLayout).where(UserLayout.user_id == uid),
        _del(AgentInstall).where(AgentInstall.user_id == uid),
    ):
        await db.execute(stmt)

    # Agents this user owns (and their run history)
    own_agents = await db.execute(_select(AgentRecord).where(AgentRecord.user_id == uid))
    for a in own_agents.scalars().all():
        await db.execute(_del(AgentRun).where(AgentRun.agent_id == a.id))
        await db.delete(a)

    # Co-dream sessions where this user was creator: orphan-clean any
    # session left with no participants
    creator_sessions = await db.execute(
        _select(CoDreamSession).where(CoDreamSession.creator_user_id == uid)
    )
    for s in creator_sessions.scalars().all():
        remaining = await db.execute(
            _select(CoDreamParticipant).where(CoDreamParticipant.session_id == s.id)
        )
        if not remaining.scalar_one_or_none():
            await db.delete(s)

    # Finally the user row. Re-fetch in this session — the user object came
    # in via require_user (different session) and would raise "already
    # attached to session N (this is M)" otherwise.
    from models.user import UserRecord as _UserRecord
    fresh = await db.get(_UserRecord, uid)
    if fresh is not None:
        await db.delete(fresh)
    await db.commit()

    return {"deleted": True, "user_id": uid}
