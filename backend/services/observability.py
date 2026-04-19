"""Observability — Sentry init + Prometheus metrics.

Both are opt-in via env. With no env set, these are no-ops and add zero
overhead.

Env:
- DREAM_SENTRY_DSN — if set, Sentry SDK is initialized at import time.
- DREAM_SENTRY_TRACES_SAMPLE_RATE (default 0.1) — fraction of requests
  to send transaction traces for.
- (no env needed for /metrics — counters always run, just check the
  endpoint to scrape.)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from threading import Lock
from typing import Any, Optional


# ---------------- Structured logging ---------------------------------------
#
# Centralized logger factory. Use `get_logger("dreamapp.<area>")` instead of
# `print()`. Calls accept `extra={"user_id": ..., "dream_id": ...}` so logs
# can be filtered/searched in production by attribution.
#
# In dev (DREAM_ENV != "production"), output is human-readable.
# In prod, output is JSON-line so a log shipper (Loki, Datadog, etc.) can
# index the structured fields.

_LOG_INITIALIZED = False
_LOG_LOCK = Lock()

# Standard LogRecord attributes — anything else is treated as `extra`.
_RESERVED_LOG_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}


class _JsonFormatter(logging.Formatter):
    """Compact JSON-line formatter for production. Always single-line."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        base: dict[str, Any] = {
            "ts": int(record.created * 1000),
            "lvl": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        # Promote `extra={...}` fields to top-level
        for k, v in record.__dict__.items():
            if k not in _RESERVED_LOG_FIELDS and not k.startswith("_"):
                # Best-effort serialization — never let a bad value crash logging
                try:
                    json.dumps(v, default=str)
                    base[k] = v
                except Exception:
                    base[k] = str(v)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str, ensure_ascii=False)


