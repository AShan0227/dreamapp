"""Unified LLM client with caching, retries, and per-call observability.

Cache semantics:
  - Keyed on (model, system, messages, max_tokens, temperature).
  - Auto-disabled when temperature > CACHE_TEMP_CUTOFF — high-temp calls are
    creative and should NOT serve a stale identical response. Caller can
    still pass `use_cache=False` to force a miss for any call.
  - Bypassed when AI failure (5xx, timeout) — result of a retry is not stored.

Retries:
  - On httpx network errors and 5xx, retry up to RETRY_ATTEMPTS times with
    jittered exponential backoff. 4xx errors are not retried (bug, not blip).

Observability:
  - Counter dreamapp_llm_calls_total{model, status, cached}
  - Counter dreamapp_llm_tokens_total{model, kind=prompt|completion}
  - Latency: each call also records into the same observability counters
    (the existing observability module exposes inc-style counters; callers
    that want histograms should switch to a real client).
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from collections import OrderedDict
from typing import Optional

import httpx

from config import settings


log = logging.getLogger("dreamapp.llm")


# ---- Tuning knobs ---------------------------------------------------------

# Above this temperature, identical inputs should NOT serve cached output.
# 0.2 is a clean cutoff: deterministic JSON parsers/scorers usually run at
# 0.0-0.1; creative writing at 0.7-1.0.
CACHE_TEMP_CUTOFF = 0.2

# Retry policy
RETRY_ATTEMPTS = 2          # total attempts = 1 + RETRY_ATTEMPTS
RETRY_BACKOFF_BASE_MS = 250
RETRY_BACKOFF_MAX_MS = 4000

# Default per-call timeout (seconds). Tunable per call.
DEFAULT_TIMEOUT_S = 60.0


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


# ---- Cache ----------------------------------------------------------------

class _LLMCache:
    """LRU cache. Key includes ALL inputs that influence output, including
    temperature + model. Two callers passing the same messages but different
    temperatures will not collide.
    """

    def __init__(self, maxsize: int = 200):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    @staticmethod
    def _key(
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        content = json.dumps(
            {
                "model": model,
                "m": messages,
                "s": system,
                "t": max_tokens,
                "temp": round(temperature, 3),
            },
            sort_keys=True,
        )
        return hashlib.sha1(content.encode()).hexdigest()

    def get(self, *args, **kwargs) -> Optional[str]:
        key = self._key(*args, **kwargs)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, *args, value: str, **kwargs) -> None:
        key = self._key(*args, **kwargs)
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def stats(self) -> dict:
        return {"size": len(self._cache), "maxsize": self._maxsize}


_cache = _LLMCache()


def llm_cache_stats() -> dict:
    """Exposed for /metrics & admin debugging."""
    return _cache.stats()


# ---- Observability hooks (best-effort, never raise) -----------------------

def _inc(name: str, labels: Optional[dict] = None) -> None:
    try:
        from services.observability import inc
        inc(name, labels)
    except Exception:
        pass


# ---- Public API -----------------------------------------------------------

async def chat_completion(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 1000,
    use_cache: bool = True,
    temperature: float = 0.8,
    timeout_s: Optional[float] = None,
) -> str:
    """Send a chat completion request. Returns the assistant's text response.

    `use_cache` is auto-disabled when temperature > CACHE_TEMP_CUTOFF — see
    module docstring.
    """
    model = settings.llm_model
    timeout = timeout_s if timeout_s is not None else DEFAULT_TIMEOUT_S
    cache_eligible = use_cache and temperature <= CACHE_TEMP_CUTOFF

    if cache_eligible:
        cached = _cache.get(
            model=model,
            messages=messages,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if cached is not None:
            _inc("dreamapp_llm_calls_total", {"model": model, "status": "ok", "cached": "1"})
            return cached

    full_messages: list[dict] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    payload = {
        "model": model,
        "messages": full_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_exc: Optional[Exception] = None
    for attempt in range(RETRY_ATTEMPTS + 1):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            # 4xx is a bug (auth, schema, content-policy) — don't retry, bubble up
            if 400 <= resp.status_code < 500:
                _inc("dreamapp_llm_calls_total", {"model": model, "status": f"http_{resp.status_code}", "cached": "0"})
                log.warning("llm 4xx", extra={"model": model, "status": resp.status_code, "elapsed_ms": elapsed_ms})
                resp.raise_for_status()

            # 5xx → retry
            if resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}",
                    request=resp.request,
                    response=resp,
                )
                _inc("dreamapp_llm_calls_total", {"model": model, "status": f"http_{resp.status_code}", "cached": "0"})
                log.warning("llm 5xx, will retry", extra={"model": model, "status": resp.status_code, "attempt": attempt})
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(_backoff_seconds(attempt))
                    continue
                resp.raise_for_status()

            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            result = _strip_think_tags(raw)

            # Token observability — provider may or may not return this; defensive.
            usage = (data or {}).get("usage") or {}
            if usage:
                _inc("dreamapp_llm_tokens_total", {"model": model, "kind": "prompt"})
                _inc("dreamapp_llm_tokens_total", {"model": model, "kind": "completion"})

            _inc("dreamapp_llm_calls_total", {"model": model, "status": "ok", "cached": "0"})
            log.info(
                "llm ok",
                extra={
                    "model": model,
                    "elapsed_ms": elapsed_ms,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "cached": False,
                },
            )

            if cache_eligible:
                _cache.put(
                    model=model,
                    messages=messages,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    value=result,
                )
            return result

        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            _inc("dreamapp_llm_calls_total", {"model": model, "status": "network", "cached": "0"})
            log.warning("llm network error, will retry", extra={"model": model, "err": str(e), "attempt": attempt})
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(_backoff_seconds(attempt))
                continue
            raise

    # Should be unreachable — loop either returns or raises — but for the type checker
    if last_exc:
        raise last_exc
    raise RuntimeError("llm: exhausted retries without exception (should not happen)")


def _backoff_seconds(attempt: int) -> float:
    base_ms = min(RETRY_BACKOFF_BASE_MS * (2 ** attempt), RETRY_BACKOFF_MAX_MS)
    jitter_ms = random.uniform(0, base_ms * 0.3)
    return (base_ms + jitter_ms) / 1000.0
