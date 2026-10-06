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


def test_panel_state(tmp_path):
    path = tmp_path / "ai.json"
    prefs.save(prefs.AIPrefs(panel_width=500, panel_collapsed=True), path)
    loaded = prefs.load(path)
    assert (loaded.panel_width, loaded.panel_collapsed) == (500, True)
    path.write_text('{"panel_width": 5, "panel_collapsed": "evet"}')
    loaded = prefs.load(path)
    assert (loaded.panel_width, loaded.panel_collapsed) == (340, False)


def test_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert prefs.default_path() == tmp_path / "linwas" / "ai.json"


def test_update_keeps_other_fields(tmp_path):
    path = tmp_path / "ai.json"
    prefs.save(prefs.AIPrefs("gemini", {"gemini": "g1"}, panel_width=400), path)
    prefs.update(path, panel_collapsed=True)
    prefs.update(path, last_provider="deepseek", models={"deepseek": "d1"})
    loaded = prefs.load(path)
    assert loaded == prefs.AIPrefs("deepseek", {"deepseek": "d1"}, 400, True)
