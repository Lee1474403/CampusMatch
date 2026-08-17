"""Add optional public height and weight fields.

Revision ID: 20260817_0012
Revises: 20260817_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260817_0012"
down_revision = "20260817_0011"
branch_labels = None
depends_on = None


HEIGHT_CONSTRAINT = "ck_users_height_cm_range"
WEIGHT_CONSTRAINT = "ck_users_weight_kg_range"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}


def _check_constraints() -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_check_constraints("users")
        if constraint.get("name")
    }


def upgrade() -> None:
    columns = _columns()
    constraints = _check_constraints()
    with op.batch_alter_table("users") as batch:
        if "height_cm" not in columns:
            batch.add_column(sa.Column("height_cm", sa.Integer(), nullable=True))
        if "weight_kg" not in columns:
            batch.add_column(sa.Column("weight_kg", sa.Float(), nullable=True))
        if HEIGHT_CONSTRAINT not in constraints:
            batch.create_check_constraint(
                HEIGHT_CONSTRAINT,
                "height_cm IS NULL OR height_cm BETWEEN 100 AND 250",
            )
        if WEIGHT_CONSTRAINT not in constraints:
            batch.create_check_constraint(
                WEIGHT_CONSTRAINT,
                "weight_kg IS NULL OR weight_kg BETWEEN 30 AND 300",
            )


def downgrade() -> None:
    columns = _columns()
    constraints = _check_constraints()
    with op.batch_alter_table("users") as batch:
        if WEIGHT_CONSTRAINT in constraints:
            batch.drop_constraint(WEIGHT_CONSTRAINT, type_="check")
        if HEIGHT_CONSTRAINT in constraints:
            batch.drop_constraint(HEIGHT_CONSTRAINT, type_="check")
        if "weight_kg" in columns:
            batch.drop_column("weight_kg")
        if "height_cm" in columns:
            batch.drop_column("height_cm")
