from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.questionnaire import get_questionnaire, save_questionnaire_answers
from backend.app.core.database import Base
from backend.app.models.entities import QuestionnaireQuestion, User
from backend.app.schemas.questionnaire import (
    QuestionnaireAnswerInput,
    QuestionnaireSubmitRequest,
)
from backend.app.services.questionnaire import completed_questionnaire_user_ids, questionnaire_status
from backend.app.services.questionnaire_catalog import QUESTIONNAIRE, QUESTIONNAIRE_VERSION


def questionnaire_user() -> User:
    return User(
        id=1,
        account="QUESTIONNAIRE-1",
        phone="13900000001",
        email="questionnaire@example.com",
        password_hash="unused",
        nickname="问卷同学",
        gender="female",
        birth_date=date(2004, 1, 1),
        school="测试大学",
        department="测试专业",
        grade="2023级",
    )


def test_questionnaire_catalog_contains_complete_five_dimension_source() -> None:
    assert QUESTIONNAIRE_VERSION == 2
    assert len(QUESTIONNAIRE) == 26
    assert {question["dimension"] for question in QUESTIONNAIRE} == {
        "性格与处事风格",
        "金钱观与消费习惯",
        "就业与城市选择",
        "家庭与亲情关系",
        "生活方式与价值观",
    }
    assert all(
        [option["key"] for option in question["options"]] == ["A", "B", "C", "D"]
        for question in QUESTIONNAIRE
    )
    q11 = next(question for question in QUESTIONNAIRE if question["code"] == "Q11")
    assert "杭州中型互联网，年薪28万" in q11["options"][2]["text"]


@pytest.mark.asyncio
async def test_questionnaire_partial_save_then_completion() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        current_user = questionnaire_user()
        questions = [
            QuestionnaireQuestion(
                id=1,
                code="Q1",
                dimension="性格与处事风格",
                prompt="问题一",
                options=[{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
                sort_order=1,
            ),
            QuestionnaireQuestion(
                id=2,
                code="Q2",
                dimension="金钱观与消费习惯",
                prompt="问题二",
                options=[{"key": "A", "text": "选项A"}, {"key": "B", "text": "选项B"}],
                sort_order=2,
            ),
        ]
        db.add_all([current_user, *questions])
        await db.commit()

        first = await save_questionnaire_answers(
            QuestionnaireSubmitRequest(
                answers=[QuestionnaireAnswerInput(question_id=1, answer_key="a")]
            ),
            current_user,
            db,
        )
        assert first.completed is False
        assert first.answered_count == 1

        second = await save_questionnaire_answers(
            QuestionnaireSubmitRequest(
                answers=[QuestionnaireAnswerInput(question_id=2, answer_key="B")]
            ),
            current_user,
            db,
        )
        assert second.completed is True
        assert second.message == "问卷已完成，深度匹配已自动启用"
        assert await completed_questionnaire_user_ids(db, {current_user.id}) == {current_user.id}

        payload = await get_questionnaire(current_user, db)
        assert payload.total_questions == 2
        assert payload.answers == {1: "A", 2: "B"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_questionnaire_rejects_invalid_option() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        current_user = questionnaire_user()
        db.add_all(
            [
                current_user,
                QuestionnaireQuestion(
                    id=1,
                    code="Q1",
                    dimension="性格与处事风格",
                    prompt="问题一",
                    options=[{"key": "A", "text": "选项A"}],
                    sort_order=1,
                ),
            ]
        )
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await save_questionnaire_answers(
                QuestionnaireSubmitRequest(
                    answers=[QuestionnaireAnswerInput(question_id=1, answer_key="B")]
                ),
                current_user,
                db,
            )
        assert exc_info.value.status_code == 422
        assert (await questionnaire_status(db, current_user.id)).answered_count == 0

    await engine.dispose()
