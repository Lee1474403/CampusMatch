import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.entities import (
    Match,
    Notification,
    User,
    WeeklyRecommendation,
    WeeklyRecommendationRun,
)
from backend.app.services.chat_safety import blocked_pair_keys
from backend.app.services.deep_matching import (
    DeepMatchResult,
    evaluate_deep_compatibility,
    load_deep_match_context,
)
from backend.app.services.email import send_email
from backend.app.services.matching import score_pair
from backend.app.services.pairing import (
    ACTIVE_PAIR_STATUSES,
    CHINA_TZ,
    get_active_pair,
    maintain_active_pairs,
    repeat_match_penalty,
    repeat_penalties_for_candidates,
    utc_now,
)
from backend.app.services.questionnaire import completed_questionnaire_user_ids
from backend.app.services.users import is_profile_complete
from backend.app.services.websocket_manager import manager


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecommendationCandidate:
    owner: User
    candidate: User
    preliminary_score: float
    final_score: float
    selection_score: float
    shared_interests: list[str]
    repeat_penalty: float = 0.0
    deep_score: float | None = None
    deep_comment: str | None = None
    deep_match_used: bool = False


class RecommendationSelectionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def pair_key(left_user_id: int, right_user_id: int) -> tuple[int, int]:
    return tuple(sorted((left_user_id, right_user_id)))


def weekly_period_start(value: date | datetime | None = None) -> date:
    if value is None:
        current = datetime.now(CHINA_TZ).date()
    elif isinstance(value, datetime):
        current = value.astimezone(CHINA_TZ).date()
    else:
        current = value
    days_since_release = (current.weekday() - settings.weekly_matching_weekday) % 7
    return current - timedelta(days=days_since_release)


def weekly_period_end(week_start: date) -> datetime:
    return datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=CHINA_TZ)


def recommendation_batch_index(user_id: int) -> int:
    return user_id % len(settings.weekly_batch_hours)


def next_weekly_release_at(user_id: int, now: datetime | None = None) -> datetime:
    current = (now or utc_now()).astimezone(CHINA_TZ)
    batch_index = recommendation_batch_index(user_id)
    release_hour = settings.weekly_batch_hours[batch_index]
    days_until_release = (settings.weekly_matching_weekday - current.weekday()) % 7
    release_date = current.date() + timedelta(days=days_until_release)
    release = datetime.combine(
        release_date,
        time(release_hour, settings.weekly_matching_batch_minute),
        tzinfo=CHINA_TZ,
    )
    if release <= current:
        release += timedelta(days=7)
    return release.astimezone(UTC)


async def current_week_recommendations(
    db: AsyncSession,
    user_id: int,
    now: datetime | None = None,
) -> list[WeeklyRecommendation]:
    week_start = weekly_period_start(now)
    return (
        await db.scalars(
            select(WeeklyRecommendation)
            .where(
                WeeklyRecommendation.owner_user_id == user_id,
                WeeklyRecommendation.week_start == week_start,
            )
            .order_by(WeeklyRecommendation.rank)
        )
    ).unique().all()


async def weekly_batch_completed(
    db: AsyncSession,
    user_id: int,
    now: datetime | None = None,
) -> bool:
    week_start = weekly_period_start(now)
    return bool(
        await db.scalar(
            select(WeeklyRecommendationRun.id).where(
                WeeklyRecommendationRun.week_start == week_start,
                WeeklyRecommendationRun.batch_index == recommendation_batch_index(user_id),
                WeeklyRecommendationRun.status == "completed",
            )
        )
    )


async def invalidate_user_recommendations(
    db: AsyncSession,
    user_id: int,
    now: datetime | None = None,
) -> None:
    current = now or utc_now()
    week_start = weekly_period_start(current)
    await db.execute(
        update(WeeklyRecommendation)
        .where(
            WeeklyRecommendation.week_start == week_start,
            WeeklyRecommendation.invalidated_at.is_(None),
            or_(
                WeeklyRecommendation.owner_user_id == user_id,
                WeeklyRecommendation.candidate_user_id == user_id,
            ),
        )
        .values(invalidated_at=current)
    )
    await db.execute(
        update(WeeklyRecommendation)
        .where(
            WeeklyRecommendation.week_start == week_start,
            WeeklyRecommendation.owner_user_id == user_id,
            WeeklyRecommendation.dismissed_at.is_(None),
        )
        .values(dismissed_at=current)
    )


