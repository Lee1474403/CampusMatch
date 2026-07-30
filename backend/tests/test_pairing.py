from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.config import settings
from backend.app.models.entities import (
    Interest,
    Match,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    User,
    UserBlock,
)
from backend.app.services import pairing
from backend.app.services.deep_matching import DeepMatchResult
from backend.app.services.matching import PairScore
from backend.app.services.pairing import maintain_active_pairs, run_daily_matching, utc_now


def user(user_id: int, gender: str, interest: Interest) -> User:
    return User(
        id=user_id,
        account=f"T{user_id:04d}",
        phone=f"1390000{user_id:04d}",
        email=f"pair{user_id}@example.com",
        password_hash="unused",
        nickname=f"同学{user_id}",
        gender=gender,
        birth_date=date(2004, 1, user_id),
        school="测试大学",
        department="测试专业",
        grade="2023级",
        location_province="陕西",
        location_city="西安",
        hometown_province="陕西",
        hometown_city="西安",
        avatar_url="/static/test.svg",
        is_matching_enabled=True,
        interests=[interest],
    )


@pytest.mark.asyncio
async def test_daily_matching_creates_reciprocal_unique_pairs() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        music = Interest(id=1, name="音乐", emoji="🎧")
        db.add_all(
            [
                user(1, "male", music),
                user(2, "male", music),
                user(3, "female", music),
                user(4, "female", music),
            ]
        )
        await db.commit()
        created = await run_daily_matching(db, date(2026, 7, 29), force=True)
        assert len(created) == 2
        matches = (await db.scalars(select(Match))).all()
        participant_ids = [identifier for match in matches for identifier in (match.user1_id, match.user2_id)]
        assert len(participant_ids) == len(set(participant_ids)) == 4
        assert all(match.status == "pending_heartbeat" for match in matches)
        assert all(not match.user1.is_matching_enabled and not match.user2.is_matching_enabled for match in matches)

        now = utc_now()
        first = matches[0]
        first.status = "chatting"
        first.mutual_hearted_at = now - timedelta(days=8)
        first.chat_start_time = now - timedelta(days=8)
        first.last_message_time = now
        first.user1_last_message_time = now
        first.user2_last_message_time = now
        await db.commit()
        assert await maintain_active_pairs(db, now) == 1
        assert first.status == "privacy_unlocked"

        first.user1_last_message_time = now - timedelta(days=4)
        await db.commit()
        assert await maintain_active_pairs(db, now) == 1
        assert first.status == "dissolved"
        assert first.dissolve_reason == "任一方连续3天未发送消息"
    await engine.dispose()


