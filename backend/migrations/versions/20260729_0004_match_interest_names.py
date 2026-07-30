"""Keep stored match interest names compatible with detailed taxonomy.

Revision ID: 20260729_0004
Revises: 20260729_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0004"
down_revision = "20260729_0003"
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


def _rewrite_shared_interests(rename_map: dict[str, str]) -> None:
    bind = op.get_bind()
    matches = sa.table(
        "matches",
        sa.column("id", sa.Integer()),
        sa.column("shared_interests", sa.JSON()),
    )
    rows = bind.execute(sa.select(matches.c.id, matches.c.shared_interests)).mappings().all()
    for row in rows:
        current = row["shared_interests"] or []
        updated = [rename_map.get(name, name) for name in current]
        if updated != current:
            bind.execute(
                sa.update(matches).where(matches.c.id == row["id"]).values(shared_interests=updated)
            )


def upgrade() -> None:
    _rewrite_shared_interests(LEGACY_RENAMES)


def downgrade() -> None:
    _rewrite_shared_interests({new_name: old_name for old_name, new_name in LEGACY_RENAMES.items()})
