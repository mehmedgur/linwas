"""Seçilmiş model listesi testleri."""

import json

from linwas.ai.model_catalog import ROLES, available_curated, load_curated


def test_real_catalog_gemini():
    models = load_curated("gemini")
    assert [m.id for m in models] == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.1-pro-preview",
    ]
    assert all(m.role in ROLES for m in models)


def test_only_live_models_shown(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"gemini": [{"id": "a", "label": "A", "role": "main"}, {"id": "b"}]}))
    assert [m.id for m in available_curated("gemini", ["b", "x"], f)] == ["b"]
    assert available_curated("gemini", ["x"], f) == []
    assert available_curated("deepseek", ["b"], f) == []


def test_missing_file(tmp_path):
    assert load_curated("gemini", tmp_path / "yok.json") == []
