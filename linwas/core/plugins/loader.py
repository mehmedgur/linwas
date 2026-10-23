"""Eklenti yükleyici.

Eklentiler Python entry point mekanizmasıyla bildirilir:

    [project.entry-points."linwas.plugins"]
    my_plugin = "my_package.plugin:MyPlugin"

Yükleyici bu grubu tarar, sınıfları örnekler ve API sürümünü doğrular.
Uyumsuz veya yüklenemeyen eklentiler kapatılır; kullanıcıya bildirilir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from linwas.core.plugins import SOURCE_BUILTIN, PluginBase, PluginMeta

logger = logging.getLogger(__name__)

SUPPORTED_API_VERSION = "1"

# Engelleme nedenleri (Ayarlar › Eklentiler çevirir)
BLOCKED_DEVELOPER = "developer_mode_off"
BLOCKED_REVOKED = "revoked"
BLOCKED_TOO_NEW = "needs_newer_linwas"

ENTRY_POINT_GROUP = "linwas.plugins"


@dataclass
class LoadResult:
    plugin: PluginBase | None
    meta: PluginMeta | None
    error: str | None


def _load_entry_point(ep: object) -> LoadResult:
    """Tek bir entry point'i yükler; hata durumunda LoadResult.error dolu döner."""
    try:
        # importlib.metadata entry point nesnesi; .load() sınıfı döner
        cls = ep.load()  # type: ignore[union-attr]
    except Exception as exc:
        return LoadResult(plugin=None, meta=None, error=f"Yüklenemedi: {exc}")

    if not (isinstance(cls, type) and issubclass(cls, PluginBase)):
        return LoadResult(
            plugin=None,
            meta=None,
            error=f"{cls!r} PluginBase'den türetilmemiş",
        )

    try:
        instance: PluginBase = cls()
        meta = instance.meta
    except Exception as exc:
        return LoadResult(plugin=None, meta=None, error=f"Örneklenemedi: {exc}")

    if meta.api_version != SUPPORTED_API_VERSION:
        return LoadResult(
            plugin=None,
            meta=meta,
            error=(
                f"API sürümü uyumsuz: {meta.api_version!r} (desteklenen: {SUPPORTED_API_VERSION!r})"
            ),
        )

    return LoadResult(plugin=instance, meta=meta, error=None)


# Uygulamanın yüklediği eklentiler (arayüz dışı modüller, ör. AI bağlamı, buradan okur)
_active: PluginLoader | None = None


def set_active(loader: PluginLoader) -> None:
    global _active
    _active = loader


def active() -> PluginLoader | None:
    return _active


