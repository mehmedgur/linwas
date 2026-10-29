# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Seçilmiş model listesi testleri."""

import json

from linwas.ai.model_catalog import ROLES, available_curated, load_curated


def test_real_catalog_gemini():
    models = load_curated("gemini")
    assert [m.id for m in models[:3]] == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.1-pro-preview",
    ]
    assert all(m.role in ROLES for m in models)
    assert len({m.id for m in models}) == len(models)
    # 3.1 Pro ücretli, diğerleri ücretsiz katmanda
    assert [m.id for m in models if m.free is False] == ["gemini-3.1-pro-preview"]
    assert all(m.free is not None for m in models)


def test_only_live_models_shown(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"gemini": [{"id": "a", "label": "A", "role": "main"}, {"id": "b"}]}))
    assert [m.id for m in available_curated("gemini", ["b", "x"], f)] == ["b"]
    assert available_curated("gemini", ["x"], f) == []
    assert available_curated("deepseek", ["b"], f) == []


def test_missing_file(tmp_path):
    assert load_curated("gemini", tmp_path / "yok.json") == []


def test_gemini_list_follows_pages(monkeypatch):
    from linwas.ai import gemini

    pages = {
        "": {
            "models": [{"name": "models/a", "supportedGenerationMethods": ["generateContent"]}],
            "nextPageToken": "t/2",
        },
        "t%2F2": {
            "models": [
                {"name": "models/b", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/e", "supportedGenerationMethods": ["embedContent"]},
            ]
        },
    }
    seen = []

    def fake_get(path, key):
        seen.append(path)
        token = path.split("pageToken=")[1] if "pageToken=" in path else ""
        return pages[token]

    monkeypatch.setattr(gemini, "_get", fake_get)
    assert gemini.GEMINI.list_models("k") == ["a", "b"]
    assert len(seen) == 2


def test_url_with_query():
    from linwas.ai import gemini

    assert gemini._url("models?pageSize=1", "K").endswith("models?pageSize=1&key=K")
    assert gemini._url("models", "K").endswith("models?key=K")
