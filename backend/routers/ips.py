"""Dream IP (personal mythology) endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import DreamIP
from models.user import UserRecord
from services.ip_detector import detect_ips
from services.auth import require_user

router = APIRouter(prefix="/api/ips", tags=["ips"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


@router.get("/")
async def list_ips(user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """List user's Dream IPs (personal mythology)."""
    result = await db.execute(
        select(DreamIP)
        .where(DreamIP.user_id == user.id)
        .order_by(DreamIP.appearance_count.desc())
    )
    ips = result.scalars().all()

    return [
        {
            "id": ip.id,
            "name": ip.name,
            "type": ip.ip_type.value,
            "appearances": ip.appearance_count,
            "mythology": ip.mythology_text,
            "visual_prompt": ip.visual_prompt,
            "thumbnail_url": ip.thumbnail_url,
            "first_seen": ip.first_seen.isoformat() if ip.first_seen else None,
            "last_seen": ip.last_seen.isoformat() if ip.last_seen else None,
        }
        for ip in ips
    ]


@router.get("/{ip_id}")
async def get_ip(ip_id: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Get detailed Dream IP with source dreams. Owner only."""
    ip = await db.get(DreamIP, ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    if ip.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your IP")

    return {
        "id": ip.id,
        "name": ip.name,
        "type": ip.ip_type.value,
        "description": ip.description,
        "appearances": ip.appearance_count,
        "mythology": ip.mythology_text,
        "visual_prompt": ip.visual_prompt,
        "thumbnail_url": ip.thumbnail_url,
        "source_entities": ip.source_entities,
        "first_seen": ip.first_seen.isoformat() if ip.first_seen else None,
        "last_seen": ip.last_seen.isoformat() if ip.last_seen else None,
    }


@router.post("/detect")
async def trigger_detection(user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Run IP detection scan for the authenticated user."""
    new_ips = await detect_ips(user.id, db)
    return {"new_ips": len(new_ips), "ips": new_ips}
