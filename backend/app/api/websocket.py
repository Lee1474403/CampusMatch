from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select, update

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import decode_token
from backend.app.models.entities import Match, Message, Notification, User
from backend.app.services.chat_safety import chat_is_blocked, sensitive_content_error
from backend.app.services.pairing import CHAT_ENABLED_STATUSES, ensure_utc, refresh_pair_state, utc_now
from backend.app.services.websocket_manager import manager


router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/chat/{match_id}")
async def chat_socket(websocket: WebSocket, match_id: int, token: str) -> None:
    try:
        user_id = int(decode_token(token)["sub"])
    except (ValueError, TypeError):
        await websocket.close(code=4401, reason="令牌无效")
        return

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
        match = await db.scalar(
            select(Match).where(
                Match.id == match_id,
                or_(Match.user1_id == user_id, Match.user2_id == user_id),
            )
        )
        if not user or not match:
            await websocket.close(code=4403, reason="无权进入该聊天")
            return
        if await refresh_pair_state(db, match):
            await db.commit()
        if match.status == "dissolved":
            await websocket.close(code=4410, reason="配对已结束")
            return
        if match.status not in CHAT_ENABLED_STATUSES:
            await websocket.close(code=4403, reason="双方心动后才能聊天")
            return
        partner_id = match.user2_id if match.user1_id == user_id else match.user1_id
        if await chat_is_blocked(db, user_id, partner_id):
            await websocket.close(code=4403, reason="该会话已被屏蔽")
            return
        await manager.connect(user_id, match_id, websocket)
        read_result = await db.execute(
            update(Message)
            .where(Message.match_id == match_id, Message.sender_id != user_id, Message.is_read.is_(False))
            .values(is_read=True)
        )
        await db.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.type == "message",
                Notification.related_id == match_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        await db.commit()
        if read_result.rowcount:
            await manager.send_to_user(partner_id, {"type": "read", "match_id": match_id, "user_id": user_id})
        await manager.send_to_users(
            {user_id, partner_id}, {"type": "presence", "user_id": user_id, "online": True}
        )
        try:
            while True:
                payload = await websocket.receive_json()
                if payload.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                content = str(payload.get("content", "")).strip()
                if not content or len(content) > 1000:
                    await websocket.send_json({"type": "error", "message": "消息需为 1-1000 个字符"})
                    continue
                content_error = sensitive_content_error(content)
                if content_error:
                    await websocket.send_json(
                        {"type": "error", "code": "SENSITIVE_CONTENT", "message": content_error}
                    )
                    continue
                await db.refresh(match)
                if await chat_is_blocked(db, user_id, partner_id):
                    await websocket.send_json(
                        {"type": "error", "code": "CHAT_BLOCKED", "message": "该会话已被屏蔽"}
                    )
                    await websocket.close(code=4410)
                    return
                if await refresh_pair_state(db, match):
                    await db.commit()
                if match.status == "dissolved":
                    await websocket.send_json({"type": "pair_dissolved", "message": "配对已结束，聊天已关闭"})
                    await websocket.close(code=4410)
                    return
                now = utc_now()
                message = Message(
                    match_id=match_id,
                    sender_id=user_id,
                    content=content,
                    is_read=manager.is_in_match(partner_id, match_id),
                    sent_at=now,
                )
                db.add(message)
                db.add(
                    Notification(
                        user_id=partner_id,
                        type="message",
                        content=f"{user.nickname} 发来新消息",
                        related_id=match_id,
                        is_read=message.is_read,
                    )
                )
                if not match.chat_start_time:
                    match.chat_start_time = now
                match.last_message_time = now
                if match.user1_id == user_id:
                    match.user1_last_message_time = now
                else:
                    match.user2_last_message_time = now
                await refresh_pair_state(db, match, now)
                await db.commit()
                await db.refresh(message)
                event = {
                    "type": "message",
                    "data": {
                        "id": message.id,
                        "match_id": message.match_id,
                        "sender_id": message.sender_id,
                        "sender_nickname": user.nickname,
                        "content": message.content,
                        "is_read": message.is_read,
                        "sent_at": ensure_utc(message.sent_at).isoformat(),
                    },
                }
                await manager.send_to_users({user_id, partner_id}, event)
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(user_id, websocket)
            await manager.send_to_user(
                partner_id, {"type": "presence", "user_id": user_id, "online": manager.is_online(user_id)}
            )
