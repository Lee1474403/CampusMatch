from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.chat import block_match_partner, send_message_http, unblock_user
from backend.app.core.database import Base
from backend.app.models.entities import Interest, Match, User, UserBlock
from backend.app.schemas.chat import BlockUserRequest, MessageCreate
from backend.app.services.chat_safety import chat_is_blocked


def make_user(user_id: int, gender: str, interest: Interest) -> User:
    item = User(
        id=user_id,
        account=f"B{user_id:04d}",
        phone=f"1370000{user_id:04d}",
        email=f"block{user_id}@example.com",
        password_hash="unused",
        nickname=f"屏蔽测试{user_id}",
        gender=gender,
        birth_date=date(2004, 1, user_id),
        school="测试大学",
        department="测试学院",
        grade="2023级",
        location_province="陕西",
        location_city="西安",
        hometown_province="陕西",
        hometown_city="西安",
        avatar_url="/static/test.svg",
        is_matching_enabled=True,
    )
    item.interests = [interest]
    return item


@pytest.mark.asyncio
async def test_blocking_ends_pair_stops_chat_and_can_be_removed() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        interest = Interest(id=1, name="反诈测试", emoji="🛡️", category="测试", sort_order=1)
        male = make_user(1, "male", interest)
        female = make_user(2, "female", interest)
        match = Match(
            id=1,
            user1=male,
            user2=female,
            scheduled_date=date(2026, 8, 4),
            status="chatting",
            match_score=90,
            preliminary_score=90,
        )
        db.add_all([interest, male, female, match])
        await db.commit()

        response = await block_match_partner(
            match.id,
            BlockUserRequest(reason="疑似诈骗"),
            male,
            db,
        )

        assert response.blocked is True
        assert match.status == "dissolved"
        assert not male.is_matching_enabled and not female.is_matching_enabled
        assert await chat_is_blocked(db, male.id, female.id)
        block = await db.scalar(select(UserBlock))
        assert block and block.reason == "疑似诈骗"

        with pytest.raises(HTTPException) as blocked_send:
            await send_message_http(match.id, MessageCreate(content="你好"), male, db)
        assert blocked_send.value.status_code == 410

        removed = await unblock_user(female.id, male, db)
        assert removed.blocked is False
        assert not await chat_is_blocked(db, male.id, female.id)
        assert match.status == "dissolved"

    await engine.dispose()
