"""Ayarlar › Eklentiler: kurulu eklentiler, Linwas kataloğu ve geliştirici kipi.

Kodsuz eklentiler `core/plugins/declarative.py`, katalog `core/plugins/catalog.py`. Kurma,
güncelleme ve kaldırma kullanıcı klasöründe olur (root gerekmez); değişiklik Linwas yeniden
açılınca geçerli.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.core import app_settings
from linwas.core.plugins import (
    SOURCE_BUILTIN,
    SOURCE_CATALOG,
    SOURCE_DEVELOPER,
    PluginBase,
    catalog,
    declarative,
)
from linwas.core.plugins.loader import (
    BLOCKED_DEVELOPER,
    BLOCKED_REVOKED,
    BLOCKED_TOO_NEW,
    PluginLoader,
)
from linwas.ui import icons
from linwas.ui.dialogs.plugin_permissions import PluginPermissionsDialog
from linwas.ui.sidebar import tr as sidebar_tr


def tr(text: str) -> str:
    return QCoreApplication.translate("PluginsSettings", text)


class _Job(QThread):
    done = Signal(object)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # hata nesnesi olarak döner, arayüz çevirir
            self.done.emit(exc)


def _catalog_error_text(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    return {
        "not_configured": tr("This Linwas build has no plugin catalog address."),
        "network": tr("The catalog could not be reached. Check the internet connection."),
        "signature": tr(
            "The catalog could not be verified with the Linwas key. Nothing was installed."
        ),
        "checksum": tr("The downloaded plugin does not match the catalog. Nothing was installed."),
        "format": tr("The catalog or plugin file is damaged. Nothing was installed."),
    }.get(code, tr("Something went wrong: {error}").format(error=exc))


def _blocked_text(code: str) -> str:
    return {
        BLOCKED_DEVELOPER: tr("Not running: developer mode is off."),
        BLOCKED_REVOKED: tr("Turned off: Linwas withdrew this plugin from the catalog."),
        BLOCKED_TOO_NEW: tr("Not running: it needs a newer Linwas."),
    }.get(code, code)


def _pick(text: dict[str, str], lang: str) -> str:
    return text.get(lang) or text.get("en", "")


class PluginsPanel:
    """Ayarlar bölümündeki eklenti kartları; `section.card(...)` ile kart açar."""

    def __init__(self, section: object, page: QWidget) -> None:
        self._page = page
        self._jobs: list[_Job] = []
        self._settings = app_settings.load()
        self._lang = self._settings.language

        # Kurulu eklentiler
        card = section.card(tr("Installed plugins"))
        intro = QLabel(
            tr(
                "Plugins add pages, checks and help to Linwas. Built-in plugins come with "
                "Linwas; official ones come from the signed Linwas package repository; "
                "catalog plugins contain no program code and can only use safe, listed tasks."
            ),
            card,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        card.layout.addWidget(intro)
        self._list = QVBoxLayout()
        self._list.setSpacing(8)
        card.layout.addLayout(self._list)
        self._restart = QLabel(
            tr("Restart Linwas to apply the change: quit it completely, then open it again."),
            card,
        )
        self._restart.setObjectName("Warning")
        self._restart.setWordWrap(True)
        self._restart.hide()
        card.layout.addWidget(self._restart)

        # Katalog
        card = section.card(tr("Plugin catalog"))
        desc = QLabel(
            tr(
                "Plugins checked and signed by Linwas. The list and every file are verified "
                "with the Linwas key before anything is installed."
            ),
            card,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        card.layout.addWidget(desc)
        row = QHBoxLayout()
        self._refresh_btn = QPushButton(tr("Check the catalog"), card)
        self._refresh_btn.setProperty("primary", True)
        self._refresh_btn.clicked.connect(self._refresh_catalog)
        row.addWidget(self._refresh_btn)
        self._catalog_status = QLabel("", card)
        self._catalog_status.setWordWrap(True)
        row.addWidget(self._catalog_status, 1)
        card.layout.addLayout(row)
        self._catalog_list = QVBoxLayout()
        self._catalog_list.setSpacing(8)
        card.layout.addLayout(self._catalog_list)
        self._catalog: catalog.Catalog | None = None

        # Geliştirici kipi
        card = section.card(tr("Developer mode"))
        self._dev = QCheckBox(tr("Allow installing plugin files that are not in the catalog"), card)
        self._dev.setChecked(self._settings.plugin_developer_mode)
        self._dev.toggled.connect(self._set_developer_mode)
        card.layout.addWidget(self._dev)
        warn = QLabel(
            tr(
                "For people who write plugins. Such files are not checked by Linwas; they still "
                "cannot run code and every system task asks for your confirmation."
            ),
            card,
        )
        warn.setObjectName("Secondary")
        warn.setWordWrap(True)
        card.layout.addWidget(warn)
        row = QHBoxLayout()
        self._file_btn = QPushButton(tr("Install from file…"), card)
        self._file_btn.clicked.connect(self._install_file)
        row.addWidget(self._file_btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        self._file_btn.setVisible(self._settings.plugin_developer_mode)

    # --- Yardımcılar ---

    def _run(self, fn: Callable[[], object], slot: Callable[[object], None]) -> None:
        job = _Job(fn)
        job.done.connect(slot)
        job.finished.connect(lambda: self._jobs.remove(job))
        self._jobs.append(job)
        job.start()

    def _loader(self) -> PluginLoader:
        loader = getattr(self._page.window(), "plugin_loader", None)
        if loader is None:
            loader = PluginLoader()
            with contextlib.suppress(Exception):
                loader.discover()
        return loader

    def _changed(self) -> None:
        self._restart.show()
        self.reload()

    @staticmethod
    def _name(plugin: PluginBase) -> str:
        if plugin.source != SOURCE_BUILTIN:
            return plugin.meta.name
        own = {"Hardware information": tr("Hardware information")}
        return own.get(plugin.meta.name) or sidebar_tr(plugin.meta.name)

    @staticmethod
    def _summary(plugin: PluginBase) -> str:
        """Eklentinin Linwas'a ne eklediği (kapılardan sayılır)."""
        try:
            pages = [sidebar_tr(p.label) for p in plugin.pages()]
            checks = len(plugin.scan_checks())
            cards = len(plugin.troubleshooting_cards())
            guide = len(plugin.guide_entries())
            ai = type(plugin).ai_context is not PluginBase.ai_context
        except Exception:
            return ""
        parts = []
        if pages:
            parts.append(tr("page: {names}").format(names=", ".join(pages)))
        if checks:
            parts.append(tr("{n} troubleshooting check(s)").format(n=checks))
        if cards:
            parts.append(tr("{n} problem card(s)").format(n=cards))
        if guide:
            parts.append(tr("{n} guide entry(ies)").format(n=guide))
        if ai:
            parts.append(tr("information for the assistant"))
        return tr("Adds: {items}").format(items="; ".join(parts)) if parts else ""

    # --- Kurulu eklentiler ---

    def reload(self) -> None:
        loader = self._loader()
        self._clear(self._list)
        errors: dict[str, list[str]] = {}
        for name, error in loader.errors():
            errors.setdefault(name, []).append(error)
        # Bu oturumda kurulan/kaldırılan kodsuz eklentiler de görünsün (diskten okunur)
        plugins = [
            p for p in loader.all_plugins() if not isinstance(p, declarative.DeclarativePlugin)
        ]
        blocked = {p.meta.id: loader.blocked_reason(p) for p in loader.all_plugins()}
        found, bad = declarative.installed()
        for item in found:
            plugins.append(declarative.DeclarativePlugin(item.manifest, item.source, self._lang))
        for name, message in bad:
            errors.setdefault(name, []).append(message)
        plugins.sort(key=lambda p: (p.source != SOURCE_BUILTIN, self._name(p).casefold()))
        for plugin in plugins:
            pid = plugin.meta.id
            self._list.addWidget(self._row(plugin, blocked.get(pid, ""), errors.pop(pid, [])))
        for name, messages in errors.items():
            lbl = QLabel(f"⚠ {name}: " + "; ".join(messages), self._page)
            lbl.setObjectName("Warning")
            lbl.setWordWrap(True)
            self._list.addWidget(lbl)
        if self._catalog is not None:
            self._show_catalog(self._catalog)

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _row(self, plugin: PluginBase, blocked: str, errors: list[str]) -> QWidget:
        meta = plugin.meta
        frame = QFrame(self._page)
        frame.setObjectName("OptionTile")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)
        glyph = QLabel(frame)
        glyph.setFixedSize(32, 32)
        icons.bind(glyph, "plugin", "tile", 32)
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(8)
        name = QLabel(self._name(plugin), frame)
        name.setObjectName("OptionTitle")
        head.addWidget(name)
        badge = QLabel(
            {
                SOURCE_BUILTIN: tr("Built-in"),
                SOURCE_CATALOG: tr("Catalog"),
                SOURCE_DEVELOPER: tr("Developer"),
            }.get(plugin.source, tr("Official")),
            frame,
        )
        badge.setObjectName("LinwasTag")
        head.addWidget(badge)
        head.addStretch(1)
        info.addLayout(head)
        sub = QLabel(" · ".join(d for d in (meta.version, meta.publisher) if d), frame)
        sub.setObjectName("OptionNote")
        info.addWidget(sub)
        for text in (meta.description, self._summary(plugin)):
            if text:
                lbl = QLabel(text, frame)
                lbl.setObjectName("OptionNote")
                lbl.setWordWrap(True)
                info.addWidget(lbl)
        for text in ([_blocked_text(blocked)] if blocked else []) + [f"⚠ {e}" for e in errors]:
            lbl = QLabel(text, frame)
            lbl.setObjectName("Warning")
            lbl.setWordWrap(True)
            info.addWidget(lbl)
        if isinstance(plugin, declarative.DeclarativePlugin):
            actions = QHBoxLayout()
            perms_btn = QPushButton(tr("Permissions"), frame)
            perms_btn.clicked.connect(lambda: self._show_permissions(plugin))
            actions.addWidget(perms_btn)
            remove_btn = QPushButton(tr("Remove"), frame)
            remove_btn.clicked.connect(lambda: self._remove(plugin))
            actions.addWidget(remove_btn)
            actions.addStretch(1)
            info.addLayout(actions)
        row.addLayout(info, 1)

        if plugin.required:
            req = QLabel(tr("Always on"), frame)
            req.setObjectName("OptionNote")
            req.setToolTip(tr("Other parts of Linwas need this plugin."))
            row.addWidget(req, 0, Qt.AlignmentFlag.AlignTop)
        else:
            toggle = QCheckBox(tr("On"), frame)
            toggle.setChecked(meta.id not in self._settings.disabled_plugins)
            toggle.toggled.connect(lambda on, pid=meta.id: self._set_enabled(pid, on))
            row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignTop)
        return frame

    def _set_enabled(self, plugin_id: str, on: bool) -> None:
        self._settings = app_settings.load()
        disabled = set(self._settings.disabled_plugins)
        (disabled.discard if on else disabled.add)(plugin_id)
        self._settings.disabled_plugins = sorted(disabled)
        app_settings.save(self._settings)
        self._restart.show()

    def _show_permissions(self, plugin: declarative.DeclarativePlugin) -> None:
        meta = plugin.meta
        PluginPermissionsDialog(
            meta.name,
            meta.version,
            meta.publisher,
            plugin.source,
            declarative.permissions(plugin.manifest),
            parent=self._page,
            read_only=True,
        ).exec()

    def _remove(self, plugin: PluginBase) -> None:
        answer = QMessageBox.question(
            self._page,
            tr("Remove plugin"),
            tr("Remove {name}? Its checks, cards and guide entries disappear.").format(
                name=plugin.meta.name
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            declarative.uninstall(plugin.meta.id)
        except (OSError, declarative.ManifestError) as exc:
            QMessageBox.warning(self._page, tr("Remove plugin"), str(exc))
            return
        self._changed()

    # --- Kurma (ortak) ---

    def _confirm_and_install(self, text: str, source: str) -> None:
        try:
            manifest = declarative.parse(text)
        except declarative.ManifestError as exc:
            QMessageBox.warning(
                self._page,
                tr("Install plugin"),
                tr("This is not a valid Linwas plugin.") + f"\n\n{exc}",
            )
            return
        perms = declarative.permissions(manifest)
        current = next(
            (i for i in declarative.installed()[0] if i.manifest["id"] == manifest["id"]), None
        )
        new_keys: set[str] = set()
        if current is not None:
            new_keys = perms.keys() - declarative.permissions(current.manifest).keys()
        dialog = PluginPermissionsDialog(
            _pick(manifest["name"], self._lang),
            manifest["version"],
            manifest["publisher"],
            source,
            perms,
            update=current is not None,
            new_keys=new_keys,
            parent=self._page,
        )
        if dialog.exec() != PluginPermissionsDialog.DialogCode.Accepted:
            return
        try:
            declarative.install(text, source)
        except (OSError, declarative.ManifestError) as exc:
            QMessageBox.warning(self._page, tr("Install plugin"), str(exc))
            return
        self._changed()

    # --- Geliştirici kipi ---

    def _set_developer_mode(self, on: bool) -> None:
        if on:
            answer = QMessageBox.warning(
                self._page,
                tr("Developer mode"),
                tr(
                    "Plugin files outside the catalog are not checked by Linwas. Turn on "
                    "developer mode only if you write or test plugins yourself."
                ),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                self._dev.blockSignals(True)
                self._dev.setChecked(False)
                self._dev.blockSignals(False)
                return
        self._settings = app_settings.load()
        self._settings.plugin_developer_mode = on
        app_settings.save(self._settings)
        self._file_btn.setVisible(on)
        self._restart.show()

    def _install_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._page, tr("Install plugin"), str(Path.home()), tr("Linwas plugin (*.json)")
        )
        if not path:
            return
        try:
            data = Path(path).read_bytes()[: declarative.MAX_FILE_BYTES + 1]
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.warning(self._page, tr("Install plugin"), str(exc))
            return
        self._confirm_and_install(text, SOURCE_DEVELOPER)

    # --- Katalog ---

    def _refresh_catalog(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._catalog_status.setText(tr("Checking…"))
        self._run(catalog.refresh, self._on_catalog)

    def _on_catalog(self, result: object) -> None:
        self._refresh_btn.setEnabled(True)
        if isinstance(result, BaseException):
            self._catalog_status.setText(_catalog_error_text(result))
            return
        self._catalog = result  # type: ignore[assignment]
        count = len(self._catalog.entries)
        self._catalog_status.setText(
            tr("{n} plugin(s) in the catalog.").format(n=count)
            if count
            else tr("The catalog is empty.")
        )
        self._show_catalog(self._catalog)
        # Geri çekilen kurulu eklenti varsa uyar (bir sonraki açılışta kapatılır)
        installed = {i.manifest["id"]: i.manifest["version"] for i in declarative.installed()[0]}
        if any(self._catalog.revoked_reason(pid, ver) for pid, ver in installed.items()):
            self._restart.show()

    def _show_catalog(self, cat: catalog.Catalog) -> None:
        self._clear(self._catalog_list)
        installed = {i.manifest["id"]: i for i in declarative.installed()[0]}
        for entry in cat.entries:
            if cat.revoked_reason(entry.id, entry.version):
                continue
            frame = QFrame(self._page)
            frame.setObjectName("OptionTile")
            row = QHBoxLayout(frame)
            row.setContentsMargins(14, 10, 14, 10)
            info = QVBoxLayout()
            info.setSpacing(2)
            title = QLabel(_pick(entry.name, self._lang), frame)
            title.setObjectName("OptionTitle")
            info.addWidget(title)
            sub = QLabel(f"{entry.version} · {entry.publisher}", frame)
            sub.setObjectName("OptionNote")
            info.addWidget(sub)
            text = _pick(entry.description, self._lang)
            if text:
                lbl = QLabel(text, frame)
                lbl.setObjectName("OptionNote")
                lbl.setWordWrap(True)
                info.addWidget(lbl)
            row.addLayout(info, 1)
            have = installed.get(entry.id)
            if have is None:
                btn = QPushButton(tr("Install"), frame)
                btn.setProperty("primary", True)
            elif declarative.version_tuple(entry.version) > declarative.version_tuple(
                have.manifest["version"]
            ):
                btn = QPushButton(tr("Update"), frame)
                btn.setProperty("primary", True)
            else:
                btn = QPushButton(tr("Installed"), frame)
                btn.setEnabled(False)
            btn.clicked.connect(lambda _c=False, e=entry, b=btn: self._download(e, b))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            self._catalog_list.addWidget(frame)

    def _download(self, entry: catalog.CatalogEntry, button: QPushButton) -> None:
        button.setEnabled(False)
        button.setText(tr("Downloading…"))

        def done(result: object) -> None:
            if isinstance(result, BaseException):
                QMessageBox.warning(self._page, tr("Install plugin"), _catalog_error_text(result))
                if self._catalog is not None:
                    self._show_catalog(self._catalog)
                return
            self._confirm_and_install(str(result), SOURCE_CATALOG)
            if self._catalog is not None:
                self._show_catalog(self._catalog)

        self._run(lambda: catalog.download(entry), done)
