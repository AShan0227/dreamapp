"""Single source of truth for serving video URLs to clients.

Why this exists: presigned MinIO URLs expire (24h default). Storing the
URL on the dream record means links break the next day. Instead we store
``video_object_name`` and resign on every read.

Usage from any router:

    from services.video_url import serve_video_url
    payload["video_url"] = serve_video_url(dream)

For batch endpoints (Plaza), call this for each row — the resign is
local (no extra network), so cost is trivial.
"""

from __future__ import annotations

from typing import Any, Optional


# Long-lived URLs for plaza / shared dreams (7 days). Owner-only fetches
# get a shorter lease (1h) because the frontend re-fetches the dream
# anyway and we want minimal exposure if a token is leaked.
_PUBLIC_TTL_SECONDS = 7 * 24 * 3600
_OWNER_TTL_SECONDS = 1 * 3600


def serve_video_url(dream: Any, *, public: bool = False) -> Optional[str]:
    """Return a fresh playable URL for the dream's video, or None.

    `public=True` requests a longer-lived URL suitable for plaza listings.

    Falls back to the legacy `video_url` column when no `video_object_name`
    has been recorded yet (handles dreams generated before this column
    existed).
    """
    object_name = getattr(dream, "video_object_name", None)
    if object_name:
        try:
            from services.storage import get_presigned_url
            ttl = _PUBLIC_TTL_SECONDS if public else _OWNER_TTL_SECONDS
            url = get_presigned_url(object_name, expires=ttl)
            if url:
                return url
        except Exception:
            pass
        # MinIO unreachable but we know the object name — fall back to the
        # in-container nginx static path so single-replica dev still works.
        rel = object_name.replace("dreams/", "", 1)
        parts = rel.split("/", 1)
        if len(parts) == 2:
            return f"/videos/{parts[0]}/{parts[1]}"

    # Legacy dreams: keep returning whatever URL was stored (might be a
    # Kling CDN link, /videos/ path, or an expired presigned URL).
    return getattr(dream, "video_url", None)
