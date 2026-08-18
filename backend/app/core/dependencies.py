from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import decode_token
from backend.app.models.entities import User


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.cookies.get(settings.access_cookie_name)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise unauthorized
    try:
        user_id = int(decode_token(token)["sub"])
    except (ValueError, TypeError):
        raise unauthorized from None
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.is_email_verified.is_(True),
        )
    )
    if not user:
        raise unauthorized
    return user


async def get_current_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
