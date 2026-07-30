from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.entities import Notification, User
from backend.app.schemas.notification import NotificationOut, NotificationPage


router = APIRouter(prefix="/notifications", tags=["通知"])


def notification_out(item: Notification) -> NotificationOut:
    return NotificationOut(
        id=item.id,
        type=item.type,
        content=item.content,
        related_id=item.related_id,
        is_read=item.is_read,
        created_at=item.created_at,
    )


@router.get("", response_model=NotificationPage)
async def list_notifications(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> NotificationPage:
    items = (
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    ).all()
    unread = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    )
    return NotificationPage(items=[notification_out(item) for item in items], unread_count=unread or 0)


@router.patch("/read-all")
async def mark_all_notifications_read(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    await db.execute(
        update(Notification).where(Notification.user_id == user.id).values(is_read=True)
    )
    await db.commit()
    return {"message": "全部已读"}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    item = await db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="通知不存在")
    item.is_read = True
    await db.commit()
    return {"message": "已读"}
