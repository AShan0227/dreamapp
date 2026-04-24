"""Video concat regression tests.

Pins the bugs found while debugging dream `0fdbcb89-...` on 2026-04-24:

1. **Relative cwd path bug** — `settings.video_storage_path` is `"data/videos"`
   (relative). Old code passed relative `list_path` to ffmpeg with cwd=dream_dir,
   so ffmpeg looked for `data/videos/<id>/concat_list.txt` INSIDE its own cwd
   (= `data/videos/<id>/`). Always failed silently, fallback published shot_01.

2. **download_clip lacked retries** — single transient failure → only some
   clips downloaded → `clip_paths == [shot_01]` → fallback to single-shot.

3. **concat_clips silent fallback** — multi-shot dream with partial download
   would publish `shot_01.mp4` and pretend that was the film.

These tests don't need network, ffmpeg, or MinIO — they verify the SHAPE
of the output and the retry / atomicity contract in `download_clip`.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.video_concat import (  # noqa: E402
    download_clip,
    concat_clips,
    DOWNLOAD_ATTEMPTS,
    DOWNLOAD_MIN_BYTES,
)


# ---- download_clip: retry + atomicity --------------------------------------

@pytest.mark.asyncio
async def test_download_clip_returns_false_on_empty_url():
    assert await download_clip("", "/tmp/x") is False


@pytest.mark.asyncio
async def test_download_clip_atomic_on_failure(tmp_path):
    """A failed download must NOT leave a partial file at the target path
    (would confuse the cache-skip logic in concat_clips)."""
    target = str(tmp_path / "shot_99.mp4")

    # Simulate consistent failure
    async def boom(*a, **k):
        raise RuntimeError("network down")

    with patch("services.video_concat.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=boom)
        ok = await download_clip("https://example.com/clip.mp4", target)

    assert ok is False
    assert not os.path.exists(target), "partial / phantom file must not be left behind"


@pytest.mark.asyncio
async def test_download_clip_rejects_undersized_response(tmp_path):
    """Provider returning < DOWNLOAD_MIN_BYTES is treated as failure
    (truncated download, e.g. proxy stripped most bytes)."""
    target = str(tmp_path / "shot_99.mp4")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b"X" * 100   # way under DOWNLOAD_MIN_BYTES (50_000)
    fake_resp.raise_for_status = MagicMock()

    with patch("services.video_concat.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=fake_resp)
        ok = await download_clip("https://example.com/clip.mp4", target)

    assert ok is False
    assert not os.path.exists(target)


@pytest.mark.asyncio
async def test_download_clip_succeeds_after_retry(tmp_path):
    """Transient failure → retry → success must produce a complete file."""
    target = str(tmp_path / "shot_99.mp4")
    payload = b"M" * (DOWNLOAD_MIN_BYTES + 100)

    fake_ok = MagicMock()
    fake_ok.status_code = 200
    fake_ok.content = payload
    fake_ok.raise_for_status = MagicMock()

    call_count = {"n": 0}
    async def flaky_get(*a, **k):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise RuntimeError("transient")
        return fake_ok

    with patch("services.video_concat.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=flaky_get)
        ok = await download_clip("https://example.com/clip.mp4", target)

    assert ok is True
    assert os.path.exists(target)
    assert os.path.getsize(target) == len(payload)


# ---- concat_clips: empty / partial / abandon paths -----------------------

@pytest.mark.asyncio
async def test_concat_clips_empty_input():
    """Empty input → no work, no MinIO call, returns ('','')."""
    url, obj = await concat_clips([], "test-empty-dream")
    assert url == ""
    assert obj == ""


@pytest.mark.asyncio
async def test_concat_clips_no_downloads_returns_empty():
    """If every download fails → return ('','') so caller leaves status
    as 'generating' (will retry on next poll). Must NOT silently
    publish a phantom URL.
    """
    with patch("services.video_concat.download_clip", AsyncMock(return_value=False)):
        url, obj = await concat_clips(
            ["https://example.com/a.mp4", "https://example.com/b.mp4"],
            "test-no-dl-dream",
        )
    assert url == ""
    assert obj == ""


@pytest.mark.asyncio
async def test_concat_clips_abandons_when_majority_failed(tmp_path):
    """When more than half of clips fail to download, abandon and let
    the caller retry — DON'T publish a half-baked film. This is the bug
    that historically caused 1/8 dreams to be marked 'completed'."""
    # Patch download_clip: succeed only for index 0 (shot_01); rest fail.
    fake_files = [tmp_path / f"shot_{i+1:02d}.mp4" for i in range(8)]

    async def patchy_download(url, filepath):
        # Succeed for the first one only
        if "0.mp4" in url or url.endswith("a.mp4"):
            with open(filepath, "wb") as f:
                f.write(b"X" * (DOWNLOAD_MIN_BYTES + 1))
            return True
        return False

    urls = [f"https://example.com/{i}.mp4" for i in range(8)]
    with patch("services.video_concat.download_clip", AsyncMock(side_effect=patchy_download)):
        url, obj = await concat_clips(urls, "test-partial-dream")

    # Old code returned shot_01 here. New code must return ('','') so
    # nothing bogus gets persisted.
    assert url == "" and obj == "", (
        "Partial download must NOT publish single-shot fallback. "
        f"Got url={url!r} obj={obj!r}"
    )


@pytest.mark.asyncio
async def test_concat_clips_skips_already_downloaded(tmp_path, monkeypatch):
    """If a valid clip already exists on disk (from a previous concat
    attempt), download_clip must NOT be called again — supports the
    /reconcatenate self-heal path."""
    # Point video_storage_path to a temp dir
    from config import settings
    monkeypatch.setattr(settings, "video_storage_path", str(tmp_path), raising=False)

    dream_id = "test-skip-cache"
    dream_dir = tmp_path / dream_id
    dream_dir.mkdir()
    # Pre-create 2 valid clips (size > MIN_BYTES)
    for i in range(2):
        with open(dream_dir / f"shot_{i+1:02d}.mp4", "wb") as f:
            f.write(b"M" * (DOWNLOAD_MIN_BYTES * 2))

    download_call_count = {"n": 0}
    async def counting_dl(url, filepath):
        download_call_count["n"] += 1
        return False  # if we even GET called, that's a regression

    with patch("services.video_concat.download_clip", AsyncMock(side_effect=counting_dl)):
        # We don't care about ffmpeg success here — just that downloads were skipped.
        # Use 2 URLs matching the 2 cached clips.
        try:
            await concat_clips(
                ["https://example.com/0.mp4", "https://example.com/1.mp4"],
                dream_id,
            )
        except Exception:
            pass   # ffmpeg may fail in the test sandbox; OK

    assert download_call_count["n"] == 0, (
        f"Cached clips must be reused without re-downloading. "
        f"download_clip was called {download_call_count['n']} time(s)."
    )


# ---- Path absolutization (the headline regression) ----------------------

def test_video_storage_path_is_absolutized(tmp_path, monkeypatch):
    """Pin: even if config supplies a RELATIVE storage path,
    concat_clips internally resolves to absolute. Without this, ffmpeg
    invocation with cwd=dream_dir resolved `-i list_path` to
    `data/videos/<id>/data/videos/<id>/concat_list.txt` → file not found.
    """
    from config import settings
    monkeypatch.setattr(settings, "video_storage_path", "data/videos", raising=False)

    # We don't run concat — just assert the path resolution machinery exists.
    # The actual fix is one line: `Path(settings.video_storage_path).resolve()`.
    src = (Path(__file__).resolve().parents[1] / "services" / "video_concat.py").read_text()
    assert ".resolve()" in src and "video_storage_path" in src, (
        "concat_clips must call .resolve() on settings.video_storage_path "
        "to guarantee absolute paths reach ffmpeg via cwd."
    )
