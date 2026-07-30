"""Add hometown province and city for preliminary matching.

Revision ID: 20260730_0007
Revises: 20260730_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0007"
down_revision = "20260730_0006"
branch_labels = None
depends_on = None


DEMO_HOMETOWNS = {
    "20260001": ("陕西", "西安"),
    "20260002": ("河南", "洛阳"),
    "20260003": ("四川", "成都"),
    "20260004": ("山东", "济南"),
    "20260005": ("河南", "郑州"),
    "20260006": ("陕西", "宝鸡"),
    "20260007": ("陕西", "西安"),
    "20260008": ("四川", "绵阳"),
    "20260009": ("陕西", "咸阳"),
    "20260010": ("河南", "洛阳"),
}


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(sa.inspect(bind), "users")
    identifier_name = "account" if "account" in columns else "student_id"
    with op.batch_alter_table("users") as batch:
        if "hometown_province" not in columns:
            batch.add_column(sa.Column("hometown_province", sa.String(length=40), nullable=True))
        if "hometown_city" not in columns:
            batch.add_column(sa.Column("hometown_city", sa.String(length=40), nullable=True))

    users = sa.table(
        "users",
        sa.column(identifier_name, sa.String()),
        sa.column("hometown_province", sa.String()),
        sa.column("hometown_city", sa.String()),
        sa.column("is_matching_enabled", sa.Boolean()),
        sa.column("matching_enabled_at", sa.DateTime(timezone=True)),
    )
    for account, (province, city) in DEMO_HOMETOWNS.items():
        bind.execute(
            sa.update(users)
            .where(users.c[identifier_name] == account)
            .values(hometown_province=province, hometown_city=city)
        )
    bind.execute(
        sa.update(users)
        .where(
            sa.or_(
                users.c.hometown_province.is_(None),
                users.c.hometown_city.is_(None),
            )
        )
        .values(is_matching_enabled=False, matching_enabled_at=None)
    )


def downgrade() -> None:
    columns = _column_names(sa.inspect(op.get_bind()), "users")
    with op.batch_alter_table("users") as batch:
        if "hometown_city" in columns:
            batch.drop_column("hometown_city")
        if "hometown_province" in columns:
            batch.drop_column("hometown_province")
