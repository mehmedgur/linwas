"""Programlar sayfası: arama (APT, Flatpak, Windows alternatifleri, üçüncü taraf)
ve Kurulu programlar sekmesi."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.apt_search import AptPackage, expand_query, search_apt
from linwas.backend.flatpak import FlatpakPackage, search_flatpak
from linwas.backend.flatpak import is_available as flatpak_ok
from linwas.backend.installed_apps import InstalledApp, is_other_version, match_installed
from linwas.core.tasks import Task, TaskStep
from linwas.ui.dialogs.remove_app import RemovalFlow, RemovalRequest
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.installed_apps import InstalledAppsView, source_badge_text
from linwas.ui.widgets.card import Card

_DATA = Path(__file__).resolve().parent.parent.parent / "data"


def tr(text: str) -> str:
    return QCoreApplication.translate("SoftwarePage", text)


def _load_json(name: str) -> Any:
    try:
        return json.loads((_DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if name.endswith(".json") and "alternatives" in name else []


# --- Veri ---


@dataclass
class ThirdPartyApp:
    id: str
    name: str
    description: str
    package: str
    key_url: str
    keyring_path: str
    source_line: str
    list_name: str


def _load_third_party() -> list[ThirdPartyApp]:
    raw = _load_json("third_party_apps.json")
    return [ThirdPartyApp(**r) for r in raw if isinstance(r, dict)]


def _windows_alts(query: str) -> dict[str, Any] | None:
    """Sorgu bir Windows uygulaması ise alternatifler sözlüğünü döner."""
    mapping = _load_json("windows_alternatives.json")
    q = query.strip().lower()
    return mapping.get(q)


# --- Worker ---


@dataclass
class _SearchResult:
    apt: list[AptPackage]
    flatpak: list[FlatpakPackage]
    extra_terms: list[str]  # Türkçe sorgu için ayrıca aranan İngilizce terimler


class _DebWorker(QThread):
    done = Signal(object)  # DebInfo

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        from linwas.backend.deb_inspect import inspect

        self.done.emit(inspect(self._path))


class _SearchWorker(QThread):
    done = Signal(_SearchResult)

    def __init__(self, query: str) -> None:
        super().__init__()
        self._query = query

    def run(self) -> None:
        terms = expand_query(self._query)
        apt: list[AptPackage] = []
        flatpak: list[FlatpakPackage] = []
        use_flatpak = flatpak_ok()
        for q in [self._query, *terms]:
            for pkg in search_apt(q):
                if all(p.name != pkg.name for p in apt):
                    apt.append(pkg)
            if use_flatpak:
                for fp in search_flatpak(q):
                    if all(f.app_id != fp.app_id for f in flatpak):
                        flatpak.append(fp)
        # Masaüstü uygulamaları önce
        apt.sort(key=lambda p: p.graphical is not True)
        self.done.emit(_SearchResult(apt=apt[:40], flatpak=flatpak[:20], extra_terms=terms))


# --- Paket satırı ---


class _ResultRow(QWidget):
    install_apt = Signal(str)  # package name
    install_flatpak = Signal(str)  # app_id
    install_third_party = Signal(str)  # third_party id
    remove_clicked = Signal(str, str, str)  # (kaynak, kimlik, görünen ad)

    def __init__(
        self,
        name: str,
        description: str,
        version: str,
        source: str,  # "apt" | "flatpak" | "third-party"
        installed: bool,
        pkg_id: str,  # apt name veya flatpak app_id
        parent: QWidget | None = None,
        other_version: str = "",  # kurulu başka sürümün görünen adı
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(8)

        # Sol: isim + açıklama
        info = QVBoxLayout()
        name_lbl = QLabel(name, self)
        name_lbl.setStyleSheet("font-weight: bold;")
        info.addWidget(name_lbl)
        if description:
            desc_lbl = QLabel(description, self)
            desc_lbl.setObjectName("Secondary")
            desc_lbl.setWordWrap(True)
            info.addWidget(desc_lbl)
        if other_version:
            note = QLabel(
                tr("Another version of this program is already installed: {name}").format(
                    name=other_version
                ),
                self,
            )
            note.setStyleSheet("color:#9d5d00;")
            note.setWordWrap(True)
            info.addWidget(note)
        row.addLayout(info, 1)

        # Kaynak rozeti
        source_colors = {
            "apt": ("#0067c0", "#e3f2fd", "APT"),
            "flatpak": ("#5c35cc", "#ede7f6", "Flatpak"),
            "third-party": ("#9d5d00", "#fff3cc", tr("3rd Party")),
        }
        if source in source_colors:
            fg, bg, label = source_colors[source]
            badge = QLabel(label, self)
            badge.setStyleSheet(
                f"background-color:{bg}; color:{fg}; border-radius:4px;"
                " padding:1px 7px; font-size:11px; font-weight:bold;"
            )
            row.addWidget(badge)

        # Versiyon
        if version:
            ver_lbl = QLabel(version, self)
            ver_lbl.setObjectName("Secondary")
            row.addWidget(ver_lbl)

        # Buton: kurulu programda "Kur" yerine "Kaldır"
        if installed:
            lbl = QLabel("✓ " + tr("Installed"), self)
            lbl.setStyleSheet("color:#0e7a0e; font-weight:bold;")
            row.addWidget(lbl)
            if source in ("apt", "flatpak"):
                remove = QPushButton(tr("Remove"), self)
                remove.setAccessibleName(tr("Remove {name}").format(name=name))
                remove.setFixedWidth(80)
                remove.clicked.connect(lambda: self.remove_clicked.emit(source, pkg_id, name))
                row.addWidget(remove)
        else:
            btn = QPushButton(tr("Install"), self)
            btn.setProperty("primary", True)
            btn.setFixedWidth(80)
            if source == "apt":
                btn.clicked.connect(lambda: self.install_apt.emit(pkg_id))
            elif source == "flatpak":
                btn.clicked.connect(lambda: self.install_flatpak.emit(pkg_id))
            elif source == "third-party":
                btn.clicked.connect(lambda: self.install_third_party.emit(pkg_id))
            row.addWidget(btn)


# --- Windows alternatif banner ---


class _AltBanner(Card):
    install_apt = Signal(str)
    install_flatpak = Signal(str)

    def __init__(
        self,
        windows_name: str,
        alt: dict[str, Any],
        parent: QWidget | None = None,
        installed: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.layout.addWidget(
            QLabel(
                tr("Looking for {win}? Try these Linux alternatives:").format(
                    win=alt.get("label", windows_name)
                ),
                self,
            )
        )
        btn_row = QHBoxLayout()
        installed = installed or set()
        for pkg in alt.get("apt", []):
            b = QPushButton(f"APT: {pkg}", self)
            if pkg in installed:
                # Zaten kurulu: kurma düğmesi yerine bilgi
                b.setText(f"✓ APT: {pkg}")
                b.setEnabled(False)
                b.setToolTip(tr("Installed"))
            b.clicked.connect(lambda _=None, p=pkg: self.install_apt.emit(p))
            btn_row.addWidget(b)
        for app_id in alt.get("flatpak", []):
            short = app_id.split(".")[-1]
            b = QPushButton(f"Flatpak: {short}", self)
            if app_id in installed:
                b.setText(f"✓ Flatpak: {short}")
                b.setEnabled(False)
                b.setToolTip(tr("Installed"))
            b.clicked.connect(lambda _=None, a=app_id: self.install_flatpak.emit(a))
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        self.layout.addLayout(btn_row)


# --- Sayfa ---


class SoftwarePage(BasePage):
    """Programlar sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _SearchWorker | None = None
        # Yerine yenisi başlatılan aramalar bitene kadar burada tutulur (silinirse Qt çöker)
        self._old_workers: list[_SearchWorker] = []
        self._last_result: _SearchResult | None = None
        self._third_party = _load_third_party()
        self._removal = RemovalFlow(self)
        self._removal.task_ready.connect(self.task_run_now)

        # Debounce timer
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._do_search)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        # Arama kutusu
        self._search = QLineEdit(content)
        self._search.setPlaceholderText(
            tr("Search for apps or type a Windows app name (e.g. Photoshop, Word)…")
        )
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_text_changed)
        self._search.setMinimumHeight(36)
        outer.addWidget(self._search)

        deb_row = QHBoxLayout()
        deb_row.addStretch(1)
        deb_btn = QPushButton(tr("Install a .deb file…"), content)
        deb_btn.setToolTip(tr("Linwas checks the file before installing it."))
        deb_btn.clicked.connect(self._pick_deb)
        deb_row.addWidget(deb_btn)
        outer.addLayout(deb_row)

        # Flatpak yok uyarısı
        if not flatpak_ok():
            info = QLabel(tr("Flatpak is not installed. Only APT packages will be shown."), content)
            info.setObjectName("Secondary")
            outer.addWidget(info)

        # Durum / sonuç alanı
        self._status_lbl = QLabel(tr("Type to search…"), content)
        self._status_lbl.setObjectName("Secondary")
        outer.addWidget(self._status_lbl)

        # Sonuç kapsayıcısı
        self._results_widget = QWidget(content)
        self._results_layout = QVBoxLayout(self._results_widget)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(0)
        outer.addWidget(self._results_widget)

        outer.addStretch(1)
        scroll.setWidget(content)

        self._installed = InstalledAppsView(self)
        self._installed.task_run_now.connect(self.task_run_now)
        # Kurulu liste geç gelirse son arama "zaten kurulu" bilgisiyle yeniden çizilir
        self._installed.apps_loaded.connect(self._rerender_results)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(scroll, tr("Search"))
        self._tabs.addTab(self._installed, tr("Installed programs"))

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(24, 20, 24, 20)
        page_layout.setSpacing(8)
        title = QLabel(tr("Software"), self)
        title.setObjectName("H1")
        page_layout.addWidget(title)
        page_layout.addWidget(self._tabs, 1)

    def on_tasks_finished(self) -> None:
        # Kurulum/kaldırma sonrası kurulu bilgisi değişmiş olabilir
        if self._installed.isVisible():
            self._installed.reload()
        else:
            self._installed.mark_stale()
        if len(self._search.text().strip()) >= 2:
            self._do_search()

    def _on_text_changed(self, text: str) -> None:
        if len(text.strip()) < 2:
            self._clear_results()
            self._status_lbl.setText(tr("Type to search…"))
            return
        self._status_lbl.setText(tr("Searching…"))
        self._debounce.start()

    def _do_search(self) -> None:
        query = self._search.text().strip()
        if len(query) < 2:
            return
        if self._worker and self._worker.isRunning():
            # Eski aramanın sonucu yok sayılır; iş parçacığı kendi bitene kadar yaşar
            old = self._worker
            old.done.disconnect(self._on_results)
            self._old_workers.append(old)
            old.finished.connect(lambda w=old: self._old_workers.remove(w))

        # "Zaten kurulu" denetimi için kurulu programlar arka planda bir kez yüklenir
        if not self._installed.is_loaded:
            self._installed.reload()

        self._worker = _SearchWorker(query)
        self._worker.done.connect(self._on_results)
        self._worker.start()

    def _clear_results(self) -> None:
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _rerender_results(self) -> None:
        if self._last_result is not None and len(self._search.text().strip()) >= 2:
            self._on_results(self._last_result)

    def _on_results(self, result: _SearchResult) -> None:
        self._last_result = result
        self._clear_results()
        query = self._search.text().strip()
        installed_apps = self._installed.apps

        # Aranan program zaten kurulu mu?
        matches = match_installed(query, installed_apps)
        if matches:
            banner = _InstalledBanner(matches[:5], self._results_widget)
            banner.remove_clicked.connect(self._on_remove_installed)
            self._results_layout.addWidget(banner)
            self._results_layout.addSpacing(8)

        # Windows alternatif banner
        alt = _windows_alts(query)
        if alt:
            installed_ids = {a.id for a in installed_apps}
            banner = _AltBanner(query, alt, self._results_widget, installed_ids)
            banner.install_apt.connect(self._install_apt_clicked)
            banner.install_flatpak.connect(self._install_flatpak_clicked)
            self._results_layout.addWidget(banner)
            self._results_layout.addSpacing(8)

        # APT + Flatpak sonuçlarını birleştir (önce APT)
        total = len(result.apt) + len(result.flatpak)

        # APT sonuçları
        if result.apt:
            sep = _SectionSep(tr("APT Packages"), self._results_widget)
            self._results_layout.addWidget(sep)
            for pkg in result.apt:
                row = _ResultRow(
                    name=pkg.name,
                    description=pkg.description,
                    version=pkg.version,
                    source="apt",
                    installed=pkg.installed,
                    pkg_id=pkg.name,
                    parent=self._results_widget,
                    other_version=self._other_version_name(pkg, installed_apps),
                )
                row.install_apt.connect(self._install_apt_clicked)
                row.remove_clicked.connect(self._on_remove)
                self._results_layout.addWidget(row)
                self._add_separator()

        # Flatpak sonuçları
        if result.flatpak:
            sep = _SectionSep(tr("Flatpak (Flathub)"), self._results_widget)
            self._results_layout.addWidget(sep)
            for pkg in result.flatpak:
                row = _ResultRow(
                    name=pkg.name,
                    description=pkg.description,
                    version=pkg.version,
                    source="flatpak",
                    installed=pkg.installed,
                    pkg_id=pkg.app_id,
                    parent=self._results_widget,
                )
                row.install_flatpak.connect(self._install_flatpak_clicked)
                row.remove_clicked.connect(self._on_remove)
                self._results_layout.addWidget(row)
                self._add_separator()

        # Üçüncü taraf listesinde eşleşme var mı?
        q_lower = query.lower()
        for app in self._third_party:
            if q_lower in app.name.lower() or q_lower in app.id:
                row = _ResultRow(
                    name=app.name,
                    description=app.description,
                    version="",
                    source="third-party",
                    installed=False,
                    pkg_id=app.id,
                    parent=self._results_widget,
                )
                row.install_third_party.connect(self._queue_third_party)
                self._results_layout.addWidget(row)
                self._add_separator()
                total += 1

        if total == 0 and not alt:
            text = tr('No results for "{q}"').format(q=query)
        else:
            text = tr('{n} result(s) for "{q}"').format(n=total, q=query)
        if result.extra_terms:
            text += " · " + tr("also searched: {terms}").format(terms=", ".join(result.extra_terms))
        self._status_lbl.setText(text)

    def _add_separator(self) -> None:
        sep = QFrame(self._results_widget)
        sep.setFrameShape(QFrame.Shape.HLine)
        self._results_layout.addWidget(sep)

    # --- Görev oluşturma ---

    # --- APT / Flatpak seçimi ---

    @staticmethod
    def _norm(text: str) -> str:
        return "".join(ch for ch in text.casefold() if ch.isalnum())

    def _flatpak_twin(self, apt_name: str) -> FlatpakPackage | None:
        if not self._last_result:
            return None
        key = self._norm(apt_name)
        for fp in self._last_result.flatpak:
            if key in (self._norm(fp.name), self._norm(fp.app_id.rsplit(".", 1)[-1])):
                return fp
        return None

    def _apt_twin(self, app_id: str) -> AptPackage | None:
        if not self._last_result:
            return None
        fp = next((f for f in self._last_result.flatpak if f.app_id == app_id), None)
        keys = {self._norm(app_id.rsplit(".", 1)[-1])}
        if fp:
            keys.add(self._norm(fp.name))
        return next((a for a in self._last_result.apt if self._norm(a.name) in keys), None)

    def _choose_source(self, name: str, apt_version: str, flatpak_version: str) -> str | None:
        """Aynı program iki kaynakta varsa sorar: "apt" | "flatpak" | None (vazgeç)."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("Choose where to install from"))
        box.setText(tr("{name} is available from two sources.").format(name=name))
        box.setInformativeText(
            tr(
                "System packages (APT{apt}): updated together with your system, use less "
                "space, well tested with your system.\n\n"
                "Flatpak (Flathub{fp}): usually a newer version, runs isolated from the "
                "system, uses more disk space."
            ).format(
                apt=f" {apt_version}" if apt_version else "",
                fp=f" {flatpak_version}" if flatpak_version else "",
            )
        )
        apt_btn = box.addButton(tr("System package (APT)"), QMessageBox.ButtonRole.AcceptRole)
        fp_btn = box.addButton(tr("Flatpak"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is apt_btn:
            return "apt"
        if box.clickedButton() is fp_btn:
            return "flatpak"
        return None

    def _install_apt_clicked(self, name: str) -> None:
        twin = self._flatpak_twin(name)
        if twin and not twin.installed:
            apt = next((a for a in self._last_result.apt if a.name == name), None)  # type: ignore[union-attr]
            choice = self._choose_source(twin.name, apt.version if apt else "", twin.version)
            if choice == "flatpak":
                self._queue_flatpak(twin.app_id)
                return
            if choice is None:
                return
        self._queue_apt(name)

    def _install_flatpak_clicked(self, app_id: str) -> None:
        twin = self._apt_twin(app_id)
        if twin and not twin.installed:
            fp = next(f for f in self._last_result.flatpak if f.app_id == app_id)  # type: ignore[union-attr]
            choice = self._choose_source(fp.name, twin.version, fp.version)
            if choice == "apt":
                self._queue_apt(twin.name)
                return
            if choice is None:
                return
        self._queue_flatpak(app_id)

    # --- .deb ---

    def _pick_deb(self) -> None:
        from PySide6.QtCore import QStandardPaths
        from PySide6.QtWidgets import QFileDialog

        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Choose a .deb file"), start, tr("Debian packages (*.deb)")
        )
        if path:
            self.open_deb(path)

    def open_deb(self, path: str) -> None:
        """Dosyayı arka planda inceler, sonucu pencerede gösterir."""
        self._status_lbl.setText(tr("Checking the file…"))
        worker = _DebWorker(path)
        worker.done.connect(self._on_deb_inspected)
        self._deb_worker = worker
        worker.start()

    def _on_deb_inspected(self, info: object) -> None:
        from linwas.ui.dialogs.deb_install import DebInstallDialog

        self._status_lbl.setText("")
        dialog = DebInstallDialog(info, self)  # type: ignore[arg-type]
        if dialog.exec() == DebInstallDialog.DialogCode.Accepted:
            self.task_run_now.emit(
                Task(
                    label=tr("Install {pkg}").format(pkg=info.package),  # type: ignore[attr-defined]
                    steps=[TaskStep(op_id="deb.install", params={"path": info.path})],  # type: ignore[attr-defined]
                )
            )

    def _queue_apt(self, name: str) -> None:
        task = Task(
            label=tr("Install {pkg}").format(pkg=name),
            steps=[TaskStep(op_id="package.install", params={"name": name})],
        )
        self.task_run_now.emit(task)

    def _queue_flatpak(self, app_id: str) -> None:
        task = Task(
            label=tr("Install {pkg}").format(pkg=app_id),
            steps=[TaskStep(op_id="flatpak.install", params={"app_id": app_id})],
        )
        self.task_run_now.emit(task)

    @staticmethod
    def _other_version_name(pkg: AptPackage, installed_apps: list[InstalledApp]) -> str:
        if pkg.installed:
            return ""
        other = is_other_version(pkg.name, installed_apps)
        return f"{other.name} ({other.id})" if other else ""

    def _on_remove_installed(self, app: InstalledApp) -> None:
        self._removal.start(
            RemovalRequest(
                id=app.id, name=app.name, source=app.source, preinstalled=app.preinstalled
            )
        )

    def _on_remove(self, source: str, pkg_id: str, name: str) -> None:
        self._removal.start(RemovalRequest(id=pkg_id, name=name, source=source))

    def _queue_third_party(self, app_id: str) -> None:
        app = next((a for a in self._third_party if a.id == app_id), None)
        if not app:
            return
        task = Task(
            label=tr("Install {name} (third-party repository)").format(name=app.name),
            steps=[
                TaskStep(
                    op_id="apt.add_key",
                    label=tr("Add signing key"),
                    params={"url": app.key_url, "keyring_path": app.keyring_path},
                ),
                TaskStep(
                    op_id="apt.add_source",
                    label=tr("Add repository"),
                    params={"source_line": app.source_line, "list_name": app.list_name},
                ),
                TaskStep(
                    op_id="package.update_index",
                    label=tr("Refresh package index"),
                    params={},
                ),
                TaskStep(
                    op_id="package.install",
                    label=tr("Install {pkg}").format(pkg=app.package),
                    params={"name": app.package},
                ),
            ],
        )
        self.task_run_now.emit(task)


class _InstalledBanner(Card):
    """Aranan program zaten kuruluysa en üstte gösterilir."""

    remove_clicked = Signal(object)  # InstalledApp

    def __init__(self, apps: list[InstalledApp], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(
            tr("Already installed") if len(apps) == 1 else tr("Already installed programs"),
            self,
        )
        title.setObjectName("H2")
        self.layout.addWidget(title)
        for app in apps:
            row = QHBoxLayout()
            name = QLabel(f"✓ <b>{html.escape(app.name)}</b> ({html.escape(app.id)})", self)
            name.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(name, 1)
            row.addWidget(QLabel(source_badge_text(app.source), self))
            remove = QPushButton(tr("Remove"), self)
            remove.setAccessibleName(tr("Remove {name}").format(name=app.name))
            remove.setEnabled(not app.user_install)
            remove.clicked.connect(lambda _=None, a=app: self.remove_clicked.emit(a))
            row.addWidget(remove)
            self.layout.addLayout(row)


class _SectionSep(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 0, 4)
        lbl = QLabel(text, self)
        lbl.setObjectName("H2")
        row.addWidget(lbl)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(sep, 1)
