"""Video concatenation service — merges multi-shot clips into one film.

Storage strategy: MinIO is durable primary; local disk is scratch for
ffmpeg + a fast re-serve cache.

Returns ``(playable_url, object_name)``. The object_name goes into
``dreams.video_object_name`` (stable) and the playable_url goes into
``dreams.video_url`` (derived; resign on read once the presigned URL
expires — see services/video_url.serve_video_url).
"""

import asyncio
import os
import random
import subprocess
import tempfile
from pathlib import Path

import httpx

from config import settings

try:
    from services.observability import get_logger
    log = get_logger("video_concat")
except Exception:  # pragma: no cover — observability optional in tests
    import logging
    log = logging.getLogger("dreamapp.video_concat")


# Concat-flow tunables
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_BACKOFF_BASE_S = 0.8
DOWNLOAD_TIMEOUT_S = 90        # was 60; large multi-shot clips can be 8-10MB
DOWNLOAD_MIN_BYTES = 50_000    # under this is suspicious — Seedance/Kling never returns < 200KB
FFMPEG_TIMEOUT_S = 180


async def download_clip(url: str, filepath: str) -> bool:
    """Download a video clip from URL with retries.

    Robust against:
      - Transient network errors (3 attempts, jittered exp backoff)
      - Provider-side 5xx
      - Truncated downloads (validated against DOWNLOAD_MIN_BYTES)
      - Partial-write corruption (atomic rename via tempfile)
    Returns True iff a file of plausible size landed at `filepath`.
    """
    if not url:
        return False
    last_err: Exception | None = None
    for attempt in range(DOWNLOAD_ATTEMPTS):
        # Atomic write: tmp → rename. Prevents readers / concat from seeing
        # a half-written file if the process crashes mid-download.
        tmp_path = filepath + f".part.{os.getpid()}.{attempt}"
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_S) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp,
                    )
                resp.raise_for_status()
                payload = resp.content
            if len(payload) < DOWNLOAD_MIN_BYTES:
                raise ValueError(f"downloaded {len(payload)} bytes — below MIN_BYTES")
            with open(tmp_path, "wb") as f:
                f.write(payload)
            os.replace(tmp_path, filepath)   # atomic
            return True
        except Exception as e:
            last_err = e
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            if attempt < DOWNLOAD_ATTEMPTS - 1:
                delay = DOWNLOAD_BACKOFF_BASE_S * (2 ** attempt) * (0.85 + random.random() * 0.3)
                await asyncio.sleep(delay)
                continue
            log.warning(
                "download_clip exhausted retries",
                extra={"url": url[:120], "filepath": filepath, "err": str(e)[:200]},
            )
    return False


def _local_videos_url(dream_id: str, filename: str) -> str:
    """Stable URL for the in-container `/videos/...` static mount.

    Used as a fallback when MinIO isn't reachable, and during dev.
    """
    return f"/videos/{dream_id}/{filename}"


async def _publish(local_path: str, object_name: str) -> tuple[str, str]:
    """Upload to MinIO and return ``(playable_url, object_name)``.

    Caller should persist `object_name` (stable) and re-derive the URL on
    each read so links never expire.
    """
    try:
        from services.storage import upload_video, get_presigned_url
        if upload_video(object_name, local_path):
            url = get_presigned_url(object_name)
            if url:
                return url, object_name
    except Exception as e:
        print(f"MinIO publish failed: {e}")

    # Fallback — local container path through nginx
    rel = object_name.replace("dreams/", "", 1)
    parts = rel.split("/", 1)
    fallback_url = (
        _local_videos_url(parts[0], parts[1]) if len(parts) == 2 else ""
    )
    return fallback_url, object_name


