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

from linwas.core.plugins import PluginBase, PluginMeta

logger = logging.getLogger(__name__)

SUPPORTED_API_VERSION = "1"

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


class PluginLoader:
    """Kurulu eklentileri keşfeder ve yükler."""

    def __init__(self) -> None:
        self._plugins: list[PluginBase] = []
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
        """Yüklenen eklenti örneklerini döner."""
        return list(self._plugins)

    def errors(self) -> list[tuple[str, str]]:
        """(eklenti adı, hata) çiftlerini döner."""
        return list(self._errors)

    def add_error(self, name: str, message: str) -> None:
        """Yükleme sonrası (ör. sayfa oluşturulurken) oluşan hatayı kaydeder."""
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

        self._plugins.append(instance)
        return instance
