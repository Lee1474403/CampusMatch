"""Add required school profile field and make department optional.

Revision ID: 20260730_0009
Revises: 20260730_0008
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0009"
down_revision = "20260730_0008"
branch_labels = None
depends_on = None


DEMO_ACCOUNTS = tuple(f"202600{index:02d}" for index in range(1, 11))
DEMO_SCHOOL = "CampusMatch示范大学"


def _columns() -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade() -> None:
    columns = _columns()
    identifier_name = "account" if "account" in columns else "student_id"
    with op.batch_alter_table("users") as batch:
        if "school" not in columns:
            batch.add_column(sa.Column("school", sa.String(length=120), nullable=True))
        if not columns["department"]["nullable"]:
            batch.alter_column(
                "department",
                existing_type=sa.String(length=80),
                nullable=True,
            )

    users = sa.table(
        "users",
        sa.column(identifier_name, sa.String()),
        sa.column("school", sa.String()),
        sa.column("is_matching_enabled", sa.Boolean()),
        sa.column("matching_enabled_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    bind.execute(
        sa.update(users)
        .where(users.c[identifier_name].in_(DEMO_ACCOUNTS), users.c.school.is_(None))
        .values(school=DEMO_SCHOOL)
    )
    bind.execute(
        sa.update(users)
        .where(sa.or_(users.c.school.is_(None), users.c.school == ""))
        .values(is_matching_enabled=False, matching_enabled_at=None)
    )


def downgrade() -> None:
    columns = _columns()
    users = sa.table("users", sa.column("department", sa.String()))
    op.get_bind().execute(
        sa.update(users).where(users.c.department.is_(None)).values(department="未填写")
    )
    with op.batch_alter_table("users") as batch:
        if columns["department"]["nullable"]:
            batch.alter_column(
                "department",
                existing_type=sa.String(length=80),
                nullable=False,
            )
        if "school" in columns:
            batch.drop_column("school")
