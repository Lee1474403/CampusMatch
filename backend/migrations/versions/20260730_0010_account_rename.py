"""Rename the globally unique student_id field to account.

Revision ID: 20260730_0010
Revises: 20260730_0009
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0010"
down_revision = "20260730_0009"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}


def _indexes() -> dict[str, dict]:
    return {index["name"]: index for index in sa.inspect(op.get_bind()).get_indexes("users")}


def upgrade() -> None:
    columns = _columns()
    if "student_id" in columns and "account" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "student_id",
                new_column_name="account",
                existing_type=sa.String(length=32),
                existing_nullable=False,
            )

    indexes = _indexes()
    if "ix_users_student_id" in indexes:
        op.drop_index("ix_users_student_id", table_name="users")
        indexes.pop("ix_users_student_id", None)
    if "ix_users_account" not in indexes:
        op.create_index("ix_users_account", "users", ["account"], unique=True)


def downgrade() -> None:
    indexes = _indexes()
    if "ix_users_account" in indexes:
        op.drop_index("ix_users_account", table_name="users")
    columns = _columns()
    if "account" in columns and "student_id" not in columns:
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "account",
                new_column_name="student_id",
                existing_type=sa.String(length=32),
                existing_nullable=False,
            )
    if "ix_users_student_id" not in _indexes():
        op.create_index("ix_users_student_id", "users", ["student_id"], unique=True)
