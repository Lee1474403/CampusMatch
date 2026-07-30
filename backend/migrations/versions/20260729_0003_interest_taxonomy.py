"""Add categorized, detailed interest taxonomy.

Revision ID: 20260729_0003
Revises: 20260729_0002
"""

from alembic import op
import sqlalchemy as sa

from backend.app.services.seed import INTERESTS


revision = "20260729_0003"
down_revision = "20260729_0002"
branch_labels = None
depends_on = None


LEGACY_RENAMES = {
    "运动": "综合运动",
    "音乐": "音乐综合",
    "阅读": "阅读综合",
    "电影": "电影综合",
    "游戏": "综合游戏",
    "摄影": "摄影综合",
    "旅行": "旅行综合",
    "美食": "美食探店",
    "乐器": "乐器演奏",
    "动漫": "动漫综合",
}

LEGACY_FINAL_NAMES = set(LEGACY_RENAMES.values()) | {
    "编程", "绘画", "舞蹈", "宠物", "手工", "辩论", "志愿服务",
    "健身", "桌游", "烘焙", "骑行", "书法", "露营", "戏剧",
}


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def _interest_rows(bind) -> dict[str, int]:
    rows = bind.execute(sa.text("SELECT id, name FROM interests")).mappings().all()
    return {row["name"]: row["id"] for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = _column_names(inspector, "interests")

    with op.batch_alter_table("interests") as batch:
        if "category" not in columns:
            batch.add_column(
                sa.Column("category", sa.String(length=30), nullable=False, server_default=sa.text("'其他'"))
            )
        if "sort_order" not in columns:
            batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    existing = _interest_rows(bind)
    for old_name, new_name in LEGACY_RENAMES.items():
        old_id = existing.get(old_name)
        if not old_id:
            continue
        new_id = existing.get(new_name)
        if new_id and new_id != old_id:
            bind.execute(
                sa.text(
                    "INSERT INTO user_interests (user_id, interest_id) "
                    "SELECT source.user_id, :new_id FROM user_interests AS source "
                    "WHERE source.interest_id = :old_id AND NOT EXISTS ("
                    "SELECT 1 FROM user_interests AS target "
                    "WHERE target.user_id = source.user_id AND target.interest_id = :new_id)"
                ),
                {"old_id": old_id, "new_id": new_id},
            )
            bind.execute(sa.text("DELETE FROM user_interests WHERE interest_id = :old_id"), {"old_id": old_id})
            bind.execute(sa.text("DELETE FROM interests WHERE id = :old_id"), {"old_id": old_id})
        else:
            bind.execute(
                sa.text("UPDATE interests SET name = :new_name WHERE id = :interest_id"),
                {"new_name": new_name, "interest_id": old_id},
            )
        existing = _interest_rows(bind)

    interests_table = sa.table(
        "interests",
        sa.column("name", sa.String()),
        sa.column("emoji", sa.String()),
        sa.column("category", sa.String()),
        sa.column("sort_order", sa.Integer()),
    )
    existing = _interest_rows(bind)
    missing = []
    for name, emoji, category, sort_order in INTERESTS:
        if name in existing:
            bind.execute(
                sa.update(interests_table)
                .where(interests_table.c.name == name)
                .values(emoji=emoji, category=category, sort_order=sort_order)
            )
        else:
            missing.append({"name": name, "emoji": emoji, "category": category, "sort_order": sort_order})
    if missing:
        op.bulk_insert(interests_table, missing)

    inspector = sa.inspect(bind)
    if "ix_interests_category_order" not in _index_names(inspector, "interests"):
        op.create_index("ix_interests_category_order", "interests", ["category", "sort_order"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    catalog_names = {name for name, _, _, _ in INTERESTS}
    removable_names = sorted(catalog_names - LEGACY_FINAL_NAMES)
    if removable_names:
        placeholders = ", ".join(f":name_{index}" for index in range(len(removable_names)))
        params = {f"name_{index}": name for index, name in enumerate(removable_names)}
        ids = bind.execute(
            sa.text(f"SELECT id FROM interests WHERE name IN ({placeholders})"), params
        ).scalars().all()
        if ids:
            id_placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
            id_params = {f"id_{index}": identifier for index, identifier in enumerate(ids)}
            bind.execute(sa.text(f"DELETE FROM user_interests WHERE interest_id IN ({id_placeholders})"), id_params)
            bind.execute(sa.text(f"DELETE FROM interests WHERE id IN ({id_placeholders})"), id_params)

    for old_name, new_name in LEGACY_RENAMES.items():
        bind.execute(
            sa.text("UPDATE interests SET name = :old_name WHERE name = :new_name"),
            {"old_name": old_name, "new_name": new_name},
        )

    inspector = sa.inspect(bind)
    with op.batch_alter_table("interests") as batch:
        if "ix_interests_category_order" in _index_names(inspector, "interests"):
            batch.drop_index("ix_interests_category_order")
        columns = _column_names(inspector, "interests")
        if "sort_order" in columns:
            batch.drop_column("sort_order")
        if "category" in columns:
            batch.drop_column("category")
