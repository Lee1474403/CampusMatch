from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.database import get_db
from backend.app.core.rate_limit import client_ip, limit_login, limit_register, limit_resend
from backend.app.core.security import (
    create_token,
    decode_token,
    generate_email_verification_token,
    hash_email_verification_token,
    hash_password,
    hash_token,
    verify_password,
)
from backend.app.models.entities import RefreshToken, User
from backend.app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    RegistrationResponse,
    ResendVerificationRequest,
    VerificationResponse,
    VerifyEmailRequest,
)
from backend.app.services.audit import audit_event, mask_email
from backend.app.services.email import EmailDeliveryError, send_verification_email


router = APIRouter(prefix="/auth", tags=["认证"])


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _request_user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:255] if value else None


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": settings.force_https,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        **common,
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in (settings.access_cookie_name, settings.refresh_cookie_name):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.force_https,
            httponly=True,
            samesite="lax",
        )


def _new_refresh_record(user_id: int, token: str, request: Request) -> RefreshToken:
    return RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
        ip_address=client_ip(request),
        user_agent=_request_user_agent(request),
    )


async def _issue_session(
    db: AsyncSession,
    user: User,
    request: Request,
    response: Response,
) -> None:
    access_token = create_token(user.id, "access")
    refresh_token = create_token(user.id, "refresh")
    db.add(_new_refresh_record(user.id, refresh_token, request))
    _set_auth_cookies(response, access_token, refresh_token)


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegistrationResponse:
    await limit_register(request)
    email = str(payload.email).lower()
    duplicate = await db.scalar(
        select(User).where(
            or_(
                User.account == payload.account,
                User.phone == payload.phone,
                User.email == email,
            )
        )
    )
    if duplicate:
        conflict = "账号" if duplicate.account == payload.account else "手机号" if duplicate.phone == payload.phone else "邮箱"
        audit_event(request, "register", identifier=email, outcome="rejected", detail=f"duplicate_{conflict}")
        raise HTTPException(status_code=409, detail=f"该{conflict}已注册")

    raw_token = generate_email_verification_token()
    expires_at = utc_now() + timedelta(hours=settings.email_verification_expire_hours)
    user = User(
        account=payload.account,
        phone=payload.phone,
        email=email,
        password_hash=hash_password(payload.password),
        gender=payload.gender,
        real_name=payload.real_name,
        nickname=payload.nickname,
        birth_date=payload.birth_date,
        school=payload.school,
        department=payload.department,
        grade=payload.grade,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        is_email_verified=False,
        email_verification_token=hash_email_verification_token(raw_token),
        verification_token_expires_at=expires_at,
    )
    db.add(user)
    await db.flush()
    try:
        await send_verification_email(email, raw_token)
    except EmailDeliveryError as exc:
        await db.rollback()
        audit_event(request, "register", identifier=email, outcome="failed", detail="email_delivery")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.commit()
    audit_event(request, "register", user_id=user.id, identifier=email)
    return RegistrationResponse(message="注册成功，验证邮件已发送，请先验证邮箱", email=mask_email(email))


