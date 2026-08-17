from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_superuser, get_current_user
from backend.app.config import settings
from backend.app.models.entities import Match, Message, Notification, User, WeeklyRecommendation
from backend.app.schemas.match import (
    HeartDecisionRequest,
    HeartDecisionResponse,
    MatchOut,
    MatchingStatus,
    MatchingToggleRequest,
    MatchingToggleResponse,
    WeeklyHeartDecisionResponse,
    WeeklyRecommendationOut,
)
from backend.app.services.pairing import (
    CHAT_ENABLED_STATUSES,
    ensure_utc,
    get_active_pair,
    pair_detail_from_match,
    refresh_pair_state,
    utc_now,
)
from backend.app.services.recommendations import (
    RecommendationSelectionError,
    current_week_recommendations,
    generate_weekly_recommendations,
    invalidate_user_recommendations,
    next_weekly_release_at,
    select_weekly_recommendation,
    weekly_batch_completed,
    weekly_period_end,
    weekly_period_start,
)
from backend.app.services.users import is_profile_complete, missing_profile_fields, private_profile_from_user, profile_from_user
from backend.app.services.websocket_manager import manager


router = APIRouter(tags=["每周推荐"])


def recommendation_out(item: WeeklyRecommendation) -> WeeklyRecommendationOut:
    available = bool(
        item.invalidated_at is None
        and item.dismissed_at is None
        and item.candidate.is_active
        and item.candidate.is_matching_enabled
    )
    return WeeklyRecommendationOut(
        id=item.id,
        rank=item.rank,
        week_start=item.week_start,
        user=profile_from_user(item.candidate),
        preliminary_score=item.preliminary_score,
        deep_score=item.deep_score,
        final_score=item.final_score,
        deep_comment=item.deep_comment,
        deep_match_used=item.deep_match_used,
        shared_interests=item.shared_interests or [],
        selected=item.selected_at is not None,
        dismissed=item.dismissed_at is not None,
        available=available,
    )


@router.get("/matching/status", response_model=MatchingStatus)
async def matching_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MatchingStatus:
    now = utc_now()
    pair = await get_active_pair(db, user.id)
    if pair and await refresh_pair_state(db, pair, now):
        await db.commit()
        if pair.status == "dissolved":
            pair = None

    complete = is_profile_complete(user)
    missing = missing_profile_fields(user)
    recommendations = [] if pair else await current_week_recommendations(db, user.id, now)
    recommendation_models = [recommendation_out(item) for item in recommendations]
    visible_recommendations = [item for item in recommendation_models if item.available]
    selected_recommendation = next(
        (item for item in recommendation_models if item.selected and not item.dismissed),
        None,
    )
    generated = await weekly_batch_completed(db, user.id, now)
    week_start = weekly_period_start(now)
    if not complete:
        message = "请先完善个人资料"
    elif pair and pair.status == "pending_heartbeat":
        message = "旧版配对仍在等待双方心动"
    elif pair and pair.status == "chatting":
        message = "已双向心动，聊天满7天后解锁隐私信息"
    elif pair and pair.status == "privacy_unlocked":
        message = "连续聊天已满7天，双方隐私信息已解锁"
    elif selected_recommendation:
        message = "已选择本周心动对象，等待对方的选择"
    elif visible_recommendations:
        message = f"本周推荐已出，共 {len(visible_recommendations)} 位，请选出唯一心动对象"
    elif generated and user.is_matching_enabled:
        message = "本周暂时没有可推荐的对象，下周会重新计算"
    elif user.is_matching_enabled:
        message = "已加入每周匹配池，推荐将在周六分批生成"
    else:
        message = "资料已完善，可以开启每周匹配"
    return MatchingStatus(
        profile_complete=complete,
        missing_profile_fields=missing,
        matching_enabled=user.is_matching_enabled,
        has_active_pair=pair is not None,
        pair=pair_detail_from_match(pair, user.id, now) if pair else None,
        recommendations_generated=generated,
        recommendation_week_start=week_start if generated or recommendation_models else None,
        recommendation_valid_until=weekly_period_end(week_start) if generated or recommendation_models else None,
        recommendations=visible_recommendations,
        selected_recommendation=selected_recommendation,
        next_release_at=next_weekly_release_at(user.id, now),
        server_time=now,
        message=message,
    )


