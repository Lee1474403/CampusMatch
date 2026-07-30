from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.entities import QuestionnaireAnswer, QuestionnaireQuestion, User
from backend.app.schemas.questionnaire import (
    QuestionnaireOut,
    QuestionnaireQuestionOut,
    QuestionnaireStatusOut,
    QuestionnaireSubmitRequest,
    QuestionnaireSubmitResponse,
)
from backend.app.services.questionnaire import questionnaire_status


router = APIRouter(prefix="/questionnaire", tags=["深度匹配问卷"])


@router.get("", response_model=QuestionnaireOut)
async def get_questionnaire(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> QuestionnaireOut:
    questions = (
        await db.scalars(
            select(QuestionnaireQuestion)
            .where(QuestionnaireQuestion.is_active.is_(True))
            .order_by(QuestionnaireQuestion.sort_order, QuestionnaireQuestion.id)
        )
    ).all()
    answers = (
        await db.scalars(select(QuestionnaireAnswer).where(QuestionnaireAnswer.user_id == user.id))
    ).all()
    status = await questionnaire_status(db, user.id)
    return QuestionnaireOut(
        **status.model_dump(),
        questions=[
            QuestionnaireQuestionOut(
                id=question.id,
                code=question.code,
                dimension=question.dimension,
                prompt=question.prompt,
                options=question.options,
                sort_order=question.sort_order,
            )
            for question in questions
        ],
        answers={answer.question_id: answer.answer_key for answer in answers},
    )


@router.get("/status", response_model=QuestionnaireStatusOut)
async def get_questionnaire_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> QuestionnaireStatusOut:
    return await questionnaire_status(db, user.id)


@router.put("/answers", response_model=QuestionnaireSubmitResponse)
async def save_questionnaire_answers(
    payload: QuestionnaireSubmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuestionnaireSubmitResponse:
    submitted = {answer.question_id: answer.answer_key for answer in payload.answers}
    if len(submitted) != len(payload.answers):
        raise HTTPException(status_code=422, detail="同一道题不能重复提交")
    if submitted:
        questions = (
            await db.scalars(
                select(QuestionnaireQuestion).where(
                    QuestionnaireQuestion.id.in_(submitted),
                    QuestionnaireQuestion.is_active.is_(True),
                )
            )
        ).all()
        question_map = {question.id: question for question in questions}
        if len(question_map) != len(submitted):
            raise HTTPException(status_code=422, detail="包含不存在或已停用的问卷题目")
        for question_id, answer_key in submitted.items():
            valid_keys = {option["key"] for option in question_map[question_id].options}
            if answer_key not in valid_keys:
                raise HTTPException(
                    status_code=422,
                    detail=f"{question_map[question_id].code} 的选项无效",
                )

        current_answers = {
            answer.question_id: answer
            for answer in (
                await db.scalars(
                    select(QuestionnaireAnswer).where(
                        QuestionnaireAnswer.user_id == user.id,
                        QuestionnaireAnswer.question_id.in_(submitted),
                    )
                )
            ).all()
        }
        for question_id, answer_key in submitted.items():
            current = current_answers.get(question_id)
            if current:
                current.answer_key = answer_key
            else:
                db.add(
                    QuestionnaireAnswer(
                        user_id=user.id,
                        question_id=question_id,
                        answer_key=answer_key,
                    )
                )
        await db.commit()

    status = await questionnaire_status(db, user.id)
    return QuestionnaireSubmitResponse(
        **status.model_dump(),
        message="问卷已完成，深度匹配已自动启用" if status.completed else "问卷进度已保存",
    )
