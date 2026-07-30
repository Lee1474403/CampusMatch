from pathlib import Path

from backend.app.services import chat_safety


def reset_catalog(monkeypatch, directory: Path) -> None:
    monkeypatch.setattr(chat_safety, "BLOCKED_WORDS_DIR", directory)
    monkeypatch.setattr(chat_safety, "_catalog_signature", ())
    monkeypatch.setattr(chat_safety, "_catalog", ())


def test_sensitive_words_ignore_spaces_punctuation_and_case(tmp_path, monkeypatch) -> None:
    (tmp_path / "fraud.txt").write_text("转账\nbankcard\n", encoding="utf-8")
    reset_catalog(monkeypatch, tmp_path)

    hits = chat_safety.find_sensitive_words("请先转-账，再提供 BANK card")

    assert [hit.category for hit in hits] == ["fraud"]
    assert chat_safety.sensitive_content_error("能不能转 账") == "消息包含诈骗或资金风险内容，请修改后再发送"


def test_sensitive_word_catalog_hot_reloads_after_file_change(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "violence.txt"
    catalog.write_text("血腥\n", encoding="utf-8")
    reset_catalog(monkeypatch, tmp_path)
    assert chat_safety.find_sensitive_words("这是一段正常聊天") == []

    catalog.write_text("血腥\n危险短语测试\n", encoding="utf-8")

    hits = chat_safety.find_sensitive_words("这里包含危险 短语测试")
    assert hits and hits[0].category == "violence"


def test_normal_conversation_is_not_blocked() -> None:
    assert chat_safety.sensitive_content_error("今天下课后一起去图书馆吗？") is None
