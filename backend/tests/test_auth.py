from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import register
from backend.app.core.database import Base
from backend.app.models.entities import User
from backend.app.schemas.auth import RegisterRequest


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
        "grade": "2024级",
        "height_cm": 176,
        "weight_kg": 64.5,
    }
    values.update(updates)
    return RegisterRequest(**values)


@pytest.mark.asyncio
async def test_account_is_globally_unique_and_not_tied_to_a_forced_format() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await register(registration_payload(), db)
        with pytest.raises(HTTPException) as duplicate:
            await register(
                registration_payload(phone="13887654321", email="another@example.com"),
                db,
            )

        assert duplicate.value.status_code == 409
        assert duplicate.value.detail == "该账号已注册"
        assert await db.scalar(select(func.count(User.id))) == 1
        registered = await db.scalar(select(User))
        assert registered.height_cm == 176
        assert registered.weight_kg == 64.5

    await engine.dispose()
