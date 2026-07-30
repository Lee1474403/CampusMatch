"""Add persistent user blocking relationships.

Revision ID: 20260730_0008
Revises: 20260730_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0008"
down_revision = "20260730_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_blocks" not in inspector.get_table_names():
        op.create_table(
            "user_blocks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("blocker_id", sa.Integer(), nullable=False),
            sa.Column("blocked_id", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("blocker_id != blocked_id", name="ck_user_blocks_not_self"),
            sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_direction"),
        )
        inspector = sa.inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("user_blocks")}
    blocker_index = op.f("ix_user_blocks_blocker_id")
    blocked_index = op.f("ix_user_blocks_blocked_id")
    if blocker_index not in indexes:
        op.create_index(blocker_index, "user_blocks", ["blocker_id"], unique=False)
    if blocked_index not in indexes:
        op.create_index(blocked_index, "user_blocks", ["blocked_id"], unique=False)


def downgrade() -> None:
    if "user_blocks" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("user_blocks")
