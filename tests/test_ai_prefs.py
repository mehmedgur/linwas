"""AI tercihleri testleri."""

from linwas.ai import prefs


def test_round_trip(tmp_path):
    path = tmp_path / "ai.json"
    prefs.save(prefs.AIPrefs("deepseek", {"deepseek": "deepseek-chat"}), path)
    loaded = prefs.load(path)
    assert loaded.last_provider == "deepseek"
    assert loaded.models == {"deepseek": "deepseek-chat"}


def test_missing_or_broken_file(tmp_path):
    assert prefs.load(tmp_path / "yok.json") == prefs.AIPrefs()
    bad = tmp_path / "bad.json"
    bad.write_text("{bozuk")
    assert prefs.load(bad) == prefs.AIPrefs()


def test_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert prefs.default_path() == tmp_path / "linwas" / "ai.json"
