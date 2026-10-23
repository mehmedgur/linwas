"""Kodsuz (bildirimsel) eklentiler: `manifest.json` şeması, doğrulama, izin özeti ve kurulum.

Üçüncü taraf eklentiler Python kodu çalıştıramaz; yalnızca bu modülün tanıdığı yapıları
kullanır (kararlar.md › Eklenti mimarisi). Görevler izin listesindeki işlemlerden, eklentilere
açık olanlarla (PLUGIN_OPERATIONS) ve sabit, kurulumda doğrulanan parametrelerle kurulur.
Denetimler hazır türlerle yalnızca okur.

Biçim (şema 1):
    {
      "schema": 1,
      "id": "org.example.printer-help",
      "version": "1.0.0",
      "name": {"en": "Printer help", "tr": "Yazıcı yardımı"},
      "description": {"en": "..."},
      "publisher": "Example",
      "homepage": "https://example.org",
      "min_linwas": "2.0.0",
      "troubleshooting": [{"id": "...", "title": T, "description": T, "actions": [A]}],
      "checks": [{"id": "...", "ok": T, "problem": T, "test": TEST, "fixes": [A]}],
      "guide": [{"keywords": ["..."], "text": T, "kind": "setting", "page": "..."}]
    }
    T    = {"en": "...", "tr": "..."}  (en zorunlu)
    A    = {"label": T, "page": "cleanup"} | {"label": T, "settings": "sound"}
         | {"label": T, "url": "https://..."} | {"label": T, "task": [{"op": "...", "params": {}}]}
    TEST = {"type": "command_exists", "command": "lpstat"}
         | {"type": "file_exists", "path": "/etc/cups/printers.conf"}
         | {"type": "service_active", "service": "cups"}
         | {"type": "package_installed", "package": "hplip"}
         | {"type": "kernel_module_loaded", "module": "btusb"}
         | {"type": "disk_free", "path": "/", "min_gb": 5}
         (+ isteğe bağlı "expect": false → koşul sağlanmıyorsa sorun yok)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from linwas.core.plugins import (
    SOURCE_CATALOG,
    SOURCE_DEVELOPER,
    GuideEntry,
    PluginAction,
    PluginBase,
    PluginMeta,
    ScanCheck,
    TroubleshootingCard,
)
from linwas.core.whitelist import OPERATIONS, RiskLevel, ValidationError, validate

SCHEMA = 1
MAX_FILE_BYTES = 256 * 1024
MAX_ITEMS = 50
MAX_TEXT = 500
MANIFEST = "manifest.json"
INSTALL_INFO = "install.json"

# Eklentilerin görevlerinde kullanabileceği işlemler. Sistem dosyası yazan, depo/anahtar ekleyen,
# dışarıdan paket kuran, servis kapatan ya da yedekten geri yükleyen işlemler kapalıdır.
PLUGIN_OPERATIONS = frozenset(
    {
        "package.install",
        "flatpak.install",
        "package.update_index",
        "package.update_all",
        "package.fix_broken",
        "package.autoremove",
        "flatpak.update_all",
        "service.restart",
        "service.enable",
        "apt.clean",
        "journal.vacuum",
        "driver.rebuild_modules",
        "firmware.refresh",
        "snapshot.timeshift_create",
    }
)

TEST_TYPES = (
    "command_exists",
    "file_exists",
    "service_active",
    "package_installed",
    "kernel_module_loaded",
    "disk_free",
)
GUIDE_KINDS = ("setting", "program", "shortcut", "concept")

_RE_ID = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
_RE_VERSION = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
_RE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")  # sayfa / ayar / öğe kimliği
_RE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+@-]{0,63}$")  # komut / servis / paket / modül
_RE_LANG = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")


class ManifestError(ValueError):
    """Eklenti tanımı geçersiz (mesaj İngilizce, teknik; arayüz genel bir metin gösterir)."""


def plugins_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "linwas" / "plugins"


# --- Doğrulama ---


def _text(value: Any, where: str) -> dict[str, str]:
    if isinstance(value, str):
        value = {"en": value}
    if not isinstance(value, dict) or not isinstance(value.get("en"), str) or not value["en"]:
        raise ManifestError(f"{where}: an English text ('en') is required")
    out = {}
    for lang, text in value.items():
        if not (isinstance(lang, str) and _RE_LANG.match(lang) and isinstance(text, str)):
            raise ManifestError(f"{where}: invalid translation {lang!r}")
        if len(text) > MAX_TEXT:
            raise ManifestError(f"{where}: text is too long")
        out[lang] = text.strip()
    return out


def _opt_text(value: Any, where: str) -> dict[str, str]:
    """İsteğe bağlı metin: yoksa boş."""
    return _text(value, where) if value else {"en": ""}


def _list(data: dict, key: str) -> list[dict]:
    items = data.get(key, [])
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ManifestError(f"{key}: must be a list of at most {MAX_ITEMS} items")
    if not all(isinstance(i, dict) for i in items):
        raise ManifestError(f"{key}: every item must be an object")
    return items


def _key(value: Any, where: str) -> str:
    if not (isinstance(value, str) and _RE_KEY.match(value)):
        raise ManifestError(f"{where}: invalid identifier {value!r}")
    return value


def _action(raw: dict, where: str) -> dict:
    label = _text(raw.get("label"), f"{where}.label")
    kinds = [k for k in ("page", "settings", "url", "task") if k in raw]
    if len(kinds) != 1:
        raise ManifestError(f"{where}: exactly one of page/settings/url/task is required")
    kind = kinds[0]
    if kind in ("page", "settings"):
        return {"label": label, kind: _key(raw[kind], f"{where}.{kind}")}
    if kind == "url":
        url = raw["url"]
        if not (isinstance(url, str) and url.startswith("https://") and len(url) <= 300):
            raise ManifestError(f"{where}.url: only https:// links are allowed")
        if any(c.isspace() for c in url):
            raise ManifestError(f"{where}.url: invalid link")
        return {"label": label, "url": url}
    steps = raw["task"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 5:
        raise ManifestError(f"{where}.task: 1 to 5 steps are required")
    checked = []
    for i, step in enumerate(steps):
        op = step.get("op") if isinstance(step, dict) else None
        params = step.get("params", {}) if isinstance(step, dict) else None
        if op not in PLUGIN_OPERATIONS:
            raise ManifestError(f"{where}.task[{i}]: operation {op!r} is not allowed for plugins")
        if not isinstance(params, dict) or not all(isinstance(v, str) for v in params.values()):
            raise ManifestError(f"{where}.task[{i}]: params must be text values")
        try:
            checked.append({"op": op, "params": validate(op, params)})
        except ValidationError as exc:
            raise ManifestError(f"{where}.task[{i}]: {exc}") from exc
    return {"label": label, "task": checked}


def _test(raw: Any, where: str) -> dict:
    if not isinstance(raw, dict) or raw.get("type") not in TEST_TYPES:
        raise ManifestError(f"{where}: type must be one of {', '.join(TEST_TYPES)}")
    kind = raw["type"]
    test: dict[str, Any] = {"type": kind, "expect": raw.get("expect", True)}
    if not isinstance(test["expect"], bool):
        raise ManifestError(f"{where}.expect: must be true or false")
    field_name = {
        "command_exists": "command",
        "service_active": "service",
        "package_installed": "package",
        "kernel_module_loaded": "module",
    }.get(kind)
    if field_name:
        value = raw.get(field_name)
        if not (isinstance(value, str) and _RE_NAME.match(value)):
            raise ManifestError(f"{where}.{field_name}: invalid name {value!r}")
        test[field_name] = value
        return test
    path = raw.get("path")
    if not (
        isinstance(path, str)
        and path.startswith("/")
        and len(path) <= 256
        and ".." not in Path(path).parts
    ):
        raise ManifestError(f"{where}.path: an absolute path is required")
    test["path"] = path
    if kind == "disk_free":
        min_gb = raw.get("min_gb")
        if not (isinstance(min_gb, (int, float)) and 0 < min_gb <= 10_000):
            raise ManifestError(f"{where}.min_gb: must be a number of gigabytes")
        test["min_gb"] = min_gb
    return test


def parse(text: str) -> dict:
    """JSON metnini doğrular, temizlenmiş tanımı döner (yalnızca bilinen alanlar kalır)."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ManifestError("manifest is too large")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ManifestError(f"schema must be {SCHEMA}")
    plugin_id = data.get("id")
    if not (isinstance(plugin_id, str) and len(plugin_id) <= 64 and _RE_ID.match(plugin_id)):
        raise ManifestError("id must look like org.example.name")
    if plugin_id.startswith("linwas.") or plugin_id == "linwas":
        raise ManifestError("the linwas.* namespace is reserved")
    version = data.get("version")
    if not (isinstance(version, str) and _RE_VERSION.match(version)):
        raise ManifestError("version must look like 1.0.0")
    publisher = data.get("publisher", "")
    if not isinstance(publisher, str) or not publisher.strip() or len(publisher) > 80:
        raise ManifestError("publisher is required")
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "id": plugin_id,
        "version": version,
        "name": _text(data.get("name"), "name"),
        "description": _opt_text(data.get("description"), "description"),
        "publisher": publisher.strip(),
    }
    homepage = data.get("homepage")
    if homepage is not None:
        if not (isinstance(homepage, str) and homepage.startswith("https://")):
            raise ManifestError("homepage must be an https:// link")
        out["homepage"] = homepage
    min_linwas = data.get("min_linwas")
    if min_linwas is not None:
        if not (isinstance(min_linwas, str) and _RE_VERSION.match(min_linwas)):
            raise ManifestError("min_linwas must look like 2.0.0")
        out["min_linwas"] = min_linwas

    ids: set[str] = set()

    def unique(value: Any, where: str) -> str:
        key = _key(value, where)
        if key in ids:
            raise ManifestError(f"{where}: duplicate id {key!r}")
        ids.add(key)
        return key

    out["troubleshooting"] = [
        {
            "id": unique(item.get("id"), f"troubleshooting[{i}].id"),
            "title": _text(item.get("title"), f"troubleshooting[{i}].title"),
            "description": _opt_text(item.get("description"), f"troubleshooting[{i}].description"),
            "actions": [
                _action(a, f"troubleshooting[{i}].actions[{j}]")
                for j, a in enumerate(_list(item, "actions"))
            ],
        }
        for i, item in enumerate(_list(data, "troubleshooting"))
    ]
    out["checks"] = [
        {
            "id": unique(item.get("id"), f"checks[{i}].id"),
            "ok": _text(item.get("ok"), f"checks[{i}].ok"),
            "problem": _text(item.get("problem"), f"checks[{i}].problem"),
            "test": _test(item.get("test"), f"checks[{i}].test"),
            "fixes": [
                _action(a, f"checks[{i}].fixes[{j}]") for j, a in enumerate(_list(item, "fixes"))
            ],
        }
        for i, item in enumerate(_list(data, "checks"))
    ]
    guide = []
    for i, item in enumerate(_list(data, "guide")):
        keywords = item.get("keywords")
        if not (
            isinstance(keywords, list)
            and 1 <= len(keywords) <= 10
            and all(isinstance(k, str) and 0 < len(k) <= 60 for k in keywords)
        ):
            raise ManifestError(f"guide[{i}].keywords: 1 to 10 short words are required")
        kind = item.get("kind", "concept")
        if kind not in GUIDE_KINDS:
            raise ManifestError(f"guide[{i}].kind: must be one of {', '.join(GUIDE_KINDS)}")
        entry = {"keywords": keywords, "text": _text(item.get("text"), f"guide[{i}].text")}
        entry["kind"] = kind
        for target in ("page", "settings"):
            if target in item:
                entry[target] = _key(item[target], f"guide[{i}].{target}")
        guide.append(entry)
    out["guide"] = guide
    if not (out["troubleshooting"] or out["checks"] or out["guide"]):
        raise ManifestError("the plugin adds nothing")
    return out


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".")[:3] if p.isdigit())


