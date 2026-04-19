"""
╔══════════════════════════════════════════════════════════════════╗
║ routers/dreams.py — consolidated dream lifecycle + video + interp ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  SECTIONS (grep for the banner to jump):                         ║
║                                                                  ║
║  [LIFECYCLE] /start · /chat · /voice-to-text · list/get/         ║
║              delete/update                                       ║
║  [VIDEO]     /{id}/generate · /{id}/video-status                 ║
║  [INTERPRET] /{id}/interpret · /{id}/citations · /{id}/feedback  ║
║              · /{id}/rewrite                                     ║
║                                                                  ║
║  Shared helpers (crisis gate, background entity extractor,       ║
║  `_with_fresh_video_url`, `_suggest_next_action`) live between   ║
║  sections.                                                       ║
║                                                                  ║
║  If/when this file crosses 1500 lines, split per FastAPI         ║
║  sub-router pattern:                                             ║
║     dreams_lifecycle.py + dreams_video.py + dreams_interpret.py  ║
║     → this file becomes: `include_router(lifecycle_router)` etc. ║
║  Kept flat today so every existing test + frontend route stays   ║
║  working without import-path churn.                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.dream import (
    DreamChatRequest,
    DreamChatResponse,
    DreamGenerateRequest,
    DreamRecord,
    DreamResponse,
    DreamStartRequest,
    DreamStatus,
    DreamUpdateRequest,
)
from models.user import UserRecord
from fastapi import BackgroundTasks
from services.director import VideoDirector
from services.interviewer import DreamInterviewer
from services.interpreter import DreamInterpreter
from services.kling import get_video_generator
from services.video_gen import VideoPrompt
from services.video_concat import concat_clips
from services.entity_extractor import extract_entities, canonicalize_against_existing, extract_emotion_scores, is_nightmare
from services.auth import require_user, get_optional_user, assert_dream_owner, assert_dream_mutable_by
from services.quota import check_and_consume_video_quota
from services.video_url import serve_video_url


def _with_fresh_video_url(dream: DreamRecord, *, public: bool = False) -> DreamResponse:
    """Build a DreamResponse with a freshly-signed video URL.

    Avoids the 24h presigned URL expiry by signing on read. Mutation is
    in-memory only — does NOT persist to the DB.
    """
    fresh = serve_video_url(dream, public=public)
    payload = DreamResponse.model_validate(dream)
    payload.video_url = fresh or payload.video_url
    return payload

router = APIRouter(prefix="/api/dreams", tags=["dreams"])

# Service instances
interviewer = DreamInterviewer()
director = VideoDirector()
interpreter = DreamInterpreter()
video_gen = get_video_generator()


# --- Dependency: DB session ---
# Injected via app state, see main.py


async def get_db():
    from main import async_session

    async with async_session() as session:
        yield session


# Use FastAPI Depends in actual routes
from fastapi import Depends


@router.post("/start", response_model=DreamChatResponse)
async def start_dream(
    req: DreamStartRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new dream interview. Authenticated.

    Crisis check runs on the user's initial input before we call the LLM —
    if triggered, we skip interview, create a stub dream marked as
    crisis_paused, log the flag, and return the hotline payload so the
    frontend can render a care-first interstitial.
    """
    from services import crisis
    locale = getattr(user, "locale", None) or "zh-CN"
    detection = crisis.detect(req.initial_input, locale=locale)

    if detection.suppress_ai:
        dream = DreamRecord(
            user_id=user.id,
            user_initial_input=req.initial_input,
            chat_history=[],
            video_style=req.style,
            status=DreamStatus.interviewing,  # user can resume if they choose
            knowledge_citations={},
        )
        db.add(dream)
        await db.commit()
        await db.refresh(dream)
        await crisis.log_crisis_flag(db, user.id, dream.id, detection, surface="interview")
        payload = crisis.crisis_response_payload(detection)
        payload["dream_id"] = dream.id
        return JSONResponse(status_code=200, content=payload)

    ai_message, chat_history, cited = await interviewer.start_interview(req.initial_input, db=db)

    dream = DreamRecord(
        user_id=user.id,
        user_initial_input=req.initial_input,
        chat_history=chat_history,
        video_style=req.style,
        status=DreamStatus.interviewing,
        knowledge_citations={"interviewer": cited} if cited else {},
    )
    db.add(dream)
    await db.commit()
    await db.refresh(dream)

    # Watch-level (sub-crisis) signals are logged silently for pattern tracking.
    if detection.severity == "watch":
        await crisis.log_crisis_flag(db, user.id, dream.id, detection, surface="interview")

    try:
        from services import analytics as _an
        await _an.track("dream_started", user_id=user.id, props={"dream_id": dream.id, "method": "interview"})
    except Exception:
        pass

    # Wave M — advance daily streak. No-op if user already recorded today.
    try:
        from services.streak import bump_streak
        bumped = await bump_streak(db, user)
        if bumped.get("milestone"):
            # Surface milestone in-app notification (fire-and-forget)
            from services.threads import notify
            await notify(
                db, user_id=user.id, kind="streak_milestone",
                payload={
                    "days": bumped["current"],
                    "coins_awarded": bumped.get("coins_awarded", 0),
                },
            )
    except Exception:
        pass  # never fail dream start on streak error

    return DreamChatResponse(
        dream_id=dream.id,
        ai_message=ai_message,
        is_complete=False,
        round_number=1,
    )


