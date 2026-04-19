"""Lightweight async scheduler — runs Sleep Cycle on a fixed interval.

Replaces apscheduler for a single recurring task. Spawned from FastAPI
lifespan, cancelled on shutdown. No extra dependency.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker

log = logging.getLogger("dreamapp.scheduler")

# Cadence: weekly by default. Overridable via env through config if needed.
SLEEP_CYCLE_INTERVAL_HOURS = 24 * 7
# First run delay (avoid blocking startup). ~15min after boot.
FIRST_RUN_DELAY_SECONDS = 15 * 60


class SleepCycleScheduler:
    """Single-shot-at-a-time background loop for knowledge distillation."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        interval_hours: float = SLEEP_CYCLE_INTERVAL_HOURS,
        first_delay_seconds: float = FIRST_RUN_DELAY_SECONDS,
    ):
        self.session_factory = session_factory
        self.interval_hours = interval_hours
        self.first_delay_seconds = first_delay_seconds
        self._task: Optional[asyncio.Task] = None
        self._last_run: Optional[datetime] = None
        self._last_result: Optional[dict] = None
        self._run_count = 0

    async def _loop(self):
        try:
            await asyncio.sleep(self.first_delay_seconds)
            while True:
                await self._run_once()
                await asyncio.sleep(self.interval_hours * 3600)
        except asyncio.CancelledError:
            log.info("SleepCycleScheduler stopped")
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("SleepCycleScheduler crashed: %s", e)

    async def _run_once(self):
        from services.sleep_cycle_knowledge import run_sleep_cycle
        try:
            async with self.session_factory() as db:
                result = await run_sleep_cycle(db)
                self._last_run = datetime.utcnow()
                self._last_result = result
                self._run_count += 1
                log.info(
                    "Sleep cycle #%d: decayed=%s, promoted=%s, merged=%s, pruned=%s",
                    self._run_count,
                    result.get("decayed"),
                    result.get("promoted_l2_to_l1"),
                    result.get("merged_duplicates"),
                    result.get("pruned_quarantined"),
                )
        except Exception as e:  # noqa: BLE001
            log.exception("Sleep cycle run failed: %s", e)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            log.info(
                "SleepCycleScheduler started: first run in %ss, then every %sh",
                self.first_delay_seconds,
                self.interval_hours,
            )

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def status(self) -> dict:
        next_run_at = None
        if self._last_run:
            next_run_at = (
                self._last_run + timedelta(hours=self.interval_hours)
            ).isoformat()
        return {
            "running": bool(self._task and not self._task.done()),
            "run_count": self._run_count,
            "last_run_at": self._last_run.isoformat() if self._last_run else None,
            "last_result": self._last_result,
            "interval_hours": self.interval_hours,
            "next_run_at": next_run_at,
        }


# Global singleton, initialized in main.py lifespan
scheduler: Optional[SleepCycleScheduler] = None
