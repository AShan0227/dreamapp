"""SeedDance 1.5 Pro — 字节跳动豆包视频生成API."""

import asyncio
from dataclasses import dataclass

import httpx

from config import settings
from services.video_gen import VideoGenerator, VideoPrompt, VideoResult


@dataclass
class MultiVideoResult:
    task_ids: list[str]
    video_urls: list[str]
    statuses: list[str]
    overall_status: str


class SeedanceGenerator(VideoGenerator):
    """SeedDance 1.5 Pro via Volcano Engine ARK API."""

    def __init__(self):
        self.api_key = settings.seedance_api_key
        self.base_url = settings.seedance_base_url
        self.model = settings.seedance_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _submit_one(self, client: httpx.AsyncClient, prompt: str, **kwargs) -> str:
        """Submit a single t2v task. Returns task_id."""
        full_prompt = f"{prompt}  --duration 5 --camerafixed false --watermark false"
        payload = {
            "model": self.model,
            "content": [{"type": "text", "text": full_prompt}],
        }
        resp = await client.post(
            f"{self.base_url}/contents/generations/tasks",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("id", "")

    async def generate(self, prompt: VideoPrompt) -> VideoResult:
        """Submit a single text-to-video task."""
        async with httpx.AsyncClient(timeout=60) as client:
            task_id = await self._submit_one(client, prompt.prompt)
        return VideoResult(video_url="", duration=prompt.duration, provider="seedance", task_id=task_id, status="processing")

    async def generate_multi(self, prompts: list[str], batch_size: int = 5, **kwargs) -> MultiVideoResult:
        """Submit first batch of shots."""
        first_batch = prompts[:batch_size]
        task_ids = []

        async with httpx.AsyncClient(timeout=60) as client:
            for i, prompt in enumerate(first_batch):
                for attempt in range(3):
                    try:
                        tid = await self._submit_one(client, prompt)
                        task_ids.append(tid)
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < 2:
                            await asyncio.sleep(5 * (attempt + 1))
                            continue
                        task_ids.append(f"error:{e}")
                        break
                    except Exception as e:
                        task_ids.append(f"error:{e}")
                        break
                if i < len(first_batch) - 1:
                    await asyncio.sleep(2)

        pending_count = len(prompts) - len(first_batch)
        all_ids = task_ids + ["pending"] * pending_count

        return MultiVideoResult(
            task_ids=all_ids,
            video_urls=[""] * len(all_ids),
            statuses=["processing"] * len(task_ids) + ["pending"] * pending_count,
            overall_status="processing",
        )

    async def submit_next_batch(self, pending_prompts: list[str], batch_size: int = 5, **kwargs) -> list[str]:
        """Submit next batch."""
        batch = pending_prompts[:batch_size]
        task_ids = []
        async with httpx.AsyncClient(timeout=60) as client:
            for i, prompt in enumerate(batch):
                for attempt in range(3):
                    try:
                        tid = await self._submit_one(client, prompt)
                        task_ids.append(tid)
                        break
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt < 2:
                            await asyncio.sleep(5 * (attempt + 1))
                        else:
                            task_ids.append(f"error:{e}")
                        break
                    except Exception as e:
                        task_ids.append(f"error:{e}")
                        break
                if i < len(batch) - 1:
                    await asyncio.sleep(2)
        return task_ids

    async def check_status(self, task_id: str) -> VideoResult:
        """Poll single task."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/contents/generations/tasks/{task_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "running")
        video_url = ""
        if status == "succeeded":
            content = data.get("content", {})
            if isinstance(content, dict):
                video_url = content.get("video_url", "")

        mapped = {"succeeded": "completed", "failed": "failed", "running": "processing", "pending": "processing"}.get(status, "processing")
        return VideoResult(video_url=video_url, duration=5.0, provider="seedance", task_id=task_id, status=mapped)

    async def check_multi_status(self, task_ids: list[str]) -> MultiVideoResult:
        """Poll all tasks."""
        video_urls = []
        statuses = []

        async with httpx.AsyncClient(timeout=30) as client:
            for tid in task_ids:
                if tid.startswith("error:"):
                    statuses.append("failed")
                    video_urls.append("")
                    continue
                try:
                    resp = await client.get(
                        f"{self.base_url}/contents/generations/tasks/{tid}",
                        headers=self._headers(),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    st = data.get("status", "running")
                    url = ""
                    if st == "succeeded":
                        content = data.get("content", {})
                        if isinstance(content, dict):
                            url = content.get("video_url", "")
                        statuses.append("completed")
                    elif st == "failed":
                        statuses.append("failed")
                    else:
                        statuses.append("processing")
                    video_urls.append(url)
                except Exception:
                    statuses.append("processing")
                    video_urls.append("")

        if all(s == "completed" for s in statuses):
            overall = "completed"
        elif all(s in ("completed", "failed") for s in statuses):
            overall = "partial" if any(s == "completed" for s in statuses) else "failed"
        else:
            overall = "processing"

        return MultiVideoResult(task_ids=task_ids, video_urls=video_urls, statuses=statuses, overall_status=overall)