from services.observability import track_bg_task


@track_bg_task("entity_extraction")
async def _bg_extract_entities(dream_id: str, dream_script: dict, chat_history: list[dict]):
    """Background task: extract entities after dream script is generated."""
    try:
        from models.entities import DreamEntity
        from main import async_session

        entities = await extract_entities(dream_script, chat_history)

        async with async_session() as db:
            dream = await db.get(DreamRecord, dream_id)
            if not dream:
                return

            # Load existing entities for this user for canonicalization
            existing = []
            existing_entities: list = []   # ORM objects — kept for probation lookup below
            if dream.user_id:
                from sqlalchemy import select
                result = await db.execute(
                    select(DreamEntity).where(DreamEntity.user_id == dream.user_id)
                )
                # SQLAlchemy Result iterators can only be consumed ONCE.
                # Materialize to a list so the probation loop below can scan
                # it for every new entity. Previously a second .scalars().all()
                # silently returned empty → probation tracking was broken.
                existing_entities = list(result.scalars().all())
                existing = [
                    {"canonical_name": e.canonical_name, "entity_type": e.entity_type.value, "description": e.description}
                    for e in existing_entities
                ]

            from models.entities import ProbationStatus

            for ent in entities:
                canonical = canonicalize_against_existing(ent, existing)

                # Genesis Probation: check if this canonical already exists
                existing_entity = None
                for ex in existing_entities:
                    if ex.canonical_name == canonical:
                        existing_entity = ex
                        break

                if existing_entity:
                    # Existing entity: increment use count
                    existing_entity.probation_uses += 1
                    existing_entity.probation_successes += 1
                    if (existing_entity.probation_status == ProbationStatus.probation
                            and existing_entity.probation_successes >= 3):
                        existing_entity.probation_status = ProbationStatus.graduated
                        existing_entity.confidence = min(1.0, existing_entity.confidence + 0.2)

                # Always create new entity record (tracks per-dream appearances)
                entity = DreamEntity(
                    dream_id=dream_id,
                    user_id=dream.user_id,
                    entity_type=ent.get("entity_type", "symbol"),
                    canonical_name=canonical,
                    display_name=ent.get("display_name", canonical),
                    description=ent.get("description", ""),
                    attributes=ent.get("attributes", {}),
                    probation_status=ProbationStatus.probation,
                    confidence=0.5,
                )
                db.add(entity)
                existing.append({"canonical_name": canonical, "entity_type": ent.get("entity_type", ""), "description": ent.get("description", "")})

            # Generate embeddings for entities and dream
            try:
                from services.embeddings import embed_entity, embed_dream
                for entity in [e for e in db.new if hasattr(e, 'canonical_name')]:
                    emb = embed_entity(entity.canonical_name, entity.display_name, entity.description)
                    if emb and hasattr(entity, 'embedding'):
                        entity.embedding = emb

                # Embed the dream itself
                if dream.dream_script:
                    dream_emb = embed_dream(dream.dream_script)
                    if dream_emb and hasattr(dream, 'embedding'):
                        dream.embedding = dream_emb
            except Exception as e:
                print(f"Embedding generation skipped: {e}")

            dream.entity_extraction_done = True
            await db.commit()

            # Genesis: check if sleep cycle should trigger
            if dream.user_id:
                from services.sleep_cycle import should_sleep, run_sleep_cycle
                if await should_sleep(dream.user_id, db):
                    await run_sleep_cycle(dream.user_id, db)
                    print(f"Sleep cycle triggered for user {dream.user_id}")

    except Exception as e:
        print(f"Entity extraction failed for {dream_id}: {e}")