@pytest.mark.asyncio
async def test_blocked_users_are_never_matched_again(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(
        pairing,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(100.0, ["华语流行"], ["测试"]),
    )

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        db.add_all([male, female])
        await db.flush()
        db.add(UserBlock(blocker_id=male.id, blocked_id=female.id, reason="疑似诈骗"))
        await db.commit()

        created = await run_daily_matching(db, date(2026, 8, 4), force=True)

        assert created == []
        assert (await db.scalars(select(Match))).all() == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_completed_questionnaires_use_deep_score_before_pairing(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def fake_deep_score(*_args, **_kwargs) -> DeepMatchResult:
        return DeepMatchResult(deep_score=92, comment="你们在生活节奏与家庭责任上较为同频，也愿意通过沟通协调差异。")

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(pairing, "evaluate_deep_compatibility", fake_deep_score)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        question = QuestionnaireQuestion(
            id=1,
            code="Q1",
            dimension="性格与处事风格",
            prompt="测试题目",
            options=[{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
            sort_order=1,
            is_active=True,
        )
        db.add_all([male, female, question])
        await db.flush()
        db.add_all(
            [
                QuestionnaireAnswer(user_id=male.id, question_id=question.id, answer_key="A"),
                QuestionnaireAnswer(user_id=female.id, question_id=question.id, answer_key="A"),
            ]
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 7, 30), force=True)
        assert len(created) == 1
        match = created[0]
        assert match.deep_match_used is True
        assert match.deep_score == 92
        assert match.deep_comment
        assert match.match_score == round(match.preliminary_score * 0.4 + 92 * 0.6, 1)

    await engine.dispose()


@pytest.mark.asyncio
async def test_deep_score_changes_global_pair_selection_and_keeps_pairs_unique(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    preliminary = {(1, 3): 90, (1, 4): 89, (2, 3): 88, (2, 4): 87}
    deep = {(1, 3): 10, (1, 4): 99, (2, 3): 98, (2, 4): 60}
    calls: list[tuple[int, int]] = []

    def fake_rule_score(left: User, right: User, *_args) -> PairScore:
        return PairScore(preliminary[(left.id, right.id)], ["华语流行"], ["测试"])

    async def fake_deep_score(_context, left_id: int, right_id: int) -> DeepMatchResult:
        calls.append((left_id, right_id))
        score = deep[(left_id, right_id)]
        return DeepMatchResult(deep_score=score, comment=f"用户对 {left_id}-{right_id} 的友善适配评语")

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "deep_match_candidate_pool_size", 10)
    monkeypatch.setattr(settings, "deep_match_max_daily_calls", 10)
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(pairing, "score_pair", fake_rule_score)
    monkeypatch.setattr(pairing, "evaluate_deep_compatibility", fake_deep_score)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        users = [
            user(1, "male", music),
            user(2, "male", music),
            user(3, "female", music),
            user(4, "female", music),
        ]
        question = QuestionnaireQuestion(
            id=1,
            code="Q1",
            dimension="性格与处事风格",
            prompt="测试题目",
            options=[{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
            sort_order=1,
            is_active=True,
        )
        db.add_all([*users, question])
        await db.flush()
        db.add_all(
            QuestionnaireAnswer(user_id=item.id, question_id=question.id, answer_key="A")
            for item in users
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 7, 31), force=True)
        assert len(created) == 2
        assert {(match.user1_id, match.user2_id) for match in created} == {(1, 4), (2, 3)}
        assert len(calls) == 4
        assert all(match.deep_match_used for match in created)
        assert {identifier for match in created for identifier in (match.user1_id, match.user2_id)} == {1, 2, 3, 4}

    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_qwen_budget_falls_back_for_remaining_users(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    preliminary = {(1, 3): 95, (1, 4): 94, (2, 3): 93, (2, 4): 92}
    calls: list[tuple[int, int]] = []

    def fake_rule_score(left: User, right: User, *_args) -> PairScore:
        return PairScore(preliminary[(left.id, right.id)], [], ["测试"])

    async def fake_deep_score(_context, left_id: int, right_id: int) -> DeepMatchResult:
        calls.append((left_id, right_id))
        return DeepMatchResult(deep_score=100, comment="这是一段积极友善的测试评语。")

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "deep_match_candidate_pool_size", 10)
    monkeypatch.setattr(settings, "deep_match_max_daily_calls", 2)
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(pairing, "score_pair", fake_rule_score)
    monkeypatch.setattr(pairing, "evaluate_deep_compatibility", fake_deep_score)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        users = [
            user(1, "male", music),
            user(2, "male", music),
            user(3, "female", music),
            user(4, "female", music),
        ]
        question = QuestionnaireQuestion(
            id=1,
            code="Q1",
            dimension="性格与处事风格",
            prompt="测试题目",
            options=[{"key": "A", "text": "选项A"}],
            sort_order=1,
            is_active=True,
        )
        db.add_all([*users, question])
        await db.flush()
        db.add_all(
            QuestionnaireAnswer(user_id=item.id, question_id=question.id, answer_key="A")
            for item in users
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 8, 1), force=True)
        assert len(created) == 2
        assert len(calls) == 2
        assert sum(match.deep_match_used for match in created) == 1
        fallback = next(match for match in created if not match.deep_match_used)
        assert fallback.match_score == fallback.preliminary_score

    await engine.dispose()


@pytest.mark.asyncio
async def test_qwen_failure_falls_back_to_preliminary_score(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def failed_deep_score(*_args, **_kwargs):
        return None

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(pairing, "evaluate_deep_compatibility", failed_deep_score)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        question = QuestionnaireQuestion(
            id=1,
            code="Q1",
            dimension="性格与处事风格",
            prompt="测试题目",
            options=[{"key": "A", "text": "选项A"}],
            sort_order=1,
            is_active=True,
        )
        db.add_all([male, female, question])
        await db.flush()
        db.add_all(
            [
                QuestionnaireAnswer(user_id=male.id, question_id=question.id, answer_key="A"),
                QuestionnaireAnswer(user_id=female.id, question_id=question.id, answer_key="A"),
            ]
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 8, 2), force=True)
        assert len(created) == 1
        assert created[0].deep_match_used is False
        assert created[0].deep_score is None
        assert created[0].match_score == created[0].preliminary_score

    await engine.dispose()


@pytest.mark.asyncio
async def test_final_score_threshold_stops_low_quality_rule_matches(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(
        pairing,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(59.9, [], ["低于阈值"]),
    )

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        db.add_all([user(1, "male", music), user(2, "female", music)])
        await db.commit()

        created = await run_daily_matching(db, date(2026, 8, 3), force=True)
        assert created == []
        assert (await db.scalars(select(Match))).all() == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_recent_previous_pair_is_ranked_below_a_fresh_pair(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    scores = {(1, 2): 90.0, (1, 3): 80.0}

    def fake_rule_score(left: User, right: User, *_args) -> PairScore:
        return PairScore(scores[(left.id, right.id)], [], ["测试"])

    monkeypatch.setattr(pairing, "score_pair", fake_rule_score)
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(settings, "repeat_match_recent_window_days", 30)
    monkeypatch.setattr(settings, "repeat_match_recent_penalty", 30)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        previous_partner = user(2, "female", music)
        fresh_partner = user(3, "female", music)
        db.add_all([male, previous_partner, fresh_partner])
        await db.flush()
        now = utc_now()
        db.add(
            Match(
                user1_id=male.id,
                user2_id=previous_partner.id,
                scheduled_date=date(2026, 7, 20),
                status="dissolved",
                match_score=90,
                preliminary_score=90,
                matched_at=now - timedelta(days=10),
                dissolved_at=now - timedelta(days=1),
                dissolve_reason="测试历史配对",
            )
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 7, 30), force=True)
        assert len(created) == 1
        assert {created[0].user1_id, created[0].user2_id} == {male.id, fresh_partner.id}
        assert created[0].match_score == 80.0

    await engine.dispose()


@pytest.mark.asyncio
async def test_recent_previous_pair_can_match_when_it_is_the_only_quality_option(monkeypatch) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(
        pairing,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(80.0, [], ["测试"]),
    )
    monkeypatch.setattr(settings, "deep_match_min_final_score", 60)
    monkeypatch.setattr(settings, "repeat_match_recent_penalty", 30)

    async with session_factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        db.add_all([male, female])
        await db.flush()
        now = utc_now()
        db.add(
            Match(
                user1_id=male.id,
                user2_id=female.id,
                scheduled_date=date(2026, 7, 20),
                status="dissolved",
                match_score=80,
                preliminary_score=80,
                matched_at=now - timedelta(days=10),
                dissolved_at=now - timedelta(days=1),
                dissolve_reason="测试历史配对",
            )
        )
        await db.commit()

        created = await run_daily_matching(db, date(2026, 7, 30), force=True)
        assert len(created) == 1
        assert created[0].match_score == 80.0

    await engine.dispose()
