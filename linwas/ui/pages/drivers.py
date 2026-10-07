"""Sürücüler / Firmware görünümü (Güncelleme merkezi altında) — GPU, Ağ/Wi-Fi, Firmware."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
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

from linwas.backend import driver_options as dopt
from linwas.backend.drivers import DriverCandidate, DriverCategory, list_drivers
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("DriversPage", text)


_CATEGORY_LABELS = {
    DriverCategory.GPU: "Graphics",
    DriverCategory.NETWORK: "Network & Wi-Fi",
    DriverCategory.PRINTER: "Printers & Scanners",
    DriverCategory.FIRMWARE: "Firmware Updates",
}


def _translation_markers() -> None:
    """Dinamik kategori etiketleri için çeviri tarayıcısı işaretleyicileri. Hiç çağrılmaz."""
    tr("Graphics")
    tr("Network & Wi-Fi")
    tr("Printers & Scanners")
    tr("Firmware Updates")


def _description(text: str) -> str:
    """Backend'in İngilizce açıklamasını çevirir (sayılı fwupd metni ayrıca ele alınır)."""
    m = re.match(r"^(\d+) firmware update\(s\) available", text)
    if m:
        return tr("{n} firmware update(s) available (BIOS, SSD, docks…).").format(n=m.group(1))
    m = re.match(r"^(\d+) device\(s\)$", text)
    if m:
        return tr("{n} device(s)").format(n=m.group(1))
    # Değişken adla çağrılır: çeviri denetimi (tests/test_translations.py) modül bağlamını
    # sabit olmayan `QCoreApplication.translate` çağrısından okur, bu çağrı onu bozmasın
    translate = QCoreApplication.translate
    return translate("DriverDescriptions", text)


def _description_markers() -> None:
    """backend/drivers.py açıklamaları için çeviri işaretleyicileri. Hiç çağrılmaz."""
    QCoreApplication.translate(
        "DriverDescriptions", "AMD GPU firmware — improves stability and performance."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "Broadcom STA proprietary driver — alternative if firmware fails."
    )
    QCoreApplication.translate("DriverDescriptions", "Broadcom Wi-Fi driver is installed.")
    QCoreApplication.translate(
        "DriverDescriptions", "Broadcom Wi-Fi firmware — required for wireless to work."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "Intel Wi-Fi firmware — required for some Intel wireless cards."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "Intel media driver — hardware video decode/encode acceleration."
    )
    QCoreApplication.translate(
        "DriverDescriptions",
        "Lets the computer use printers and scanners that work without a driver over USB "
        "(IPP-over-USB).",
    )
    QCoreApplication.translate(
        "DriverDescriptions", "MediaTek Wi-Fi firmware — required for wireless to work."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "NVIDIA open-source kernel modules (Turing+ only, experimental)."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "NVIDIA proprietary driver — better performance and CUDA support."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "NVIDIA proprietary driver — recommended for full performance."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "Printer driver for this brand, from your system's software sources."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "Realtek network firmware — required for some Realtek cards."
    )
    QCoreApplication.translate(
        "DriverDescriptions", "fwupd — hardware firmware updates (BIOS, SSD, dock, etc.)."
    )
    QCoreApplication.translate("DriverDescriptions", "Firmware Update Tool")
    QCoreApplication.translate(
        "DriverDescriptions",
        "Vulkan graphics for AMD and Intel — needed by most games (and Proton).",
    )
    QCoreApplication.translate(
        "DriverDescriptions", "AMD video acceleration — smoother video with less CPU use."
    )
    QCoreApplication.translate(
        "DriverDescriptions",
        "Processor microcode — security and stability fixes from the CPU maker.",
    )
    QCoreApplication.translate("DriverDescriptions", "Processor (CPU)")


# --- Worker ---


class _ScanWorker(QThread):
    # (list[DriverCandidate], Secure Boot açık mı, MOK kayıtlı mı | None, KernelOffer | None)
    done = Signal(object)
    error = Signal(str)

    def run(self) -> None:
        try:
            from linwas.backend.kernel import kernel_offer

            drivers = list_drivers()
            secure_boot = dopt.secure_boot_enabled()
            mok = dopt.mok_enrolled() if secure_boot else None
            self.done.emit((drivers, secure_boot, mok, kernel_offer()))
        except Exception as exc:
            self.error.emit(str(exc))