# --- İzin özeti ---


@dataclass
class Permissions:
    """Kurulumdan önce kullanıcıya gösterilecek her şey."""

    tasks: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)  # (op, risk, params)
    pages: list[str] = field(default_factory=list)
    settings: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    reads: list[tuple[str, str]] = field(default_factory=list)  # (denetim türü, hedef)

    def keys(self) -> set[str]:
        """Karşılaştırma için: güncelleme yeni izin istiyor mu."""
        out = {f"task:{op}:{json.dumps(p, sort_keys=True)}" for op, _r, p in self.tasks}
        out |= {f"page:{p}" for p in self.pages} | {f"settings:{s}" for s in self.settings}
        out |= {f"url:{u}" for u in self.urls} | {f"read:{k}:{t}" for k, t in self.reads}
        return out

    @property
    def highest_risk(self) -> str:
        order = [RiskLevel.LOW.value, RiskLevel.MEDIUM.value, RiskLevel.HIGH.value]
        risks = [r for _o, r, _p in self.tasks]
        return max(risks, key=order.index) if risks else ""


def permissions(manifest: dict) -> Permissions:
    perms = Permissions()

    def add(action: dict) -> None:
        if "task" in action:
            for step in action["task"]:
                entry = (step["op"], OPERATIONS[step["op"]].risk.value, step["params"])
                if entry not in perms.tasks:
                    perms.tasks.append(entry)
        for kind, bucket in (("page", perms.pages), ("settings", perms.settings)):
            if kind in action and action[kind] not in bucket:
                bucket.append(action[kind])
        if "url" in action and action["url"] not in perms.urls:
            perms.urls.append(action["url"])

    for card in manifest["troubleshooting"]:
        for action in card["actions"]:
            add(action)
    for check in manifest["checks"]:
        test = check["test"]
        target = next(
            (test[k] for k in ("command", "service", "package", "module", "path") if k in test), ""
        )
        if (test["type"], target) not in perms.reads:
            perms.reads.append((test["type"], target))
        for action in check["fixes"]:
            add(action)
    for entry in manifest["guide"]:
        add(entry)
    return perms