async def _recommendation_repeat_penalties(
    db: AsyncSession,
    user_ids: set[int],
    now: datetime,
) -> dict[tuple[int, int], float]:
    penalties = await repeat_penalties_for_candidates(db, user_ids, now)
    selected_rows = await db.execute(
        select(
            WeeklyRecommendation.owner_user_id,
            WeeklyRecommendation.candidate_user_id,
            WeeklyRecommendation.selected_at,
        ).where(
            WeeklyRecommendation.owner_user_id.in_(user_ids),
            WeeklyRecommendation.candidate_user_id.in_(user_ids),
            WeeklyRecommendation.selected_at.is_not(None),
        )
    )
    for owner_id, candidate_id, selected_at in selected_rows:
        penalty = repeat_match_penalty(selected_at, now)
        key = pair_key(owner_id, candidate_id)
        penalties[key] = max(penalties.get(key, 0.0), penalty)
    return penalties


def _rule_candidates_for_owner(
    owner: User,
    pool: list[User],
    run_date: date,
    penalties: dict[tuple[int, int], float],
    blocked_pairs: set[tuple[int, int]],
) -> list[RecommendationCandidate]:
    candidates: list[RecommendationCandidate] = []
    for candidate in pool:
        key = pair_key(owner.id, candidate.id)
        if candidate.gender == owner.gender or candidate.id == owner.id or key in blocked_pairs:
            continue
        score = score_pair(owner, candidate, run_date)
        repeat_penalty = penalties.get(key, 0.0)
        candidates.append(
            RecommendationCandidate(
                owner=owner,
                candidate=candidate,
                preliminary_score=score.score,
                final_score=score.score,
                selection_score=max(0.0, round(score.score - repeat_penalty, 1)),
                shared_interests=score.shared_interests,
                repeat_penalty=repeat_penalty,
            )
        )
    return sorted(candidates, key=lambda item: (-item.selection_score, item.candidate.id))


async def _existing_weekly_deep_evaluations(
    db: AsyncSession,
    week_start: date,
) -> dict[tuple[int, int], DeepMatchResult | None]:
    rows = (
        await db.scalars(
            select(WeeklyRecommendation).where(
                WeeklyRecommendation.week_start == week_start,
                WeeklyRecommendation.deep_match_used.is_(True),
                WeeklyRecommendation.deep_score.is_not(None),
            )
        )
    ).all()
    return {
        pair_key(item.owner_user_id, item.candidate_user_id): DeepMatchResult(
            deep_score=item.deep_score,
            comment=item.deep_comment or "",
        )
        for item in rows
    }


