from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import QuestionnaireAnswer, QuestionnaireQuestion
from backend.app.schemas.questionnaire import QuestionnaireStatusOut
from backend.app.services.questionnaire_catalog import QUESTIONNAIRE, QUESTIONNAIRE_VERSION


async def seed_questionnaire(db: AsyncSession) -> None:
    existing = {
        question.code: question
        for question in (await db.scalars(select(QuestionnaireQuestion))).all()
    }
    active_codes = {item["code"] for item in QUESTIONNAIRE}
    for values in QUESTIONNAIRE:
        question = existing.get(values["code"])
        if question:
            question.dimension = values["dimension"]
            question.prompt = values["prompt"]
            question.options = values["options"]
            question.sort_order = values["sort_order"]
            question.version = QUESTIONNAIRE_VERSION
            question.is_active = True
        else:
            db.add(
                QuestionnaireQuestion(
                    **values,
                    version=QUESTIONNAIRE_VERSION,
                    is_active=True,
                )
            )
    for code, question in existing.items():
        if code not in active_codes:
            question.is_active = False
    await db.commit()


async def questionnaire_status(db: AsyncSession, user_id: int) -> QuestionnaireStatusOut:
    total = await db.scalar(
        select(func.count(QuestionnaireQuestion.id)).where(QuestionnaireQuestion.is_active.is_(True))
    ) or 0
    answered = await db.scalar(
        select(func.count(QuestionnaireAnswer.question_id))
        .join(QuestionnaireQuestion, QuestionnaireQuestion.id == QuestionnaireAnswer.question_id)
        .where(
            QuestionnaireAnswer.user_id == user_id,
            QuestionnaireQuestion.is_active.is_(True),
        )
    ) or 0
    return QuestionnaireStatusOut(
        answered_count=answered,
        total_questions=total,
        completed=total > 0 and answered == total,
    )


async def completed_questionnaire_user_ids(
    db: AsyncSession, user_ids: set[int] | None = None
) -> set[int]:
    total = await db.scalar(
        select(func.count(QuestionnaireQuestion.id)).where(QuestionnaireQuestion.is_active.is_(True))
    ) or 0
    if not total:
        return set()
    query = (
        select(QuestionnaireAnswer.user_id)
        .join(QuestionnaireQuestion, QuestionnaireQuestion.id == QuestionnaireAnswer.question_id)
        .where(QuestionnaireQuestion.is_active.is_(True))
        .group_by(QuestionnaireAnswer.user_id)
        .having(func.count(QuestionnaireAnswer.question_id) == total)
    )
    if user_ids is not None:
        if not user_ids:
            return set()
        query = query.where(QuestionnaireAnswer.user_id.in_(user_ids))
    return set((await db.scalars(query)).all())