class PluginLoader:
    """Kurulu eklentileri keşfeder ve yükler.

    `disabled` içindeki kimlikler yüklenir ama etkin sayılmaz (Ayarlar'da açılabilsin diye
    listede kalır); kapatılamaz (`required`) eklentiler her zaman etkindir.
    """

    def __init__(self, disabled: set[str] | None = None) -> None:
        self._plugins: list[PluginBase] = []
        self._disabled = set(disabled or ())
        self._blocked: dict[str, str] = {}  # kimlik → engelleme nedeni (BLOCKED_*)
        self._errors: list[tuple[str, str]] = []  # (eklenti adı, hata mesajı)

    def discover(self) -> None:
        """Entry point grubunu tarayarak tüm eklentileri yükler."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=ENTRY_POINT_GROUP)
        except Exception as exc:
            logger.warning("Entry point tarama hatası: %s", exc)
            return

        for ep in eps:
            result = _load_entry_point(ep)
            if result.plugin is not None:
                self._plugins.append(result.plugin)
                logger.info(
                    "Eklenti yüklendi: %s v%s",
                    result.meta.id if result.meta else ep.name,
                    result.meta.version if result.meta else "?",
                )
            else:
                name = result.meta.id if result.meta else getattr(ep, "name", str(ep))
                msg = result.error or "Bilinmeyen hata"
                self._errors.append((name, msg))
                logger.warning("Eklenti kapatıldı (%s): %s", name, msg)

    def plugins(self) -> list[PluginBase]:
        """Etkin eklenti örneklerini döner."""
        return [p for p in self._plugins if self.is_enabled(p)]

    def all_plugins(self) -> list[PluginBase]:
        """Kapalılar dahil yüklenen bütün eklentiler (Ayarlar › Eklentiler listesi)."""
        return list(self._plugins)

    def is_enabled(self, plugin: PluginBase) -> bool:
        if plugin.meta.id in self._blocked:
            return False
        return plugin.required or plugin.meta.id not in self._disabled

    def blocked_reason(self, plugin: PluginBase) -> str:
        """Kullanıcı açsa da çalışmama nedeni (İngilizce kod; arayüz çevirir)."""
        return self._blocked.get(plugin.meta.id, "")

    def add_plugin(self, plugin: PluginBase, blocked: str = "") -> None:
        """Hazır eklenti örneğini ekler (kodsuz eklentiler); `blocked` doluysa çalışmaz."""
        if any(p.meta.id == plugin.meta.id for p in self._plugins):
            self.add_error(plugin.meta.id, "duplicate plugin id")
            return
        self._plugins.append(plugin)
        if blocked:
            self._blocked[plugin.meta.id] = blocked

    def load_declarative(self, lang: str, developer_mode: bool) -> None:
        """Kurulu kodsuz eklentileri yükler.

        Engellenenler listede kalır (kaldırılabilsin diye): geliştirici kipi kapalıyken imzasız
        eklentiler, katalogdan geri çekilenler, daha yeni Linwas isteyenler.
        """
        from linwas import __version__
        from linwas.core.plugins import SOURCE_DEVELOPER, catalog, declarative

        found, errors = declarative.installed()
        for name, message in errors:
            self.add_error(name, message)
        revoked = catalog.cached()
        current = declarative.version_tuple(__version__)
        for item in found:
            plugin = declarative.DeclarativePlugin(item.manifest, item.source, lang)
            blocked = ""
            if item.source == SOURCE_DEVELOPER and not developer_mode:
                blocked = BLOCKED_DEVELOPER
            elif revoked and revoked.revoked_reason(item.manifest["id"], item.manifest["version"]):
                blocked = BLOCKED_REVOKED
            elif declarative.version_tuple(item.manifest.get("min_linwas", "0.0.0")) > current:
                blocked = BLOCKED_TOO_NEW
            self.add_plugin(plugin, blocked)

    def gate(self, name: str) -> list[Any]:
        """Etkin eklentilerin bir kapısının sonuçlarını birleştirir (ör. "scan_checks").

        Bozuk bir eklentinin hatası diğerlerini durdurmaz; hata listeye yazılır.
        """
        out: list[Any] = []
        for plugin in self.plugins():
            try:
                out.extend(getattr(plugin, name)())
            except Exception as exc:
                self.add_error(plugin.meta.id, f"{name}: {exc}")
        return out

    def errors(self) -> list[tuple[str, str]]:
        """(eklenti adı, hata) çiftlerini döner."""
        return list(self._errors)

    def add_error(self, name: str, message: str) -> None:
        """Yükleme sonrası (ör. sayfa oluşturulurken) oluşan hatayı kaydeder (yinelenmez)."""
        if (name, message) not in self._errors:
            self._errors.append((name, message))

    def load_class(self, cls: type[PluginBase]) -> PluginBase | None:
        """Doğrudan sınıf vererek eklenti yükler (testler ve yerleşik eklentiler için)."""
        try:
            instance = cls()
            meta = instance.meta
        except Exception as exc:
            logger.warning("Eklenti örneklenemedi (%s): %s", cls, exc)
            return None

        if meta.api_version != SUPPORTED_API_VERSION:
            logger.warning("Eklenti API sürümü uyumsuz (%s): %s", meta.id, meta.api_version)
            return None

        instance.source = SOURCE_BUILTIN
        self._plugins.append(instance)
        return instance
