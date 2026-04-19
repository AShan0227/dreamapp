"""Authentication dependencies and ownership helpers.

Centralized so every router can do `Depends(require_user)` instead of
each one re-implementing token extraction. Two flavors:

- get_optional_user: returns Optional[UserRecord] — for endpoints that
  work both authed and anon (e.g. plaza browse).
- require_user: raises 401 if no valid token — for everything that
  mutates user data.

assert_dream_owner enforces row-level ownership.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import UserRecord


async def _get_db():
    """Local copy of the DB dependency to avoid circular import on main."""
    from main import async_session
    async with async_session() as session:
        yield session


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(_get_db),
) -> Optional[UserRecord]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        return None
    result = await db.execute(select(UserRecord).where(UserRecord.token == token))
    return result.scalar_one_or_none()


async def require_user(
    user: Optional[UserRecord] = Depends(get_optional_user),
) -> UserRecord:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Best-effort Sentry user context — any subsequent exception in this
    # request will carry user_id. Never raise from here.
    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            scope.set_user({"id": user.id})
            if getattr(user, "is_staff", False):
                scope.set_tag("user_is_staff", "1")
    except Exception:
        pass
    return user


def assert_dream_owner(dream, user: UserRecord) -> None:
    """Raise 403 if dream is owned by someone else.

    Legacy dreams (user_id is NULL) are read-only for everyone — they
    pass this check since `dream.user_id` is falsy. Mutations on legacy
    dreams should additionally check `dream.user_id is not None`.
    """
    if dream.user_id and dream.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your dream")


def assert_dream_mutable_by(dream, user: UserRecord) -> None:
    """Stricter: caller must be the owner. Rejects legacy NULL-owner dreams."""
    if dream.user_id is None:
        raise HTTPException(
            status_code=403,
            detail="Legacy dream — read only. Re-record to claim ownership.",
        )
    if dream.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your dream")
