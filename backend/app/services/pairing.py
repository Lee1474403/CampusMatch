import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.entities import Match, MatchingRun, Notification, User
from backend.app.schemas.match import PairDetail
from backend.app.services.deep_matching import (
    DeepMatchResult,
    evaluate_deep_compatibility,
    load_deep_match_context,
)
from backend.app.services.email import send_email
from backend.app.services.chat_safety import blocked_pair_keys
from backend.app.services.matching import score_pair
from backend.app.services.questionnaire import completed_questionnaire_user_ids
from backend.app.services.users import is_profile_complete, private_profile_from_user, profile_from_user
from backend.app.services.websocket_manager import manager


CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
ACTIVE_PAIR_STATUSES = ("pending_heartbeat", "chatting", "privacy_unlocked")
CHAT_ENABLED_STATUSES = ("chatting", "privacy_unlocked")
HEARTBEAT_WINDOW = timedelta(days=7)
INACTIVITY_WINDOW = timedelta(days=3)
PRIVACY_UNLOCK_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class MatchCandidate:
    male: User
    female: User
    preliminary_score: float
    final_score: float
    selection_score: float
    shared_interests: list[str]
    repeat_penalty: float = 0.0
    deep_score: float | None = None
    deep_comment: str | None = None
    deep_match_used: bool = False


def _candidate_key(male: User, female: User) -> tuple[int, int]:
    return male.id, female.id


def _history_key(left_user_id: int, right_user_id: int) -> tuple[int, int]:
    return tuple(sorted((left_user_id, right_user_id)))


def _rule_candidates(
    males: list[User],
    females: list[User],
    run_date: date,
    repeat_penalties: dict[tuple[int, int], float] | None = None,
    excluded_pairs: set[tuple[int, int]] | None = None,
) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    penalties = repeat_penalties or {}
    excluded = excluded_pairs or set()
    for male in males:
        for female in females:
            if _history_key(male.id, female.id) in excluded:
                continue
            score = score_pair(male, female, run_date)
            repeat_penalty = penalties.get(_history_key(male.id, female.id), 0.0)
            candidates.append(
                MatchCandidate(
                    male=male,
                    female=female,
                    preliminary_score=score.score,
                    final_score=score.score,
                    selection_score=max(0.0, round(score.score - repeat_penalty, 1)),
                    shared_interests=score.shared_interests,
                    repeat_penalty=repeat_penalty,
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            -item.selection_score,
            min(item.male.id, item.female.id),
            max(item.male.id, item.female.id),
        ),
    )


async def _persist_match_candidate(
    db: AsyncSession,
    candidate: MatchCandidate,
    run_date: date,
    matched_at: datetime,
) -> Match:
    user1, user2 = sorted((candidate.male, candidate.female), key=lambda item: item.id)
    match = Match(
        user1=user1,
        user2=user2,
        scheduled_date=run_date,
        status="pending_heartbeat",
        match_score=candidate.final_score,
        preliminary_score=candidate.preliminary_score,
        deep_score=candidate.deep_score,
        deep_comment=candidate.deep_comment,
        deep_match_used=candidate.deep_match_used,
        shared_interests=candidate.shared_interests,
        matched_at=matched_at,
        expires_at=matched_at + HEARTBEAT_WINDOW,
    )
    db.add(match)
    await db.flush()
    user1.is_matching_enabled = False
    user2.is_matching_enabled = False
    user1.matching_enabled_at = None
    user2.matching_enabled_at = None
    deep_label = "深度匹配" if candidate.deep_match_used else "今日配对"
    db.add_all(
        [
            Notification(
                user_id=user1.id,
                type="daily_pair",
                content=f"{deep_label}已出：{user2.nickname}，快去看看吧",
                related_id=match.id,
            ),
            Notification(
                user_id=user2.id,
                type="daily_pair",
                content=f"{deep_label}已出：{user1.nickname}，快去看看吧",
                related_id=match.id,
            ),
        ]
    )
    return match


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def repeat_match_penalty(reference_time: datetime | None, now: datetime | None = None) -> float:
    reference = ensure_utc(reference_time)
    if reference is None:
        return 0.0
    current = ensure_utc(now) if now is not None else utc_now()
    elapsed_days = max(0.0, (current - reference).total_seconds() / 86400)
    if elapsed_days <= settings.repeat_match_recent_window_days:
        return settings.repeat_match_recent_penalty
    if elapsed_days <= settings.repeat_match_medium_window_days:
        return settings.repeat_match_medium_penalty
    if elapsed_days <= settings.repeat_match_long_window_days:
        return settings.repeat_match_long_penalty
    return 0.0


