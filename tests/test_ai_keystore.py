# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Anahtar kasası testleri (oturum belleği modu)."""

import linwas.ai.keystore as ks


def _reset():
    ks._session_keys.clear()
    ks._cache.clear()
    ks._keyring_available = False  # keyring yok gibi davran


def test_set_and_get_session():
    _reset()
    ks.set_key("test_provider", "sk-abc123")
    assert ks.get_key("test_provider") == "sk-abc123"


def test_get_missing_returns_none():
    _reset()
    assert ks.get_key("nonexistent") is None


def test_delete():
    _reset()
    ks.set_key("test_provider", "sk-abc123")
    ks.delete_key("test_provider")
    assert ks.get_key("test_provider") is None


def test_overwrite():
    _reset()
    ks.set_key("p", "key1")
    ks.set_key("p", "key2")
    assert ks.get_key("p") == "key2"


def test_multiple_providers():
    _reset()
    ks.set_key("chatgpt", "key-a")
    ks.set_key("gemini", "key-b")
    assert ks.get_key("chatgpt") == "key-a"
    assert ks.get_key("gemini") == "key-b"
