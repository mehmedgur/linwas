"""Kodsuz eklentiler: şema, reddedilen işlemler, izin özeti, kurulum ve katalog."""

import hashlib
import json
from pathlib import Path

import pytest

from linwas.core.plugins import SOURCE_CATALOG, SOURCE_DEVELOPER, catalog, declarative
from linwas.core.plugins.loader import BLOCKED_DEVELOPER, BLOCKED_REVOKED, PluginLoader

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "packaging" / "plugin-catalog" / "plugins" / "org.linwas.recipes.json"


def _manifest(**extra) -> dict:
    data = {
        "schema": 1,
        "id": "org.example.help",
        "version": "1.0.0",
        "name": {"en": "Help", "tr": "Yardım"},
        "publisher": "Example",
        "troubleshooting": [
            {
                "id": "queue",
                "title": "Stuck",
                "actions": [
                    {
                        "label": "Restart",
                        "task": [{"op": "service.restart", "params": {"name": "cups"}}],
                    },
                    {"label": "Printers", "page": "hardware"},
                ],
            }
        ],
    }
    data.update(extra)
    return data


def test_sample_plugin_is_valid():
    manifest = declarative.parse(SAMPLE.read_text(encoding="utf-8"))
    assert manifest["id"] == "org.linwas.recipes"
    assert declarative.permissions(manifest).tasks


@pytest.mark.parametrize(
    "change",
    [
        {"id": "linwas.evil"},  # ayrılmış ad alanı
        {"id": "nodots"},
        {"version": "1.0"},
        {"schema": 2},
        {"publisher": ""},
        {"troubleshooting": [], "checks": [], "guide": []},  # hiçbir şey eklemiyor
    ],
)
def test_invalid_manifest(change):
    with pytest.raises(declarative.ManifestError):
        declarative.parse(json.dumps(_manifest(**change)))


@pytest.mark.parametrize(
    "step",
    [
        {"op": "deb.install", "params": {"path": "/tmp/x.deb"}},  # eklentilere kapalı
        {"op": "file.write_text", "params": {}},
        {"op": "service.restart", "params": {"name": "bad name; rm"}},  # izin listesi reddeder
        {"op": "package.install", "params": {"name": 3}},
    ],
)
def test_forbidden_or_invalid_task(step):
    data = _manifest()
    data["troubleshooting"][0]["actions"][0]["task"] = [step]
    with pytest.raises(declarative.ManifestError):
        declarative.parse(json.dumps(data))


def test_only_https_links_and_absolute_paths():
    data = _manifest()
    data["troubleshooting"][0]["actions"][1] = {"label": "x", "url": "http://example.org"}
    with pytest.raises(declarative.ManifestError):
        declarative.parse(json.dumps(data))
    data = _manifest(
        checks=[
            {
                "id": "c",
                "ok": "ok",
                "problem": "bad",
                "test": {"type": "file_exists", "path": "/etc/../root/x"},
            }
        ]
    )
    with pytest.raises(declarative.ManifestError):
        declarative.parse(json.dumps(data))


def test_permissions_and_new_keys():
    old = declarative.permissions(declarative.parse(json.dumps(_manifest())))
    data = _manifest()
    data["troubleshooting"][0]["actions"].append(
        {"label": "x", "task": [{"op": "package.install", "params": {"name": "hplip"}}]}
    )
    new = declarative.permissions(declarative.parse(json.dumps(data)))
    assert [t[0] for t in old.tasks] == ["service.restart"]
    assert old.pages == ["hardware"]
    assert new.keys() - old.keys() == {'task:package.install:{"name": "hplip"}'}


def test_run_test_expect(tmp_path: Path):
    target = tmp_path / "f"
    target.write_text("x")
    assert declarative.run_test({"type": "file_exists", "path": str(target), "expect": True})[0]
    assert not declarative.run_test({"type": "file_exists", "path": str(target), "expect": False})[
        0
    ]


def test_install_and_tamper_detection(tmp_path: Path):
    text = json.dumps(_manifest())
    declarative.install(text, SOURCE_CATALOG, base=tmp_path)
    found, errors = declarative.installed(tmp_path)
    assert [i.manifest["id"] for i in found] == ["org.example.help"] and not errors
    # Katalogdan kurulan dosya sonradan değiştirilirse yüklenmez
    (tmp_path / "org.example.help" / "manifest.json").write_text(text.replace("Help", "Evil"))
    found, errors = declarative.installed(tmp_path)
    assert not found and errors


def test_loader_blocks_developer_plugins_and_revoked(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    declarative.install(json.dumps(_manifest()), SOURCE_DEVELOPER)
    loader = PluginLoader()
    loader.load_declarative("tr", developer_mode=False)
    plugin = loader.all_plugins()[0]
    assert plugin.meta.name == "Yardım"
    assert loader.blocked_reason(plugin) == BLOCKED_DEVELOPER and not loader.plugins()

    revoked = catalog.Catalog(revoked={"org.example.help": ({"*"}, {"en": "bad"})})
    monkeypatch.setattr(catalog, "cached", lambda: revoked)
    loader = PluginLoader()
    loader.load_declarative("en", developer_mode=True)
    assert loader.blocked_reason(loader.all_plugins()[0]) == BLOCKED_REVOKED


def _index(data: bytes) -> bytes:
    return json.dumps(
        {
            "schema": 1,
            "plugins": [
                {
                    "id": "org.example.help",
                    "version": "1.0.0",
                    "name": {"en": "Help"},
                    "publisher": "Example",
                    "url": "files/org.example.help-1.0.0.json",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
            ],
            "revoked": [{"id": "org.example.old", "versions": ["*"]}],
        }
    ).encode()


def test_catalog_parse_and_download(monkeypatch):
    data = json.dumps(_manifest()).encode()
    cat = catalog.parse_index(_index(data), "https://repo.example/plugins/index.json")
    entry = cat.entries[0]
    assert entry.url == "https://repo.example/plugins/files/org.example.help-1.0.0.json"
    assert cat.revoked_reason("org.example.old", "9.9.9") is not None
    monkeypatch.setattr(catalog, "_fetch", lambda url, limit: data)
    assert json.loads(catalog.download(entry))["id"] == "org.example.help"
    monkeypatch.setattr(catalog, "_fetch", lambda url, limit: data + b" ")
    with pytest.raises(catalog.CatalogError) as err:
        catalog.download(entry)
    assert err.value.code == "checksum"


def test_catalog_refuses_unverified_index(monkeypatch):
    monkeypatch.setenv(catalog.ENV_URL, "https://repo.example/plugins/index.json")
    monkeypatch.setattr(catalog, "_fetch", lambda url, limit: b"{}")
    monkeypatch.setattr(catalog, "verify", lambda data, sig: False)
    with pytest.raises(catalog.CatalogError) as err:
        catalog.refresh()
    assert err.value.code == "signature"


def test_catalog_rejects_plain_http(monkeypatch):
    monkeypatch.delenv(catalog.ENV_URL, raising=False)
    data = json.dumps(_manifest()).encode()
    index = _index(data).replace(b"files/", b"http://evil.example/")
    with pytest.raises(catalog.CatalogError):
        catalog.parse_index(index, "https://repo.example/plugins/index.json")