async def repeat_penalties_for_candidates(
    db: AsyncSession,
    user_ids: set[int],
    now: datetime | None = None,
) -> dict[tuple[int, int], float]:
    if len(user_ids) < 2:
        return {}
    rows = await db.execute(
        select(Match.user1_id, Match.user2_id, Match.matched_at, Match.dissolved_at).where(
            Match.user1_id.in_(user_ids),
            Match.user2_id.in_(user_ids),
        )
    )
    latest_by_pair: dict[tuple[int, int], datetime] = {}
    for user1_id, user2_id, matched_at, dissolved_at in rows:
        reference = ensure_utc(dissolved_at or matched_at)
        if reference is None:
            continue
        key = _history_key(user1_id, user2_id)
        if key not in latest_by_pair or reference > latest_by_pair[key]:
            latest_by_pair[key] = reference
    current = now or utc_now()
    return {
        key: penalty
        for key, reference in latest_by_pair.items()
        if (penalty := repeat_match_penalty(reference, current)) > 0
    }


def next_release_at(now: datetime | None = None) -> datetime:
    current = (now or utc_now()).astimezone(CHINA_TZ)
    release = datetime.combine(current.date(), time(12, 0), tzinfo=CHINA_TZ)
    if current >= release:
        release += timedelta(days=1)
    return release.astimezone(UTC)


async def get_active_pair(db: AsyncSession, user_id: int) -> Match | None:
    return await db.scalar(
        select(Match)
        .where(
            or_(Match.user1_id == user_id, Match.user2_id == user_id),
            Match.status.in_(ACTIVE_PAIR_STATUSES),
        )
        .order_by(Match.matched_at.desc())
        .limit(1)
    )


def partner_for(match: Match, user_id: int) -> User:
    return match.user2 if match.user1_id == user_id else match.user1


def heart_state_for(match: Match, user_id: int) -> tuple[bool, bool]:
    if match.user1_id == user_id:
        return match.user1_hearted, match.user2_hearted
    return match.user2_hearted, match.user1_hearted


