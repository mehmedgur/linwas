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