# --- Denetimlerin çalıştırılması (yalnızca okur) ---


def _run_quiet(cmd: list[str]) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=False, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ""
    return r.returncode, r.stdout.strip()


def run_test(test: dict) -> tuple[bool, str]:
    """(koşul sağlandı mı == expect, ayrıntı). Kabuk yok; yalnızca okuyan komutlar."""
    kind = test["type"]
    if kind == "command_exists":
        found = shutil.which(test["command"]) is not None
        detail = test["command"]
    elif kind == "file_exists":
        found = Path(test["path"]).exists()
        detail = test["path"]
    elif kind == "service_active":
        _code, out = _run_quiet(["systemctl", "is-active", "--", test["service"]])
        found = out == "active"
        detail = f"{test['service']}: {out or 'unknown'}"
    elif kind == "package_installed":
        _code, out = _run_quiet(["dpkg-query", "-W", "-f=${Status}", "--", test["package"]])
        found = out.endswith("installed") and "not-installed" not in out
        detail = test["package"]
    elif kind == "kernel_module_loaded":
        found = Path("/sys/module", test["module"]).is_dir()
        detail = test["module"]
    else:  # disk_free
        try:
            free_gb = shutil.disk_usage(test["path"]).free / 1024**3
        except OSError:
            return True, f"{test['path']}: not found"
        found = free_gb >= test["min_gb"]
        detail = f"{free_gb:.1f} GB free"
    return found == test["expect"], detail