@router.post("/verify-email", response_model=VerificationResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VerificationResponse:
    token_hash = hash_email_verification_token(payload.token)
    user = await db.scalar(select(User).where(User.email_verification_token == token_hash))
    if not user:
        audit_event(request, "email_verify", outcome="rejected", detail="invalid_token")
        raise HTTPException(status_code=400, detail="验证链接无效")
    if not user.verification_token_expires_at or ensure_utc(user.verification_token_expires_at) <= utc_now():
        user.email_verification_token = None
        user.verification_token_expires_at = None
        await db.commit()
        audit_event(request, "email_verify", user_id=user.id, identifier=user.email, outcome="rejected", detail="expired")
        raise HTTPException(status_code=400, detail="验证链接已过期，请重新发送验证邮件")

    user.is_email_verified = True
    user.email_verification_token = None
    user.verification_token_expires_at = None
    await db.commit()
    audit_event(request, "email_verify", user_id=user.id, identifier=user.email)
    return VerificationResponse(message="邮箱验证成功，现在可以登录了")


@router.post("/resend-verification", response_model=VerificationResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VerificationResponse:
    email = str(payload.email).lower()
    await limit_resend(request, email)
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        audit_event(request, "email_resend", identifier=email, outcome="accepted", detail="unknown_email")
        return VerificationResponse(message="如果该邮箱已注册且尚未验证，系统将发送验证邮件")
    if user.is_email_verified:
        audit_event(request, "email_resend", user_id=user.id, identifier=email, outcome="accepted", detail="already_verified")
        return VerificationResponse(message="该邮箱已经完成验证，可以直接登录")

    now = utc_now()
    if user.email_verification_token and user.verification_token_expires_at:
        expires_at = ensure_utc(user.verification_token_expires_at)
        if expires_at > now:
            retry_after = max(1, int((expires_at - now).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="同一邮箱24小时内只能发送一次验证邮件",
                headers={"Retry-After": str(retry_after)},
            )

    raw_token = generate_email_verification_token()
    user.email_verification_token = hash_email_verification_token(raw_token)
    user.verification_token_expires_at = now + timedelta(hours=settings.email_verification_expire_hours)
    try:
        await send_verification_email(email, raw_token)
    except EmailDeliveryError as exc:
        await db.rollback()
        audit_event(request, "email_resend", user_id=user.id, identifier=email, outcome="failed", detail="email_delivery")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.commit()
    audit_event(request, "email_resend", user_id=user.id, identifier=email)
    return VerificationResponse(message="新的验证邮件已发送，请在24小时内完成验证")


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    identifier = payload.identifier.strip()
    await limit_login(request, identifier)
    user = await db.scalar(
        select(User).where(
            or_(User.account == identifier, User.phone == identifier, User.email == identifier.lower())
        )
    )
    if not user or not verify_password(payload.password, user.password_hash):
        audit_event(request, "login", identifier=identifier, outcome="failed", detail="invalid_credentials")
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    if not user.is_active:
        audit_event(request, "login", user_id=user.id, identifier=identifier, outcome="rejected", detail="inactive")
        raise HTTPException(status_code=403, detail="账号已被停用")
    if not user.is_email_verified:
        audit_event(request, "login", user_id=user.id, identifier=identifier, outcome="rejected", detail="email_unverified")
        raise HTTPException(status_code=403, detail="请先验证邮箱")

    await _issue_session(db, user, request, response)
    await db.commit()
    audit_event(request, "login", user_id=user.id, identifier=identifier)
    return AuthResponse(message="登录成功", expires_in=settings.access_token_expire_minutes * 60)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=401, detail="刷新令牌不存在")
    try:
        payload = decode_token(raw_token, "refresh")
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期") from None

    stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if not stored or stored.revoked_at is not None or ensure_utc(stored.expires_at) <= utc_now():
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="刷新令牌已失效")
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.is_email_verified.is_(True),
        )
    )
    if not user or stored.user_id != user_id:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="用户不存在或已停用")

    now = utc_now()
    stored.last_used_at = now
    stored.revoked_at = now
    await _issue_session(db, user, request, response)
    await db.commit()
    audit_event(request, "token_refresh", user_id=user.id)
    return AuthResponse(message="登录状态已刷新", expires_in=settings.access_token_expire_minutes * 60)


@router.post("/logout", response_model=VerificationResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> VerificationResponse:
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    user_id: int | None = None
    if raw_token:
        stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
        if stored and stored.revoked_at is None:
            stored.revoked_at = utc_now()
            user_id = stored.user_id
            await db.commit()
    _clear_auth_cookies(response)
    audit_event(request, "logout", user_id=user_id)
    return VerificationResponse(message="已退出登录")