async def generate_weekly_recommendations(
    db: AsyncSession,
    run_date: date | None = None,
    *,
    batch_index: int,
    batch_count: int | None = None,
    force: bool = False,
) -> list[WeeklyRecommendation]:
    week_start = weekly_period_start(run_date)
    configured_batch_count = len(settings.weekly_batch_hours)
    total_batches = batch_count or configured_batch_count
    if total_batches < 1 or not 0 <= batch_index < total_batches:
        raise ValueError("匹配批次编号超出范围")

    run = await db.scalar(
        select(WeeklyRecommendationRun).where(
            WeeklyRecommendationRun.week_start == week_start,
            WeeklyRecommendationRun.batch_index == batch_index,
        )
    )
    if run and run.status == "completed" and not force:
        return []
    if not run:
        run = WeeklyRecommendationRun(
            week_start=week_start,
            batch_index=batch_index,
            batch_count=total_batches,
        )
        db.add(run)
    run.status = "running"
    run.batch_count = total_batches
    run.eligible_user_count = 0
    run.recommendation_count = 0
    run.deep_calls_count = 0
    run.started_at = utc_now()
    run.completed_at = None
    run.error_message = None
    await db.commit()

    try:
        await maintain_active_pairs(db)
        active_rows = await db.execute(
            select(Match.user1_id, Match.user2_id).where(Match.status.in_(ACTIVE_PAIR_STATUSES))
        )
        unavailable = {user_id for row in active_rows for user_id in row}
        eligible = (
            await db.scalars(
                select(User).where(User.is_active.is_(True), User.is_matching_enabled.is_(True))
            )
        ).unique().all()
        eligible = [
            user
            for user in eligible
            if user.id not in unavailable and is_profile_complete(user)
        ]
        owners = [user for user in eligible if user.id % total_batches == batch_index]
        run.eligible_user_count = len(owners)

        owner_ids = {owner.id for owner in owners}
        if force and owner_ids:
            await db.execute(
                delete(WeeklyRecommendation).where(
                    WeeklyRecommendation.week_start == week_start,
                    WeeklyRecommendation.owner_user_id.in_(owner_ids),
                    WeeklyRecommendation.selected_at.is_(None),
                )
            )

        all_user_ids = {user.id for user in eligible}
        repeat_penalties = await _recommendation_repeat_penalties(db, all_user_ids, utc_now())
        blocked_pairs = await blocked_pair_keys(db, all_user_ids)
        owner_candidates = {
            owner.id: _rule_candidates_for_owner(
                owner,
                eligible,
                week_start,
                repeat_penalties,
                blocked_pairs,
            )
            for owner in owners
        }

        completed_ids = await completed_questionnaire_user_ids(db, all_user_ids)
        deep_enabled = bool(settings.dashscope_api_key and completed_ids)
        context = await load_deep_match_context(db, completed_ids) if deep_enabled else None
        evaluation_cache = await _existing_weekly_deep_evaluations(db, week_start)
        calls_used_before = await db.scalar(
            select(func.coalesce(func.sum(WeeklyRecommendationRun.deep_calls_count), 0)).where(
                WeeklyRecommendationRun.week_start == week_start,
                WeeklyRecommendationRun.id != run.id,
            )
        )
        calls_remaining = max(0, settings.deep_match_max_weekly_calls - int(calls_used_before or 0))

        requested_pairs: dict[tuple[int, int], RecommendationCandidate] = {}
        if deep_enabled and context and calls_remaining:
            for candidates in owner_candidates.values():
                deep_candidates = [
                    item
                    for item in candidates
                    if item.owner.id in completed_ids and item.candidate.id in completed_ids
                ][: settings.deep_match_candidate_pool_size]
                for item in deep_candidates:
                    key = pair_key(item.owner.id, item.candidate.id)
                    if key not in evaluation_cache:
                        previous = requested_pairs.get(key)
                        if previous is None or item.selection_score > previous.selection_score:
                            requested_pairs[key] = item

            pending = sorted(
                requested_pairs.items(),
                key=lambda item: (-item[1].selection_score, item[0]),
            )[:calls_remaining]
            if pending:
                results = await asyncio.gather(
                    *[
                        evaluate_deep_compatibility(context, key[0], key[1])
                        for key, _candidate in pending
                    ],
                    return_exceptions=True,
                )
                run.deep_calls_count = len(pending)
                for (key, _candidate), result in zip(pending, results, strict=True):
                    evaluation_cache[key] = result if isinstance(result, DeepMatchResult) else None

        created: list[WeeklyRecommendation] = []
        for owner in owners:
            already_selected = await db.scalar(
                select(WeeklyRecommendation.id).where(
                    WeeklyRecommendation.owner_user_id == owner.id,
                    WeeklyRecommendation.week_start == week_start,
                    WeeklyRecommendation.selected_at.is_not(None),
                )
            )
            if already_selected:
                continue
            ranked: list[RecommendationCandidate] = []
            for item in owner_candidates[owner.id]:
                evaluation = evaluation_cache.get(pair_key(item.owner.id, item.candidate.id))
                if evaluation is None:
                    ranked.append(item)
                    continue
                final_score = round(
                    settings.deep_match_preliminary_weight * item.preliminary_score
                    + settings.deep_match_model_weight * evaluation.deep_score,
                    1,
                )
                ranked.append(
                    RecommendationCandidate(
                        owner=item.owner,
                        candidate=item.candidate,
                        preliminary_score=item.preliminary_score,
                        final_score=final_score,
                        selection_score=max(0.0, round(final_score - item.repeat_penalty, 1)),
                        shared_interests=item.shared_interests,
                        repeat_penalty=item.repeat_penalty,
                        deep_score=evaluation.deep_score,
                        deep_comment=evaluation.comment,
                        deep_match_used=True,
                    )
                )
            ranked.sort(key=lambda item: (-item.selection_score, item.candidate.id))
            for rank, item in enumerate(ranked[: settings.weekly_recommendation_count], start=1):
                recommendation = WeeklyRecommendation(
                    owner=item.owner,
                    candidate=item.candidate,
                    week_start=week_start,
                    rank=rank,
                    preliminary_score=item.preliminary_score,
                    deep_score=item.deep_score,
                    final_score=item.final_score,
                    selection_score=item.selection_score,
                    repeat_penalty=item.repeat_penalty,
                    deep_comment=item.deep_comment,
                    deep_match_used=item.deep_match_used,
                    shared_interests=item.shared_interests,
                )
                db.add(recommendation)
                created.append(recommendation)

        await db.flush()
        first_by_owner: dict[int, WeeklyRecommendation] = {}
        for recommendation in created:
            first_by_owner.setdefault(recommendation.owner_user_id, recommendation)
        db.add_all(
            [
                Notification(
                    user_id=owner_id,
                    type="weekly_recommendations",
                    content=f"本周推荐已出：为你找到 {sum(item.owner_user_id == owner_id for item in created)} 位同学",
                    related_id=first.id,
                )
                for owner_id, first in first_by_owner.items()
            ]
        )
        run.recommendation_count = len(created)
        run.status = "completed"
        run.completed_at = utc_now()
        await db.commit()

        for owner_id, first in first_by_owner.items():
            await manager.send_to_user(
                owner_id,
                {
                    "type": "weekly_recommendations",
                    "recommendation_id": first.id,
                    "message": "本周推荐已出，请查看",
                },
            )
        if first_by_owner:
            owner_map = {owner.id: owner for owner in owners}
            await asyncio.gather(
                *[
                    send_email(
                        owner_map[owner_id].email,
                        "CampusMatch：本周推荐已出",
                        "本周的校园心动推荐已经生成，登录 CampusMatch 查看吧。",
                    )
                    for owner_id in first_by_owner
                ],
                return_exceptions=True,
            )
        logger.info(
            "每周推荐批次完成 week=%s batch=%s/%s owners=%s recommendations=%s deep_calls=%s",
            week_start,
            batch_index + 1,
            total_batches,
            len(owners),
            len(created),
            run.deep_calls_count,
        )
        return created
    except Exception as exc:
        await db.rollback()
        failed_run = await db.scalar(
            select(WeeklyRecommendationRun).where(
                WeeklyRecommendationRun.week_start == week_start,
                WeeklyRecommendationRun.batch_index == batch_index,
            )
        )
        if failed_run:
            failed_run.status = "failed"
            failed_run.completed_at = utc_now()
            failed_run.error_message = str(exc)[:500]
            await db.commit()
        logger.exception("每周推荐批次失败 week=%s batch=%s", week_start, batch_index + 1)
        raise