# --- Eklenti nesnesi ---


def _pick(text: dict[str, str], lang: str) -> str:
    return text.get(lang) or text.get(lang.split("_")[0]) or text.get("en", "")


def _to_action(action: dict, lang: str) -> PluginAction:
    label = _pick(action["label"], lang)
    if "task" in action:
        return PluginAction(
            "task", label, steps=[(s["op"], dict(s["params"])) for s in action["task"]]
        )
    for kind in ("page", "settings", "url"):
        if kind in action:
            return PluginAction(kind, label, target=action[kind])
    raise ManifestError("unknown action")


class DeclarativePlugin(PluginBase):
    """`manifest.json`'dan kurulan eklenti; Python kodu yoktur."""

    def __init__(self, manifest: dict, source: str, lang: str = "en") -> None:
        self._m = manifest
        self._lang = lang
        self.source = source

    @property
    def manifest(self) -> dict:
        return self._m

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            id=self._m["id"],
            name=_pick(self._m["name"], self._lang),
            version=self._m["version"],
            publisher=self._m["publisher"],
            description=_pick(self._m["description"], self._lang),
        )

    def troubleshooting_cards(self) -> list[TroubleshootingCard]:
        return [
            TroubleshootingCard(
                id=f"{self._m['id']}.{c['id']}",
                symptom=_pick(c["title"], self._lang),
                description=_pick(c["description"], self._lang),
                actions=[_to_action(a, self._lang) for a in c["actions"]],
            )
            for c in self._m["troubleshooting"]
        ]

    def scan_checks(self) -> list[ScanCheck]:
        return [
            ScanCheck(
                id=f"{self._m['id']}.{c['id']}",
                label=_pick(c["ok"], self._lang),
                problem_label=_pick(c["problem"], self._lang),
                run=lambda test=c["test"]: run_test(test),
                fixes=[_to_action(a, self._lang) for a in c["fixes"]],
            )
            for c in self._m["checks"]
        ]

    def guide_entries(self) -> list[GuideEntry]:
        return [
            GuideEntry(
                keywords=list(g["keywords"]),
                label=_pick(g["text"], self._lang),
                target_page_id=g.get("page", ""),
                settings_launcher_key=g.get("settings", ""),
                kind=g["kind"],
            )
            for g in self._m["guide"]
        ]