async def concat_clips(video_urls: list[str], dream_id: str) -> tuple[str, str]:
    """Download all clips and concat into one video.

    Returns ``(playable_url, object_name)``.
      - Empty tuple `("", "")` means truly nothing succeeded.
      - Single-clip path (`shot_NN.mp4` object name) ONLY when the input
        list itself contained exactly one URL — never as a fallback for
        a multi-clip job whose downloads partially failed (that's what
        used to happen and silently published shot_01 as the "film").
      - Multi-clip path (`dream_film.mp4` object name) when ffmpeg
        concat succeeded.

    Strategy on partial download failure:
      We re-skip the failed indices (download_clip already retries 3x).
      If, after retries, fewer than HALF the requested clips downloaded,
      we abandon and return `("", "")` — the caller can leave status as
      'generating' and the next status poll will retry.
    """
    if not video_urls:
        return "", ""

    # Force ABSOLUTE path. `settings.video_storage_path` is configured as
    # `"data/videos"` (relative) in production. Without resolve(), the
    # subprocess.run(cwd=dream_dir) + relative `-i list_path` combination
    # made ffmpeg look for `data/videos/<id>/concat_list.txt` INSIDE
    # `data/videos/<id>/` (i.e. `data/videos/<id>/data/videos/<id>/...`).
    # That's why concat silently failed for years — caller's fallback
    # quietly published the first shot as the "film" and nobody noticed.
    video_dir = Path(settings.video_storage_path).resolve()
    video_dir.mkdir(parents=True, exist_ok=True)

    dream_dir = video_dir / dream_id
    dream_dir.mkdir(exist_ok=True)

    # Download all clips IN PARALLEL with bounded concurrency. Was serial
    # — for 8 shots × ~5MB that was minutes wall time.
    sem = asyncio.Semaphore(4)

    async def _dl(idx: int, url: str) -> tuple[int, str | None]:
        path = str(dream_dir / f"shot_{idx+1:02d}.mp4")
        # If a previous, validated copy is already on disk, skip the
        # download entirely (status polls re-call concat repeatedly).
        try:
            if os.path.exists(path) and os.path.getsize(path) >= DOWNLOAD_MIN_BYTES:
                return idx, path
        except OSError:
            pass
        async with sem:
            ok = await download_clip(url, path)
        return idx, (path if ok else None)

    results = await asyncio.gather(*[_dl(i, u) for i, u in enumerate(video_urls) if u])
    # Sort by original index so concat order matches shot order (gather
    # may return out of order under concurrent download).
    results.sort(key=lambda x: x[0])
    clip_paths: list[str] = [p for _, p in results if p]

    if not clip_paths:
        log.warning("concat_clips: zero clips downloaded", extra={"dream_id": dream_id})
        return "", ""

    # Genuine single-input: the dream really only has 1 shot. Publish it.
    if len(video_urls) == 1 and len(clip_paths) == 1:
        only = clip_paths[0]
        return await _publish(only, f"dreams/{dream_id}/{os.path.basename(only)}")

    # Multi-input but most downloads failed → return empty so the caller
    # leaves status='generating' and a later poll re-attempts the whole
    # thing. Better silent retry than a half-baked "completed" film.
    if len(clip_paths) < max(2, (len(video_urls) + 1) // 2):
        log.warning(
            "concat_clips: only %d/%d clips downloaded — abandoning, status will retry",
            len(clip_paths), len(video_urls),
            extra={"dream_id": dream_id},
        )
        return "", ""

    # ffmpeg concat. Use `os.path.basename` so concat_list.txt has only
    # filenames (ffmpeg cwd is dream_dir).
    list_path = str(dream_dir / "concat_list.txt")
    with open(list_path, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{os.path.basename(cp)}'\n")

    output_path = str(dream_dir / "dream_film.mp4")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                output_path,
            ],
            cwd=str(dream_dir),
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except Exception as e:
        log.exception("ffmpeg concat exception", extra={"dream_id": dream_id, "err": str(e)})
        return "", ""

    if result.returncode != 0 or not os.path.exists(output_path):
        log.warning(
            "ffmpeg concat failed",
            extra={
                "dream_id": dream_id,
                "rc": result.returncode,
                "stderr": (result.stderr[:500].decode("utf-8", errors="replace") if result.stderr else ""),
            },
        )
        return "", ""

    return await _publish(output_path, f"dreams/{dream_id}/dream_film.mp4")