async def select_weekly_recommendation(
    db: AsyncSession,
    recommendation_id: int,
    user: User,
    now: datetime | None = None,
) -> tuple[WeeklyRecommendation, Match | None, bool]:
    current = now or utc_now()
    week_start = weekly_period_start(current)
    recommendation = await db.scalar(
        select(WeeklyRecommendation).where(
            WeeklyRecommendation.id == recommendation_id,
            WeeklyRecommendation.owner_user_id == user.id,
            WeeklyRecommendation.week_start == week_start,
        )
    )
    if not recommendation:
        raise RecommendationSelectionError(404, "本周推荐不存在或已经过期")

    locked_users = (
        await db.scalars(
            select(User)
            .where(User.id.in_([user.id, recommendation.candidate_user_id]))
            .order_by(User.id)
            .with_for_update()
        )
    ).all()
    users_by_id = {item.id: item for item in locked_users}
    owner = users_by_id.get(user.id)
    candidate = users_by_id.get(recommendation.candidate_user_id)
    if not owner or not candidate:
        raise RecommendationSelectionError(404, "推荐对象不存在")

    existing_selection = await db.scalar(
        select(WeeklyRecommendation).where(
            WeeklyRecommendation.owner_user_id == user.id,
            WeeklyRecommendation.week_start == week_start,
            WeeklyRecommendation.selected_at.is_not(None),
        )
    )
    if existing_selection:
        if existing_selection.id == recommendation.id:
            pair = await get_active_pair(db, user.id)
            return existing_selection, pair, False
        raise RecommendationSelectionError(409, "本周已经选择过心动对象，不能更改")
    if recommendation.invalidated_at or recommendation.dismissed_at:
        raise RecommendationSelectionError(410, "该推荐已经失效")
    if await get_active_pair(db, owner.id):
        raise RecommendationSelectionError(409, "你已经进入有效配对，不能再次选择")
    if not candidate.is_active or not candidate.is_matching_enabled or await get_active_pair(db, candidate.id):
        recommendation.invalidated_at = current
        await db.commit()
        raise RecommendationSelectionError(410, "对方当前已不在匹配池，请等待下周推荐")

    recommendation.selected_at = current
    await db.execute(
        update(WeeklyRecommendation)
        .where(
            WeeklyRecommendation.owner_user_id == user.id,
            WeeklyRecommendation.week_start == week_start,
            WeeklyRecommendation.id != recommendation.id,
            WeeklyRecommendation.dismissed_at.is_(None),
        )
        .values(dismissed_at=current)
    )
    await db.flush()

    reverse = await db.scalar(
        select(WeeklyRecommendation).where(
            WeeklyRecommendation.owner_user_id == candidate.id,
            WeeklyRecommendation.candidate_user_id == owner.id,
            WeeklyRecommendation.week_start == week_start,
            WeeklyRecommendation.selected_at.is_not(None),
            WeeklyRecommendation.invalidated_at.is_(None),
        )
    )
    match: Match | None = None
    became_mutual = reverse is not None
    if became_mutual:
        user1, user2 = sorted((owner, candidate), key=lambda item: item.id)
        score_source = recommendation if recommendation.deep_match_used else reverse
        match = Match(
            user1=user1,
            user2=user2,
            scheduled_date=week_start,
            status="chatting",
            user1_hearted=True,
            user2_hearted=True,
            match_score=score_source.final_score,
            preliminary_score=score_source.preliminary_score,
            deep_score=score_source.deep_score,
            deep_comment=score_source.deep_comment,
            deep_match_used=score_source.deep_match_used,
            shared_interests=score_source.shared_interests or [],
            matched_at=current,
            mutual_hearted_at=current,
            last_message_time=current,
            user1_last_message_time=current,
            user2_last_message_time=current,
        )
        db.add(match)
        await db.flush()
        owner.is_matching_enabled = False
        owner.matching_enabled_at = None
        candidate.is_matching_enabled = False
        candidate.matching_enabled_at = None
        await db.execute(
            update(WeeklyRecommendation)
            .where(
                WeeklyRecommendation.week_start == week_start,
                WeeklyRecommendation.invalidated_at.is_(None),
                or_(
                    WeeklyRecommendation.owner_user_id.in_([owner.id, candidate.id]),
                    WeeklyRecommendation.candidate_user_id.in_([owner.id, candidate.id]),
                ),
            )
            .values(invalidated_at=current)
        )
        db.add_all(
            [
                Notification(
                    user_id=owner.id,
                    type="mutual_heart",
                    content=f"你和 {candidate.nickname} 已双向心动，聊天已开启",
                    related_id=match.id,
                ),
                Notification(
                    user_id=candidate.id,
                    type="mutual_heart",
                    content=f"你和 {owner.nickname} 已双向心动，聊天已开启",
                    related_id=match.id,
                ),
            ]
        )

    await db.commit()
    if match:
        await manager.send_to_users(
            {owner.id, candidate.id},
            {"type": "pair_status", "match_id": match.id, "status": match.status},
        )
    return recommendation, match, became_mutual
