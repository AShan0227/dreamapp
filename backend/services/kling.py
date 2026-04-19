import asyncio
import time
from dataclasses import dataclass

import httpx
import jwt

from config import settings
from services.video_gen import VideoGenerator, VideoPrompt, VideoResult


@dataclass
class MultiVideoResult:
    """Result of multi-shot video generation."""
    task_ids: list[str]
    video_urls: list[str]
    statuses: list[str]
    overall_status: str  # processing | completed | partial | failed


class KlingGenerator(VideoGenerator):
    """Kling (可灵) API video generation with JWT auth."""

    def __init__(self):
        self.access_key = settings.kling_access_key
        self.secret_key = settings.kling_secret_key
        self.base_url = settings.kling_base_url

    def _generate_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.access_key,
            "exp": now + 1800,
            "nbf": now - 5,
            "iat": now,
        }
        return jwt.encode(
            payload, self.secret_key, algorithm="HS256",
            headers={"alg": "HS256", "typ": "JWT"},
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._generate_token()}",
            "Content-Type": "application/json",
        }

    _NEG_PROMPT = "blur, distortion, watermark, text, low quality, morphing faces, extra limbs, floating limbs, sliding feet, smooth plastic skin, cartoonish, 3D render, flickering, camera drift, facial warping"

    async def _submit_t2v(self, client: httpx.AsyncClient, prompt: str, aspect_ratio: str = "16:9") -> str:
        """Submit text-to-video task. Returns task_id."""
        payload = {
            "model_name": "kling-v3",
            "prompt": prompt,
            "negative_prompt": self._NEG_PROMPT,
            "duration": "5",
            "aspect_ratio": aspect_ratio,
            "mode": "std",
        }
        resp = await client.post(
            f"{self.base_url}/v1/videos/text2video",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("task_id", "")

    async def _submit_i2v(self, client: httpx.AsyncClient, prompt: str, image_url: str, aspect_ratio: str = "16:9") -> str:
        """Submit image-to-video task. Returns task_id."""
        payload = {
            "model_name": "kling-v3",
            "image": image_url,
            "prompt": prompt,
            "negative_prompt": self._NEG_PROMPT,
            "duration": "5",
            "aspect_ratio": aspect_ratio,
            "mode": "std",
        }
        resp = await client.post(
            f"{self.base_url}/v1/videos/image2video",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("task_id", "")

    async def _submit_one(self, client: httpx.AsyncClient, prompt: str, aspect_ratio: str = "16:9", ref_image: str = "") -> str:
        """Submit video task (t2v or i2v depending on ref_image)."""
        if ref_image:
            return await self._submit_i2v(client, prompt, ref_image, aspect_ratio)
        return await self._submit_t2v(client, prompt, aspect_ratio)

    async def _get_last_frame_url(self, client: httpx.AsyncClient, task_id: str) -> str:
        """Get the video URL of a completed task, to use as reference for next shot."""
        resp = await client.get(
            f"{self.base_url}/v1/videos/text2video/{task_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        if data.get("task_status") == "succeed":
            videos = data.get("task_result", {}).get("videos", [])
            if videos:
                return videos[0].get("url", "")
        return ""

    async def generate(self, prompt: VideoPrompt) -> VideoResult:
        """Submit a single video generation task."""
        async with httpx.AsyncClient(timeout=60) as client:
            task_id = await self._submit_one(client, prompt.prompt, prompt.aspect_ratio)

        return VideoResult(
            video_url="",
            duration=prompt.duration,
            provider="kling",
            task_id=task_id,
            status="processing",
        )

    # Concurrency cap on Kling submissions. The provider rate-limits ~10/s
    # per merchant; 5 concurrent in-flight submissions is safe and gives a
    # ~5x latency improvement over the old sequential-with-sleep loop.
    _SUBMIT_CONCURRENCY = 5

    async def _submit_with_retry(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        prompt: str,
        aspect_ratio: str,
        ref_image: str = "",
    ) -> str:
        """One shot's submission, retrying on 429. Returns task_id or 'error:...'."""
        async with sem:
            for attempt in range(3):
                try:
                    return await self._submit_one(client, prompt, aspect_ratio, ref_image=ref_image)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and attempt < 2:
                        # Exponential backoff with jitter — not a hard sleep on the loop
                        delay = (10 * (attempt + 1)) * (0.85 + 0.3 * (hash(prompt) % 100) / 100.0)
                        await asyncio.sleep(delay)
                        continue
                    # If i2v fails, fall back to t2v
                    if ref_image:
                        try:
                            return await self._submit_t2v(client, prompt, aspect_ratio)
                        except Exception:
                            pass
                    return f"error:{e}"
                except Exception as e:
                    return f"error:{e}"
            return "error:exhausted_retries"

    async def generate_multi(self, prompts: list[str], aspect_ratio: str = "16:9", batch_size: int = 5) -> MultiVideoResult:
        """Submit first batch of shots IN PARALLEL with bounded concurrency.

        Old sequential path took ~8s minimum just on `sleep(2)` gaps for a
        5-shot batch. Parallel-with-semaphore drops that to ~1-2s while still
        respecting Kling's per-merchant rate limit.
        """
        first_batch = prompts[:batch_size]
        sem = asyncio.Semaphore(self._SUBMIT_CONCURRENCY)

        async with httpx.AsyncClient(timeout=60) as client:
            tasks = [
                self._submit_with_retry(client, sem, p, aspect_ratio)
                for p in first_batch
            ]
            task_ids = list(await asyncio.gather(*tasks))

        pending_count = len(prompts) - len(first_batch)
        all_task_ids = task_ids + ["pending"] * pending_count

        return MultiVideoResult(
            task_ids=all_task_ids,
            video_urls=[""] * len(all_task_ids),
            statuses=["processing"] * len(task_ids) + ["pending"] * pending_count,
            overall_status="processing",
        )

    async def submit_next_batch(
        self, pending_prompts: list[str], aspect_ratio: str = "16:9",
        batch_size: int = 5, last_video_url: str = ""
    ) -> list[str]:
        """Submit next batch in parallel. First shot can chain from last video's
        last frame for visual continuity; remaining shots are independent t2v.
        """
        batch = pending_prompts[:batch_size]
        sem = asyncio.Semaphore(self._SUBMIT_CONCURRENCY)

        async with httpx.AsyncClient(timeout=60) as client:
            tasks = [
                self._submit_with_retry(
                    client, sem, p, aspect_ratio,
                    ref_image=(last_video_url if i == 0 and last_video_url else ""),
                )
                for i, p in enumerate(batch)
            ]
            return list(await asyncio.gather(*tasks))

    async def check_status(self, task_id: str) -> VideoResult:
        """Poll Kling for single task completion."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v1/videos/text2video/{task_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        task_data = data.get("data", {})
        status = task_data.get("task_status", "processing")

        video_url = ""
        if status == "succeed":
            videos = task_data.get("task_result", {}).get("videos", [])
            if videos:
                video_url = videos[0].get("url", "")

        return VideoResult(
            video_url=video_url,
            duration=float(task_data.get("duration", 5)),
            provider="kling",
            task_id=task_id,
            status="completed" if status == "succeed" else ("failed" if status == "failed" else "processing"),
        )

    async def check_multi_status(self, task_ids: list[str]) -> MultiVideoResult:
        """Poll all tasks IN PARALLEL. Returns updated statuses and URLs.

        Old implementation polled task_ids sequentially → N × 200ms RTT.
        Parallelized via gather + small semaphore to avoid spamming Kling.
        """
        sem = asyncio.Semaphore(self._SUBMIT_CONCURRENCY)

        async def _poll_one(client: httpx.AsyncClient, task_id: str) -> tuple[str, str]:
            """Returns (status, video_url). Internal-only."""
            if task_id.startswith("error:") or task_id == "pending":
                return ("failed" if task_id.startswith("error:") else "pending", "")
            async with sem:
                try:
                    resp = await client.get(
                        f"{self.base_url}/v1/videos/text2video/{task_id}",
                        headers=self._headers(),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    task_data = data.get("data", {})
                    status = task_data.get("task_status", "processing")
                    url = ""
                    if status == "succeed":
                        videos = task_data.get("task_result", {}).get("videos", [])
                        if videos:
                            url = videos[0].get("url", "")
                        return ("completed", url)
                    if status == "failed":
                        return ("failed", "")
                    return ("processing", "")
                except Exception:
                    return ("processing", "")

        async with httpx.AsyncClient(timeout=30) as client:
            results = await asyncio.gather(*(_poll_one(client, tid) for tid in task_ids))

        statuses = [r[0] for r in results]
        video_urls = [r[1] for r in results]

        # Determine overall status
        if all(s == "completed" for s in statuses):
            overall = "completed"
        elif all(s in ("completed", "failed") for s in statuses):
            overall = "partial" if any(s == "completed" for s in statuses) else "failed"
        else:
            overall = "processing"

        return MultiVideoResult(
            task_ids=task_ids,
            video_urls=video_urls,
            statuses=statuses,
            overall_status=overall,
        )


def get_video_generator():
    """Factory: return the configured video generator."""
    provider = settings.video_provider
    if provider == "kling":
        return KlingGenerator()
    elif provider == "seedance":
        from services.seedance import SeedanceGenerator
        return SeedanceGenerator()
    raise ValueError(f"Unknown video provider: {provider}")
