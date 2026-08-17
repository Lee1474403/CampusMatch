from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.config import settings
from backend.app.core.database import Base
from backend.app.models.entities import (
    Interest,
    Match,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    User,
    WeeklyRecommendation,
)
from backend.app.services import recommendations
from backend.app.services.deep_matching import DeepMatchResult
from backend.app.services.matching import PairScore
from backend.app.services.recommendations import (
    RecommendationSelectionError,
    generate_weekly_recommendations,
    invalidate_user_recommendations,
    select_weekly_recommendation,
)


def user(user_id: int, gender: str, interest: Interest) -> User:
    return User(
        id=user_id,
        account=f"W{user_id:04d}",
        phone=f"1370000{user_id:04d}",
        email=f"weekly{user_id}@example.com",
        password_hash="unused",
        nickname=f"周推荐{user_id}",
        gender=gender,
        birth_date=date(2004, 1, min(user_id, 28)),
        school="测试大学",
        department="测试专业",
        grade="大二",
        location_province="陕西",
        location_city="西安",
        hometown_province="陕西",
        hometown_city="西安",
        avatar_url="/static/test.svg",
        is_matching_enabled=True,
        interests=[interest],
    )


async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_weekly_recommendations_are_directional_and_limited_to_three(monkeypatch) -> None:
    engine, factory = await session_factory()
    monkeypatch.setattr(settings, "dashscope_api_key", None)

    def directional_score(left: User, right: User, *_args) -> PairScore:
        preferred = {
            1: [5, 6, 7, 8],
            5: [2, 3, 4, 1],
        }.get(left.id, sorted([item for item in range(1, 9) if item != left.id]))
        return PairScore(100 - preferred.index(right.id) if right.id in preferred else 60, [], ["测试"])

    monkeypatch.setattr(recommendations, "score_pair", directional_score)
    async with factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        users = [
            *[user(identifier, "male", music) for identifier in range(1, 5)],
            *[user(identifier, "female", music) for identifier in range(5, 9)],
        ]
        db.add_all(users)
        await db.commit()

        created = await generate_weekly_recommendations(
            db,
            date(2026, 8, 15),
            batch_index=0,
            batch_count=1,
            force=True,
        )
        assert len(created) == 24
        owner_one = [item for item in created if item.owner_user_id == 1]
        owner_five = [item for item in created if item.owner_user_id == 5]
        assert [item.candidate_user_id for item in owner_one] == [5, 6, 7]
        assert [item.candidate_user_id for item in owner_five] == [2, 3, 4]
        assert 1 not in [item.candidate_user_id for item in owner_five]
        assert all(len([item for item in created if item.owner_user_id == owner.id]) == 3 for owner in users)

    await engine.dispose()