def _init_logging() -> None:
    global _LOG_INITIALIZED
    with _LOG_LOCK:
        if _LOG_INITIALIZED:
            return
        env = os.getenv("DREAM_ENV", "production").lower()
        is_prod = env in ("production", "prod", "live")
        level_name = os.getenv("DREAM_LOG_LEVEL", "INFO" if is_prod else "DEBUG").upper()
        level = getattr(logging, level_name, logging.INFO)

        root = logging.getLogger("dreamapp")
        root.setLevel(level)
        # Don't double-attach handlers if logging.basicConfig was already called
        if not root.handlers:
            h = logging.StreamHandler(sys.stdout)
            if is_prod:
                h.setFormatter(_JsonFormatter())
            else:
                h.setFormatter(logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s — %(message)s",
                    datefmt="%H:%M:%S",
                ))
            root.addHandler(h)
            root.propagate = False
        _LOG_INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger. Always prefer this over `print()`.

    Naming: dreamapp.<area> — e.g. dreamapp.llm, dreamapp.payments.
    """
    if not _LOG_INITIALIZED:
        _init_logging()
    if not name.startswith("dreamapp"):
        name = f"dreamapp.{name}" if name else "dreamapp"
    return logging.getLogger(name)


# ---------------- Sentry ----------------------------------------------------

def init_sentry() -> bool:
    """Best-effort Sentry init. Returns True if it actually wired up."""
    dsn = os.getenv("DREAM_SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=float(os.getenv("DREAM_SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,  # never auto-send user info
            environment=os.getenv("DREAM_ENV", "production"),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
            ],
        )
        print(f"Sentry initialized (env={os.getenv('DREAM_ENV', 'production')})")
        return True
    except ImportError:
        print("WARNING: DREAM_SENTRY_DSN set but sentry-sdk not installed")
        return False
    except Exception as e:
        print(f"WARNING: Sentry init failed: {e}")
        return False


# ---------------- Lightweight Prometheus-format metrics ---------------------
#
# Built ad-hoc instead of pulling prometheus_client. We have ~10 metrics
# total — a tiny dict + a render function does the job and avoids another
# dependency. If we ever need histograms/quantiles, swap in prometheus_client.

_lock = Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
_help: dict[str, str] = {}
_type: dict[str, str] = {}


def register(name: str, type_: str, help_: str) -> None:
    _help[name] = help_
    _type[name] = type_


def _key(name: str, labels: dict[str, str] | None) -> tuple:
    items = tuple(sorted((labels or {}).items()))
    return (name, items)


def inc(name: str, labels: dict[str, str] | None = None, by: float = 1.0) -> None:
    k = _key(name, labels)
    with _lock:
        _counters[k] = _counters.get(k, 0.0) + by


def gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    k = _key(name, labels)
    with _lock:
        _counters[k] = float(value)


def render() -> str:
    """Render current state in Prometheus exposition format (text/plain)."""
    out: list[str] = []
    by_name: dict[str, list[tuple[tuple, float]]] = {}
    with _lock:
        for k, v in _counters.items():
            by_name.setdefault(k[0], []).append((k[1], v))
    for name in sorted(by_name):
        if name in _help:
            out.append(f"# HELP {name} {_help[name]}")
        if name in _type:
            out.append(f"# TYPE {name} {_type[name]}")
        for label_tuple, val in by_name[name]:
            if label_tuple:
                labels_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                out.append(f"{name}{{{labels_str}}} {val}")
            else:
                out.append(f"{name} {val}")
    return "\n".join(out) + "\n"


# Pre-register metric metadata
register("dreamapp_requests_total", "counter", "HTTP requests handled, by status class")
register("dreamapp_request_duration_seconds_sum", "counter", "Sum of request handling time")
register("dreamapp_request_duration_seconds_count", "counter", "Count of requests timed")
register("dreamapp_video_generations_total", "counter", "Video generation jobs submitted")
register("dreamapp_video_failures_total", "counter", "Video generations that ended in failure")
register("dreamapp_quota_exhausted_total", "counter", "429 responses from the daily quota")
register("dreamapp_knowledge_retrievals_total", "counter", "Times a stage hit pgvector for context")
register("dreamapp_feedback_total", "counter", "User feedback events, by aspect+helpful")
register("dreamapp_uptime_seconds", "gauge", "Process uptime")
register("dreamapp_users_total", "gauge", "Registered users (sampled lazily)")
register("dreamapp_bg_task_total", "counter", "Background tasks attempted, by name")
register("dreamapp_bg_task_failures_total", "counter", "Background tasks that raised, by name")
register("dreamapp_request_body_too_large_total", "counter", "413 responses from request size cap")
register("dreamapp_rate_limited_total", "counter", "Requests rejected by RateLimitMiddleware")
register("dreamapp_request_latency_bucket", "counter", "Request latency bucket (pseudo-histogram)")
register("dreamapp_llm_calls_total", "counter", "LLM calls by model/status/cached")
register("dreamapp_llm_tokens_total", "counter", "LLM tokens billed by model/kind")
register("dreamapp_llm_cache_size", "gauge", "Current LRU cache size")

_BOOT_AT = time.time()


def uptime_seconds() -> float:
    return time.time() - _BOOT_AT


def track_bg_task(name: str):
    """Decorator that wraps an async background task with metrics + Sentry.

    Usage:
        @track_bg_task("entity_extraction")
        async def _bg_extract_entities(...): ...

    Records bg_task_total / bg_task_failures_total with the task name as a
    label, and (if Sentry is configured) reports the exception there.
    """
    def _decorate(fn):
        async def _wrapped(*args, **kwargs):
            inc("dreamapp_bg_task_total", {"name": name})
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                inc("dreamapp_bg_task_failures_total", {"name": name})
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(e)
                except Exception:
                    pass
                import logging
                logging.getLogger("dreamapp.bg").exception(
                    "Background task %s failed: %s", name, e,
                )
                raise
        _wrapped.__name__ = getattr(fn, "__name__", "bg_task")
        return _wrapped
    return _decorate
