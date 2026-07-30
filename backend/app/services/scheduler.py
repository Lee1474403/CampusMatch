import asyncio
import logging
from datetime import datetime, time, timedelta, timezone as fixed_timezone

from sqlalchemy import select

from backend.app.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import MatchingRun
from backend.app.services.pairing import maintain_active_pairs, run_daily_matching


logger = logging.getLogger(__name__)
timezone = fixed_timezone(timedelta(hours=8), name=settings.matching_timezone)
_tasks: list[asyncio.Task] = []


async def daily_matching_job() -> None:
    async with AsyncSessionLocal() as db:
        created = await run_daily_matching(db)
        logger.info("每日匹配任务完成，生成 %s 对", len(created))


async def pair_maintenance_job() -> None:
    async with AsyncSessionLocal() as db:
        changed = await maintain_active_pairs(db)
        if changed:
            logger.info("配对状态维护完成，更新 %s 条", changed)


async def run_missed_daily_job_if_needed() -> None:
    now = datetime.now(timezone)
    release = datetime.combine(now.date(), time(settings.matching_release_hour, 0), tzinfo=timezone)
    if now < release:
        return
    async with AsyncSessionLocal() as db:
        completed = await db.scalar(
            select(MatchingRun.id).where(
                MatchingRun.run_date == now.date(), MatchingRun.completed_at.is_not(None)
            )
        )
        if not completed:
            await run_daily_matching(db, now.date())


async def _daily_loop() -> None:
    while True:
        now = datetime.now(timezone)
        release = datetime.combine(now.date(), time(settings.matching_release_hour, 0), tzinfo=timezone)
        if now >= release:
            release += timedelta(days=1)
        await asyncio.sleep(max(1, (release - now).total_seconds()))
        try:
            await daily_matching_job()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("每日匹配任务执行失败")


async def _maintenance_loop() -> None:
    while True:
        await asyncio.sleep(600)
        try:
            await pair_maintenance_job()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("配对状态维护任务执行失败")


def start_scheduler() -> None:
    if _tasks:
        return
    _tasks.extend(
        [
            asyncio.create_task(_daily_loop(), name="campusmatch-daily-pairing"),
            asyncio.create_task(_maintenance_loop(), name="campusmatch-pair-maintenance"),
        ]
    )


async def stop_scheduler() -> None:
    for task in _tasks:
        task.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
