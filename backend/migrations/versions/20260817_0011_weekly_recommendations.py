"""Add weekly directional recommendations and batch run records.

Revision ID: 20260817_0011
Revises: 20260730_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20260817_0011"
down_revision = "20260730_0010"
branch_labels = None
depends_on = None


def _create_run_table() -> None:
    op.create_table(
        "weekly_recommendation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("batch_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("eligible_user_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recommendation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deep_calls_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_weekly_recommendation_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start", "batch_index", name="uq_weekly_recommendation_run_batch"),
    )
    op.create_index(
        "ix_weekly_recommendation_runs_week_start",
        "weekly_recommendation_runs",
        ["week_start"],
        unique=False,
    )
    op.create_index(
        "ix_weekly_recommendation_runs_week_status",
        "weekly_recommendation_runs",
        ["week_start", "status"],
        unique=False,
    )


def _create_recommendation_table() -> None:
    op.create_table(
        "weekly_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("preliminary_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("deep_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("selection_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("repeat_penalty", sa.Float(), server_default="0", nullable=False),
        sa.Column("deep_comment", sa.String(length=200), nullable=True),
        sa.Column("deep_match_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("shared_interests", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("owner_user_id != candidate_user_id", name="ck_weekly_recommendations_not_self"),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_weekly_recommendations_rank"),
        sa.ForeignKeyConstraint(["candidate_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "candidate_user_id",
            "week_start",
            name="uq_weekly_recommendation_candidate",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "week_start",
            "rank",
            name="uq_weekly_recommendation_rank",
        ),
    )
    op.create_index(
        "ix_weekly_recommendations_owner_user_id",
        "weekly_recommendations",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_weekly_recommendations_candidate_user_id",
        "weekly_recommendations",
        ["candidate_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_weekly_recommendations_week_start",
        "weekly_recommendations",
        ["week_start"],
        unique=False,
    )
    op.create_index(
        "ix_weekly_recommendations_owner_week",
        "weekly_recommendations",
        ["owner_user_id", "week_start"],
        unique=False,
    )
    op.create_index(
        "ix_weekly_recommendations_candidate_week",
        "weekly_recommendations",
        ["candidate_user_id", "week_start"],
        unique=False,
    )


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "weekly_recommendation_runs" not in existing_tables:
        _create_run_table()
    if "weekly_recommendations" not in existing_tables:
        _create_recommendation_table()


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "weekly_recommendations" in existing_tables:
        op.drop_table("weekly_recommendations")
    if "weekly_recommendation_runs" in existing_tables:
        op.drop_table("weekly_recommendation_runs")
