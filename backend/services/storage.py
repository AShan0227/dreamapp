"""MinIO S3-compatible object storage service."""

import io
from datetime import timedelta
from typing import Optional

from config import settings

_client = None


def _get_client():
    """Lazy-load MinIO client."""
    global _client
    if _client is None:
        try:
            from minio import Minio
            _client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            # Ensure bucket exists
            if not _client.bucket_exists(settings.minio_bucket):
                _client.make_bucket(settings.minio_bucket)
                print(f"Created MinIO bucket: {settings.minio_bucket}")
        except Exception as e:
            print(f"MinIO not available: {e}")
            _client = "FAILED"
    return _client if _client != "FAILED" else None


def upload_video(object_name: str, file_path: str) -> Optional[str]:
    """Upload a video file to MinIO. Returns the object name."""
    client = _get_client()
    if client is None:
        return None
    try:
        client.fput_object(settings.minio_bucket, object_name, file_path)
        return object_name
    except Exception as e:
        print(f"MinIO upload error: {e}")
        return None


def upload_bytes(object_name: str, data: bytes, content_type: str = "video/mp4") -> Optional[str]:
    """Upload bytes to MinIO."""
    client = _get_client()
    if client is None:
        return None
    try:
        client.put_object(
            settings.minio_bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name
    except Exception as e:
        print(f"MinIO upload error: {e}")
        return None


def get_presigned_url(object_name: str, expires: int = 86400) -> Optional[str]:
    """Get a pre-signed URL for downloading. Default 24h expiry."""
    client = _get_client()
    if client is None:
        return None
    try:
        url = client.presigned_get_object(
            settings.minio_bucket,
            object_name,
            expires=timedelta(seconds=expires),
        )
        return url
    except Exception as e:
        print(f"MinIO presigned URL error: {e}")
        return None


def list_objects(prefix: str = "") -> list[str]:
    """List objects in bucket with optional prefix."""
    client = _get_client()
    if client is None:
        return []
    try:
        objects = client.list_objects(settings.minio_bucket, prefix=prefix)
        return [obj.object_name for obj in objects]
    except Exception as e:
        print(f"MinIO list error: {e}")
        return []
