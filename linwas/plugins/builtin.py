"""Yerleşik özellikler eklenti olarak: her biri bir sayfa kapısı sağlar.

Sayfa modülü yalnızca create_page çağrılınca içe aktarılır; çekirdek ve bu
modül Qt'ye bağımlı değildir.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from linwas.core.plugins import PageSpec, PluginBase, PluginMeta


class _PagePlugin(PluginBase):
    """Tek sayfalı yerleşik eklenti."""

    plugin_id = ""
    name = ""
    page = PageSpec(id="", label="")
    factory = ""  # "modül:Sınıf"
    available: Callable[[], bool] = staticmethod(lambda: True)

    @property
    def meta(self) -> PluginMeta:
        from linwas import __version__

        return PluginMeta(id=self.plugin_id, name=self.name, version=__version__)

    def pages(self) -> list[PageSpec]:
        return [self.page] if self.available() else []

    def create_page(self, page_id: str, parent: object) -> object | None:
        if page_id != self.page.id:
            return None
        module_name, cls_name = self.factory.split(":")
        return getattr(importlib.import_module(module_name), cls_name)(parent)


def _plugin(
    plugin_id: str,
    name: str,
    page_id: str,
    factory: str,
    parent: str = "system",
    available: Callable[[], bool] | None = None,
) -> type[_PagePlugin]:
    attrs = {
        "plugin_id": plugin_id,
        "name": name,
        "page": PageSpec(id=page_id, label=name, parent=parent),
        "factory": factory,
    }
    if available is not None:
        attrs["available"] = staticmethod(available)
    return type(f"{page_id.title().replace('_', '')}Plugin", (_PagePlugin,), attrs)


BUILTIN_PLUGINS: tuple[type[_PagePlugin], ...] = (
    _plugin(
        "linwas.migrate", "Import from Windows", "migrate", "linwas.ui.pages.migrate:MigratePage"
    ),
    _plugin("linwas.taskmgr", "Task Manager", "taskmgr", "linwas.ui.pages.taskmgr:TaskMgrPage"),
    _plugin("linwas.cleanup", "Disk Cleanup", "cleanup", "linwas.ui.pages.cleanup:CleanupPage"),
    _plugin(
        "linwas.printers",
        "Hardware & Printers",
        "hardware",
        "linwas.ui.pages.hardware:HardwarePage",
    ),
    _plugin(
        "linwas.backup",
        "Personal Backup",
        "personal_backup",
        "linwas.ui.pages.personal_backup:PersonalBackupPage",
    ),
    _plugin(
        "linwas.power",
        "Power & Battery",
        "power",
        "linwas.ui.pages.power:PowerPage",
    ),
)
