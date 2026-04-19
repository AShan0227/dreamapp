"""B2B API key management.

Keys are issued to authenticated users (typically clinics or researchers
who upgraded to Premium and asked for API access). The plaintext key is
returned ONCE at creation; only its sha256 hash is stored.

Auth flow for B2B requests:
  1. Caller sets header `X-API-Key: dreamapi_<long random>`
  2. services.api_keys.authenticate_request(headers, db) → APIKey row
  3. Routers that opt into B2B access depend on it instead of require_user

Quotas (default 10k requests/month) reset on the 1st of each month.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.engagement import APIKey


KEY_PREFIX = "dreamapi_"


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


async def issue_key(
    db: AsyncSession, owner_user_id: str, name: str,
    scopes: list[str], monthly_quota: int = 10000,
) -> tuple[APIKey, str]:
    """Mint a new key. Returns (row, plaintext) — caller MUST surface plaintext
    once and never again.
    """
    plaintext = _generate_key()
    row = APIKey(
        owner_user_id=owner_user_id,
        name=name[:120],
        key_hash=_hash_key(plaintext),
        key_prefix=plaintext[:14],  # "dreamapi_" + 5 chars
        scopes=scopes,
        monthly_request_quota=monthly_quota,
        period_start=datetime.utcnow(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, plaintext


async def list_keys(db: AsyncSession, owner_user_id: str) -> list[dict]:
    res = await db.execute(
        select(APIKey).where(APIKey.owner_user_id == owner_user_id)
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "key_prefix": r.key_prefix + "…",
            "scopes": r.scopes or [],
            "monthly_request_quota": r.monthly_request_quota,
            "requests_this_period": r.requests_this_period,
            "is_revoked": r.is_revoked,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in res.scalars().all()
    ]


async def revoke_key(db: AsyncSession, owner_user_id: str, key_id: str) -> bool:
    res = await db.execute(
        select(APIKey).where(and_(APIKey.id == key_id, APIKey.owner_user_id == owner_user_id))
    )
    row = res.scalar_one_or_none()
    if not row:
        return False
    row.is_revoked = True
    await db.commit()
    return True


async def authenticate(db: AsyncSession, plaintext_key: str) -> Optional[APIKey]:
    """Resolve a plaintext key → APIKey row, enforcing quota + revocation.

    Bumps requests_this_period; resets the period when month rolls over.
    Returns None if invalid / revoked / quota exceeded.
    """
    if not plaintext_key or not plaintext_key.startswith(KEY_PREFIX):
        return None
    h = _hash_key(plaintext_key)
    res = await db.execute(select(APIKey).where(APIKey.key_hash == h))
    row = res.scalar_one_or_none()
    if not row or row.is_revoked:
        return None

    # Reset monthly counter if a new month started since period_start
    now = datetime.utcnow()
    if not row.period_start or (now.year, now.month) != (row.period_start.year, row.period_start.month):
        row.period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        row.requests_this_period = 0

    if (row.requests_this_period or 0) >= row.monthly_request_quota:
        return None

    row.requests_this_period = (row.requests_this_period or 0) + 1
    row.last_used_at = now
    await db.commit()
    return row
