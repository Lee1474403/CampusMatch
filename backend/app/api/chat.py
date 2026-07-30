from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.entities import Match, Message, Notification, User, UserBlock
from backend.app.schemas.chat import (
    BlockedUserOut,
    BlockUserRequest,
    BlockUserResponse,
    MessageCreate,
    MessageOut,
    ReadReceipt,
)
from backend.app.services.chat_safety import chat_is_blocked, sensitive_content_error
from backend.app.services.pairing import (
    CHAT_ENABLED_STATUSES,
    dissolve_pair,
    ensure_utc,
    refresh_pair_state,
    utc_now,
)
from backend.app.services.users import profile_from_user
from backend.app.services.websocket_manager import manager


router = APIRouter(tags=["聊天"])

def validate_message_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="消息不能为空")
    error = sensitive_content_error(normalized)
    if error:
        raise HTTPException(status_code=422, detail=error)
    return normalized


async def require_match_member(match_id: int, user_id: int, db: AsyncSession) -> Match:
    match = await db.scalar(
        select(Match).where(
            Match.id == match_id,
            or_(Match.user1_id == user_id, Match.user2_id == user_id),
        )
    )
    if not match:
        raise HTTPException(status_code=403, detail="仅配对双方可以查看聊天")
    if await refresh_pair_state(db, match):
        await db.commit()
    if match.status == "dissolved":
        raise HTTPException(status_code=410, detail="该配对已结束，聊天已关闭")
    if match.status not in CHAT_ENABLED_STATUSES:
        raise HTTPException(status_code=403, detail="双方都点击心动后才能开始聊天")
    return match


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        match_id=message.match_id,
        sender_id=message.sender_id,
        sender_nickname=message.sender.nickname,
        content=message.content,
        is_read=message.is_read,
        sent_at=ensure_utc(message.sent_at),
    )


@router.get("/matches/{match_id}/messages", response_model=list[MessageOut])
async def list_messages(
    match_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    match = await require_match_member(match_id, user.id, db)
    query = select(Message).where(Message.match_id == match_id)
    if before_id:
        query = query.where(Message.id < before_id)
    descending = (await db.scalars(query.order_by(Message.id.desc()).limit(limit))).unique().all()
    messages = list(reversed(descending))
    if messages:
        read_result = await db.execute(
            update(Message)
            .where(Message.match_id == match_id, Message.sender_id != user.id, Message.is_read.is_(False))
            .values(is_read=True)
        )
        await db.execute(
            update(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.type == "message",
                Notification.related_id == match_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await db.commit()
        for item in messages:
            if item.sender_id != user.id:
                item.is_read = True
        if read_result.rowcount:
            partner_id = match.user2_id if match.user1_id == user.id else match.user1_id
            await manager.send_to_user(partner_id, {"type": "read", "match_id": match_id, "user_id": user.id})
    return [message_out(item) for item in messages]


@router.post("/matches/{match_id}/messages", response_model=MessageOut)
async def send_message_http(
    match_id: int,
    payload: MessageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    match = await require_match_member(match_id, user.id, db)
    recipient_id = match.user2_id if match.user1_id == user.id else match.user1_id
    if await chat_is_blocked(db, user.id, recipient_id):
        raise HTTPException(status_code=403, detail="该会话已被屏蔽，无法继续发送消息")
    now = utc_now()
    message = Message(
        match_id=match.id,
        sender_id=user.id,
        content=validate_message_content(payload.content),
        is_read=manager.is_in_match(recipient_id, match.id),
        sent_at=now,
    )
    db.add(message)
    db.add(
        Notification(
            user_id=recipient_id,
            type="message",
            content=f"{user.nickname} 发来新消息",
            related_id=match.id,
            is_read=message.is_read,
        )
    )
    if not match.chat_start_time:
        match.chat_start_time = now
    match.last_message_time = now
    if match.user1_id == user.id:
        match.user1_last_message_time = now
    else:
        match.user2_last_message_time = now
    await refresh_pair_state(db, match, now)
    await db.commit()
    await db.refresh(message, attribute_names=["sender"])
    output = message_out(message)
    await manager.send_to_users(
        {user.id, recipient_id}, {"type": "message", "data": output.model_dump(mode="json")}
    )
    return output


@router.post("/matches/{match_id}/read", response_model=ReadReceipt)
async def mark_messages_read(
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadReceipt:
    await require_match_member(match_id, user.id, db)
    result = await db.execute(
        update(Message)
        .where(Message.match_id == match_id, Message.sender_id != user.id, Message.is_read.is_(False))
        .values(is_read=True)
    )
    await db.commit()
    if result.rowcount:
        match = await require_match_member(match_id, user.id, db)
        partner_id = match.user2_id if match.user1_id == user.id else match.user1_id
        await manager.send_to_user(partner_id, {"type": "read", "match_id": match_id, "user_id": user.id})
    return ReadReceipt(updated=result.rowcount or 0)


@router.post("/matches/{match_id}/block", response_model=BlockUserResponse)
async def block_match_partner(
    match_id: int,
    payload: BlockUserRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BlockUserResponse:
    match = await db.scalar(
        select(Match).where(
            Match.id == match_id,
            or_(Match.user1_id == user.id, Match.user2_id == user.id),
        )
    )
    if not match:
        raise HTTPException(status_code=403, detail="只能屏蔽自己的配对对象")
    partner_id = match.user2_id if match.user1_id == user.id else match.user1_id
    existing = await db.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == user.id,
            UserBlock.blocked_id == partner_id,
        )
    )
    if existing:
        existing.reason = payload.reason
    else:
        db.add(UserBlock(blocker_id=user.id, blocked_id=partner_id, reason=payload.reason))

    await db.execute(
        update(Message)
        .where(Message.match_id == match.id, Message.sender_id == partner_id, Message.is_read.is_(False))
        .values(is_read=True)
    )
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.type == "message",
            Notification.related_id == match.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    if match.status != "dissolved":
        await dissolve_pair(db, match, "一方已屏蔽配对对象")
    await db.commit()
    await manager.send_to_users(
        {match.user1_id, match.user2_id},
        {"type": "pair_dissolved", "match_id": match.id, "message": "该配对已结束，聊天已关闭"},
    )
    return BlockUserResponse(
        blocked_user_id=partner_id,
        blocked=True,
        message="已屏蔽对方并结束本次配对，之后不会再收到对方消息或再次匹配",
    )


@router.get("/blocks", response_model=list[BlockedUserOut])
async def list_blocked_users(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BlockedUserOut]:
    blocks = (
        await db.scalars(
            select(UserBlock)
            .where(UserBlock.blocker_id == user.id)
            .order_by(UserBlock.created_at.desc())
        )
    ).unique().all()
    return [
        BlockedUserOut(
            id=block.id,
            user=profile_from_user(block.blocked),
            reason=block.reason,
            created_at=ensure_utc(block.created_at),
        )
        for block in blocks
    ]


@router.delete("/blocks/{blocked_user_id}", response_model=BlockUserResponse)
async def unblock_user(
    blocked_user_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BlockUserResponse:
    block = await db.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == user.id,
            UserBlock.blocked_id == blocked_user_id,
        )
    )
    if not block:
        raise HTTPException(status_code=404, detail="该用户不在屏蔽列表中")
    await db.delete(block)
    await db.commit()
    return BlockUserResponse(
        blocked_user_id=blocked_user_id,
        blocked=False,
        message="已解除屏蔽；历史配对不会恢复，但之后可以重新参与匹配",
    )
