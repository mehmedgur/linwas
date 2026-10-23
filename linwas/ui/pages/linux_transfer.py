"""Taşıma › Başka Linux'a: dışa aktarma ve içe aktarma sihirbazları."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import linux_transfer as lt
from linwas.core.tasks import Task, TaskStep
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("LinuxTransfer", text)


def _size(n: int) -> str:
    return QLocale().formattedDataSize(n, 1, QLocale.DataSizeFormat.DataSizeSIFormat)


def item_label(item: lt.TransferItem) -> str:
    if item.id.startswith("files.") and item.paths:
        return Path(item.paths[0]).name
    return {
        "app.firefox": tr("Firefox (bookmarks, passwords, history, add-ons)"),
        "app.chrome": tr("Google Chrome profile"),
        "app.chromium": tr("Chromium profile"),
        "app.thunderbird": tr("Thunderbird (e-mail accounts and messages)"),
        "app.libreoffice": tr("LibreOffice settings"),
        "app.flatpak": tr("Data of Flatpak programs"),
        "desktop.settings": tr("Desktop look (theme, wallpaper, fonts, shortcuts)"),
        "desktop.fonts": tr("Fonts you installed"),
        "desktop.launchers": tr("Menu shortcuts you created"),
        "desktop.linwas": tr("Linwas settings, app folders and groups"),
        "system.wifi": tr("Wi-Fi networks and passwords"),
        "system.keys": tr("SSH and GPG keys"),
        "programs": tr("Installed programs (list; installed again on the new system)"),
    }.get(item.id, item.id)


_GROUPS = ("files", "app", "desktop", "system", "programs")


def _group_title(kind: str) -> str:
    return {
        "files": tr("Personal files"),
        "app": tr("Program settings"),
        "desktop": tr("Desktop"),
        "system": tr("System"),
        "programs": tr("Programs"),
    }[kind]


def note_text(note: str) -> str:
    code, value = lt.clean_note_value(note)
    texts = {
        "extract_failed": tr("Could not be opened (wrong password or damaged file)."),
        "copy_failed": tr("Some files could not be copied."),
        "not_in_home_source": tr("Not available when copying from another partition."),
        "relogin": tr("Log out and back in to see the desktop settings."),
        "desktop_converted": tr(
            "The old system used a different desktop; common settings were converted."
        ),
        "desktop_unsupported": tr("Desktop settings are not supported on this desktop."),
        "missing_gtk_theme": tr("Theme “%1” is not installed here; it was skipped."),
        "missing_icon_theme": tr("Icon theme “%1” is not installed here; it was skipped."),
        "wallpaper_manual": tr("Set the wallpaper yourself: %1"),
        "wifi_added": tr("%1 Wi-Fi network(s) added."),
        "wifi_skipped": tr("%1 Wi-Fi network(s) skipped (already present or unsupported)."),
    }
    return texts.get(code, code).replace("%1", value)


# --- İşçiler ---


class _MeasureWorker(QThread):
    done = Signal()

    def __init__(self, items: list[lt.TransferItem], home: Path) -> None:
        super().__init__()
        self._items, self._home = items, home

    def run(self) -> None:
        lt.measure(self._items, self._home)
        self.done.emit()


class _ExportWorker(QThread):
    step = Signal(str)
    finished_with = Signal(object)  # lt.ExportResult

    def __init__(self, items: list[lt.TransferItem], dest: Path, password: str | None) -> None:
        super().__init__()
        self._items, self._dest, self._password = items, dest, password

    def run(self) -> None:
        result = lt.export_package(self._items, self._dest, self._password, self.step.emit)
        self.finished_with.emit(result)


class _ScanWorker(QThread):
    done = Signal(list, list)  # paketler, eski ev klasörleri

    def run(self) -> None:
        self.done.emit(lt.find_packages(), lt.find_old_homes())


class _ItemsWorker(QThread):
    done = Signal(list)

    def __init__(self, source: lt.Source) -> None:
        super().__init__()
        self._source = source

    def run(self) -> None:
        self.done.emit(lt.source_items(self._source))


class _ProgramsWorker(QThread):
    done = Signal(list)

    def __init__(self, programs: list[lt.Program]) -> None:
        super().__init__()
        self._programs = programs

    def run(self) -> None:
        self.done.emit(lt.check_programs(self._programs))


class _ImportWorker(QThread):
    step = Signal(str)
    item_done = Signal(str, object)  # öğe kimliği, lt.ItemResult
    all_done = Signal()

    def __init__(
        self, source: lt.Source, items: list[lt.TransferItem], password: str | None
    ) -> None:
        super().__init__()
        self._source, self._items, self._password = source, items, password

    def run(self) -> None:
        for item in self._items:
            self.step.emit(item_label(item))
            self.item_done.emit(item.id, lt.import_item(self._source, item, self._password))
        self.all_done.emit()


# --- Ortak parçalar ---


def _scroll(parent: QWidget) -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(16)
    scroll.setWidget(content)
    return scroll, layout


class _ItemList(QWidget):
    """Gruplu, işaretli öğe listesi; her satırda boyut."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self._items: list[lt.TransferItem] = []
        self._checks: dict[str, QCheckBox] = {}
        self._sizes: dict[str, QLabel] = {}

    def set_items(self, items: list[lt.TransferItem]) -> None:
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._items, self._checks, self._sizes = items, {}, {}
        for kind in _GROUPS:
            group = [i for i in items if i.kind == kind]
            if not group:
                continue
            card = Card(self)
            head = QLabel(_group_title(kind), card)
            head.setObjectName("H2")
            card.layout.addWidget(head)
            for item in group:
                row = QHBoxLayout()
                cb = QCheckBox(item_label(item), card)
                cb.setChecked(item.selected)
                cb.toggled.connect(lambda on, it=item: self._toggle(it, on))
                row.addWidget(cb, 1)
                if item.secret:
                    lock = QLabel(tr("contains passwords"), card)
                    lock.setObjectName("Caption")
                    row.addWidget(lock)
                size = QLabel("…" if item.kind != "programs" else "", card)
                size.setObjectName("Secondary")
                size.setAlignment(Qt.AlignmentFlag.AlignRight)
                size.setMinimumWidth(90)
                row.addWidget(size)
                card.layout.addLayout(row)
                self._checks[item.id] = cb
                self._sizes[item.id] = size
            self._layout.addWidget(card)
        self.refresh_sizes()

    def _toggle(self, item: lt.TransferItem, on: bool) -> None:
        item.selected = on
        self.changed.emit()

    def refresh_sizes(self) -> None:
        for item in self._items:
            lbl = self._sizes.get(item.id)
            if lbl is not None and item.kind != "programs" and item.size:
                lbl.setText(_size(item.size))

    def items(self) -> list[lt.TransferItem]:
        return self._items

    def selected(self) -> list[lt.TransferItem]:
        return [i for i in self._items if i.selected]

    def total(self) -> int:
        return sum(i.size for i in self.selected())


