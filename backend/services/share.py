"""External share + branded watermark helpers.

For viral spread (PRODUCT_DOC §6.4) — every shared video carries a
"@DreamApp" watermark + small QR. Pro/Premium users can opt out of
the watermark.

The actual ffmpeg watermark step runs on demand (idempotent: cached by
hash of source + watermark settings).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional

from config import settings


WATERMARK_TEXT = "@DreamApp · dreamapp.cn"
SHARE_LANDING = "https://dreamapp.cn"  # change when domain provisioned


def _watermarked_filename(source_path: str, opt_out: bool) -> str:
    h = hashlib.sha1(f"{source_path}|{opt_out}|{WATERMARK_TEXT}".encode()).hexdigest()[:12]
    return f"share-{h}.mp4"


def _ensure_ffmpeg() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def make_shareable(source_local_path: str, opt_out_watermark: bool = False) -> Optional[str]:
    """Produce a shareable mp4 from a source mp4. Returns the local path
    of the output, or None if ffmpeg unavailable / source missing.

    Security: caller MUST pass a path that resolves under the configured
    video_storage_path. We validate this defensively so future callers who
    pass user-hinted paths don't open a path-traversal / arbitrary-read
    hole against ffmpeg.
    """
    src = Path(source_local_path)
    if not src.exists() or not _ensure_ffmpeg():
        return None

    # Resolve to absolute + confirm the source lives inside the allowed root.
    try:
        src_resolved = src.resolve(strict=True)
        root = Path(settings.video_storage_path).resolve()
    except Exception:
        return None
    try:
        src_resolved.relative_to(root)  # raises if src is outside root
    except ValueError:
        from services.observability import get_logger
        get_logger("share").warning(
            "make_shareable path escape rejected",
            extra={"source": str(src_resolved), "root": str(root)},
        )
        return None
    src = src_resolved

    out_dir = Path(settings.video_storage_path) / "shareable"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _watermarked_filename(str(src.resolve()), opt_out_watermark)

    if out_path.exists():
        return str(out_path)

    if opt_out_watermark:
        # Strip metadata only
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-map_metadata", "-1",
            "-c", "copy",
            str(out_path),
        ]
    else:
        # drawtext overlay (use a fontfile if you want CJK reliably)
        # bottom-right, 18px white text with semi-transparent black box
        watermark = (
            f"drawtext=text='{WATERMARK_TEXT}':fontcolor=white@0.85:"
            f"fontsize=24:box=1:boxcolor=black@0.45:boxborderw=8:"
            f"x=w-tw-20:y=h-th-20"
        )
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", watermark,
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            return None
        return str(out_path)
    except Exception:
        return None


def share_payload(dream_id: str, video_url: str) -> dict:
    """Frontend uses this to populate native share sheets.

    Returns the canonical landing URL + suggested copy + meta image hint.
    The frontend chooses how to invoke the platform-specific share SDK
    (WeChat, Douyin, etc).
    """
    landing = f"{SHARE_LANDING}/d/{dream_id}"
    return {
        "url": landing,
        "title": "I dreamed this last night.",
        "description": "Recorded, visualized, and interpreted with DreamApp.",
        "video_url": video_url,
        "share_text_zh": "我昨晚梦见的画面。看：",
        "share_text_en": "What I dreamt last night, visualized:",
    }
