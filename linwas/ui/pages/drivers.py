"""Sürücüler / Firmware görünümü (Güncelleme merkezi altında) — GPU, Ağ/Wi-Fi, Firmware."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.drivers import DriverCandidate, DriverCategory, list_drivers
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("DriversPage", text)


_CATEGORY_LABELS = {
    DriverCategory.GPU: "Graphics",
    DriverCategory.NETWORK: "Network & Wi-Fi",
    DriverCategory.FIRMWARE: "Firmware Updates",
}


def _translation_markers() -> None:
    """Dinamik kategori etiketleri için çeviri tarayıcısı işaretleyicileri. Hiç çağrılmaz."""
    tr("Graphics")
    tr("Network & Wi-Fi")
    tr("Firmware Updates")


# --- Worker ---


class _ScanWorker(QThread):
    done = Signal(list)  # list[DriverCandidate]
    error = Signal(str)

    def run(self) -> None:
        try:
            self.done.emit(list_drivers())
        except Exception as exc:
            self.error.emit(str(exc))


# --- Sürücü kartı ---


class _DriverCard(Card):
    action_requested = Signal(DriverCandidate)

    def __init__(self, driver: DriverCandidate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._driver = driver

        # Üst satır: paket adı + rozetler
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)

        pkg_lbl = QLabel(driver.package, self)
        pkg_lbl.setObjectName("H2")
        top.addWidget(pkg_lbl)
        top.addStretch(1)

        if driver.driver_type == "proprietary":
            self._add_badge(top, tr("Proprietary"), "#9d5d00", "#fff3cc")
        elif driver.driver_type == "open-source":
            self._add_badge(top, tr("Open source"), "#0e7a0e", "#e8f5e9")

        if driver.needs_reboot and not driver.installed:
            self._add_badge(top, tr("Reboot required"), "#6b3a7d", "#f3e5f5")

        if driver.recommended and not driver.installed:
            self._add_badge(top, tr("Recommended"), "#0067c0", "#e3f2fd")

        self.layout.addLayout(top)

        # Cihaz adı
        dev_lbl = QLabel(driver.device_name, self)
        dev_lbl.setObjectName("Secondary")
        dev_lbl.setWordWrap(True)
        self.layout.addWidget(dev_lbl)

        # Aktif sürücü (bilgi satırı)
        if driver.current_driver:
            active_lbl = QLabel(tr("Current driver: {d}").format(d=driver.current_driver), self)
            active_lbl.setObjectName("Secondary")
            self.layout.addWidget(active_lbl)

        # Açıklama
        desc_lbl = QLabel(driver.description, self)
        desc_lbl.setWordWrap(True)
        self.layout.addWidget(desc_lbl)

        # Alt satır: eylem butonu
        if driver.installed:
            status = QLabel("✓ " + tr("Installed"), self)
            status.setStyleSheet("color: #0e7a0e; font-weight: bold;")
            self.layout.addWidget(status)
        elif driver.package == "__fwupd_update__":
            btn = QPushButton(tr("Update firmware"), self)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda: self.action_requested.emit(driver))
            self.layout.addWidget(btn)
        else:
            btn = QPushButton(tr("Install"), self)
            btn.setProperty("primary", driver.recommended)
            btn.clicked.connect(lambda: self.action_requested.emit(driver))
            self.layout.addWidget(btn)

    def _add_badge(self, layout: QHBoxLayout, text: str, fg: str, bg: str) -> None:
        badge = QLabel(text, self)
        badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 4px;"
            " padding: 1px 7px; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(badge)


# --- Bölüm başlığı ---


class _SectionHeader(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 8, 0, 4)

        lbl = QLabel(text, self)
        lbl.setObjectName("H2")
        row.addWidget(lbl)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(sep, 1)


# --- Sayfa ---


class DriversPage(BasePage):
    """Sürücüler sayfası."""

    def __init__(
        self,
        parent: QWidget | None = None,
        categories: set[DriverCategory] | None = None,  # None = hepsi
        title: str = "",
    ) -> None:
        super().__init__(parent)
        self._worker: _ScanWorker | None = None
        self._categories = categories
        self._scanned = False

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._outer = QVBoxLayout(self._content)
        self._outer.setContentsMargins(24, 20, 24, 20)
        self._outer.setSpacing(10)

        # Başlık + Yeniden tara butonu
        title_row = QHBoxLayout()
        title = QLabel(title or tr("Drivers"), self._content)
        title.setObjectName("H1")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._refresh_btn = QPushButton(tr("Scan again"), self._content)
        self._refresh_btn.clicked.connect(self._scan)
        title_row.addWidget(self._refresh_btn)
        self._outer.addLayout(title_row)

        desc = QLabel(
            tr("Linwas scans your hardware and suggests drivers and firmware updates."),
            self._content,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        self._outer.addWidget(desc)

        # Durum etiketi
        self._status_lbl = QLabel(tr("Scanning hardware…"), self._content)
        self._status_lbl.setObjectName("H2")
        self._outer.addWidget(self._status_lbl)

        # Kartların ekleneceği alan (stretch öncesinde)
        self._cards_start = self._outer.count()  # şu anki son indeks
        self._outer.addStretch(1)

        scroll.setWidget(self._content)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        # İlk açılışta taranır (Güncelleme merkezi açılırken gereksiz tarama olmasın)
        if not self._scanned:
            self._scan()

    def _clear_cards(self) -> None:
        """status_lbl sonrasındaki tüm widget'ları temizler (stretch dahil)."""
        while self._outer.count() > self._cards_start:
            item = self._outer.takeAt(self._cards_start)
            if item.widget():
                item.widget().deleteLater()

    def _scan(self) -> None:
        self._scanned = True
        self._refresh_btn.setEnabled(False)
        self._status_lbl.setText(tr("Scanning hardware…"))
        self._clear_cards()
        self._outer.addStretch(1)

        self._worker = _ScanWorker()
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._worker.start()

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(tr("Scan failed: {error}").format(error=msg))

    def _on_done(self, candidates: list) -> None:
        self._clear_cards()
        if self._categories is not None:
            candidates = [c for c in candidates if c.category in self._categories]

        if not candidates:
            self._status_lbl.setText(
                tr("No additional drivers found. Your system is using the recommended drivers.")
            )
            self._outer.addStretch(1)
            return

        # Kaç kurulmamış önerilen var?
        pending = sum(1 for d in candidates if d.recommended and not d.installed)
        if pending:
            self._status_lbl.setText(
                tr("{n} driver/firmware update(s) recommended").format(n=pending)
            )
        else:
            self._status_lbl.setText(tr("All recommended drivers are installed"))

        # Kategorilere göre grupla
        categories_seen: list[DriverCategory] = []
        by_cat: dict[DriverCategory, list[DriverCandidate]] = {}
        for d in candidates:
            if d.category not in by_cat:
                by_cat[d.category] = []
                categories_seen.append(d.category)
            by_cat[d.category].append(d)

        insert_at = self._cards_start
        for cat in categories_seen:
            header = _SectionHeader(tr(_CATEGORY_LABELS[cat]), self._content)
            self._outer.insertWidget(insert_at, header)
            insert_at += 1
            for driver in by_cat[cat]:
                card = _DriverCard(driver, self._content)
                card.action_requested.connect(self._on_action)
                self._outer.insertWidget(insert_at, card)
                insert_at += 1

        self._outer.addStretch(1)

    def _on_action(self, driver: DriverCandidate) -> None:
        if driver.package == "__fwupd_update__":
            task = Task(
                label=tr("Update firmware (fwupd)"),
                steps=[TaskStep(op_id="firmware.fwupd_update", params={})],
            )
        else:
            task = Task(
                label=tr("Install {pkg}").format(pkg=driver.package),
                steps=[TaskStep(op_id="package.install", params={"name": driver.package})],
            )
        # Sürücü kurulumu tek adım — hemen onay penceresini aç
        self.task_run_now.emit(task)