@router.post("/chat", response_model=DreamChatResponse)
async def chat_dream(
    req: DreamChatRequest,
    bg: BackgroundTasks = None,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Continue the dream interview."""
    dream = await db.get(DreamRecord, req.dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if dream.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Dream deleted")
    if dream.status != DreamStatus.interviewing:
        raise HTTPException(status_code=400, detail="Interview already completed")

    # Crisis scan on the new user message + full user-side history
    from services import crisis
    locale = getattr(user, "locale", None) or "zh-CN"
    user_text = req.message + "\n" + "\n".join(
        m.get("content", "") for m in (dream.chat_history or []) if m.get("role") == "user"
    )
    detection = crisis.detect(user_text, locale=locale)
    if detection.suppress_ai:
        await crisis.log_crisis_flag(db, user.id, dream.id, detection, surface="interview")
        # Record user's message into history so it's not lost, but do not generate AI response.
        history = list(dream.chat_history or [])
        history.append({"role": "user", "content": req.message})
        dream.chat_history = history
        flag_modified(dream, "chat_history")
        dream.updated_at = datetime.utcnow()
        await db.commit()
        payload = crisis.crisis_response_payload(detection)
        payload["dream_id"] = dream.id
        return JSONResponse(status_code=200, content=payload)

    ai_message, chat_history, is_complete, cited = await interviewer.continue_interview(
        req.message, dream.chat_history, db=db, dream_id=req.dream_id
    )

    dream.chat_history = list(chat_history)  # new list to trigger change detection
    flag_modified(dream, "chat_history")
    if cited:
        cites = dict(dream.knowledge_citations or {})
        # Accumulate interviewer citations across rounds, dedupe
        merged = list(dict.fromkeys((cites.get("interviewer") or []) + cited))
        cites["interviewer"] = merged
        dream.knowledge_citations = cites
        flag_modified(dream, "knowledge_citations")
    if is_complete:
        # Generate dream script
        script = await interviewer.generate_script(chat_history)
        dream.dream_script = script
        dream.status = DreamStatus.scripted
        try:
            from services import analytics as _an
            await _an.track("dream_script_ready", user_id=user.id, props={
                "dream_id": dream.id,
                "interview_rounds": len([m for m in chat_history if m.get("role") == "user"]),
            })
        except Exception:
            pass
        dream.title = script.get("title", "Untitled Dream")
        dream.emotion_tags = [script.get("overall_emotion", "")]
        dream.symbol_tags = script.get("symbols", [])
        dream.character_tags = script.get("characters", [])

        # Background: extract entities for cross-temporal analysis
        asyncio.ensure_future(
            _bg_extract_entities(dream.id, script, list(chat_history))
        )

    dream.updated_at = datetime.utcnow()
    await db.commit()

    round_number = len([m for m in chat_history if m["role"] == "user"])

    return DreamChatResponse(
        dream_id=dream.id,
        ai_message=ai_message,
        is_complete=is_complete,
        round_number=round_number,
    )


@router.post("/{dream_id}/generate")
async def generate_video(
    dream_id: str,
    skip_queue: bool = False,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate multi-shot dream video. Submits first batch of 3, rest queued.

    Authenticated + ownership-checked + daily quota enforced.

    `skip_queue=true` debits 1 dream coin (Pro/Premium tier auto-skips
    without spending).
    """
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if dream.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Dream deleted")
    if not dream.dream_script:
        raise HTTPException(status_code=400, detail="Dream script not ready")

    # Crisis gate on video generation — don't spend the user's quota or our
    # LLM budget visualizing a dream that flags acute distress. This is ALSO
    # a liability mitigation: we do not render potentially self-harm imagery.
    from services import crisis as _crisis
    locale = getattr(user, "locale", None) or "zh-CN"
    user_corpus = [dream.user_initial_input or ""] + [
        m.get("content", "") for m in (dream.chat_history or []) if m.get("role") == "user"
    ] + [str((dream.dream_script or {}).get("narrative", ""))]
    detection = _crisis.detect("\n".join(user_corpus), locale=locale)
    if detection.suppress_ai:
        await _crisis.log_crisis_flag(db, user.id, dream.id, detection, surface="video_generation")
        payload = _crisis.crisis_response_payload(detection)
        payload["dream_id"] = dream.id
        raise HTTPException(status_code=451, detail=payload)

    # Quota check — burns 1 from daily allowance. Raises 429 on cap.
    remaining = await check_and_consume_video_quota(db, user)

    # Skip-queue: Pro+ tier auto-skips, free tier can pay 1 coin
    priority = False
    if skip_queue:
        from services.subscriptions import get_entitlements
        ent = await get_entitlements(db, user.id)
        if ent.get("priority_queue"):
            priority = True
        else:
            from services.engagement import debit_coins
            try:
                await debit_coins(db, user.id, 1, "spend_skip_queue", ref=dream_id)
                priority = True
            except ValueError as ve:
                # Out of coins — proceed normally, surface a hint
                print(f"skip_queue requested but {ve}; proceeding without priority")

    # Metric: count successful submissions (post-quota, pre-LLM)
    try:
        from services.observability import inc
        inc("dreamapp_video_generations_total", {"priority": str(priority).lower()})
    except Exception:
        pass
    try:
        from services import analytics as _an
        await _an.track("dream_video_generated", user_id=user.id, props={
            "dream_id": dream.id,
            "priority": bool(priority),
            "quota_remaining": remaining,
        })
    except Exception:
        pass

    dream.status = DreamStatus.generating
    dream.failure_reason = None
    await db.commit()

    try:
        # AI Director: script → multi-shot storyboard
        shot_plan, director_cites = await director.create_shot_plan(
            dream.dream_script, db=db, dream_id=dream.id
        )
        dream.video_shot_plan = shot_plan
        dream.video_prompt = json.dumps(shot_plan, ensure_ascii=False)
        if director_cites:
            cites = dict(dream.knowledge_citations or {})
            cites["director"] = director_cites
            dream.knowledge_citations = cites
            flag_modified(dream, "knowledge_citations")

        # Extract individual shot prompts
        shot_prompts = director.extract_shot_prompts(shot_plan)
        total = len(shot_prompts)

        if not shot_prompts:
            dream.status = DreamStatus.failed
            dream.failure_reason = "AI Director produced no shots"
            await db.commit()
            raise HTTPException(status_code=500, detail="AI Director produced no shots")

        # Submit first batch (3 concurrent max)
        result = await video_gen.generate_multi(shot_prompts, batch_size=5)

        # Store active task_ids and remaining prompts
        active_ids = [t for t in result.task_ids if t != "pending"]
        pending = shot_prompts[len(active_ids):]

        dream.video_task_ids = active_ids
        dream.video_pending_prompts = pending
        dream.video_urls = []
        dream.updated_at = datetime.utcnow()
        flag_modified(dream, "video_prompt")
        flag_modified(dream, "video_task_ids")
        flag_modified(dream, "video_shot_plan")
        flag_modified(dream, "video_pending_prompts")
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        dream.status = DreamStatus.failed
        dream.failure_reason = str(e)[:500]
        dream.updated_at = datetime.utcnow()
        await db.commit()
        try:
            from services.observability import inc
            inc("dreamapp_video_failures_total")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)[:200]}")

    return {
        "dream_id": dream.id,
        "status": "generating",
        "total_shots": total,
        "submitted": len(active_ids),
        "pending": len(pending),
        "video_quota_remaining": remaining,
    }


