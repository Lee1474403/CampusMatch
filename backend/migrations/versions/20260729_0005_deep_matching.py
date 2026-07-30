"""Add questionnaire answers and deep matching result fields.

Revision ID: 20260729_0005
Revises: 20260729_0004
"""

from alembic import op
import sqlalchemy as sa

from backend.app.services.questionnaire_catalog import QUESTIONNAIRE, QUESTIONNAIRE_VERSION


revision = "20260729_0005"
down_revision = "20260729_0004"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "questionnaire_questions" not in tables:
        op.create_table(
            "questionnaire_questions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=12), nullable=False),
            sa.Column("dimension", sa.String(length=40), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("code", name="uq_questionnaire_questions_code"),
        )
        op.create_index("ix_questionnaire_questions_code", "questionnaire_questions", ["code"], unique=True)
        op.create_index("ix_questionnaire_questions_dimension", "questionnaire_questions", ["dimension"], unique=False)
        op.create_index(
            "ix_questionnaire_questions_active_order",
            "questionnaire_questions",
            ["is_active", "sort_order"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    if "questionnaire_answers" not in inspector.get_table_names():
        op.create_table(
            "questionnaire_answers",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("question_id", sa.Integer(), nullable=False),
            sa.Column("answer_key", sa.String(length=1), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["question_id"], ["questionnaire_questions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id", "question_id"),
        )
        op.create_index("ix_questionnaire_answers_user", "questionnaire_answers", ["user_id"], unique=False)

    inspector = sa.inspect(bind)
    match_columns = _column_names(inspector, "matches")
    with op.batch_alter_table("matches") as batch:
        if "preliminary_score" not in match_columns:
            batch.add_column(sa.Column("preliminary_score", sa.Float(), nullable=False, server_default="0"))
        if "deep_score" not in match_columns:
            batch.add_column(sa.Column("deep_score", sa.Float(), nullable=True))
        if "deep_comment" not in match_columns:
            batch.add_column(sa.Column("deep_comment", sa.String(length=200), nullable=True))
        if "deep_match_used" not in match_columns:
            batch.add_column(sa.Column("deep_match_used", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE matches SET preliminary_score = match_score WHERE preliminary_score = 0"))

    questions = sa.table(
        "questionnaire_questions",
        sa.column("code", sa.String()),
        sa.column("dimension", sa.String()),
        sa.column("prompt", sa.Text()),
        sa.column("options", sa.JSON()),
        sa.column("sort_order", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    existing_codes = set(bind.execute(sa.select(questions.c.code)).scalars().all())
    missing = []
    for question in QUESTIONNAIRE:
        values = {**question, "version": QUESTIONNAIRE_VERSION, "is_active": True}
        if question["code"] in existing_codes:
            bind.execute(sa.update(questions).where(questions.c.code == question["code"]).values(**values))
        else:
            missing.append(values)
    if missing:
        op.bulk_insert(questions, missing)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    match_columns = _column_names(inspector, "matches")
    with op.batch_alter_table("matches") as batch:
        for column in ("deep_match_used", "deep_comment", "deep_score", "preliminary_score"):
            if column in match_columns:
                batch.drop_column(column)
    inspector = sa.inspect(bind)
    if "questionnaire_answers" in inspector.get_table_names():
        op.drop_table("questionnaire_answers")
    inspector = sa.inspect(bind)
    if "questionnaire_questions" in inspector.get_table_names():
        op.drop_table("questionnaire_questions")
