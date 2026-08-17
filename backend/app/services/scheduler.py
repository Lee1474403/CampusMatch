import asyncio
import logging
from datetime import datetime, time, timedelta, timezone as fixed_timezone

from sqlalchemy import select

from backend.app.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import WeeklyRecommendationRun
from backend.app.services.pairing import maintain_active_pairs
from backend.app.services.recommendations import generate_weekly_recommendations, weekly_period_start


logger = logging.getLogger(__name__)
timezone = fixed_timezone(timedelta(hours=8), name=settings.matching_timezone)
_tasks: list[asyncio.Task] = []


async def weekly_matching_batch_job(batch_index: int) -> None:
    async with AsyncSessionLocal() as db:
        created = await generate_weekly_recommendations(db, batch_index=batch_index)
        logger.info(
            "每周推荐批次 %s/%s 完成，生成 %s 条推荐",
            batch_index + 1,
            len(settings.weekly_batch_hours),
            len(created),
        )


async def pair_maintenance_job() -> None:
    async with AsyncSessionLocal() as db:
        changed = await maintain_active_pairs(db)
        if changed:
            logger.info("配对状态维护完成，更新 %s 条", changed)


async def run_missed_weekly_batches_if_needed() -> None:
    now = datetime.now(timezone)
    if now.weekday() != settings.weekly_matching_weekday:
        return
    week_start = weekly_period_start(now)
    for batch_index, hour in enumerate(settings.weekly_batch_hours):
        release = datetime.combine(
            now.date(),
            time(hour, settings.weekly_matching_batch_minute),
            tzinfo=timezone,
        )
        if now < release:
            continue
        async with AsyncSessionLocal() as db:
            completed = await db.scalar(
                select(WeeklyRecommendationRun.id).where(
                    WeeklyRecommendationRun.week_start == week_start,
                    WeeklyRecommendationRun.batch_index == batch_index,
                    WeeklyRecommendationRun.status == "completed",
                )
            )
        if not completed:
            logger.info("检测到周六遗漏批次 %s，开始补执行", batch_index + 1)
            await weekly_matching_batch_job(batch_index)


def _next_batch_release(now: datetime) -> tuple[datetime, int]:
    releases: list[tuple[datetime, int]] = []
    for days_ahead in range(8):
        candidate_date = now.date() + timedelta(days=days_ahead)
        if candidate_date.weekday() != settings.weekly_matching_weekday:
            continue
        for batch_index, hour in enumerate(settings.weekly_batch_hours):
            release = datetime.combine(
                candidate_date,
                time(hour, settings.weekly_matching_batch_minute),
                tzinfo=timezone,
            )
            if release > now:
                releases.append((release, batch_index))
        if releases:
            break
    return min(releases, key=lambda item: item[0])


async def _weekly_loop() -> None:
    while True:
        try:
            await run_missed_weekly_batches_if_needed()
            now = datetime.now(timezone)
            release, batch_index = _next_batch_release(now)
            await asyncio.sleep(max(1, (release - now).total_seconds()))
            await weekly_matching_batch_job(batch_index)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("每周推荐调度执行失败")
            await asyncio.sleep(60)


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
            asyncio.create_task(_weekly_loop(), name="campusmatch-weekly-recommendations"),
            asyncio.create_task(_maintenance_loop(), name="campusmatch-pair-maintenance"),
        ]
    )


async def stop_scheduler() -> None:
    for task in _tasks:
        task.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