# --- Dışa aktarma ---


class ExportWizard(QWidget):
    """Bu sistemden taşıma paketi oluşturur."""

    back = Signal()
    task_run_now = Signal(Task)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: QThread | None = None
        self._custom_dest: Path | None = None
        self._stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        # Sayfa 1: seçim
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        back = QPushButton(tr("‹ Transfer"), page)
        back.clicked.connect(self.back)
        top.addWidget(back)
        top.addStretch(1)
        lay.addLayout(top)
        title = QLabel(tr("Move this computer to another Linux"), page)
        title.setObjectName("H1")
        lay.addWidget(title)
        desc = QLabel(
            tr(
                "Linwas packs your files, program settings, desktop look and program list into "
                "one folder. On the new system, open Linwas › Transfer › Bring from another Linux."
            ),
            page,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        scroll, body = _scroll(page)
        self._list = _ItemList()
        self._list.changed.connect(self._update)
        body.addWidget(self._list)

        # Hedef
        dest = Card()
        h = QLabel(tr("Where to save"), dest)
        h.setObjectName("H2")
        dest.layout.addWidget(h)
        row = QHBoxLayout()
        self._dest = QComboBox(dest)
        self._dest.setAccessibleName(tr("Where to save"))
        self._dest.currentIndexChanged.connect(self._update)
        row.addWidget(self._dest, 1)
        pick = QPushButton(tr("Choose folder…"), dest)
        pick.clicked.connect(self._pick_folder)
        row.addWidget(pick)
        refresh = QPushButton(tr("Refresh"), dest)
        refresh.clicked.connect(self._fill_destinations)
        row.addWidget(refresh)
        dest.layout.addLayout(row)
        self._space = QLabel("", dest)
        self._space.setObjectName("Secondary")
        self._space.setWordWrap(True)
        dest.layout.addWidget(self._space)
        body.addWidget(dest)

        # Şifreleme
        sec = Card()
        h = QLabel(tr("Protection"), sec)
        h.setObjectName("H2")
        sec.layout.addWidget(h)
        self._encrypt = QCheckBox(tr("Protect the package with a password"), sec)
        self._encrypt.toggled.connect(self._update)
        sec.layout.addWidget(self._encrypt)
        self._forced = QLabel(
            tr(
                "Selected items contain passwords or keys, so the package must have a password. "
                "If you forget it, the package cannot be opened."
            ),
            sec,
        )
        self._forced.setObjectName("Warning")
        self._forced.setWordWrap(True)
        sec.layout.addWidget(self._forced)
        self._pw1 = QLineEdit(sec)
        self._pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw1.setPlaceholderText(tr("Password"))
        self._pw1.setAccessibleName(tr("Password"))
        self._pw1.textChanged.connect(self._update)
        self._pw2 = QLineEdit(sec)
        self._pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2.setPlaceholderText(tr("Password again"))
        self._pw2.setAccessibleName(tr("Password again"))
        self._pw2.textChanged.connect(self._update)
        sec.layout.addWidget(self._pw1)
        sec.layout.addWidget(self._pw2)
        self._gpg_row = QHBoxLayout()
        gpg_note = QLabel(tr("Encryption needs the “gnupg” package."), sec)
        gpg_note.setWordWrap(True)
        self._gpg_row.addWidget(gpg_note, 1)
        gpg_btn = QPushButton(tr("Install it"), sec)
        gpg_btn.clicked.connect(self._install_gpg)
        self._gpg_row.addWidget(gpg_btn)
        self._gpg_box = QWidget(sec)
        self._gpg_box.setLayout(self._gpg_row)
        sec.layout.addWidget(self._gpg_box)
        body.addWidget(sec)
        body.addStretch(1)
        lay.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self._problem = QLabel("", page)
        self._problem.setObjectName("Warning")
        self._problem.setWordWrap(True)
        bottom.addWidget(self._problem, 1)
        self._start = QPushButton(tr("Create package"), page)
        self._start.setProperty("primary", True)
        self._start.clicked.connect(self._run)
        bottom.addWidget(self._start)
        lay.addLayout(bottom)
        self._stack.addWidget(page)

        # Sayfa 2: ilerleme ve sonuç
        prog = QWidget()
        pl = QVBoxLayout(prog)
        pl.setSpacing(12)
        self._p_title = QLabel(tr("Creating the package…"), prog)
        self._p_title.setObjectName("H1")
        pl.addWidget(self._p_title)
        self._p_bar = QProgressBar(prog)
        pl.addWidget(self._p_bar)
        self._p_step = QLabel("", prog)
        self._p_step.setObjectName("Secondary")
        self._p_step.setWordWrap(True)
        pl.addWidget(self._p_step)
        self._p_result = QLabel("", prog)
        self._p_result.setWordWrap(True)
        self._p_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self._p_result)
        done_row = QHBoxLayout()
        done_row.addStretch(1)
        self._p_done = QPushButton(tr("Done"), prog)
        self._p_done.clicked.connect(self._reset)
        done_row.addWidget(self._p_done)
        pl.addLayout(done_row)
        pl.addStretch(1)
        self._stack.addWidget(prog)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        if not self._list.items():
            self._load()
        super().showEvent(event)  # type: ignore[misc]

    def _load(self) -> None:
        items = lt.scan_items(Path.home())
        self._list.set_items(items)
        self._fill_destinations()
        self._worker = _MeasureWorker(items, Path.home())
        self._worker.done.connect(self._on_measured)
        self._worker.start()
        self._update()

    def _on_measured(self) -> None:
        self._list.refresh_sizes()
        self._update()

    def _fill_destinations(self) -> None:
        from linwas.backend.personal_backup import list_destinations

        current = self._dest_path()
        self._dest.blockSignals(True)
        self._dest.clear()
        for d in list_destinations():
            self._dest.addItem(tr("External drive: %1").replace("%1", d.label), str(d.mountpoint))
        for c in lt.cloud_folders():
            self._dest.addItem(tr("Cloud: %1").replace("%1", c.name), str(c))
        if self._custom_dest is not None:
            self._dest.addItem(str(self._custom_dest), str(self._custom_dest))
        if self._dest.count() == 0:
            self._dest.addItem(tr("No external drive found — plug one in or choose a folder"), "")
        if current is not None:
            idx = self._dest.findData(str(current))
            if idx >= 0:
                self._dest.setCurrentIndex(idx)
        self._dest.blockSignals(False)
        self._update()

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("Choose folder"), str(Path.home()))
        if path:
            self._custom_dest = Path(path)
            self._fill_destinations()
            self._dest.setCurrentIndex(self._dest.findData(path))

    def _dest_path(self) -> Path | None:
        data = self._dest.currentData()
        return Path(data) if data else None

    def _install_gpg(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install encryption tool"),
                steps=[TaskStep(op_id="package.install", params={"name": "gnupg"})],
            )
        )

    def _update(self) -> None:
        items = self._list.items()
        forced = lt.needs_password(items)
        self._encrypt.blockSignals(True)
        if forced:
            self._encrypt.setChecked(True)
        self._encrypt.setEnabled(not forced)
        self._encrypt.blockSignals(False)
        self._forced.setVisible(forced)
        encrypt = self._encrypt.isChecked()
        self._pw1.setVisible(encrypt)
        self._pw2.setVisible(encrypt)
        has_gpg = lt.gpg_available()
        self._gpg_box.setVisible(encrypt and not has_gpg)

        dest = self._dest_path()
        total = self._list.total()
        problem = ""
        if dest is not None:
            free = lt.free_bytes(dest)
            self._space.setText(
                tr("Selected: %1 · Free space there: %2")
                .replace("%1", _size(total))
                .replace("%2", _size(free))
            )
            if total and free and total > free:
                problem = tr("Not enough free space at the destination.")
        else:
            self._space.setText(tr("Selected: %1").replace("%1", _size(total)))
            problem = tr("Choose where to save the package.")
        if not self._list.selected():
            problem = tr("Select at least one item.")
        elif encrypt and not has_gpg:
            problem = tr("Install the encryption tool first.")
        elif encrypt and len(self._pw1.text()) < 8:
            problem = tr("The password must be at least 8 characters.")
        elif encrypt and self._pw1.text() != self._pw2.text():
            problem = tr("The passwords do not match.")
        self._problem.setText(problem)
        self._start.setEnabled(not problem)

    def _run(self) -> None:
        dest = self._dest_path()
        if dest is None:
            return
        password = self._pw1.text() if self._encrypt.isChecked() else None
        selected = self._list.selected()
        self._p_bar.setRange(0, len(selected))
        self._p_bar.setValue(0)
        self._p_title.setText(tr("Creating the package…"))
        self._p_result.setText("")
        self._p_done.setEnabled(False)
        self._stack.setCurrentIndex(1)
        labels = {i.id: item_label(i) for i in selected}
        self._worker = _ExportWorker(self._list.items(), dest, password)
        self._worker.step.connect(
            lambda item_id: (
                self._p_step.setText(labels.get(item_id, item_id)),
                self._p_bar.setValue(self._p_bar.value() + 1),
            )
        )
        self._worker.finished_with.connect(self._on_done)
        self._worker.start()

    def _on_done(self, result: object) -> None:
        res: lt.ExportResult = result  # type: ignore[assignment]
        self._p_bar.setValue(self._p_bar.maximum())
        self._p_done.setEnabled(True)
        self._pw1.clear()
        self._pw2.clear()
        if res.package is None:
            self._p_title.setText(tr("The package could not be created"))
            self._p_result.setText(tr("Check that the destination is writable and try again."))
            return
        self._p_title.setText(tr("The package is ready"))
        text = tr("Saved to: %1").replace("%1", str(res.package))
        if res.failed:
            names = {i.id: item_label(i) for i in self._list.items()}
            text += "\n\n" + tr("Could not be added: %1").replace(
                "%1", ", ".join(names.get(f, f) for f in res.failed)
            )
        text += "\n\n" + tr(
            "Next: install Linwas on the new system, plug in this drive and open "
            "Transfer › Bring from another Linux."
        )
        self._p_result.setText(text)

    def _reset(self) -> None:
        self._stack.setCurrentIndex(0)
        self._update()