# --- Sürücü kartı ---


class _DriverCard(Card):
    action_requested = Signal(DriverCandidate)
    options_requested = Signal(DriverCandidate)
    revert_requested = Signal(DriverCandidate)

    def __init__(
        self, driver: DriverCandidate, parent: QWidget | None = None, can_revert: bool = False
    ) -> None:
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
        dev_lbl = QLabel(_description(driver.device_name), self)
        dev_lbl.setObjectName("Secondary")
        dev_lbl.setWordWrap(True)
        self.layout.addWidget(dev_lbl)

        # Aktif sürücü (bilgi satırı)
        if driver.current_driver:
            active_lbl = QLabel(tr("Current driver: {d}").format(d=driver.current_driver), self)
            active_lbl.setObjectName("Secondary")
            self.layout.addWidget(active_lbl)

        # Açıklama
        desc_lbl = QLabel(_description(driver.description), self)
        desc_lbl.setWordWrap(True)
        self.layout.addWidget(desc_lbl)

        # Alt satır: eylem düğmeleri
        row = QHBoxLayout()
        if driver.installed:
            status = QLabel("✓ " + tr("Installed"), self)
            status.setStyleSheet("color: #0e7a0e; font-weight: bold;")
            row.addWidget(status)
        elif driver.package == "__fwupd_update__":
            btn = QPushButton(tr("Update firmware"), self)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda: self.action_requested.emit(driver))
            row.addWidget(btn)
        else:
            btn = QPushButton(tr("Install"), self)
            btn.setProperty("primary", driver.recommended)
            btn.clicked.connect(lambda: self.action_requested.emit(driver))
            row.addWidget(btn)
        if driver.options:
            more = QPushButton(tr("Other options…"), self)
            more.setToolTip(tr("Choose another driver version or the open-source driver."))
            more.clicked.connect(lambda: self.options_requested.emit(driver))
            row.addWidget(more)
        if can_revert:
            back = QPushButton(tr("Return to the previous driver"), self)
            back.clicked.connect(lambda: self.revert_requested.emit(driver))
            row.addWidget(back)
        row.addStretch(1)
        self.layout.addLayout(row)

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
        self._secure_boot = False
        self._mok: bool | None = None
        self._kernel = None  # backend.kernel.KernelOffer | None
        self._candidates: list[DriverCandidate] = []
        # Görev bitince geçmişe yazılacak değişiklik: (aygıt, önceki paket, yeni paket)
        self._pending_change: tuple[str, str, str] | None = None

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

    def _shows(self, category: DriverCategory) -> bool:
        return self._categories is None or category in self._categories

    def _on_done(self, result: tuple) -> None:
        candidates, self._secure_boot, self._mok, self._kernel = result
        self._clear_cards()
        if self._categories is not None:
            candidates = [c for c in candidates if c.category in self._categories]
        self._candidates = candidates
        insert_at = self._cards_start
        # Secure Boot açık ve imza anahtarı kayıtlı değil → sürücü yüklenemez
        if self._shows(DriverCategory.GPU) and self._secure_boot and self._mok is False:
            self._outer.insertWidget(insert_at, self._mok_card())
            insert_at += 1

        if not candidates:
            self._status_lbl.setText(
                tr("No additional drivers found. Your system is using the recommended drivers.")
            )
            self._add_troubleshooting()
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

        for cat in categories_seen:
            header = _SectionHeader(tr(_CATEGORY_LABELS[cat]), self._content)
            self._outer.insertWidget(insert_at, header)
            insert_at += 1
            for driver in by_cat[cat]:
                change = dopt.last_change(driver.device_name) if driver.options else None
                current = self._current_package(driver)
                can_revert = change is not None and change.new == current
                card = _DriverCard(driver, self._content, can_revert=can_revert)
                card.action_requested.connect(self._on_action)
                card.options_requested.connect(self._on_options)
                card.revert_requested.connect(self._on_revert)
                self._outer.insertWidget(insert_at, card)
                insert_at += 1

        self._add_troubleshooting()
        self._outer.addStretch(1)

    # --- Secure Boot ve sorun giderme kartları ---

    def _mok_card(self) -> Card:
        card = Card(self._content)
        h = QLabel(tr("Secure Boot: the driver signing key is not registered"), card)
        h.setObjectName("H2")
        h.setWordWrap(True)
        card.layout.addWidget(h)
        text = QLabel(
            tr(
                "Secure Boot is on, so drivers such as NVIDIA load only after their signing key "
                "is registered. Linwas gives you a one-time password; type it on the blue screen "
                "that appears at the next restart."
            ),
            card,
        )
        text.setWordWrap(True)
        card.layout.addWidget(text)
        btn = QPushButton(tr("Register the key"), card)
        btn.setProperty("primary", True)
        btn.clicked.connect(self._enroll_key)
        card.layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _add_kernel_card(self) -> None:
        """Yeni donanım için daha yeni çekirdek (Ubuntu HWE / Debian backports)."""
        offer = self._kernel
        if offer is None or not self._shows(DriverCategory.GPU):
            return
        import os

        card = Card(self._content)
        h = QLabel(tr("Newer kernel for new hardware"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        if offer.kind == "hwe":
            what = tr("Ubuntu's hardware enablement (HWE) kernel")
        else:
            what = tr("the newer kernel from {suite}").format(suite=offer.suite)
        text = tr(
            "If a very new device (Wi-Fi, graphics, touchpad…) does not work, {what} may "
            "support it. You are using kernel {running}."
        ).format(what=what, running=os.uname().release)
        if offer.version:
            text += " " + tr("Offered version: {version}.").format(version=offer.version)
        body = QLabel(text, card)
        body.setWordWrap(True)
        card.layout.addWidget(body)
        warn = QLabel(
            tr(
                "Install it only if something does not work. A full system backup is taken "
                "first; the old kernel stays and can be chosen at startup. A restart is required."
            ),
            card,
        )
        warn.setObjectName("Secondary")
        warn.setWordWrap(True)
        card.layout.addWidget(warn)
        btn = QPushButton(tr("Install the newer kernel"), card)
        btn.clicked.connect(self._install_kernel)
        card.layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._outer.addWidget(card)

    def _install_kernel(self) -> None:
        import shutil

        offer = self._kernel
        if offer is None:
            return
        steps: list[TaskStep] = []
        if shutil.which("timeshift"):
            steps.append(
                TaskStep(
                    op_id="snapshot.timeshift_create",
                    label=tr("System backup (Timeshift)"),
                    params={},
                )
            )
        if offer.kind == "hwe":
            steps.append(
                TaskStep(
                    op_id="package.install",
                    label=tr("Install {pkg}").format(pkg=offer.package),
                    params={"name": offer.package},
                )
            )
        else:
            if offer.kind == "enable-backports":
                steps += [
                    TaskStep(
                        op_id="apt.add_source",
                        label=tr("Enable {suite}").format(suite=offer.suite),
                        params={
                            "source_line": offer.source_line,
                            "list_name": "linwas-backports.list",
                        },
                    ),
                    TaskStep(
                        op_id="package.update_index",
                        label=tr("Refresh package index"),
                        params={},
                    ),
                ]
            steps.append(
                TaskStep(
                    op_id="kernel.install_backports",
                    label=tr("Install the newer kernel"),
                    params={"suite": offer.suite},
                )
            )
        self.task_run_now.emit(Task(label=tr("Install the newer kernel"), steps=steps))

    def _add_troubleshooting(self) -> None:
        self._add_kernel_card()
        if not (self._shows(DriverCategory.GPU) or self._shows(DriverCategory.NETWORK)):
            return
        card = Card(self._content)
        h = QLabel(tr("Problems after installing a driver?"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        tips = [
            (
                tr("Black screen or the desktop does not open"),
                tr(
                    "At startup choose “Advanced options” in the boot menu and start an older "
                    "kernel or recovery mode. When Linwas opens, press “Return to the previous "
                    "driver”. You can also restore the Timeshift backup taken before the change."
                ),
            ),
            (
                tr("Wrong resolution or blurry screen"),
                tr("Restart once. If it stays, choose the resolution under Display & Scaling."),
            ),
            (
                tr("Secure Boot is on and the driver does not load"),
                tr(
                    "The key was probably not registered on the blue screen. Use “Register the "
                    "key” above and restart."
                ),
            ),
            (
                tr("Wi-Fi stopped working after a firmware or driver install"),
                tr("Restart the computer; firmware is loaded only at startup."),
            ),
        ]
        for title, body in tips:
            lbl = QLabel(f"<b>{html.escape(title)}</b><br>{html.escape(body)}", card)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            card.layout.addWidget(lbl)
        ask = QPushButton(tr("Ask the assistant"), card)
        ask.clicked.connect(self._ask_ai)
        card.layout.addWidget(ask, 0, Qt.AlignmentFlag.AlignLeft)
        self._outer.addWidget(card)

    def _ask_ai(self) -> None:
        lines = [
            f"{d.device_name}: {d.package} ({'installed' if d.installed else 'not installed'}), "
            f"kernel driver: {d.current_driver or '-'}"
            for d in self._candidates
        ]
        lines.append(f"Secure Boot: {'on' if self._secure_boot else 'off'}")
        if self._secure_boot:
            lines.append(f"MOK key registered: {self._mok}")
        self.ai_help_requested.emit(tr("Driver problem"), "\n".join(lines))

    # --- Sürücü değiştirme ---

    @staticmethod
    def _current_package(driver: DriverCandidate) -> str:
        return next((o.package for o in driver.options if o.installed), "")

    def _on_options(self, driver: DriverCandidate) -> None:
        from linwas.ui.dialogs.driver_options import DriverOptionsDialog

        dialog = DriverOptionsDialog(driver.device_name, driver.options, self)
        if dialog.exec() == DriverOptionsDialog.DialogCode.Accepted and dialog.selected:
            self._change_driver(driver, dialog.selected.package)

    def _on_revert(self, driver: DriverCandidate) -> None:
        change = dopt.last_change(driver.device_name)
        if change:
            self._change_driver(driver, change.previous)

    def _change_driver(self, driver: DriverCandidate, package: str) -> None:
        """Yedek (Timeshift varsa) → sürücü kur/kaldır → Secure Boot açıksa anahtar kaydı."""
        import shutil

        from linwas.ui.dialogs.driver_options import confirm_mok_password

        steps: list[TaskStep] = []
        if shutil.which("timeshift"):
            steps.append(
                TaskStep(
                    op_id="snapshot.timeshift_create",
                    label=tr("System backup (Timeshift)"),
                    params={},
                )
            )
        if package:
            steps.append(
                TaskStep(
                    op_id="package.install",
                    label=tr("Install {pkg}").format(pkg=package),
                    params={"name": package},
                )
            )
            if self._secure_boot and self._mok is not True:
                password = dopt.new_mok_password()
                if not confirm_mok_password(password, self):
                    return
                steps.append(
                    TaskStep(
                        op_id="secureboot.enroll_mok",
                        label=tr("Register the driver signing key"),
                        params={"password": password},
                    )
                )
            label = tr("Switch to {pkg}").format(pkg=package)
        else:
            steps.append(
                TaskStep(
                    op_id="driver.remove_nvidia",
                    label=tr("Switch to the open-source driver"),
                    params={},
                )
            )
            label = tr("Switch to the open-source driver")
        self._pending_change = (driver.device_name, self._current_package(driver), package)
        self.task_run_now.emit(Task(label=label, steps=steps))

    def _enroll_key(self) -> None:
        from linwas.ui.dialogs.driver_options import confirm_mok_password

        password = dopt.new_mok_password()
        if not confirm_mok_password(password, self):
            return
        self.task_run_now.emit(
            Task(
                label=tr("Register the driver signing key"),
                steps=[
                    TaskStep(op_id="secureboot.enroll_mok", params={"password": password}),
                ],
            )
        )

    def on_tasks_finished(self) -> None:
        # Sürücü değişikliği başarılıysa geçmişe yazılır ("Önceki sürücüye dön" için)
        if self._pending_change:
            device, previous, new = self._pending_change
            self._pending_change = None
            from linwas.backend.drivers import dpkg_installed

            done = dpkg_installed(new) if new else not (previous and dpkg_installed(previous))
            if done and new != previous:
                dopt.record_change(device, previous, new)
        if self._scanned:
            self._scan()

    def _on_action(self, driver: DriverCandidate) -> None:
        if driver.options and not driver.installed:
            # Önerilen sürücü: yedek + Secure Boot adımlarıyla birlikte kurulur
            self._change_driver(driver, driver.package)
            return
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
