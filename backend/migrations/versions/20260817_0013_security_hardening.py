"""Add email verification state and revocable refresh tokens.

Revision ID: 20260817_0013
Revises: 20260817_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260817_0013"
down_revision = "20260817_0012"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table)
        if index.get("name")
    }


def upgrade() -> None:
    user_columns = _columns("users")
    added_verified = "is_email_verified" not in user_columns
    with op.batch_alter_table("users") as batch:
        if added_verified:
            # Existing accounts are trusted during upgrade so production users are not locked out.
            batch.add_column(
                sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.true())
            )
        if "email_verification_token" not in user_columns:
            batch.add_column(sa.Column("email_verification_token", sa.String(length=64), nullable=True))
        if "verification_token_expires_at" not in user_columns:
            batch.add_column(sa.Column("verification_token_expires_at", sa.DateTime(timezone=True), nullable=True))

    if added_verified:
        op.execute(sa.text("UPDATE users SET is_email_verified = true"))
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "is_email_verified",
                existing_type=sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )

    indexes = _indexes("users")
    if "ix_users_is_email_verified" not in indexes:
        op.create_index("ix_users_is_email_verified", "users", ["is_email_verified"], unique=False)
    if "ix_users_email_verification_token" not in indexes:
        op.create_index(
            "ix_users_email_verification_token",
            "users",
            ["email_verification_token"],
            unique=True,
        )

    if "refresh_tokens" not in _tables():
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    token_indexes = _indexes("refresh_tokens")
    index_specs = (
        ("ix_refresh_tokens_user_id", ["user_id"], False),
        ("ix_refresh_tokens_token_hash", ["token_hash"], True),
        ("ix_refresh_tokens_expires_at", ["expires_at"], False),
        ("ix_refresh_tokens_user_active", ["user_id", "revoked_at", "expires_at"], False),
    )
    for name, columns, unique in index_specs:
        if name not in token_indexes:
            op.create_index(name, "refresh_tokens", columns, unique=unique)


def downgrade() -> None:
    if "refresh_tokens" in _tables():
        op.drop_table("refresh_tokens")

    user_columns = _columns("users")
    indexes = _indexes("users")
    if "ix_users_email_verification_token" in indexes:
        op.drop_index("ix_users_email_verification_token", table_name="users")
    if "ix_users_is_email_verified" in indexes:
        op.drop_index("ix_users_is_email_verified", table_name="users")
    with op.batch_alter_table("users") as batch:
        if "verification_token_expires_at" in user_columns:
            batch.drop_column("verification_token_expires_at")
        if "email_verification_token" in user_columns:
            batch.drop_column("email_verification_token")
        if "is_email_verified" in user_columns:
            batch.drop_column("is_email_verified")