# --- Kurulum ---


@dataclass
class Installed:
    manifest: dict
    source: str  # SOURCE_CATALOG | SOURCE_DEVELOPER
    sha256: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def install(text: str, source: str, base: Path | None = None) -> dict:
    """Doğrulanmış tanımı eklenti klasörüne yazar; tanımı döner."""
    if source not in (SOURCE_CATALOG, SOURCE_DEVELOPER):
        raise ManifestError("unknown source")
    manifest = parse(text)
    target = (base or plugins_dir()) / manifest["id"]
    target.mkdir(parents=True, exist_ok=True)
    (target / MANIFEST).write_text(text, encoding="utf-8")
    (target / INSTALL_INFO).write_text(
        json.dumps({"source": source, "sha256": sha256_text(text)}), encoding="utf-8"
    )
    return manifest


def uninstall(plugin_id: str, base: Path | None = None) -> None:
    if not _RE_ID.match(plugin_id):
        raise ManifestError("invalid id")
    shutil.rmtree((base or plugins_dir()) / plugin_id, ignore_errors=True)


def installed(base: Path | None = None) -> tuple[list[Installed], list[tuple[str, str]]]:
    """Kurulu kodsuz eklentiler ve okunamayanlar [(klasör adı, hata)]."""
    root = base or plugins_dir()
    found: list[Installed] = []
    errors: list[tuple[str, str]] = []
    if not root.is_dir():
        return found, errors
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        try:
            text = (folder / MANIFEST).read_text(encoding="utf-8")
            info = json.loads((folder / INSTALL_INFO).read_text(encoding="utf-8"))
            manifest = parse(text)
            if manifest["id"] != folder.name:
                raise ManifestError("folder name does not match the id")
            source = info.get("source")
            if source not in (SOURCE_CATALOG, SOURCE_DEVELOPER):
                raise ManifestError("unknown source")
            # Elle değiştirilmiş katalog eklentisi artık katalogdaki değildir
            if source == SOURCE_CATALOG and info.get("sha256") != sha256_text(text):
                raise ManifestError("the file was changed after installation")
            found.append(Installed(manifest, source, sha256_text(text)))
        except (OSError, ValueError) as exc:
            errors.append((folder.name, str(exc)))
    return found, errors