@router.get("/{dream_id}/video-status")
async def check_video_status(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll video status. Auto-submits next batch when current batch completes."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_owner(dream, user)

    if dream.status == DreamStatus.completed and dream.video_urls:
        return {
            "status": "completed",
            "video_url": dream.video_url,
            "video_urls": dream.video_urls,
            "total_shots": len(dream.video_urls),
            "completed_shots": len(dream.video_urls),
        }

    if dream.status != DreamStatus.generating:
        return {"status": dream.status.value, "video_url": dream.video_url}

    task_ids = dream.video_task_ids or []
    if not task_ids:
        return {"status": dream.status.value, "video_url": None}

    # Poll current batch
    active_ids = [t for t in task_ids if not t.startswith("error:")]
    result = await video_gen.check_multi_status(active_ids)

    # Collect completed URLs — deduplicate to prevent repeat clips
    existing_urls = list(dream.video_urls or [])
    existing_set = set(existing_urls)
    still_processing = False

    for i, (status, url) in enumerate(zip(result.statuses, result.video_urls)):
        if status == "completed" and url and url not in existing_set:
            existing_urls.append(url)
            existing_set.add(url)
        elif status == "processing":
            still_processing = True

    pending = list(dream.video_pending_prompts or [])
    total_shots = len(existing_urls) + len([s for s in result.statuses if s == "processing"]) + len(pending)

    # If current batch done and more pending → submit next batch with frame continuity
    if not still_processing and pending:
        # Use last completed video URL for i2v chaining (visual continuity)
        last_url = existing_urls[-1] if existing_urls else ""
        new_task_ids = await video_gen.submit_next_batch(pending, batch_size=5, last_video_url=last_url)
        remaining = pending[len(new_task_ids):]

        dream.video_task_ids = new_task_ids
        dream.video_pending_prompts = remaining
        dream.video_urls = existing_urls
        dream.updated_at = datetime.utcnow()
        flag_modified(dream, "video_task_ids")
        flag_modified(dream, "video_pending_prompts")
        flag_modified(dream, "video_urls")
        await db.commit()

        return {
            "status": "generating",
            "video_url": existing_urls[0] if existing_urls else None,
            "video_urls": existing_urls,
            "total_shots": total_shots,
            "completed_shots": len(existing_urls),
        }

    # If all done (no processing, no pending) → auto-concat
    if not still_processing and not pending:
        dream.video_urls = existing_urls

        # Auto-concat into single film. concat_clips returns
        # (playable_url, object_name) — we store object_name as the source
        # of truth and resign on every read.
        if len(existing_urls) > 1:
            try:
                film_url, obj_name = await concat_clips(existing_urls, dream_id)
                dream.video_url = film_url or (existing_urls[0] if existing_urls else None)
                if obj_name:
                    dream.video_object_name = obj_name
            except Exception:
                dream.video_url = existing_urls[0] if existing_urls else None
        else:
            dream.video_url = existing_urls[0] if existing_urls else None

        dream.status = DreamStatus.completed
        dream.updated_at = datetime.utcnow()
        flag_modified(dream, "video_urls")
        await db.commit()

        return {
            "status": "completed",
            "video_url": dream.video_url,
            "video_urls": existing_urls,
            "total_shots": len(existing_urls),
            "completed_shots": len(existing_urls),
        }

    # Still processing current batch
    dream.video_urls = existing_urls
    flag_modified(dream, "video_urls")
    await db.commit()

    return {
        "status": "generating",
        "video_url": existing_urls[0] if existing_urls else None,
        "video_urls": existing_urls,
        "total_shots": total_shots,
        "completed_shots": len(existing_urls),
    }


@router.post("/{dream_id}/interpret")
async def interpret_dream(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Interpret a dream."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if dream.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Dream deleted")
    if not dream.dream_script:
        raise HTTPException(status_code=400, detail="Dream script not ready")

    # Crisis check on the full user-authored content, including script narrative
    from services import crisis
    locale = getattr(user, "locale", None) or "zh-CN"
    user_corpus = [dream.user_initial_input or ""] + [
        m.get("content", "") for m in (dream.chat_history or []) if m.get("role") == "user"
    ] + [str((dream.dream_script or {}).get("narrative", ""))]
    detection = crisis.detect("\n".join(user_corpus), locale=locale)
    if detection.suppress_ai:
        await crisis.log_crisis_flag(db, user.id, dream.id, detection, surface="interpretation")
        payload = crisis.crisis_response_payload(detection)
        payload["dream_id"] = dream.id
        return JSONResponse(status_code=200, content=payload)

    try:
        interpretation, interp_cites = await interpreter.interpret(
            dream.dream_script, dream.chat_history, db=db, dream_id=dream.id
        )
        dream.interpretation = interpretation
        if interp_cites:
            cites = dict(dream.knowledge_citations or {})
            cites["interpreter"] = interp_cites
            dream.knowledge_citations = cites
            flag_modified(dream, "knowledge_citations")

        # Extract emotion scores and nightmare flag
        try:
            valence, arousal = await extract_emotion_scores(interpretation)
            dream.emotion_valence = valence
            dream.emotion_arousal = arousal
            dream.nightmare_flag = is_nightmare(dream.dream_script, interpretation)
        except Exception:
            pass

        dream.updated_at = datetime.utcnow()
        await db.commit()

        try:
            from services import analytics as _an
            await _an.track("dream_interpreted", user_id=user.id, props={
                "dream_id": dream.id,
                "nightmare": bool(dream.nightmare_flag),
            })
        except Exception:
            pass

        # Proactive IRT push: when this dream + recent history shows nightmare
        # pattern, surface the rewrite tool + therapist suggestion as a
        # structured "next_action" the frontend can render as a banner.
        # Based on Carr & Nielsen (2020) — IRT is the first-line intervention.
        next_action = await _suggest_next_action(db, user, dream)

        return {
            "dream_id": dream.id,
            "interpretation": interpretation,
            "next_action": next_action,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interpretation failed: {str(e)[:200]}")


async def _suggest_next_action(db: AsyncSession, user, dream: DreamRecord) -> dict | None:
    """If this dream + recent context warrant it, suggest IRT or a therapist.

    Returns ``None`` when the dream is benign. Otherwise:

      {"kind": "irt", "reason": "...", "cta": "Rewrite this dream's ending"}
      {"kind": "therapist", "reason": "..", "matched_count": N}

    The threshold logic is conservative — we don't want to pathologize
    every bad dream. Trigger when EITHER the current dream is flagged AND
    there are 2+ similarly-flagged dreams in the last 30 days.
    """
    if not dream.nightmare_flag:
        return None

    # Count nightmare-flagged dreams in last 30 days
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)
    rec_res = await db.execute(
        select(DreamRecord).where(
            and_(
                DreamRecord.user_id == user.id,
                DreamRecord.nightmare_flag == True,  # noqa: E712
                DreamRecord.deleted_at.is_(None),
                DreamRecord.created_at >= cutoff,
            )
        )
    )
    recent_count = len(list(rec_res.scalars().all()))

    if recent_count >= 3:
        # Strong signal — escalate to therapist suggestion
        try:
            from services.therapists import suggest_for_user
            matches = await suggest_for_user(db, user.id, limit=3)
        except Exception:
            matches = []
        return {
            "kind": "therapist",
            "reason": f"{recent_count} distressing dreams in the last 30 days",
            "matched_count": len(matches),
            "evidence": "Carr & Nielsen 2020 — chronic nightmares respond well to therapist-led IRT",
        }

    # Lighter signal — recommend self-IRT
    return {
        "kind": "irt",
        "reason": "This dream looks distressing — Imagery Rehearsal Therapy can help",
        "cta": "Rewrite this dream's ending",
        "evidence": "IRT has 70%+ efficacy for recurring nightmares (Carr 2020, Sleep Medicine Reviews)",
        "rewrite_endpoint": f"/api/dreams/{dream.id}/rewrite",
    }


@router.get("/{dream_id}/citations")
async def get_citations(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the knowledge entries that drove each stage of this dream."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_owner(dream, user)

    from models.knowledge_embedding import KnowledgeEmbedding

    cites = dream.knowledge_citations or {}
    all_ids: list[str] = []
    for stage_ids in cites.values():
        if isinstance(stage_ids, list):
            all_ids.extend(stage_ids)
    all_ids = list(dict.fromkeys(all_ids))

    entries_by_id: dict = {}
    if all_ids:
        result = await db.execute(
            select(KnowledgeEmbedding).where(KnowledgeEmbedding.id.in_(all_ids))
        )
        for e in result.scalars().all():
            # Surface academic provenance: title/authors/year for papers,
            # culture name for cultural entries, etc. The whole metadata blob
            # is small (~1KB per entry) so just send it — UI picks fields.
            meta = e.metadata_json or {}
            entries_by_id[e.id] = {
                "id": e.id,
                "source": e.source,
                "name": e.name,
                "tier": e.tier.value if hasattr(e.tier, "value") else str(e.tier),
                "content": e.content_text[:200],
                "confidence": e.confidence,
                "use_count": e.use_count,
                "success_count": e.success_count,
                "failure_count": e.failure_count,
                "status": e.status.value if hasattr(e.status, "value") else str(e.status),
                "metadata": {
                    # papers
                    "title": meta.get("title"),
                    "authors": meta.get("authors"),
                    "year": meta.get("year"),
                    "journal": meta.get("journal"),
                    # cultural / corpus
                    "culture": meta.get("culture") or meta.get("name_native"),
                    "era": meta.get("era"),
                    # generic
                    "category": meta.get("category"),
                },
            }

    return {
        "dream_id": dream.id,
        "feedback": dream.feedback or {},
        "stages": {
            stage: [entries_by_id[i] for i in (ids or []) if i in entries_by_id]
            for stage, ids in cites.items()
        },
    }


@router.post("/{dream_id}/feedback")
async def submit_feedback(
    dream_id: str,
    payload: dict,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """User feedback on a dream stage. Bumps success/failure_count on cited entries.

    Payload: {"aspect": "interpretation"|"interviewer"|"director", "helpful": true|false}
    """
    from services.knowledge_retrieval import apply_feedback

    aspect = payload.get("aspect", "interpreter")
    helpful = bool(payload.get("helpful", True))

    # Normalize aspect → citation key
    key_map = {
        "interpretation": "interpreter",
        "interpreter": "interpreter",
        "interview": "interviewer",
        "interviewer": "interviewer",
        "video": "director",
        "director": "director",
    }
    citation_key = key_map.get(aspect)
    if not citation_key:
        raise HTTPException(status_code=400, detail=f"Unknown aspect: {aspect}")

    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)

    cites = dream.knowledge_citations or {}
    ids = cites.get(citation_key, []) or []
    updated = await apply_feedback(db, ids, helpful=helpful)

    # Record user feedback on the dream itself
    fb = dict(dream.feedback or {})
    fb[aspect] = "helpful" if helpful else "unhelpful"
    dream.feedback = fb
    flag_modified(dream, "feedback")
    await db.commit()

    try:
        from services.observability import inc
        inc("dreamapp_feedback_total", {"aspect": citation_key, "helpful": str(helpful).lower()})
    except Exception:
        pass

    return {
        "dream_id": dream.id,
        "aspect": aspect,
        "helpful": helpful,
        "entries_updated": updated,
    }


@router.post("/{dream_id}/rewrite")
async def rewrite_nightmare(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Rewrite a nightmare with a new ending (user-directed)."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if not dream.dream_script:
        raise HTTPException(status_code=400, detail="Dream script not ready")

    try:
        from services.llm import chat_completion

        script_text = json.dumps(dream.dream_script, ensure_ascii=False)
        prompt = f"""This dream has disturbing or negative elements. Rewrite the dream script to give it a healing, empowering ending while keeping the same setting and characters. The dreamer should gain control and transform the negative elements.

Original dream script:
{script_text}

Output a new dream script in the same JSON format, but with the ending scenes rewritten to be healing and empowering. Keep the beginning the same. Output ONLY JSON."""

        raw = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system="You are a dream therapy assistant specializing in Imagery Rehearsal Therapy. Rewrite nightmares into empowering narratives.",
            max_tokens=4000,
        )

        from services.interpreter import _repair_json
        rewritten = _repair_json(raw)

        return {"dream_id": dream.id, "rewritten_script": rewritten}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rewrite failed: {str(e)[:200]}")


_VOICE_MAX_BYTES = 10 * 1024 * 1024   # 10 MB hard cap — any bigger is suspicious
_VOICE_ALLOWED_MIMES = {
    "audio/mpeg", "audio/mp3",
    "audio/wav", "audio/wave", "audio/x-wav",
    "audio/mp4", "audio/x-m4a", "audio/aac",
    "audio/ogg", "audio/webm",
}
# Magic-byte prefixes for common audio containers. First 12 bytes are enough.
_VOICE_MAGIC_PREFIXES: tuple[bytes, ...] = (
    b"ID3",            # MP3 with ID3 tag
    b"\xff\xfb",       # MP3 frame sync
    b"\xff\xf3",       # MP3 MPEG2 layer 3
    b"RIFF",           # WAV container
    b"OggS",           # Ogg
    b"\x1a\x45\xdf\xa3",  # Matroska/WebM
    b"fLaC",           # FLAC
    b"ftyp",           # MP4/M4A (usually offset 4, we check both positions)
)


def _looks_like_audio(body: bytes) -> bool:
    """Cheap magic-byte sniff. Not meant to be bulletproof — it's a DoS guard
    against "upload a 10 MB zipfile named audio.mp3" prank."""
    if not body or len(body) < 4:
        return False
    head = body[:16]
    for p in _VOICE_MAGIC_PREFIXES:
        if head.startswith(p):
            return True
    # MP4 ftyp is at offset 4, not 0
    if len(body) >= 8 and body[4:8] == b"ftyp":
        return True
    return False


@router.post("/voice-to-text")
async def voice_to_text(
    file: UploadFile = File(None),
    user: UserRecord = Depends(require_user),
):
    """Convert voice recording to text. Auth-required — STT is billable.

    Validation:
      - must be a real multipart UploadFile (bytes=None silently fails)
      - size capped at 10 MB
      - declared content-type must be an allowed audio MIME
      - magic-byte sniff on first 16 bytes — rejects non-audio payloads
    """
    import httpx
    from config import settings

    if file is None:
        raise HTTPException(status_code=400, detail="No audio file provided (use multipart form 'file')")

    ctype = (file.content_type or "").lower()
    if ctype not in _VOICE_ALLOWED_MIMES:
        raise HTTPException(status_code=415, detail=f"Unsupported audio type: {ctype!r}")

    # Stream into memory with a hard cap
    chunk = await file.read(_VOICE_MAX_BYTES + 1)
    if len(chunk) > _VOICE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio too large (max {_VOICE_MAX_BYTES // 1024 // 1024} MB)")
    if not _looks_like_audio(chunk):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid audio recording")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.llm_base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                files={"file": (file.filename or "audio", chunk, ctype)},
                data={"model": "speech-01"},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", "")
            return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT failed: {str(e)[:200]}")


@router.post("/voice-to-text-upload")
async def voice_to_text_upload(file: bytes = None):
    """Alternative: accept base64 encoded audio."""
    import base64
    import httpx
    from config import settings

    from fastapi import Body
    # Accept JSON body with base64 audio
    return {"status": "use_multipart", "message": "Upload audio via multipart form to /voice-to-text"}


@router.get("/", response_model=list[DreamResponse])
async def list_dreams(
    skip: int = 0,
    limit: int = 20,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's dreams, newest first. Excludes soft-deleted."""
    result = await db.execute(
        select(DreamRecord)
        .where(
            and_(
                DreamRecord.user_id == user.id,
                DreamRecord.deleted_at.is_(None),
            )
        )
        .order_by(DreamRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    dreams = result.scalars().all()
    return [_with_fresh_video_url(d) for d in dreams]


@router.get("/{dream_id}", response_model=DreamResponse)
async def get_dream(
    dream_id: str,
    user: Optional[UserRecord] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single dream. Owner gets full access; everyone else only if public."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream or dream.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Dream not found")
    is_owner = bool(user and dream.user_id and dream.user_id == user.id)
    if not is_owner and not dream.is_public:
        raise HTTPException(status_code=403, detail="Dream is private")
    return _with_fresh_video_url(dream, public=not is_owner)


@router.delete("/{dream_id}")
async def delete_dream(
    dream_id: str,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a dream. Owner only. Sets deleted_at + is_public=False."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if dream.deleted_at is not None:
        return {"dream_id": dream.id, "deleted_at": dream.deleted_at.isoformat()}
    dream.deleted_at = datetime.utcnow()
    dream.is_public = False  # remove from plaza immediately
    await db.commit()
    return {"dream_id": dream.id, "deleted_at": dream.deleted_at.isoformat()}


@router.patch("/{dream_id}", response_model=DreamResponse)
async def update_dream(
    dream_id: str,
    req: DreamUpdateRequest,
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit dream metadata. Currently supports title and video_style. Owner only."""
    dream = await db.get(DreamRecord, dream_id)
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    assert_dream_mutable_by(dream, user)
    if dream.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Dream deleted")

    if req.title is not None:
        dream.title = req.title.strip() or None
    if req.video_style is not None:
        dream.video_style = req.video_style.strip() or dream.video_style

    dream.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(dream)
    return DreamResponse.model_validate(dream)
