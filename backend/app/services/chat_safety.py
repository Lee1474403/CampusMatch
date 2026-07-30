from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import UserBlock


BLOCKED_WORDS_DIR = Path(__file__).resolve().parent.parent / "data" / "blocked_words"


@dataclass(frozen=True)
class SensitiveWordHit:
    category: str
    word: str


_catalog_lock = threading.Lock()
_catalog_signature: tuple[tuple[str, int, int], ...] = ()
_catalog: tuple[SensitiveWordHit, ...] = ()

SENSITIVE_CATEGORY_LABELS = {
    "violence": "血腥暴力",
    "sexual": "色情或不良",
    "fraud": "诈骗或资金风险",
}


def normalize_message_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _word_file_signature() -> tuple[tuple[str, int, int], ...]:
    if not BLOCKED_WORDS_DIR.exists():
        return ()
    return tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(BLOCKED_WORDS_DIR.glob("*.txt"))
    )


def _load_catalog() -> tuple[SensitiveWordHit, ...]:
    global _catalog, _catalog_signature
    signature = _word_file_signature()
    if signature == _catalog_signature and _catalog:
        return _catalog
    with _catalog_lock:
        signature = _word_file_signature()
        if signature == _catalog_signature and _catalog:
            return _catalog
        entries: dict[str, SensitiveWordHit] = {}
        for path in sorted(BLOCKED_WORDS_DIR.glob("*.txt")):
            category = path.stem
            for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
                word = raw_line.strip()
                if not word or word.startswith("#"):
                    continue
                normalized = normalize_message_text(word)
                if normalized:
                    entries.setdefault(normalized, SensitiveWordHit(category=category, word=word))
        _catalog_signature = signature
        _catalog = tuple(
            hit for _, hit in sorted(entries.items(), key=lambda item: (-len(item[0]), item[0]))
        )
        return _catalog


def find_sensitive_words(content: str) -> list[SensitiveWordHit]:
    normalized_content = normalize_message_text(content)
    if not normalized_content:
        return []
    hits: list[SensitiveWordHit] = []
    seen_categories: set[str] = set()
    for hit in _load_catalog():
        normalized_word = normalize_message_text(hit.word)
        if normalized_word in normalized_content and hit.category not in seen_categories:
            hits.append(hit)
            seen_categories.add(hit.category)
    return hits


def sensitive_content_error(content: str) -> str | None:
    hits = find_sensitive_words(content)
    if not hits:
        return None
    labels = "、".join(
        dict.fromkeys(SENSITIVE_CATEGORY_LABELS.get(hit.category, hit.category) for hit in hits)
    )
    return f"消息包含{labels}内容，请修改后再发送"


async def chat_is_blocked(db: AsyncSession, left_user_id: int, right_user_id: int) -> bool:
    block_id = await db.scalar(
        select(UserBlock.id)
        .where(
            or_(
                (UserBlock.blocker_id == left_user_id) & (UserBlock.blocked_id == right_user_id),
                (UserBlock.blocker_id == right_user_id) & (UserBlock.blocked_id == left_user_id),
            )
        )
        .limit(1)
    )
    return block_id is not None


async def blocked_pair_keys(db: AsyncSession, user_ids: set[int]) -> set[tuple[int, int]]:
    if len(user_ids) < 2:
        return set()
    rows = await db.execute(
        select(UserBlock.blocker_id, UserBlock.blocked_id).where(
            UserBlock.blocker_id.in_(user_ids),
            UserBlock.blocked_id.in_(user_ids),
        )
    )
    return {tuple(sorted((blocker_id, blocked_id))) for blocker_id, blocked_id in rows}