@router.patch("/matching/settings", response_model=MatchingToggleResponse)
async def update_matching_setting(
    payload: MatchingToggleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchingToggleResponse:
    active_pair = await get_active_pair(db, user.id)
    if payload.enabled:
        missing = missing_profile_fields(user)
        if missing:
            raise HTTPException(status_code=409, detail=f"请先完善个人资料：{'、'.join(missing)}")
        if active_pair:
            raise HTTPException(status_code=409, detail="当前配对尚未结束，不能加入新的匹配")
        user.is_matching_enabled = True
        user.matching_enabled_at = utc_now()
        message = "已开启匹配，将参加下一次周六推荐"
    else:
        user.is_matching_enabled = False
        user.matching_enabled_at = None
        await invalidate_user_recommendations(db, user.id)
        message = "已关闭匹配，本周推荐同时失效"
    await db.commit()
    return MatchingToggleResponse(
        matching_enabled=user.is_matching_enabled,
        message=message,
        next_release_at=next_weekly_release_at(user.id),
    )


@router.post(
    "/matching/recommendations/{recommendation_id}/heart",
    response_model=WeeklyHeartDecisionResponse,
)
async def choose_weekly_heart(
    recommendation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WeeklyHeartDecisionResponse:
    try:
        recommendation, pair, mutual = await select_weekly_recommendation(
            db,
            recommendation_id,
            user,
        )
    except RecommendationSelectionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return WeeklyHeartDecisionResponse(
        recommendation=recommendation_out(recommendation),
        mutual_match=mutual,
        pair=pair_detail_from_match(pair, user.id) if pair else None,
        message="双向心动成功，聊天已开启" if mutual else "心动选择已保存，本周不能更改",
    )


@router.patch("/matching/pairs/{pair_id}/heart", response_model=HeartDecisionResponse)
async def update_heart_decision(
    pair_id: int,
    payload: HeartDecisionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HeartDecisionResponse:
    pair = await db.scalar(
        select(Match).where(
            Match.id == pair_id,
            or_(Match.user1_id == user.id, Match.user2_id == user.id),
        )
    )
    if not pair:
        raise HTTPException(status_code=404, detail="配对不存在")
    await refresh_pair_state(db, pair)
    if pair.status == "dissolved":
        await db.commit()
        raise HTTPException(status_code=410, detail="该配对已经结束")
    if pair.status != "pending_heartbeat":
        raise HTTPException(status_code=409, detail="双向心动已经确认，不能再修改")

    if pair.user1_id == user.id:
        pair.user1_hearted = payload.hearted
    else:
        pair.user2_hearted = payload.hearted

    became_mutual = pair.user1_hearted and pair.user2_hearted
    if became_mutual:
        now = utc_now()
        pair.status = "chatting"
        pair.mutual_hearted_at = now
        pair.last_message_time = now
        pair.user1_last_message_time = now
        pair.user2_last_message_time = now
        pair.expires_at = None
        db.add_all(
            [
                Notification(user_id=pair.user1_id, type="mutual_heart", content=f"你和 {pair.user2.nickname} 已双向心动，聊天已开启", related_id=pair.id),
                Notification(user_id=pair.user2_id, type="mutual_heart", content=f"你和 {pair.user1.nickname} 已双向心动，聊天已开启", related_id=pair.id),
            ]
        )
    await db.commit()
    await manager.send_to_users(
        {pair.user1_id, pair.user2_id},
        {"type": "pair_status", "match_id": pair.id, "status": pair.status},
    )
    return HeartDecisionResponse(
        pair=pair_detail_from_match(pair, user.id),
        message="双向心动成功，聊天已开启" if became_mutual else "心动选择已保存，等待对方回应" if payload.hearted else "已取消心动",
    )


@router.get("/matches", response_model=list[MatchOut])
async def list_matches(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[MatchOut]:
    matches = (
        await db.scalars(
            select(Match)
            .where(
                or_(Match.user1_id == user.id, Match.user2_id == user.id),
                Match.status.in_(CHAT_ENABLED_STATUSES),
            )
            .order_by(Match.matched_at.desc())
        )
    ).unique().all()
    result: list[MatchOut] = []
    changed = False
    now = utc_now()
    for match in matches:
        changed = await refresh_pair_state(db, match, now) or changed
        if match.status == "dissolved":
            continue
        partner = match.user2 if match.user1_id == user.id else match.user1
        unread = await db.scalar(
            select(func.count(Message.id)).where(
                Message.match_id == match.id,
                Message.sender_id != user.id,
                Message.is_read.is_(False),
            )
        )
        last = await db.scalar(
            select(Message).where(Message.match_id == match.id).order_by(Message.sent_at.desc()).limit(1)
        )
        detail = pair_detail_from_match(match, user.id, now)
        result.append(
            MatchOut(
                id=match.id,
                user=profile_from_user(partner),
                status=match.status,
                matched_at=ensure_utc(match.matched_at),
                match_score=match.match_score,
                preliminary_score=match.preliminary_score,
                deep_score=match.deep_score,
                deep_comment=match.deep_comment,
                deep_match_used=match.deep_match_used,
                privacy_unlocked=detail.privacy_unlocked,
                private_profile=private_profile_from_user(partner) if detail.privacy_unlocked else None,
                chat_days=detail.chat_days,
                unlock_progress=detail.unlock_progress,
                unlock_at=detail.unlock_at,
                unread_count=unread or 0,
                last_message=last.content if last else None,
                last_message_at=ensure_utc(last.sent_at) if last else None,
                online=manager.is_online(partner.id),
            )
        )
    if changed:
        await db.commit()
    return result


@router.post("/matching/run-now")
async def run_matching_now(
    batch_index: int | None = Query(default=None, ge=0),
    _: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | str]:
    batches = range(len(settings.weekly_batch_hours)) if batch_index is None else [batch_index]
    created_count = 0
    for current_batch in batches:
        if current_batch >= len(settings.weekly_batch_hours):
            raise HTTPException(status_code=422, detail="批次编号超出配置范围")
        created = await generate_weekly_recommendations(
            db,
            batch_index=current_batch,
            force=True,
        )
        created_count += len(created)
    return {
        "message": "手动每周推荐任务已完成",
        "batches_processed": len(list(batches)),
        "recommendations_created": created_count,
    }


@router.get("/recommendations", response_model=list[WeeklyRecommendationOut])
async def list_weekly_recommendations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WeeklyRecommendationOut]:
    recommendations = await current_week_recommendations(db, user.id)
    return [item for recommendation in recommendations if (item := recommendation_out(recommendation)).available]


@router.post("/swipes", deprecated=True)
async def deprecated_swipes(_: User = Depends(get_current_user)) -> None:
    raise HTTPException(status_code=410, detail="请使用每周推荐卡片中的唯一心动按钮")
