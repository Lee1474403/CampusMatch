"""Add daily reciprocal pairing and privacy unlock state.

Revision ID: 20260729_0002
Revises: 20260728_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0002"
down_revision = "20260728_0001"
branch_labels = None
depends_on = None


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = _column_names(inspector, "users")
    with op.batch_alter_table("users") as batch:
        if "real_photos" not in user_columns:
            batch.add_column(sa.Column("real_photos", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        if "wechat" not in user_columns:
            batch.add_column(sa.Column("wechat", sa.String(length=80), nullable=True))
        if "is_matching_enabled" not in user_columns:
            batch.add_column(sa.Column("is_matching_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "matching_enabled_at" not in user_columns:
            batch.add_column(sa.Column("matching_enabled_at", sa.DateTime(timezone=True), nullable=True))

    inspector = sa.inspect(bind)
    if "ix_users_is_matching_enabled" not in _index_names(inspector, "users"):
        op.create_index("ix_users_is_matching_enabled", "users", ["is_matching_enabled"], unique=False)

    inspector = sa.inspect(bind)
    match_columns = _column_names(inspector, "matches")
    unique_names = {item["name"] for item in inspector.get_unique_constraints("matches") if item.get("name")}
    check_names = {item["name"] for item in inspector.get_check_constraints("matches") if item.get("name")}
    added_schedule = "scheduled_date" not in match_columns
    with op.batch_alter_table("matches", recreate="always" if bind.dialect.name == "sqlite" else "auto") as batch:
        if "uq_match_pair" in unique_names:
            batch.drop_constraint("uq_match_pair", type_="unique")
        if "scheduled_date" not in match_columns:
            batch.add_column(sa.Column("scheduled_date", sa.Date(), nullable=True))
        if "status" not in match_columns:
            batch.add_column(sa.Column("status", sa.String(length=24), nullable=False, server_default="chatting"))
        if "user1_hearted" not in match_columns:
            batch.add_column(sa.Column("user1_hearted", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "user2_hearted" not in match_columns:
            batch.add_column(sa.Column("user2_hearted", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "match_score" not in match_columns:
            batch.add_column(sa.Column("match_score", sa.Float(), nullable=False, server_default="0"))
        if "shared_interests" not in match_columns:
            batch.add_column(sa.Column("shared_interests", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        for name in (
            "mutual_hearted_at",
            "chat_start_time",
            "last_message_time",
            "user1_last_message_time",
            "user2_last_message_time",
            "privacy_unlocked_at",
            "expires_at",
            "dissolved_at",
        ):
            if name not in match_columns:
                batch.add_column(sa.Column(name, sa.DateTime(timezone=True), nullable=True))
        if "dissolve_reason" not in match_columns:
            batch.add_column(sa.Column("dissolve_reason", sa.String(length=80), nullable=True))
        if "ck_matches_status" not in check_names:
            batch.create_check_constraint(
                "ck_matches_status",
                "status IN ('pending_heartbeat', 'chatting', 'privacy_unlocked', 'dissolved')",
            )

    if added_schedule:
        if bind.dialect.name == "postgresql":
            op.execute(sa.text("UPDATE matches SET scheduled_date = CAST(matched_at AS date) WHERE scheduled_date IS NULL"))
        else:
            op.execute(sa.text("UPDATE matches SET scheduled_date = date(matched_at) WHERE scheduled_date IS NULL"))

    op.execute(sa.text("UPDATE matches SET mutual_hearted_at = matched_at WHERE mutual_hearted_at IS NULL"))
    op.execute(
        sa.text(
            "UPDATE matches SET chat_start_time = "
            "(SELECT MIN(messages.sent_at) FROM messages WHERE messages.match_id = matches.id) "
            "WHERE chat_start_time IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE matches SET last_message_time = COALESCE("
            "(SELECT MAX(messages.sent_at) FROM messages WHERE messages.match_id = matches.id), matched_at) "
            "WHERE last_message_time IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE matches SET user1_last_message_time = COALESCE("
            "(SELECT MAX(messages.sent_at) FROM messages WHERE messages.match_id = matches.id AND messages.sender_id = matches.user1_id), matched_at) "
            "WHERE user1_last_message_time IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE matches SET user2_last_message_time = COALESCE("
            "(SELECT MAX(messages.sent_at) FROM messages WHERE messages.match_id = matches.id AND messages.sender_id = matches.user2_id), matched_at) "
            "WHERE user2_last_message_time IS NULL"
        )
    )

    inspector = sa.inspect(bind)
    indexes = _index_names(inspector, "matches")
    if "ix_matches_scheduled_date" not in indexes:
        op.create_index("ix_matches_scheduled_date", "matches", ["scheduled_date"], unique=False)
    if "ix_matches_status_date" not in indexes:
        op.create_index("ix_matches_status_date", "matches", ["status", "scheduled_date"], unique=False)

    if added_schedule:
        with op.batch_alter_table("matches", recreate="always" if bind.dialect.name == "sqlite" else "auto") as batch:
            batch.alter_column("scheduled_date", existing_type=sa.Date(), nullable=False)
            batch.alter_column("status", existing_type=sa.String(length=24), server_default="pending_heartbeat")
            batch.alter_column("user1_hearted", existing_type=sa.Boolean(), server_default=sa.false())
            batch.alter_column("user2_hearted", existing_type=sa.Boolean(), server_default=sa.false())

    inspector = sa.inspect(bind)
    if "matching_runs" not in inspector.get_table_names():
        op.create_table(
            "matching_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_date", sa.Date(), nullable=False),
            sa.Column("candidates_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pairs_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("run_date", name="uq_matching_runs_run_date"),
        )
        op.create_index("ix_matching_runs_run_date", "matching_runs", ["run_date"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "matching_runs" in inspector.get_table_names():
        op.drop_table("matching_runs")
    with op.batch_alter_table("matches", recreate="always" if bind.dialect.name == "sqlite" else "auto") as batch:
        match_indexes = _index_names(inspector, "matches")
        match_checks = {item["name"] for item in inspector.get_check_constraints("matches") if item.get("name")}
        if "ix_matches_status_date" in match_indexes:
            batch.drop_index("ix_matches_status_date")
        if "ix_matches_scheduled_date" in match_indexes:
            batch.drop_index("ix_matches_scheduled_date")
        if "ck_matches_status" in match_checks:
            batch.drop_constraint("ck_matches_status", type_="check")
        for column in (
            "dissolve_reason", "dissolved_at", "expires_at", "privacy_unlocked_at",
            "user2_last_message_time", "user1_last_message_time", "last_message_time",
            "chat_start_time", "mutual_hearted_at", "shared_interests", "match_score",
            "user2_hearted", "user1_hearted", "status", "scheduled_date",
        ):
            batch.drop_column(column)
        batch.create_unique_constraint("uq_match_pair", ["user1_id", "user2_id"])
    with op.batch_alter_table("users") as batch:
        if "ix_users_is_matching_enabled" in _index_names(inspector, "users"):
            batch.drop_index("ix_users_is_matching_enabled")
        batch.drop_column("matching_enabled_at")
        batch.drop_column("is_matching_enabled")
        batch.drop_column("wechat")
        batch.drop_column("real_photos")
