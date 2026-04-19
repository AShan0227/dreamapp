"""Video concatenation service — merges multi-shot clips into one film.

Storage strategy: MinIO is durable primary; local disk is scratch for
ffmpeg + a fast re-serve cache.

Returns ``(playable_url, object_name)``. The object_name goes into
``dreams.video_object_name`` (stable) and the playable_url goes into
``dreams.video_url`` (derived; resign on read once the presigned URL
expires — see services/video_url.serve_video_url).
"""

import os
import subprocess
from pathlib import Path

import httpx

from config import settings


async def download_clip(url: str, filepath: str) -> bool:
    """Download a video clip from URL."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
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

    Returns ``(playable_url, object_name)``. object_name is empty if
    nothing was uploaded.
    """
    video_dir = Path(settings.video_storage_path)
    video_dir.mkdir(parents=True, exist_ok=True)

    dream_dir = video_dir / dream_id
    dream_dir.mkdir(exist_ok=True)

    # Download all clips
    clip_paths: list[str] = []
    for i, url in enumerate(video_urls):
        if not url:
            continue
        clip_path = str(dream_dir / f"shot_{i+1:02d}.mp4")
        ok = await download_clip(url, clip_path)
        if ok:
            clip_paths.append(clip_path)

    if not clip_paths:
        return "", ""

    # Single-shot — push the lone clip to MinIO and return its URL
    if len(clip_paths) == 1:
        only = clip_paths[0]
        return await _publish(only, f"dreams/{dream_id}/{os.path.basename(only)}")

    # Concat
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
            timeout=120,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return await _publish(output_path, f"dreams/{dream_id}/dream_film.mp4")
        else:
            print(
                "ffmpeg concat failed: "
                f"rc={result.returncode}, stderr={result.stderr[:300] if result.stderr else ''}"
            )
    except Exception as e:
        print(f"ffmpeg concat exception: {e}")

    # Fallback — single clip URL through MinIO/local
    return await _publish(
        clip_paths[0], f"dreams/{dream_id}/{os.path.basename(clip_paths[0])}"
    )
