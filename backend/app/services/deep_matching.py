import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models.entities import QuestionnaireAnswer, QuestionnaireQuestion


logger = logging.getLogger(__name__)


class DeepMatchResult(BaseModel):
    deep_score: float = Field(ge=0, le=100)
    comment: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class QuestionnaireProfile:
    user_id: int
    answers: dict[int, str]


@dataclass(frozen=True)
class DeepMatchContext:
    questions: list[QuestionnaireQuestion]
    profiles: dict[int, QuestionnaireProfile]


async def load_deep_match_context(
    db: AsyncSession, user_ids: set[int]
) -> DeepMatchContext:
    questions = (
        await db.scalars(
            select(QuestionnaireQuestion)
            .where(QuestionnaireQuestion.is_active.is_(True))
            .order_by(QuestionnaireQuestion.sort_order, QuestionnaireQuestion.id)
        )
    ).all()
    if not questions or not user_ids:
        return DeepMatchContext(questions=list(questions), profiles={})
    answers = (
        await db.scalars(
            select(QuestionnaireAnswer).where(QuestionnaireAnswer.user_id.in_(user_ids))
        )
    ).all()
    answer_map: dict[int, dict[int, str]] = {}
    for answer in answers:
        answer_map.setdefault(answer.user_id, {})[answer.question_id] = answer.answer_key
    required_ids = {question.id for question in questions}
    profiles = {
        user_id: QuestionnaireProfile(user_id=user_id, answers=user_answers)
        for user_id, user_answers in answer_map.items()
        if required_ids.issubset(user_answers)
    }
    return DeepMatchContext(questions=list(questions), profiles=profiles)


def _questionnaire_pair_text(
    context: DeepMatchContext,
    left: QuestionnaireProfile,
    right: QuestionnaireProfile,
) -> str:
    lines: list[str] = []
    for question in context.questions:
        options = {option["key"]: option["text"] for option in question.options}
        left_key = left.answers[question.id]
        right_key = right.answers[question.id]
        option_text = "；".join(f"{key}.{text}" for key, text in options.items())
        lines.extend(
            [
                f"{question.code}｜{question.dimension}｜{question.prompt}",
                f"选项：{option_text}",
                f"用户甲：{left_key}.{options.get(left_key, '')}",
                f"用户乙：{right_key}.{options.get(right_key, '')}",
            ]
        )
    return "\n".join(lines)


async def evaluate_deep_compatibility(
    context: DeepMatchContext,
    left_user_id: int,
    right_user_id: int,
) -> DeepMatchResult | None:
    if not settings.dashscope_api_key:
        return None
    left = context.profiles.get(left_user_id)
    right = context.profiles.get(right_user_id)
    if not left or not right:
        return None

    try:
        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.warning("langchain-openai 尚未安装，深度匹配降级为初步分数")
        return None

    parser = JsonOutputParser(pydantic_object=DeepMatchResult)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是校园恋爱价值观适配分析助手。请根据两位匿名用户的完整问卷，"
                "综合性格与处事风格、金钱观与消费习惯、就业与城市选择、家庭与亲情关系、"
                "生活方式与价值观五个维度，评估长期相处适配度。分数范围0到100。"
                "评语必须积极、友善、具体，不贴人格标签，不做心理诊断，不使用攻击或否定性措辞；"
                "既说明契合点，也温和指出需要沟通的差异，中文不超过200字。"
                "只输出符合要求的JSON，不要Markdown代码块。\n{format_instructions}",
            ),
            (
                "human",
                "以下是同一套问卷、全部选项及两位用户的选择：\n\n{questionnaire}\n\n"
                "请返回 deep_score 和 comment。",
            ),
        ]
    ).partial(format_instructions=parser.get_format_instructions())
    llm = ChatOpenAI(
        model=settings.dashscope_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=0.2,
        timeout=settings.deep_match_timeout_seconds,
        max_retries=1,
    )
    chain = prompt | llm | parser
    try:
        raw = await chain.ainvoke(
            {"questionnaire": _questionnaire_pair_text(context, left, right)}
        )
        result = DeepMatchResult.model_validate(raw)
        return DeepMatchResult(
            deep_score=round(result.deep_score, 1),
            comment=result.comment.strip()[:200],
        )
    except Exception:
        logger.exception("Qwen 深度匹配评分失败，用户对 %s-%s 将降级", left_user_id, right_user_id)
        return None
