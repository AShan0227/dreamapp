"""Security + observability middleware.

Stack (outermost first):
  RequestIDMiddleware       — stamp a UUID on every request, propagate to
                              X-Request-ID response header + Sentry scope
                              + logger context.
  RequestSizeLimitMiddleware — reject bodies > cap (default 5 MB).
  RateLimitMiddleware       — per-IP cap (default 60 rpm). XFF-aware but
                              trusts the header only from configured proxy CIDRs.
  RequestLoggingMiddleware  — structured timing log + Prometheus counters.
"""
from __future__ import annotations

import ipaddress
import os
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


_MAX_REQUEST_BYTES = int(os.getenv("DREAM_MAX_REQUEST_BYTES", str(5 * 1024 * 1024)))


# ---------------------------------------------------------------------------
# Trust boundary: XFF header. Only parse X-Forwarded-For when the
# *immediate peer* (request.client.host) is in a configured proxy network.
# Previously we trusted XFF unconditionally — letting any client spoof
# their IP and evade rate limits.
# ---------------------------------------------------------------------------
def _parse_trusted_proxies() -> list[ipaddress._BaseNetwork]:
    raw = os.getenv("DREAM_TRUSTED_PROXIES", "").strip()
    if not raw:
        # Default: private ranges (typical docker-compose / k8s cluster
        # internal traffic). Adjust to "" in envs where the app faces public
        # internet directly without a proxy.
        raw = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,::1/128,fc00::/7"
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


_TRUSTED_PROXIES = _parse_trusted_proxies()


def _client_ip(request: Request) -> str:
    """Return the real client IP, respecting XFF only from trusted proxies."""
    peer = request.client.host if request.client else ""
    if peer and _TRUSTED_PROXIES:
        try:
            peer_addr = ipaddress.ip_address(peer)
            trusted = any(peer_addr in n for n in _TRUSTED_PROXIES)
        except ValueError:
            trusted = False
        if trusted:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                # Take the first hop (left-most) — per spec this is the
                # original client. Validate it's a legal IP; if not, fall back.
                candidate = xff.split(",")[0].strip()
                try:
                    ipaddress.ip_address(candidate)
                    return candidate
                except ValueError:
                    pass
    return peer or "unknown"


# ---------------------------------------------------------------------------
# Request ID — every request gets one, echoed back, and available as
# request.state.request_id for downstream handlers/logging.
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Respect incoming header if set by a trusted upstream; otherwise mint one.
        incoming = request.headers.get("x-request-id")
        rid = incoming if incoming and len(incoming) <= 64 else uuid.uuid4().hex
        request.state.request_id = rid

        # Sentry — tag the scope so any exception carries this ID.
        try:
            import sentry_sdk
            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("request_id", rid)
                scope.set_tag("path", request.url.path)
        except Exception:
            pass

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > _MAX_REQUEST_BYTES:
            return Response(
                status_code=413,
                content=f'{{"detail":"Request body too large (max {_MAX_REQUEST_BYTES} bytes)"}}',
                media_type="application/json",
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting. XFF-aware only for trusted proxies.

    In-memory → single-replica only. For multi-replica production, swap for
    Redis-backed (see comment in Wave K audit).
    """

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        client_ip = _client_ip(request)
        now = time.time()

        # Drop buckets older than 60s
        bucket = self.requests[client_ip]
        # Efficient: find first recent index, slice from there
        cutoff = now - 60
        first_recent = next((i for i, t in enumerate(bucket) if t >= cutoff), len(bucket))
        if first_recent:
            del bucket[:first_recent]

        if len(bucket) >= self.rpm:
            # Inc metric then reject
            try:
                from services.observability import inc
                inc("dreamapp_rate_limited_total", {"path_bucket": _coarse_path(request.url.path)})
            except Exception:
                pass
            raise HTTPException(status_code=429, detail="Too many requests")

        bucket.append(now)

        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def _coarse_path(path: str) -> str:
    """Collapse `/api/dreams/<uuid>/interpret` → `/api/dreams/:id/interpret`
    so rate-limit metrics don't explode cardinality."""
    parts = path.split("/")
    return "/".join(p if (len(p) < 12 and not p.isdigit() and "-" not in p) else ":id" for p in parts)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured timing log + Prometheus counters. Uses dreamapp.http logger.

    Skips /health and /metrics to avoid log spam.
    """

    def __init__(self, app):
        super().__init__(app)
        try:
            from services.observability import get_logger
            self.log = get_logger("http")
        except Exception:
            import logging
            self.log = logging.getLogger("dreamapp.http")

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        rid = getattr(request.state, "request_id", "")
        path = request.url.path
        status = response.status_code

        # Structured log — always
        try:
            self.log.info(
                "http",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": path,
                    "status": status,
                    "duration_ms": int(duration * 1000),
                },
            )
        except Exception:
            pass

        if duration > 5.0:
            try:
                self.log.warning(
                    "slow http",
                    extra={"request_id": rid, "path": path, "duration_ms": int(duration * 1000)},
                )
            except Exception:
                pass

        try:
            from services.observability import inc
            status_class = f"{status // 100}xx"
            inc("dreamapp_requests_total", {"status": status_class})
            inc("dreamapp_request_duration_seconds_sum", by=duration)
            inc("dreamapp_request_duration_seconds_count")
            # Latency bucket histogram proxy
            bucket = _latency_bucket(duration)
            inc("dreamapp_request_latency_bucket", {"le": bucket})
            if status == 429:
                inc("dreamapp_quota_exhausted_total")
        except Exception:
            pass

        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        return response


_LATENCY_BUCKETS_SECONDS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


def _latency_bucket(duration_s: float) -> str:
    for b in _LATENCY_BUCKETS_SECONDS:
        if duration_s <= b:
            return f"{b}"
    return "+Inf"