# --- İçe aktarma ---


class ImportWizard(QWidget):
    """Taşıma paketinden ya da eski ev klasöründen bu sisteme alır."""

    back = Signal()
    task_run_now = Signal(Task)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: QThread | None = None
        self._prog_worker: QThread | None = None
        self._source: lt.Source | None = None
        self._password: str | None = None
        self._choices: list[lt.ProgramChoice] = []
        self._combos: list[QComboBox] = []
        self._stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)
        self._build_source()
        self._build_select()
        self._build_progress()

    # Sayfa 1: kaynak

    def _build_source(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        back = QPushButton(tr("‹ Transfer"), page)
        back.clicked.connect(self.back)
        top.addWidget(back)
        top.addStretch(1)
        lay.addLayout(top)
        title = QLabel(tr("Bring from another Linux"), page)
        title.setObjectName("H1")
        lay.addWidget(title)
        desc = QLabel(
            tr(
                "Plug in the drive with the Linwas transfer package, or choose the old system's "
                "partition if it is on this computer."
            ),
            page,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        lay.addWidget(desc)
        scroll, self._src_body = _scroll(page)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        self._scan_status = QLabel("", page)
        self._scan_status.setObjectName("Secondary")
        row.addWidget(self._scan_status, 1)
        again = QPushButton(tr("Search again"), page)
        again.clicked.connect(self._scan)
        row.addWidget(again)
        pick = QPushButton(tr("Choose package or old home folder…"), page)
        pick.clicked.connect(self._pick)
        row.addWidget(pick)
        lay.addLayout(row)
        self._stack.addWidget(page)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        if self._stack.currentIndex() == 0 and self._worker is None:
            self._scan()
        super().showEvent(event)  # type: ignore[misc]

    def _scan(self) -> None:
        self._scan_status.setText(tr("Searching drives and partitions…"))
        self._worker = _ScanWorker()
        self._worker.done.connect(self._on_scanned)
        self._worker.start()

    def _clear(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_scanned(self, packages: list, homes: list) -> None:
        self._clear(self._src_body)
        if not packages and not homes:
            self._scan_status.setText(tr("Nothing found. Plug in the drive or choose a folder."))
        else:
            self._scan_status.setText("")
        if packages:
            card = Card()
            h = QLabel(tr("Transfer packages"), card)
            h.setObjectName("H2")
            card.layout.addWidget(h)
            for pkg in packages:
                m = lt.read_manifest(pkg)
                if m is None:
                    continue
                text = (
                    tr("%1 · %2 · %3")
                    .replace("%1", m.hostname or pkg.name)
                    .replace("%2", m.distro)
                    .replace("%3", m.created)
                )
                btn = QPushButton(text, card)
                btn.setToolTip(str(pkg))
                btn.clicked.connect(lambda _=False, p=pkg: self._open(p))
                card.layout.addWidget(btn)
            self._src_body.addWidget(card)
        if homes:
            card = Card()
            h = QLabel(tr("Old system on this computer"), card)
            h.setObjectName("H2")
            card.layout.addWidget(h)
            note = QLabel(
                tr("Files and settings are copied directly; the program list is not available."),
                card,
            )
            note.setObjectName("Secondary")
            note.setWordWrap(True)
            card.layout.addWidget(note)
            for home in homes:
                btn = QPushButton(str(home), card)
                btn.clicked.connect(lambda _=False, p=home: self._open(p))
                card.layout.addWidget(btn)
            self._src_body.addWidget(card)
        self._src_body.addStretch(1)

    def _pick(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("Choose folder"), "/media")
        if path:
            self._open(Path(path))

    def _open(self, path: Path) -> None:
        source = lt.open_source(path)
        if source is None:
            self._scan_status.setText(
                tr("This folder is neither a Linwas transfer package nor a home folder.")
            )
            return
        self._password = None
        if source.kind == "package" and source.manifest and source.manifest.encrypted:
            if not lt.gpg_available():
                self._scan_status.setText(tr("Opening this package needs the “gnupg” package."))
                self.task_run_now.emit(
                    Task(
                        label=tr("Install encryption tool"),
                        steps=[TaskStep(op_id="package.install", params={"name": "gnupg"})],
                    )
                )
                return
            while True:
                pw, ok = QInputDialog.getText(
                    self,
                    tr("Package password"),
                    tr("Enter the password you chose when creating the package:"),
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return
                if lt.check_password(source.path, pw):
                    self._password = pw
                    break
                self._scan_status.setText(tr("Wrong password. Try again."))
        self._source = source
        self._show_select()

    # Sayfa 2: seçim

    def _build_select(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        back = QPushButton(tr("‹ Back"), page)
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        top.addWidget(back)
        top.addStretch(1)
        lay.addLayout(top)
        self._sel_title = QLabel(tr("What to bring"), page)
        self._sel_title.setObjectName("H1")
        lay.addWidget(self._sel_title)
        self._sel_info = QLabel("", page)
        self._sel_info.setObjectName("Secondary")
        self._sel_info.setWordWrap(True)
        lay.addWidget(self._sel_info)
        scroll, body = _scroll(page)
        self._list = _ItemList()
        self._list.changed.connect(self._update)
        body.addWidget(self._list)

        self._prog_card = Card()
        h = QLabel(tr("Programs"), self._prog_card)
        h.setObjectName("H2")
        self._prog_card.layout.addWidget(h)
        self._prog_note = QLabel(tr("Checking which programs are available here…"))
        self._prog_note.setObjectName("Secondary")
        self._prog_note.setWordWrap(True)
        self._prog_card.layout.addWidget(self._prog_note)
        self._table = QTableWidget(0, 2, self._prog_card)
        self._table.setHorizontalHeaderLabels([tr("Program"), tr("Install as")])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(240)
        self._prog_card.layout.addWidget(self._table)
        body.addWidget(self._prog_card)

        self._printers = QLabel("")
        self._printers.setObjectName("Secondary")
        self._printers.setWordWrap(True)
        body.addWidget(self._printers)
        body.addStretch(1)
        lay.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self._sel_problem = QLabel("", page)
        self._sel_problem.setObjectName("Warning")
        bottom.addWidget(self._sel_problem, 1)
        self._start = QPushButton(tr("Start"), page)
        self._start.setProperty("primary", True)
        self._start.clicked.connect(self._run)
        bottom.addWidget(self._start)
        lay.addLayout(bottom)
        self._stack.addWidget(page)

    def _show_select(self) -> None:
        assert self._source is not None
        src = self._source
        m = src.manifest
        if m is not None:
            info = (
                tr("From %1 (%2), created %3.")
                .replace("%1", m.hostname)
                .replace("%2", m.distro)
                .replace("%3", m.created)
            )
            if m.desktop and m.desktop != lt.current_desktop():
                info += " " + tr(
                    "The old system used a different desktop; common look settings will be "
                    "converted and the rest listed at the end."
                )
            self._sel_info.setText(info)
            self._printers.setText(
                tr("Printers on the old system: %1. Add them in Hardware & Printers.").replace(
                    "%1", ", ".join(m.printers)
                )
                if m.printers
                else ""
            )
        else:
            self._sel_info.setText(tr("From the folder %1.").replace("%1", str(src.path)))
            self._printers.setText("")
        self._list.set_items([])
        self._prog_card.setVisible(False)
        self._table.setRowCount(0)
        self._stack.setCurrentIndex(1)
        self._sel_problem.setText(tr("Reading…"))
        self._start.setEnabled(False)
        self._worker = _ItemsWorker(src)
        self._worker.done.connect(self._on_items)
        self._worker.start()

    def _on_items(self, items: list) -> None:
        self._list.set_items(items)
        self._update()
        m = self._source.manifest if self._source else None
        if m is not None and m.programs and any(i.id == "programs" for i in items):
            self._prog_card.setVisible(True)
            self._prog_note.setText(tr("Checking which programs are available here…"))
            self._prog_worker = _ProgramsWorker(m.programs)
            self._prog_worker.done.connect(self._on_programs)
            self._prog_worker.start()

    def _on_programs(self, choices: list) -> None:
        self._choices = choices
        self._combos = []
        self._table.setRowCount(len(choices))
        labels = {"apt": tr("Package from the repository"), "flatpak": tr("Flatpak (Flathub)")}
        for row, choice in enumerate(choices):
            c: lt.ProgramChoice = choice
            name = QTableWidgetItem(c.program.name)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, name)
            combo = QComboBox(self._table)
            combo.setAccessibleName(c.program.name)
            if c.installed:
                combo.addItem(tr("Already installed"), "")
            else:
                for opt in c.options:
                    text = labels[opt]
                    if opt == c.recommended and len(c.options) > 1:
                        text += " " + tr("(as before)")
                    combo.addItem(text, opt)
                combo.addItem(tr("Don't install"), "")
                if not c.options:
                    combo.setItemText(0, tr("Not found here — skip"))
                else:
                    combo.setCurrentIndex(c.options.index(c.recommended))
            self._table.setCellWidget(row, 1, combo)
            self._combos.append(combo)
        self._table.resizeColumnToContents(0)
        both = sum(1 for c in choices if len(c.options) > 1 and not c.installed)
        self._prog_note.setText(
            tr("%1 program(s) can be installed both ways; choose for each.").replace(
                "%1", str(both)
            )
            if both
            else tr("Choose how each program is installed.")
        )

    def _update(self) -> None:
        problem = "" if self._list.selected() else tr("Select at least one item.")
        self._sel_problem.setText(problem)
        self._start.setEnabled(not problem)

    # Sayfa 3: ilerleme

    def _build_progress(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        self._p_title = QLabel(tr("Bringing your data…"), page)
        self._p_title.setObjectName("H1")
        lay.addWidget(self._p_title)
        self._p_bar = QProgressBar(page)
        lay.addWidget(self._p_bar)
        self._p_step = QLabel("", page)
        self._p_step.setObjectName("Secondary")
        lay.addWidget(self._p_step)
        scroll, self._p_body = _scroll(page)
        lay.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._p_done = QPushButton(tr("Done"), page)
        self._p_done.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        row.addWidget(self._p_done)
        lay.addLayout(row)
        self._stack.addWidget(page)

    def _run(self) -> None:
        if self._source is None:
            return
        items = [i for i in self._list.selected() if i.id != "programs"]
        self._clear(self._p_body)
        self._p_bar.setRange(0, max(1, len(items)))
        self._p_bar.setValue(0)
        self._p_title.setText(tr("Bringing your data…"))
        self._p_done.setEnabled(False)
        self._stack.setCurrentIndex(2)
        self._labels = {i.id: item_label(i) for i in items}
        self._worker = _ImportWorker(self._source, items, self._password)
        self._worker.step.connect(self._p_step.setText)
        self._worker.item_done.connect(self._on_item)
        self._worker.all_done.connect(self._on_all)
        self._worker.start()

    def _on_item(self, item_id: str, result: object) -> None:
        res: lt.ItemResult = result  # type: ignore[assignment]
        self._p_bar.setValue(self._p_bar.value() + 1)
        mark = "✓" if res.ok else "✗"
        text = f"{mark} {self._labels.get(item_id, item_id)}"
        for note in res.notes:
            text += "\n     " + note_text(note)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        self._p_body.addWidget(lbl)

    def _on_all(self) -> None:
        self._password = None
        self._p_bar.setValue(self._p_bar.maximum())
        self._p_title.setText(tr("Done"))
        self._p_step.setText("")
        self._p_done.setEnabled(True)
        steps = self._program_steps()
        if steps:
            self._p_body.addWidget(
                QLabel(tr("Programs will be installed after you confirm (password needed)."))
            )
            self.task_run_now.emit(
                Task(label=tr("Install programs from the old system"), steps=steps)
            )
        self._p_body.addStretch(1)

    def _program_steps(self) -> list[TaskStep]:
        if not any(i.id == "programs" for i in self._list.selected()):
            return []
        steps: list[TaskStep] = []
        need_flatpak = False
        for choice, combo in zip(self._choices, self._combos, strict=False):
            how = combo.currentData()
            if how == "apt":
                steps.append(TaskStep(op_id="package.install", params={"name": choice.apt_name}))
            elif how == "flatpak":
                need_flatpak = True
                steps.append(
                    TaskStep(op_id="flatpak.install", params={"app_id": choice.flatpak_id})
                )
        from linwas.backend.flatpak import is_available

        if need_flatpak and not is_available():
            steps.insert(0, TaskStep(op_id="flatpak.setup", params={}))
        return steps
