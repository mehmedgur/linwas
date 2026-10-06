"""Windows'tan Taşı sayfası — 3 adımlı sihirbaz."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.migrate import (
    ImportItem,
    WindowsUser,
    find_windows_users,
    import_item,
    list_installed_programs,
    scan_import_items,
)
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card

_DATA = Path(__file__).resolve().parent.parent.parent / "data"


def tr(text: str) -> str:
    return QCoreApplication.translate("MigratePage", text)


# --- Worker'lar ---


class _ScanWorker(QThread):
    done = Signal(object)  # list[WindowsUser]
    error = Signal(str)

    def run(self) -> None:
        try:
            self.done.emit(find_windows_users())
        except Exception as exc:
            self.error.emit(str(exc))


class _ImportWorker(QThread):
    step = Signal(str, float)  # (mesaj, 0-1)
    item_done = Signal(str, bool)  # (item_id, başarılı)
    all_done = Signal(int, int)  # (başarılı, toplam)

    def __init__(self, items: list[ImportItem]) -> None:
        super().__init__()
        self._items = items

    def run(self) -> None:
        success = 0
        for item in self._items:

            def _cb(msg: str, pct: float, _id: str = item.id) -> None:
                self.step.emit(msg, pct)

            ok = import_item(item, on_progress=_cb)
            self.item_done.emit(item.id, ok)
            if ok:
                success += 1
        self.all_done.emit(success, len(self._items))


# --- Adım 1: Kaynak seçimi ---


class _SourceStep(QWidget):
    source_selected = Signal(object)  # WindowsUser

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._users: list[WindowsUser] = []
        self._worker: _ScanWorker | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(tr("Step 1: Find Windows"), self)
        title.setObjectName("H1")
        layout.addWidget(title)

        desc = QLabel(
            tr(
                "Linwas will scan your drives for a Windows installation.\n"
                "Make sure your Windows drive is mounted."
            ),
            self,
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._status = QLabel(tr("Click Scan to start…"), self)
        self._status.setObjectName("H2")
        layout.addWidget(self._status)

        self._scan_btn = QPushButton(tr("Scan for Windows"), self)
        self._scan_btn.setProperty("primary", True)
        self._scan_btn.clicked.connect(self._scan)
        layout.addWidget(self._scan_btn)

        # BitLocker uyarısı
        self._bitlocker_warn = QLabel(
            tr("⚠ If your Windows drive uses BitLocker encryption, it must be unlocked first."),
            self,
        )
        self._bitlocker_warn.setWordWrap(True)
        self._bitlocker_warn.setStyleSheet("color: #9d5d00;")
        self._bitlocker_warn.setVisible(False)
        layout.addWidget(self._bitlocker_warn)

        # Fast Startup uyarısı
        self._hibernate_warn = QLabel(
            tr(
                "⚠ Fast Startup is enabled on this Windows installation. "
                "Disable it in Windows (Power settings → Turn on fast startup → OFF) "
                "and restart Windows normally before importing."
            ),
            self,
        )
        self._hibernate_warn.setWordWrap(True)
        self._hibernate_warn.setStyleSheet("color: #9d5d00;")
        self._hibernate_warn.setVisible(False)
        layout.addWidget(self._hibernate_warn)

        # Kullanıcı listesi
        self._user_container = QWidget(self)
        self._user_layout = QVBoxLayout(self._user_container)
        self._user_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._user_container)

        layout.addStretch(1)

    def _scan(self) -> None:
        self._scan_btn.setEnabled(False)
        self._status.setText(tr("Scanning…"))
        self._clear_users()

        self._worker = _ScanWorker()
        self._worker.done.connect(self._on_scan_done)
        self._worker.error.connect(self._on_scan_error)
        self._worker.finished.connect(lambda: self._scan_btn.setEnabled(True))
        self._worker.start()

    def _on_scan_error(self, msg: str) -> None:
        self._status.setText(tr("Scan failed: {error}").format(error=msg))

    def _on_scan_done(self, users: object) -> None:
        user_list: list[WindowsUser] = users  # type: ignore[assignment]
        if not user_list:
            self._status.setText(tr("No Windows installation found."))
            self._status.setStyleSheet("color: #9d5d00;")
            return

        self._users = user_list
        self._status.setText(tr("{n} Windows user(s) found — select one:").format(n=len(user_list)))
        self._status.setStyleSheet("")

        for user in user_list:
            btn = QPushButton(f"{user.user_name}  ({user.drive})", self._user_container)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda _=None, u=user: self._select(u))
            self._user_layout.addWidget(btn)

        # Uyarılar
        any_hibernate = any(u.hibernated for u in user_list)
        any_bitlocker = any(u.bitlocker for u in user_list)
        self._hibernate_warn.setVisible(any_hibernate)
        self._bitlocker_warn.setVisible(any_bitlocker)

    def _select(self, user: WindowsUser) -> None:
        if user.hibernated:
            return  # hibernated → taşıma güvenli değil
        self.source_selected.emit(user)

    def _clear_users(self) -> None:
        while self._user_layout.count():
            item = self._user_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


# --- Adım 2: Ne taşınsın? ---


class _SelectStep(QWidget):
    back = Signal()
    start_import = Signal(list)  # list[ImportItem]
    install_hivex = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[ImportItem] = []
        self._checks: dict[str, QCheckBox] = {}

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        title = QLabel(tr("Step 2: What to import"), self)
        title.setObjectName("H1")
        outer.addWidget(title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Windows programs → Linux alternatives section
        self._progs_card = Card(self)
        progs_title = QLabel(tr("Detected Windows programs:"), self._progs_card)
        self._progs_card.layout.addWidget(progs_title)
        self._progs_lbl = QLabel("", self._progs_card)
        self._progs_lbl.setObjectName("Secondary")
        self._progs_lbl.setWordWrap(True)
        self._progs_card.layout.addWidget(self._progs_lbl)
        self._progs_card.setVisible(False)
        outer.addWidget(self._progs_card)

        # Windows ayarları
        self._prefs_card = Card(self)
        h = QLabel(tr("Windows settings"), self._prefs_card)
        h.setObjectName("H2")
        self._prefs_card.layout.addWidget(h)
        self._prefs_box = QVBoxLayout()
        self._prefs_card.layout.addLayout(self._prefs_box)
        outer.addWidget(self._prefs_card)
        self._prefs = None
        self._pref_checks: dict[str, QCheckBox] = {}

        # Alt butonlar
        btn_row = QHBoxLayout()
        back_btn = QPushButton(tr("Back"), self)
        back_btn.clicked.connect(self.back)
        btn_row.addWidget(back_btn)
        btn_row.addStretch(1)
        self._import_btn = QPushButton(tr("Start Import"), self)
        self._import_btn.setProperty("primary", True)
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._import_btn)
        outer.addLayout(btn_row)

    def populate(self, user: WindowsUser) -> None:
        # Temizle
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checks.clear()

        items = scan_import_items(user)
        self._items = items

        for item in items:
            if not item.available:
                continue
            row = QHBoxLayout()
            cb = QCheckBox(
                f"{item.label} ({item.size_mb:.0f} MB)" if item.size_mb else item.label,
                self,
            )
            cb.setChecked(item.selected)
            cb.stateChanged.connect(self._update_btn)
            row.addWidget(cb)
            desc = QLabel(item.description, self)
            desc.setObjectName("Secondary")
            desc.setWordWrap(True)
            row.addWidget(desc, 1)
            container = QWidget(self)
            container.setLayout(row)
            self._list_layout.addWidget(container)
            self._checks[item.id] = cb

        # Windows program listesi
        progs = list_installed_programs(user)
        if progs:
            alts = _match_alternatives(progs)
            if alts:
                self._progs_lbl.setText(", ".join(alts[:20]))
                self._progs_card.setVisible(True)

        self._populate_prefs(user)
        self._update_btn()

    def _populate_prefs(self, user: WindowsUser) -> None:
        import os

        from linwas.backend.desktop import detect_desktop
        from linwas.backend.migrate import detect_windows_prefs, hivexsh_available

        while self._prefs_box.count():
            item = self._prefs_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._pref_checks = {}
        if not hivexsh_available():
            note = QLabel(
                tr(
                    "To read keyboard layout, theme, mouse and region settings from Windows, "
                    "Linwas needs the “libhivex-bin” package."
                ),
                self,
            )
            note.setWordWrap(True)
            self._prefs_box.addWidget(note)
            btn = QPushButton(tr("Install it"), self)
            btn.clicked.connect(self.install_hivex)
            self._prefs_box.addWidget(btn)
            return
        prefs = detect_windows_prefs(user)
        self._prefs = prefs
        if prefs is None:
            self._prefs_box.addWidget(QLabel(tr("Windows settings could not be read."), self))
            return
        options = []
        if prefs.keyboard_layout:
            options.append(("keyboard", tr("Keyboard layout: {v}").format(v=prefs.keyboard_layout)))
        if prefs.locale:
            options.append(("region", tr("Language & region formats: {v}").format(v=prefs.locale)))
        if prefs.dark_mode is not None:
            options.append(("theme", tr("Dark theme") if prefs.dark_mode else tr("Light theme")))
        if prefs.mouse_buttons_swapped:
            options.append(("mouse", tr("Left-handed mouse")))
        if prefs.scale_percent and prefs.scale_percent > 100:
            options.append(("scale", tr("Bigger text ({n}%)").format(n=prefs.scale_percent)))
        gnome = detect_desktop(os.environ).value == "gnome"
        for key, text in options:
            cb = QCheckBox(text, self)
            cb.setChecked(gnome)
            cb.setEnabled(gnome)
            self._prefs_box.addWidget(cb)
            self._pref_checks[key] = cb
        if options and not gnome:
            self._prefs_box.addWidget(
                QLabel(tr("On this desktop, set these in the system settings."), self)
            )
        if prefs.printers:
            lbl = QLabel(
                tr("Printers used on Windows: {names}. Add them in Hardware & Printers.").format(
                    names=", ".join(prefs.printers[:8])
                ),
                self,
            )
            lbl.setWordWrap(True)
            lbl.setObjectName("Secondary")
            self._prefs_box.addWidget(lbl)
        if not options and not prefs.printers:
            self._prefs_box.addWidget(QLabel(tr("No settings found to bring over."), self))

    def apply_prefs(self) -> None:
        """Seçilen Windows ayarlarını uygular (içe aktarma başlarken)."""
        import os

        from linwas.backend.desktop import detect_desktop
        from linwas.backend.migrate import apply_prefs

        chosen = {k for k, cb in self._pref_checks.items() if cb.isChecked()}
        if self._prefs is not None and chosen:
            apply_prefs(self._prefs, chosen, detect_desktop(os.environ).value)

    def _update_btn(self) -> None:
        self._import_btn.setEnabled(any(cb.isChecked() for cb in self._checks.values()))

    def _on_start(self) -> None:
        selected = [
            item
            for item in self._items
            if item.id in self._checks and self._checks[item.id].isChecked()
        ]
        self.apply_prefs()
        self.start_import.emit(selected)


def _match_alternatives(programs: list[str]) -> list[str]:
    """Tanınan Windows programlarına Linux alternatiflerini döner."""
    try:
        mapping = json.loads((_DATA / "windows_alternatives.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    matches: list[str] = []
    for prog in programs:
        prog_lower = prog.lower()
        for key, val in mapping.items():
            if key in prog_lower or prog_lower in key:
                alts = val.get("apt", []) + val.get("flatpak", [])
                if alts:
                    label = val.get("label", prog)
                    matches.append(f"{label} → {', '.join(alts[:2])}")
                break
    return matches


# --- Adım 3: İlerleme ---


class _ProgressStep(QWidget):
    done = Signal(int, int)
    restart = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(tr("Step 3: Importing…"), self)
        title.setObjectName("H1")
        layout.addWidget(title)

        self._status = QLabel(tr("Preparing…"), self)
        self._status.setObjectName("H2")
        layout.addWidget(self._status)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        layout.addWidget(self._progress)

        self._log = QLabel("", self)
        self._log.setObjectName("Secondary")
        self._log.setWordWrap(True)
        layout.addWidget(self._log)

        self._result_lbl = QLabel("", self)
        self._result_lbl.setObjectName("H2")
        self._result_lbl.setVisible(False)
        layout.addWidget(self._result_lbl)

        self._restart_btn = QPushButton(tr("Import more"), self)
        self._restart_btn.setVisible(False)
        self._restart_btn.clicked.connect(self.restart)
        layout.addWidget(self._restart_btn)

        layout.addStretch(1)
        self._worker: _ImportWorker | None = None

    def start(self, items: list[ImportItem]) -> None:
        self._progress.setRange(0, len(items))
        self._progress.setValue(0)
        self._result_lbl.setVisible(False)
        self._restart_btn.setVisible(False)
        self._status.setText(tr("Importing…"))

        self._worker = _ImportWorker(items)
        self._worker.step.connect(self._on_step)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _on_step(self, msg: str, _pct: float) -> None:
        self._log.setText(msg)

    def _on_item_done(self, _item_id: str, ok: bool) -> None:
        self._progress.setValue(self._progress.value() + 1)

    def _on_all_done(self, success: int, total: int) -> None:
        self._result_lbl.setText(
            tr("{ok} of {total} item(s) imported successfully.").format(ok=success, total=total)
        )
        self._result_lbl.setVisible(True)
        self._restart_btn.setVisible(True)
        self._status.setText(tr("Done"))
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self.done.emit(success, total)


# --- Ana sayfa ---


class MigratePage(BasePage):
    """Windows'tan Taşı sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user: WindowsUser | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)

        # Diskten okunamayanlar için rehberler (şifreler, Wi-Fi, Outlook)
        guide_row = QHBoxLayout()
        guide_row.addStretch(1)
        guides = QPushButton(tr("Passwords, Wi-Fi and Outlook guides…"), self)
        guides.clicked.connect(self._open_guides)
        guide_row.addWidget(guides)
        outer.addLayout(guide_row)

        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack)

        self._step1 = _SourceStep(self._stack)
        self._step2 = _SelectStep(self._stack)
        self._step3 = _ProgressStep(self._stack)

        for step in (self._step1, self._step2, self._step3):
            self._stack.addWidget(step)

        self._step1.source_selected.connect(self._on_source_selected)
        self._step2.back.connect(lambda: self._stack.setCurrentWidget(self._step1))
        self._step2.start_import.connect(self._on_start_import)
        self._step2.install_hivex.connect(self._install_hivex)
        self._step3.restart.connect(lambda: self._stack.setCurrentWidget(self._step1))
        self._step3.done.connect(lambda ok, tot: None)

        self._stack.setCurrentWidget(self._step1)

    def _open_guides(self) -> None:
        from linwas.ui.dialogs.migrate_guides import MigrateGuidesDialog

        MigrateGuidesDialog(self).exec()

    def _install_hivex(self) -> None:
        from linwas.core.tasks import Task, TaskStep

        self.task_run_now.emit(
            Task(
                label=tr("Install Windows registry reader"),
                steps=[TaskStep(op_id="package.install", params={"name": "libhivex-bin"})],
            )
        )

    def on_tasks_finished(self) -> None:
        if self._user is not None and self._stack.currentWidget() is self._step2:
            self._step2.populate(self._user)

    def _on_source_selected(self, user: WindowsUser) -> None:
        self._user = user
        self._step2.populate(user)
        self._stack.setCurrentWidget(self._step2)

    def _on_start_import(self, items: list[ImportItem]) -> None:
        self._stack.setCurrentWidget(self._step3)
        self._step3.start(items)
