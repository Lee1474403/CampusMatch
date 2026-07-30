from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.security import create_token, decode_token, hash_password, verify_password
from backend.app.models.entities import User
from backend.app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair


router = APIRouter(prefix="/auth", tags=["认证"])


def _token_pair(user_id: int) -> TokenPair:
    return TokenPair(
        access_token=create_token(user_id, "access"),
        refresh_token=create_token(user_id, "refresh"),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    duplicate = await db.scalar(
        select(User).where(
            or_(
                User.account == payload.account,
                User.phone == payload.phone,
                User.email == payload.email.lower(),
            )
        )
    )
    if duplicate:
        conflict = "账号" if duplicate.account == payload.account else "手机号" if duplicate.phone == payload.phone else "邮箱"
        raise HTTPException(status_code=409, detail=f"该{conflict}已注册")
    user = User(
        account=payload.account,
        phone=payload.phone,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        gender=payload.gender,
        real_name=payload.real_name,
        nickname=payload.nickname,
        birth_date=payload.birth_date,
        school=payload.school,
        department=payload.department,
        grade=payload.grade,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_pair(user.id)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    identifier = payload.identifier.strip()
    user = await db.scalar(
        select(User).where(
            or_(User.account == identifier, User.phone == identifier, User.email == identifier.lower())
        )
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被停用")
    return _token_pair(user.id)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    try:
        user_id = int(decode_token(payload.refresh_token, "refresh")["sub"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期") from None
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return _token_pair(user.id)


@router.post("/logout")
async def logout(_: User = Depends(get_current_user)) -> dict[str, str]:
    return {"message": "已退出登录，请在客户端删除令牌"}
