# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sohbet geçmişi testleri."""

import pytest

from linwas.ai.base import Message
from linwas.ai.chat_history import ChatHistoryDB, Conversation


@pytest.fixture
def db(tmp_path):
    return ChatHistoryDB(db_path=tmp_path / "chat.db")


def make_conv(provider="chatgpt", model="gpt-4o"):
    conv = Conversation(provider=provider, model=model)
    conv.messages = [
        Message(role="user", content="Merhaba"),
        Message(role="assistant", content="Merhaba! Size nasıl yardımcı olabilirim?"),
    ]
    return conv


def test_save_and_load(db):
    conv = make_conv()
    db.save(conv)
    loaded = db.load(conv.id)
    assert loaded is not None
    assert loaded.provider == "chatgpt"
    assert len(loaded.messages) == 2
    assert loaded.messages[0].content == "Merhaba"


def test_load_missing_returns_none(db):
    assert db.load("nonexistent") is None


def test_list(db):
    db.save(make_conv(provider="chatgpt"))
    db.save(make_conv(provider="gemini"))
    convs = db.list()
    assert len(convs) == 2


def test_update_messages(db):
    conv = make_conv()
    db.save(conv)
    conv.messages.append(Message(role="user", content="Yeni soru"))
    db.save(conv)
    loaded = db.load(conv.id)
    assert len(loaded.messages) == 3


def test_delete(db):
    conv = make_conv()
    db.save(conv)
    db.delete(conv.id)
    assert db.load(conv.id) is None


def test_clear_all(db):
    db.save(make_conv())
    db.save(make_conv())
    db.clear_all()
    assert db.list() == []


def test_message_model_saved(db):
    conv = make_conv()
    conv.messages[1].model = "deepseek-chat"
    db.save(conv)
    assert db.load(conv.id).messages[1].model == "deepseek-chat"


def test_title_from_first_user_message_without_context(db):
    from linwas.ai.chat_history import CONTEXT_MARKER

    conv = make_conv()
    conv.messages.insert(0, Message(role="system", content="sistem"))
    conv.messages[1].content = "Yazıcım çalışmıyor" + CONTEXT_MARKER + "OS: Pardus"
    db.save(conv)
    assert db.list()[0].title == "Yazıcım çalışmıyor"


def test_long_title_shortened(db):
    conv = make_conv()
    conv.messages[0].content = "a " * 100
    db.save(conv)
    assert len(db.list()[0].title) <= 60


def test_provider_model_updated_on_save(db):
    conv = make_conv()
    db.save(conv)
    conv.provider, conv.model = "gemini", "gemini-2.5-flash"
    db.save(conv)
    loaded = db.load(conv.id)
    assert (loaded.provider, loaded.model) == ("gemini", "gemini-2.5-flash")


def test_migrates_old_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE conversations (id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
        " model TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,"
        " created_at TEXT NOT NULL);"
        "INSERT INTO conversations VALUES ('c1','chatgpt','gpt','2026','2026');"
        "INSERT INTO messages (conversation_id, role, content, created_at)"
        " VALUES ('c1','user','eski','2026');"
    )
    con.commit()
    con.close()
    loaded = ChatHistoryDB(path).load("c1")
    assert loaded.messages[0].content == "eski" and loaded.messages[0].model == ""


class _FakeProvider:
    def __init__(self, pid):
        self.provider_id = pid
        self.display_name = pid
        self.seen = []

    def chat(self, messages, model, api_key):
        from linwas.ai.base import AIResponse

        self.seen.append((model, [m.content for m in messages]))
        return AIResponse(text=f"yanıt-{model}", input_tokens=1, output_tokens=1, model=model)


def test_session_switch_keeps_history(tmp_path, monkeypatch):
    from linwas.ai import manager
    from linwas.ai.usage import UsageDB

    monkeypatch.setattr(manager, "get_key", lambda pid: "k")
    monkeypatch.setattr(manager, "build_system_prompt", lambda: "SYS")
    a, b = _FakeProvider("deepseek"), _FakeProvider("gemini")
    hist = ChatHistoryDB(tmp_path / "h.db")
    s = manager.AISession(a, "m1", UsageDB(tmp_path / "u.db"), hist)
    s.send("soru 1")
    s.switch(b, "m2")
    s.send("soru 2")
    # İkinci sağlayıcı önceki konuşmayı da görür
    assert b.seen[0] == ("m2", ["SYS", "soru 1", "yanıt-m1", "soru 2"])
    assert [m.model for m in s.messages if m.role == "assistant"] == ["m1", "m2"]
    saved = hist.load(s.conversation_id)
    assert (saved.provider, saved.model) == ("gemini", "m2")


def test_session_resume(tmp_path, monkeypatch):
    from linwas.ai import manager
    from linwas.ai.usage import UsageDB

    monkeypatch.setattr(manager, "get_key", lambda pid: "k")
    monkeypatch.setattr(manager, "build_system_prompt", lambda: "YENI-SYS")
    hist = ChatHistoryDB(tmp_path / "h.db")
    conv = make_conv()
    conv.messages.insert(0, Message(role="system", content="ESKI-SYS"))
    hist.save(conv)
    p = _FakeProvider("gemini")
    s = manager.AISession.resume(hist.load(conv.id), p, "m3", UsageDB(tmp_path / "u.db"), hist)
    assert [m.role for m in s.messages] == ["user", "assistant"]
    s.send("devam")
    assert p.seen[0][1][0] == "YENI-SYS"
    assert s.conversation_id == conv.id
