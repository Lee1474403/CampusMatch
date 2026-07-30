from pydantic import BaseModel, Field, field_validator


class QuestionnaireOptionOut(BaseModel):
    key: str
    text: str


class QuestionnaireQuestionOut(BaseModel):
    id: int
    code: str
    dimension: str
    prompt: str
    options: list[QuestionnaireOptionOut]
    sort_order: int


class QuestionnaireStatusOut(BaseModel):
    answered_count: int
    total_questions: int
    completed: bool


class QuestionnaireOut(QuestionnaireStatusOut):
    questions: list[QuestionnaireQuestionOut]
    answers: dict[int, str] = Field(default_factory=dict)


class QuestionnaireAnswerInput(BaseModel):
    question_id: int
    answer_key: str = Field(min_length=1, max_length=1)

    @field_validator("answer_key")
    @classmethod
    def normalize_answer_key(cls, value: str) -> str:
        return value.strip().upper()


class QuestionnaireSubmitRequest(BaseModel):
    answers: list[QuestionnaireAnswerInput]


class QuestionnaireSubmitResponse(QuestionnaireStatusOut):
    message: str
