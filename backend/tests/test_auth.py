from datetime import UTC, date, datetime, timedelta
from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import login, logout, refresh, register, resend_verification, verify_email
from backend.app.config import settings
from backend.app.core.database import Base
from backend.app.core.rate_limit import limiter
from backend.app.models.entities import RefreshToken, User
from backend.app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    VerifyEmailRequest,
)


def registration_payload(**updates) -> RegisterRequest:
    values = {
        "account": "nwpu123456",
        "phone": "13812345678",
        "email": "account@example.com",
        "password": "Campus123",
        "gender": "male",
        "nickname": "账号测试",
        "birth_date": date(2005, 1, 1),
        "school": "测试大学",
        "department": None,
        "grade": "大二",
        "height_cm": 176,
        "weight_kg": 64.5,
    }
    values.update(updates)
    return RegisterRequest(**values)


def request_for(path: str, *, cookie: str | None = None, ip: str = "127.0.0.1") -> Request:
    headers = [(b"user-agent", b"CampusMatch pytest")]
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": (ip, 12345),
            "server": ("testserver", 80),
        }
    )


def response_cookie(response: Response, name: str) -> str:
    for header in response.headers.getlist("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        if name in parsed:
            return parsed[name].value
    raise AssertionError(f"cookie {name} was not set")


@pytest.fixture
async def database():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await limiter.clear()
    try:
        async with session_factory() as db:
            yield db
    finally:
        await limiter.clear()
        await engine.dispose()


@pytest.fixture
def sent_tokens(monkeypatch):
    tokens: list[tuple[str, str]] = []

    async def fake_send(recipient: str, token: str) -> None:
        tokens.append((recipient, token))

    monkeypatch.setattr("backend.app.api.auth.send_verification_email", fake_send)
    return tokens


@pytest.mark.asyncio
async def test_registration_is_unique_and_requires_email_verification(database, sent_tokens) -> None:
    result = await register(registration_payload(), request_for("/api/auth/register"), database)

    assert result.email == "a***@example.com"
    assert len(sent_tokens) == 1
    registered = await database.scalar(select(User))
    assert registered.is_email_verified is False
    assert registered.email_verification_token != sent_tokens[0][1]
    assert registered.height_cm == 176
    assert registered.weight_kg == 64.5

    with pytest.raises(HTTPException) as unverified:
        await login(
            LoginRequest(identifier="nwpu123456", password="Campus123"),
            request_for("/api/auth/login"),
            Response(),
            database,
        )
    assert unverified.value.status_code == 403
    assert unverified.value.detail == "请先验证邮箱"

    with pytest.raises(HTTPException) as duplicate:
        await register(
            registration_payload(phone="13887654321", email="another@example.com"),
            request_for("/api/auth/register", ip="127.0.0.2"),
            database,
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail == "该账号已注册"
    assert await database.scalar(select(func.count(User.id))) == 1


@pytest.mark.asyncio
async def test_verify_login_refresh_rotation_and_logout(database, sent_tokens, monkeypatch) -> None:
    await register(registration_payload(), request_for("/api/auth/register"), database)
    raw_verification_token = sent_tokens[0][1]
    verified = await verify_email(
        VerifyEmailRequest(token=raw_verification_token),
        request_for("/api/auth/verify-email"),
        database,
    )
    assert verified.message == "邮箱验证成功，现在可以登录了"

    monkeypatch.setattr(settings, "force_https", True)
    login_response = Response()
    await login(
        LoginRequest(identifier="account@example.com", password="Campus123"),
        request_for("/api/auth/login"),
        login_response,
        database,
    )
    set_cookie_headers = login_response.headers.getlist("set-cookie")
    assert len(set_cookie_headers) == 2
    assert all("HttpOnly" in header and "SameSite=lax" in header and "Secure" in header for header in set_cookie_headers)
    access_cookie = response_cookie(login_response, settings.access_cookie_name)
    refresh_cookie = response_cookie(login_response, settings.refresh_cookie_name)
    assert access_cookie and refresh_cookie
    assert await database.scalar(select(func.count(RefreshToken.id))) == 1

    refresh_response = Response()
    await refresh(
        request_for(
            "/api/auth/refresh",
            cookie=f"{settings.refresh_cookie_name}={refresh_cookie}",
        ),
        refresh_response,
        database,
    )
    rotated_cookie = response_cookie(refresh_response, settings.refresh_cookie_name)
    assert rotated_cookie != refresh_cookie
    records = (await database.scalars(select(RefreshToken).order_by(RefreshToken.id))).all()
    assert len(records) == 2
    assert records[0].revoked_at is not None
    assert records[1].revoked_at is None

    logout_response = Response()
    await logout(
        request_for(
            "/api/auth/logout",
            cookie=f"{settings.refresh_cookie_name}={rotated_cookie}",
        ),
        logout_response,
        database,
    )
    await database.refresh(records[1])
    assert records[1].revoked_at is not None
    assert all("Max-Age=0" in header for header in logout_response.headers.getlist("set-cookie"))


@pytest.mark.asyncio
async def test_expired_link_and_24_hour_resend_cooldown(database, sent_tokens) -> None:
    await register(registration_payload(), request_for("/api/auth/register"), database)
    raw_token = sent_tokens[0][1]

    with pytest.raises(HTTPException) as cooldown:
        await resend_verification(
            ResendVerificationRequest(email="account@example.com"),
            request_for("/api/auth/resend-verification"),
            database,
        )
    assert cooldown.value.status_code == 429
    assert "24小时" in cooldown.value.detail

    user = await database.scalar(select(User))
    user.verification_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await database.commit()
    with pytest.raises(HTTPException) as expired:
        await verify_email(
            VerifyEmailRequest(token=raw_token),
            request_for("/api/auth/verify-email"),
            database,
        )
    assert expired.value.status_code == 400
    assert "已过期" in expired.value.detail


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429(database) -> None:
    for _ in range(5):
        with pytest.raises(HTTPException) as invalid:
            await login(
                LoginRequest(identifier="missing@example.com", password="wrong"),
                request_for("/api/auth/login"),
                Response(),
                database,
            )
        assert invalid.value.status_code == 401

    with pytest.raises(HTTPException) as limited:
        await login(
            LoginRequest(identifier="missing@example.com", password="wrong"),
            request_for("/api/auth/login"),
            Response(),
            database,
        )
    assert limited.value.status_code == 429
    assert limited.value.headers["Retry-After"]