@pytest.mark.asyncio
async def test_only_one_heart_is_allowed_and_mutual_choice_opens_chat(monkeypatch) -> None:
    engine, factory = await session_factory()
    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(
        recommendations,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(88.0, ["华语流行"], ["测试"]),
    )

    async with factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        chosen = user(2, "female", music)
        other = user(3, "female", music)
        db.add_all([male, chosen, other])
        await db.commit()
        await generate_weekly_recommendations(
            db,
            date(2026, 8, 15),
            batch_index=0,
            batch_count=1,
            force=True,
        )
        male_recommendations = (
            await db.scalars(
                select(WeeklyRecommendation)
                .where(WeeklyRecommendation.owner_user_id == male.id)
                .order_by(WeeklyRecommendation.rank)
            )
        ).all()
        chosen_recommendation = next(
            item for item in male_recommendations if item.candidate_user_id == chosen.id
        )
        other_recommendation = next(
            item for item in male_recommendations if item.candidate_user_id == other.id
        )

        selected, match, mutual = await select_weekly_recommendation(db, chosen_recommendation.id, male)
        assert selected.selected_at is not None
        assert match is None
        assert mutual is False
        assert other_recommendation.dismissed_at is not None

        with pytest.raises(RecommendationSelectionError) as duplicate:
            await select_weekly_recommendation(db, other_recommendation.id, male)
        assert duplicate.value.status_code == 409

        reverse = await db.scalar(
            select(WeeklyRecommendation).where(
                WeeklyRecommendation.owner_user_id == chosen.id,
                WeeklyRecommendation.candidate_user_id == male.id,
            )
        )
        _, match, mutual = await select_weekly_recommendation(db, reverse.id, chosen)
        assert mutual is True
        assert match is not None
        assert match.status == "chatting"
        assert match.user1_hearted and match.user2_hearted
        assert male.is_matching_enabled is False
        assert chosen.is_matching_enabled is False
        assert len((await db.scalars(select(Match))).all()) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_disabling_matching_withdraws_own_choice_without_hiding_it_from_history(monkeypatch) -> None:
    engine, factory = await session_factory()
    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(
        recommendations,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(82.0, [], ["测试"]),
    )

    async with factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        db.add_all([male, female])
        await db.commit()
        await generate_weekly_recommendations(
            db,
            date(2026, 8, 15),
            batch_index=0,
            batch_count=1,
            force=True,
        )
        own = await db.scalar(
            select(WeeklyRecommendation).where(WeeklyRecommendation.owner_user_id == male.id)
        )
        reverse = await db.scalar(
            select(WeeklyRecommendation).where(WeeklyRecommendation.owner_user_id == female.id)
        )
        await select_weekly_recommendation(db, own.id, male)

        await invalidate_user_recommendations(db, male.id)
        await db.commit()
        await db.refresh(own)
        await db.refresh(reverse)

        assert own.selected_at is not None
        assert own.invalidated_at is not None
        assert own.dismissed_at is not None
        assert reverse.invalidated_at is not None
        assert reverse.dismissed_at is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_weekly_batch_only_generates_for_assigned_owner_ids(monkeypatch) -> None:
    engine, factory = await session_factory()
    monkeypatch.setattr(settings, "dashscope_api_key", None)
    monkeypatch.setattr(
        recommendations,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(80.0, [], ["测试"]),
    )

    async with factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        users = [user(identifier, "male" if identifier % 2 else "female", music) for identifier in range(1, 10)]
        db.add_all(users)
        await db.commit()
        created = await generate_weekly_recommendations(
            db,
            date(2026, 8, 15),
            batch_index=1,
            batch_count=3,
            force=True,
        )
        assert created
        assert {item.owner_user_id % 3 for item in created} == {1}
        assert {item.owner_user_id for item in created} == {1, 4, 7}

    await engine.dispose()


@pytest.mark.asyncio
async def test_deep_score_is_weighted_before_weekly_ranking(monkeypatch) -> None:
    engine, factory = await session_factory()

    async def fake_deep_score(*_args, **_kwargs) -> DeepMatchResult:
        return DeepMatchResult(deep_score=90.0, comment="你们在性格、生活方式与未来规划上具有互补空间。")

    monkeypatch.setattr(settings, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings, "deep_match_max_weekly_calls", 10)
    monkeypatch.setattr(
        recommendations,
        "score_pair",
        lambda *_args, **_kwargs: PairScore(50.0, ["华语流行"], ["测试"]),
    )
    monkeypatch.setattr(recommendations, "evaluate_deep_compatibility", fake_deep_score)

    async with factory() as db:
        music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐", sort_order=1)
        male = user(1, "male", music)
        female = user(2, "female", music)
        question = QuestionnaireQuestion(
            id=1,
            code="Q1",
            dimension="性格",
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

        created = await generate_weekly_recommendations(
            db,
            date(2026, 8, 15),
            batch_index=0,
            batch_count=1,
            force=True,
        )
        assert len(created) == 2
        assert all(item.deep_match_used for item in created)
        assert all(item.final_score == 74.0 for item in created)
        assert all(item.deep_comment for item in created)

    await engine.dispose()
