"""Dream Customization (PRODUCT_DOC §7.1).

Re-render an existing dream with new style / mood / camera / music / time
parameters. Optionally extend the dream with user-written continuation
text ("completion" kind).

The actual re-render goes through the existing director → video pipeline,
just with a modified script. We keep the original dream untouched; the
customization is its own row with its own video URL.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.dream import DreamRecord
from models.social import DreamCustomization
from services.director import VideoDirector
from services.kling import get_video_generator
from services.video_concat import concat_clips
from services.llm import chat_completion


def _modify_script(
    script: dict, parameters: dict, user_completion_text: str | None
) -> dict:
    """Apply customization parameters to a dream script.

    Pure function — does not call LLM unless completion text needs to be
    woven in (handled by extend_with_completion).
    """
    out = dict(script)
    if parameters.get("style"):
        out["visual_style"] = parameters["style"]
    if parameters.get("mood"):
        out["overall_emotion"] = parameters["mood"]
    if parameters.get("camera"):
        # Inject camera_default into each scene
        scenes = list(out.get("scenes", []))
        for s in scenes:
            s.setdefault("camera", parameters["camera"])
        out["scenes"] = scenes
    if parameters.get("time") and out.get("scenes"):
        # Apply time treatment hint to scenes
        for s in out["scenes"]:
            s["time_treatment"] = parameters["time"]
    if parameters.get("music"):
        out["soundscape"] = parameters["music"]
    return out


async def extend_with_completion(
    script: dict, user_completion_text: str
) -> dict:
    """Use the LLM to extend a dream script with user-written continuation.

    The LLM rewrites the SCRIPT (not the video) so it integrates the user's
    chosen ending while keeping the same visual style + characters.
    """
    if not user_completion_text.strip():
        return script

    prompt = f"""Continue this dream script. Keep the visual style, characters,
and tone consistent. Use the user's continuation as the basis for new scenes.

ORIGINAL SCRIPT:
{json.dumps(script, ensure_ascii=False)}

USER'S CONTINUATION (incorporate into 2-3 new scenes at the end):
{user_completion_text}

Output the FULL extended script as JSON, same schema. Output ONLY JSON."""

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system="You are a dream-script writer. Extend the user's dream while staying faithful to its symbolism and visual language.",
        max_tokens=4000,
    )
    from services.interpreter import _repair_json
    extended = _repair_json(raw)
    return extended if isinstance(extended, dict) else script


async def create_customization(
    db: AsyncSession,
    user_id: str,
    source_dream_id: str,
    kinds: list[str],
    parameters: dict,
    user_completion_text: str | None = None,
) -> DreamCustomization:
    """Create + persist the customization row in pending state.

    Caller should follow up by enqueueing the actual video generation
    (or trigger inline if the route returns 202).
    """
    cz = DreamCustomization(
        user_id=user_id,
        source_dream_id=source_dream_id,
        kinds=kinds,
        parameters=parameters,
        user_completion_text=user_completion_text,
        status="pending",
    )
    db.add(cz)
    await db.commit()
    await db.refresh(cz)
    return cz


async def render_customization(
    db: AsyncSession, customization_id: str
) -> DreamCustomization:
    """Run the actual generation: modify script, hit director + video gen."""
    cz = await db.get(DreamCustomization, customization_id)
    if not cz:
        raise ValueError("Customization not found")

    src = await db.get(DreamRecord, cz.source_dream_id)
    if not src or not src.dream_script:
        cz.status = "failed"
        cz.failure_reason = "Source dream missing or not scripted"
        await db.commit()
        return cz

    cz.status = "generating"
    await db.commit()

    try:
        modified = _modify_script(src.dream_script, cz.parameters or {}, cz.user_completion_text)
        if cz.user_completion_text:
            modified = await extend_with_completion(modified, cz.user_completion_text)

        director = VideoDirector()
        plan, _cited = await director.create_shot_plan(modified, db=db, dream_id=cz.id)
        prompts = director.extract_shot_prompts(plan)
        if not prompts:
            cz.status = "failed"
            cz.failure_reason = "Director produced no shots"
            await db.commit()
            return cz

        video = get_video_generator()
        result = await video.generate_multi(prompts, batch_size=5)
        # Wait for completion (poll once — assumes ~30s overall budget for
        # short customization; production would queue this)
        urls = [u for u in result.video_urls if u]
        if urls:
            film_url, obj_name = await concat_clips(urls, cz.id)
            cz.video_url = film_url
            cz.video_object_name = obj_name
            cz.video_urls = urls
            cz.status = "completed"
        else:
            cz.status = "generating"  # Caller will poll
        await db.commit()
        return cz
    except Exception as e:
        cz.status = "failed"
        cz.failure_reason = str(e)[:500]
        await db.commit()
        return cz