def pair_detail_from_match(match: Match, user_id: int, now: datetime | None = None) -> PairDetail:
    current = now or utc_now()
    partner = partner_for(match, user_id)
    my_hearted, partner_hearted = heart_state_for(match, user_id)
    chat_start = ensure_utc(match.chat_start_time)
    elapsed = max(0.0, (current - chat_start).total_seconds()) if chat_start else 0.0
    chat_days = min(7, int(elapsed // 86400))
    unlock_progress = min(100, int(elapsed / PRIVACY_UNLOCK_WINDOW.total_seconds() * 100)) if chat_start else 0
    unlocked = match.status == "privacy_unlocked"
    return PairDetail(
        id=match.id,
        status=match.status,
        partner=profile_from_user(partner),
        scheduled_date=match.scheduled_date,
        matched_at=ensure_utc(match.matched_at),
        match_score=match.match_score,
        preliminary_score=match.preliminary_score,
        deep_score=match.deep_score,
        deep_comment=match.deep_comment,
        deep_match_used=match.deep_match_used,
        shared_interests=match.shared_interests or [],
        my_hearted=my_hearted,
        partner_hearted=partner_hearted,
        chat_enabled=match.status in CHAT_ENABLED_STATUSES,
        chat_start_time=chat_start,
        last_message_time=ensure_utc(match.last_message_time),
        chat_days=chat_days,
        unlock_progress=100 if unlocked else unlock_progress,
        unlock_at=chat_start + PRIVACY_UNLOCK_WINDOW if chat_start else None,
        privacy_unlocked=unlocked,
        private_profile=private_profile_from_user(partner) if unlocked else None,
        heartbeat_expires_at=ensure_utc(match.expires_at) if match.status == "pending_heartbeat" else None,
    )


async def dissolve_pair(db: AsyncSession, match: Match, reason: str, now: datetime | None = None) -> None:
    if match.status == "dissolved":
        return
    current = now or utc_now()
    match.status = "dissolved"
    match.dissolved_at = current
    match.dissolve_reason = reason
    match.user1.is_matching_enabled = False
    match.user2.is_matching_enabled = False
    match.user1.matching_enabled_at = None
    match.user2.matching_enabled_at = None
    db.add_all(
        [
            Notification(user_id=match.user1_id, type="pair_dissolved", content=f"你和 {match.user2.nickname} 的配对已结束，可重新决定是否开启匹配", related_id=match.id),
            Notification(user_id=match.user2_id, type="pair_dissolved", content=f"你和 {match.user1.nickname} 的配对已结束，可重新决定是否开启匹配", related_id=match.id),
        ]
    )


async def refresh_pair_state(db: AsyncSession, match: Match, now: datetime | None = None) -> bool:
    current = now or utc_now()
    if match.status == "pending_heartbeat":
        expires = ensure_utc(match.expires_at)
        if expires and current >= expires:
            await dissolve_pair(db, match, "7天内未完成双向心动", current)
            return True
        return False

    if match.status in CHAT_ENABLED_STATUSES:
        left_last = ensure_utc(match.user1_last_message_time or match.mutual_hearted_at)
        right_last = ensure_utc(match.user2_last_message_time or match.mutual_hearted_at)
        if (left_last and current - left_last >= INACTIVITY_WINDOW) or (
            right_last and current - right_last >= INACTIVITY_WINDOW
        ):
            await dissolve_pair(db, match, "任一方连续3天未发送消息", current)
            return True
        chat_start = ensure_utc(match.chat_start_time)
        if match.status == "chatting" and chat_start and current - chat_start >= PRIVACY_UNLOCK_WINDOW:
            match.status = "privacy_unlocked"
            match.privacy_unlocked_at = current
            db.add_all(
                [
                    Notification(user_id=match.user1_id, type="privacy_unlocked", content=f"你和 {match.user2.nickname} 已连续聊天满7天，隐私信息已解锁", related_id=match.id),
                    Notification(user_id=match.user2_id, type="privacy_unlocked", content=f"你和 {match.user1.nickname} 已连续聊天满7天，隐私信息已解锁", related_id=match.id),
                ]
            )
            return True
    return False


async def maintain_active_pairs(db: AsyncSession, now: datetime | None = None) -> int:
    matches = (
        await db.scalars(select(Match).where(Match.status.in_(ACTIVE_PAIR_STATUSES)))
    ).unique().all()
    changed = 0
    for match in matches:
        if await refresh_pair_state(db, match, now):
            changed += 1
    if changed:
        await db.commit()
    return changed


async def run_daily_matching(
    db: AsyncSession,
    run_date: date | None = None,
    *,
    force: bool = False,
) -> list[Match]:
    china_today = run_date or datetime.now(CHINA_TZ).date()
    existing_run = await db.scalar(select(MatchingRun).where(MatchingRun.run_date == china_today))
    if existing_run and existing_run.completed_at and not force:
        return []
    run = existing_run or MatchingRun(run_date=china_today)
    if not existing_run:
        db.add(run)
        await db.flush()

    await maintain_active_pairs(db)
    active_rows = await db.execute(
        select(Match.user1_id, Match.user2_id).where(Match.status.in_(ACTIVE_PAIR_STATUSES))
    )
    unavailable = {user_id for row in active_rows for user_id in row}
    candidates = (
        await db.scalars(
            select(User).where(User.is_active.is_(True), User.is_matching_enabled.is_(True))
        )
    ).unique().all()
    candidates = [user for user in candidates if user.id not in unavailable and is_profile_complete(user)]
    run.candidates_count = len(candidates)

    created: list[Match] = []
    now = utc_now()
    remaining = {user.id: user for user in candidates}
    repeat_penalties = await repeat_penalties_for_candidates(db, set(remaining), now)
    blocked_pairs = await blocked_pair_keys(db, set(remaining))
    completed_ids = await completed_questionnaire_user_ids(db, set(remaining))
    deep_service_enabled = bool(settings.dashscope_api_key and completed_ids)
    context = await load_deep_match_context(db, completed_ids) if deep_service_enabled else None
    evaluation_cache: dict[tuple[int, int], DeepMatchResult | None] = {}
    calls_used = 0

    while True:
        all_candidates = _rule_candidates(
            [user for user in remaining.values() if user.gender == "male"],
            [user for user in remaining.values() if user.gender == "female"],
            china_today,
            repeat_penalties,
            blocked_pairs,
        )
        if not all_candidates:
            break

        if deep_service_enabled and context:
            top_candidates = [
                candidate for candidate in all_candidates
                if candidate.male.id in completed_ids and candidate.female.id in completed_ids
            ][: settings.deep_match_candidate_pool_size]
            calls_remaining = max(0, settings.deep_match_max_daily_calls - calls_used)
            pending = [
                candidate for candidate in top_candidates
                if _candidate_key(candidate.male, candidate.female) not in evaluation_cache
            ][:calls_remaining]
            if pending:
                results = await asyncio.gather(
                    *[
                        evaluate_deep_compatibility(
                            context,
                            candidate.male.id,
                            candidate.female.id,
                        )
                        for candidate in pending
                    ],
                    return_exceptions=True,
                )
                calls_used += len(pending)
                for candidate, result in zip(pending, results, strict=True):
                    evaluation = result if isinstance(result, DeepMatchResult) else None
                    evaluation_cache[_candidate_key(candidate.male, candidate.female)] = evaluation

        ranked: list[MatchCandidate] = []
        for candidate in all_candidates:
            is_deep_pair = (
                deep_service_enabled
                and candidate.male.id in completed_ids
                and candidate.female.id in completed_ids
            )
            if is_deep_pair:
                key = _candidate_key(candidate.male, candidate.female)
                if key not in evaluation_cache:
                    # The daily Qwen budget is global across all pairing rounds. Once it is
                    # exhausted, remaining complete-questionnaire pairs safely fall back to
                    # their preliminary score instead of being stranded in the matching pool.
                    if calls_used >= settings.deep_match_max_daily_calls:
                        ranked.append(candidate)
                    continue
                evaluation = evaluation_cache[key]
                if evaluation is None:
                    ranked.append(candidate)
                    continue
                final_score = round(
                    settings.deep_match_preliminary_weight * candidate.preliminary_score
                    + settings.deep_match_model_weight * evaluation.deep_score,
                    1,
                )
                ranked.append(
                    MatchCandidate(
                        male=candidate.male,
                        female=candidate.female,
                        preliminary_score=candidate.preliminary_score,
                        final_score=final_score,
                        selection_score=max(0.0, round(final_score - candidate.repeat_penalty, 1)),
                        shared_interests=candidate.shared_interests,
                        repeat_penalty=candidate.repeat_penalty,
                        deep_score=evaluation.deep_score,
                        deep_comment=evaluation.comment,
                        deep_match_used=True,
                    )
                )
            else:
                ranked.append(candidate)

        if not ranked:
            break
        qualified = [
            candidate for candidate in ranked
            if candidate.final_score >= settings.deep_match_min_final_score
        ]
        if not qualified:
            break
        qualified.sort(
            key=lambda item: (
                -item.selection_score,
                min(item.male.id, item.female.id),
                max(item.male.id, item.female.id),
            )
        )
        selected = qualified[0]
        created.append(await _persist_match_candidate(db, selected, china_today, now))
        remaining.pop(selected.male.id, None)
        remaining.pop(selected.female.id, None)

    run.pairs_count = len(created)
    run.completed_at = utc_now()
    await db.commit()

    for match in created:
        await manager.send_to_users(
            {match.user1_id, match.user2_id},
            {"type": "daily_pair", "match_id": match.id, "message": "今日配对已出，请查看"},
        )
    if created:
        await asyncio.gather(
            *[
                send_email(user.email, "CampusMatch：今日配对已出", "今天的一对一配对已经公布，登录 CampusMatch 查看吧。")
                for match in created
                for user in (match.user1, match.user2)
            ],
            return_exceptions=True,
        )
    return created
