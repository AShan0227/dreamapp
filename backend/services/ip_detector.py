"""Dream IP Detection — identify recurring characters/locations → personal mythology."""

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import DreamEntity, DreamIP, IPType
from services.llm import chat_completion


async def detect_ips(user_id: str, db: AsyncSession, min_appearances: int = 3) -> list[dict]:
    """Scan user's entity history and promote recurring entities to Dream IPs."""
    # Group entities by canonical_name with counts
    result = await db.execute(
        select(
            DreamEntity.canonical_name,
            DreamEntity.entity_type,
            func.count(DreamEntity.id).label("count"),
            func.min(DreamEntity.created_at).label("first_seen"),
            func.max(DreamEntity.created_at).label("last_seen"),
        )
        .where(DreamEntity.user_id == user_id)
        .group_by(DreamEntity.canonical_name, DreamEntity.entity_type)
        .having(func.count(DreamEntity.id) >= min_appearances)
    )
    recurring = result.all()

    new_ips = []

    for canonical_name, entity_type, count, first_seen, last_seen in recurring:
        # Check if IP already exists
        existing = await db.execute(
            select(DreamIP).where(
                and_(
                    DreamIP.user_id == user_id,
                    DreamIP.name == canonical_name,
                )
            )
        )
        if existing.scalar_one_or_none():
            # Update count
            ip = existing.scalar_one_or_none()
            if ip:
                ip.appearance_count = count
                ip.last_seen = last_seen
                ip.updated_at = datetime.utcnow()
            continue

        # Get all instances for this entity
        instances = await db.execute(
            select(DreamEntity).where(
                and_(
                    DreamEntity.user_id == user_id,
                    DreamEntity.canonical_name == canonical_name,
                )
            )
        )
        all_instances = instances.scalars().all()

        # Generate mythology text via LLM
        descriptions = [e.description for e in all_instances if e.description]
        attributes = [e.attributes for e in all_instances if e.attributes]

        mythology = await _generate_mythology(
            canonical_name, entity_type, descriptions, attributes, count
        )

        # Map entity type to IP type
        ip_type_map = {
            "character": IPType.character,
            "location": IPType.location,
            "scene": IPType.location,
            "symbol": IPType.motif,
            "object": IPType.motif,
        }

        ip = DreamIP(
            user_id=user_id,
            name=canonical_name,
            ip_type=ip_type_map.get(entity_type, IPType.motif),
            description=mythology.get("description", ""),
            appearance_count=count,
            first_seen=first_seen,
            last_seen=last_seen,
            source_entities=[e.id for e in all_instances],
            visual_prompt=mythology.get("visual_prompt", ""),
            mythology_text=mythology.get("mythology_text", ""),
        )
        db.add(ip)
        new_ips.append({
            "name": canonical_name,
            "type": ip_type_map.get(entity_type, IPType.motif).value,
            "appearances": count,
            "mythology": mythology.get("mythology_text", ""),
        })

    await db.commit()
    return new_ips


async def _generate_mythology(
    name: str, entity_type: str, descriptions: list[str], attributes: list[dict], count: int
) -> dict:
    """Generate a poetic mythology text for a recurring dream entity."""
    desc_text = "\n".join(f"- {d}" for d in descriptions[:5])
    attr_text = json.dumps(attributes[:5], ensure_ascii=False)

    raw = await chat_completion(
        messages=[{"role": "user", "content": f"""This entity appears {count} times across different dreams:

Name: {name}
Type: {entity_type}
Descriptions from different dreams:
{desc_text}

Attributes:
{attr_text}

Generate:
1. A poetic "mythology text" — describe this entity as if it's a character in the dreamer's personal mythology (2-3 sentences, evocative and personal)
2. A consolidated visual description for image generation (1 sentence, specific and visual)
3. A one-sentence description

Output JSON: {{"mythology_text": "...", "visual_prompt": "...", "description": "..."}}"""}],
        system="You are a dream mythologist. Create personal mythology from recurring dream elements. Output ONLY JSON.",
        max_tokens=500,
    )

    try:
        if "```" in raw:
            raw = raw.split("```json")[1].split("```")[0] if "```json" in raw else raw.split("```")[1].split("```")[0]
        return json.loads(raw.strip())
    except (json.JSONDecodeError, IndexError):
        return {
            "mythology_text": f"In your dreams, {name} appears again and again — a recurring presence in your inner world.",
            "visual_prompt": f"A {entity_type} called {name}",
            "description": name,
        }
