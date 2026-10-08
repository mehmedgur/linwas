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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import driver_health
from linwas.backend import driver_options as dopt
from linwas.backend.devices import Device, list_devices
from linwas.backend.drivers import DriverCandidate, DriverCategory, list_drivers
from linwas.backend.hardware_cards import (
    PROPRIETARY_DRIVERS,
    HardwareCard,
    build_cards,
    module_version,
    short_name,
)
from linwas.core.tasks import Task, TaskStep
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("DriversPage", text)


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
    # (list[DriverCandidate], Secure Boot açık mı, MOK kayıtlı mı | None, KernelOffer | None,
    #  list[Device])
    done = Signal(object)
    error = Signal(str)

    def run(self) -> None:
        try:
            from linwas.backend.kernel import kernel_offer

            drivers = list_drivers()
            secure_boot = dopt.secure_boot_enabled()
            mok = dopt.mok_enrolled() if secure_boot else None
            self.done.emit((drivers, secure_boot, mok, kernel_offer(), list_devices()))
        except Exception as exc:
            self.error.emit(str(exc))


# --- Sağlık kontrolü ---


class _HealthWorker(QThread):
    done = Signal(object)  # list[HealthItem]

    def __init__(self, devices: list[Device], secure_boot: bool, mok: bool | None) -> None:
        super().__init__()
        self._args = (devices, secure_boot, mok)

    def run(self) -> None:
        try:
            self.done.emit(driver_health.check_all(*self._args))
        except Exception:  # denetim hiçbir zaman sayfayı düşürmesin
            self.done.emit([])


def _health_texts(item: driver_health.HealthItem) -> tuple[str, str]:
    """(başlık, açıklama)."""
    v = item.values
    texts = {
        "nvidia_ok": (
            tr("The NVIDIA driver is working"),
            tr("Version {version} is loaded."),
        ),
        "nvidia_mismatch": (
            tr("The NVIDIA driver was updated: restart needed"),
            tr(
                "Version {loaded} is running but {installed} is installed. Restart so the new "
                "version is used."
            ),
        ),
        "nvidia_secure_boot": (
            tr("Secure Boot is blocking the NVIDIA driver"),
            tr("Register the driver signing key and restart the computer."),
        ),
        "nvidia_nouveau": (
            tr("The open-source driver is still in use"),
            tr(
                "The NVIDIA driver is installed but the computer has not been restarted since. "
                "Restart to switch to it."
            ),
        ),
        "nvidia_not_loaded": (
            tr("The NVIDIA driver is installed but not running"),
            tr("Version {version} is installed but not loaded. A restart usually fixes this."),
        ),
        "dkms_ok": (
            tr("Drivers are prepared for the running kernel"),
            tr("Checked: {modules}."),
        ),
        "dkms_missing": (
            tr("Some drivers are not prepared for the running kernel"),
            tr(
                "{modules} could not be prepared for kernel {kernel}. This usually happens after "
                "a kernel update. Linwas can prepare them again."
            ),
        ),
        "render_ok": (
            tr("Graphics acceleration is working"),
            tr("Your desktop is drawn by: {renderer}."),
        ),
        "render_software": (
            tr("No graphics acceleration"),
            tr(
                "The desktop is drawn by the processor ({renderer}), so it may be slow. The "
                "graphics driver is not working."
            ),
        ),
    }
    title, body = texts.get(item.key, (item.key, ""))
    return title, body.format(**v)


# --- Donanım kartı ---

_WIFI_DRIVERS = ("iwlwifi", "ath", "rtw", "rtl8", "mt7", "brcmfmac", "wl", "b43")

# (yazı rengi, zemin) — durum rozetleri
_STATUS_STYLE = {
    "ok": ("#0e7a0e", "#e8f5e9"),
    "recommended": ("#0067c0", "#e3f2fd"),
    "problem": ("#c42b1c", "#fde7e9"),
}


def _is_wifi(device: Device) -> bool:
    name = device.name.lower()
    if any(k in name for k in ("wireless", "wi-fi", "wifi", "wlan", "802.11")):
        return True
    return device.driver.startswith(_WIFI_DRIVERS)


def _kind(card: HardwareCard) -> tuple[str, str]:
    """(simge, tür adı)."""
    group = card.group
    if group == "display":
        return "display", tr("Graphics card")
    if group == "network":
        if card.device is None or _is_wifi(card.device):
            return "network", tr("Wi-Fi")
        return "ethernet", tr("Wired network (Ethernet)")
    if group == "audio":
        return "sound", tr("Sound")
    if group == "bluetooth":
        return "bluetooth", tr("Bluetooth")
    if group == "camera":
        return "camera", tr("Camera")
    return "hardware", tr("Printer / scanner")


def _driver_text(card: HardwareCard) -> str:
    dev = card.device
    if dev is None:
        return tr("Not connected right now")
    if dev.driver in PROPRIETARY_DRIVERS:
        maker = "NVIDIA" if dev.driver == "nvidia" else "Broadcom"
        return tr("Uses the {maker} proprietary driver").format(maker=maker)
    if dev.driver:
        return tr("Uses the built-in Linux driver")
    if dev.problem:
        return tr("No driver is working for this device")
    return tr("No driver in use")


def _status_text(status: str) -> str:
    if status == "problem":
        return tr("Problem")
    if status == "recommended":
        return tr("Recommended driver available")
    return tr("Working")


class _HardwareCard(Card):
    action_requested = Signal(DriverCandidate)
    options_requested = Signal(DriverCandidate)
    revert_requested = Signal(DriverCandidate)

    def __init__(
        self,
        card: HardwareCard,
        can_revert: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.layout.setSpacing(10)
        icon_name, kind = _kind(card)
        dev = card.device

        head = QHBoxLayout()
        head.setSpacing(14)
        ico = QLabel(self)
        ico.setObjectName("CategoryIcon")
        ico.setFixedSize(48, 48)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.bind(ico, icon_name, "on_accent", 28)
        head.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        if dev is not None:
            title_text = short_name(dev.name)
        elif card.candidates:
            title_text = _description(card.candidates[0].device_name)
        else:
            title_text = kind
        title = QLabel(title_text, self)
        title.setObjectName("H2")
        title.setWordWrap(True)
        text.addWidget(title)
        sub = QLabel(f"{kind} · {_driver_text(card)}", self)
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        text.addWidget(sub)
        head.addLayout(text, 1)

        fg, bg = _STATUS_STYLE[card.status]
        badge = QLabel(_status_text(card.status), self)
        badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 10px;"
            " padding: 2px 10px; font-size: 11px; font-weight: bold;"
        )
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(head)

        # Kurulabilecek sürücüler / sürüm seçenekleri
        for cand in card.candidates:
            if cand.installed and not cand.options:
                continue
            self.layout.addWidget(self._candidate_row(cand, cand.package in can_revert))

        # Ayrıntılar (teknik bilgi)
        details_btn = QToolButton(self)
        details_btn.setObjectName("DetailsToggle")
        details_btn.setText(tr("Details"))
        details_btn.setCheckable(True)
        details_btn.setAutoRaise(True)
        details_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        icons.bind(details_btn, "chevron_right", "secondary", 14)
        details = QLabel(self._details_html(card), self)
        details.setObjectName("Secondary")
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setWordWrap(True)
        details.hide()

        def toggle(on: bool) -> None:
            details.setVisible(on)
            icons.bind(details_btn, "chevron_down" if on else "chevron_right", "secondary", 14)

        details_btn.toggled.connect(toggle)
        self.layout.addWidget(details_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(details)

    def _candidate_row(self, cand: DriverCandidate, can_revert: bool) -> QWidget:
        row = QWidget(self)
        row.setObjectName("CardRow")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(62, 0, 0, 0)
        lay.setSpacing(4)

        desc = QLabel(_description(cand.description), row)
        desc.setWordWrap(True)
        lay.addWidget(desc)

        buttons = QHBoxLayout()
        if cand.installed:
            status = QLabel("✓ " + tr("Installed"), row)
            status.setObjectName("Success")
            buttons.addWidget(status)
        else:
            btn = QPushButton(
                tr("Update firmware") if cand.package == "__fwupd_update__" else tr("Install"), row
            )
            btn.setProperty("primary", cand.recommended)
            btn.clicked.connect(lambda: self.action_requested.emit(cand))
            buttons.addWidget(btn)
        if cand.options:
            more = QPushButton(tr("Other options…"), row)
            more.setToolTip(tr("Choose another driver version or the open-source driver."))
            more.clicked.connect(lambda: self.options_requested.emit(cand))
            buttons.addWidget(more)
        if can_revert:
            back = QPushButton(tr("Return to the previous driver"), row)
            back.clicked.connect(lambda: self.revert_requested.emit(cand))
            buttons.addWidget(back)
        if cand.recommended and not cand.installed:
            buttons.addWidget(
                self._tag(tr("Recommended"), "#0067c0", "#e3f2fd"), 0, Qt.AlignmentFlag.AlignVCenter
            )
        if cand.driver_type == "proprietary":
            buttons.addWidget(
                self._tag(tr("Proprietary"), "#9d5d00", "#fff3cc"), 0, Qt.AlignmentFlag.AlignVCenter
            )
        if cand.needs_reboot and not cand.installed:
            buttons.addWidget(
                self._tag(tr("Reboot required"), "#6b3a7d", "#f3e5f5"),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
        buttons.addStretch(1)
        lay.addLayout(buttons)
        return row

    def _tag(self, text: str, fg: str, bg: str) -> QLabel:
        tag = QLabel(text, self)
        tag.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 4px;"
            " padding: 1px 7px; font-size: 11px; font-weight: bold;"
        )
        return tag

    @staticmethod
    def _details_html(card: HardwareCard) -> str:
        rows: list[tuple[str, str]] = []
        dev = card.device
        if dev is not None:
            rows.append((tr("Full name"), dev.name))
            rows.append((tr("Kernel driver"), dev.driver or "—"))
            if dev.module and dev.module != dev.driver:
                rows.append((tr("Available module"), dev.module))
            version = module_version(dev.driver)
            if version:
                rows.append((tr("Driver version"), version))
            rows.append((tr("Device ID"), f"{dev.ids} ({dev.bus.upper()})"))
        for cand in card.candidates:
            if cand.package.startswith("__"):
                continue
            state = tr("installed") if cand.installed else tr("not installed")
            rows.append((tr("Package"), f"{cand.package} ({state})"))
        return "<br>".join(f"<b>{html.escape(k)}:</b> {html.escape(v)}" for k, v in rows)


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
        self._devices: list[Device] = []
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

        # Sürücü sağlık kontrolü (yalnızca elle; yeniden taramada silinmez)
        self._health_worker: _HealthWorker | None = None
        self._health_card = self._build_health_card()
        self._outer.addWidget(self._health_card)

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
        self._health_btn.setEnabled(False)
        self._clear_health()  # sonuçlar eski taramaya ait; yeniden "Denetle" gerekir
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
        candidates, self._secure_boot, self._mok, self._kernel, devices = result
        self._clear_cards()
        if self._categories is not None:
            candidates = [c for c in candidates if c.category in self._categories]
        self._candidates = candidates
        self._devices = devices
        insert_at = self._cards_start
        # Secure Boot açık ve imza anahtarı kayıtlı değil → sürücü yüklenemez
        if self._shows(DriverCategory.GPU) and self._secure_boot and self._mok is False:
            self._outer.insertWidget(insert_at, self._mok_card())
            insert_at += 1

        self._health_btn.setEnabled(True)
        cards = build_cards(devices, candidates)
        problems = sum(1 for c in cards if c.status == "problem")
        pending = sum(1 for d in candidates if d.recommended and not d.installed)
        if problems:
            self._status_lbl.setText(tr("{n} device(s) need attention").format(n=problems))
        elif pending:
            self._status_lbl.setText(
                tr("{n} driver/firmware update(s) recommended").format(n=pending)
            )
        else:
            self._status_lbl.setText(tr("All your hardware is working"))

        for card in cards:
            can_revert: set[str] = set()
            for driver in card.candidates:
                change = dopt.last_change(driver.device_name) if driver.options else None
                if change is not None and change.new == self._current_package(driver):
                    can_revert.add(driver.package)
            widget = _HardwareCard(card, can_revert, self._content)
            widget.action_requested.connect(self._on_action)
            widget.options_requested.connect(self._on_options)
            widget.revert_requested.connect(self._on_revert)
            self._outer.insertWidget(insert_at, widget)
            insert_at += 1

        self._add_troubleshooting()
        self._outer.addStretch(1)

    # --- Sağlık kontrolü ---

    def _build_health_card(self) -> Card:
        card = Card(self._content)
        head = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        h = QLabel(tr("Driver health check"), card)
        h.setObjectName("H2")
        text.addWidget(h)
        hint = QLabel(
            tr(
                "Checks that installed drivers are really working: loaded, built for the "
                "running kernel and drawing your desktop."
            ),
            card,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        text.addWidget(hint)
        head.addLayout(text, 1)
        self._health_btn = QPushButton(tr("Check"), card)
        self._health_btn.setEnabled(False)  # tarama bitince açılır
        self._health_btn.clicked.connect(self._check_health)
        head.addWidget(self._health_btn, 0, Qt.AlignmentFlag.AlignTop)
        card.layout.addLayout(head)
        self._health_box = QVBoxLayout()
        self._health_box.setSpacing(8)
        card.layout.addLayout(self._health_box)
        return card

    def _clear_health(self) -> None:
        while self._health_box.count():
            item = self._health_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _check_health(self) -> None:
        self._health_btn.setEnabled(False)
        self._clear_health()
        busy = QLabel(tr("Checking drivers…"), self._health_card)
        busy.setObjectName("Secondary")
        self._health_box.addWidget(busy)
        self._health_worker = _HealthWorker(self._devices, self._secure_boot, self._mok)
        self._health_worker.done.connect(self._on_health)
        self._health_worker.finished.connect(lambda: self._health_btn.setEnabled(True))
        self._health_worker.start()

    def _on_health(self, items: list) -> None:
        self._clear_health()
        if not items:
            lbl = QLabel(tr("Nothing to check: no extra drivers are in use."), self._health_card)
            lbl.setObjectName("Secondary")
            self._health_box.addWidget(lbl)
            return
        for item in items:
            self._health_box.addWidget(self._health_row(item))

    def _health_row(self, item: driver_health.HealthItem) -> QWidget:
        row = QWidget(self._health_card)
        row.setObjectName("CardRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        mark = QLabel(row)
        mark.setFixedSize(22, 22)
        icons.bind(mark, "check" if item.ok else "info", "accent" if item.ok else "normal", 20)
        if not item.ok:
            mark.setStyleSheet("background-color: #fde7e9; border-radius: 11px;")
        lay.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)

        title, body = _health_texts(item)
        text = QVBoxLayout()
        text.setSpacing(2)
        t = QLabel(title, row)
        t.setObjectName("AppName" if not item.ok else "")
        t.setWordWrap(True)
        text.addWidget(t)
        b = QLabel(body, row)
        b.setObjectName("Secondary")
        b.setWordWrap(True)
        text.addWidget(b)
        lay.addLayout(text, 1)

        fix = self._fix_button(item, row)
        if fix is not None:
            lay.addWidget(fix, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _fix_button(self, item: driver_health.HealthItem, parent: QWidget) -> QPushButton | None:
        if item.fix == "reboot":
            btn = QPushButton(tr("Restart now"), parent)
            btn.clicked.connect(self._restart)
        elif item.fix == "rebuild_modules":
            btn = QPushButton(tr("Prepare drivers again"), parent)
            btn.clicked.connect(lambda: self._rebuild_modules(item.package))
        elif item.fix == "secure_boot":
            btn = QPushButton(tr("Register the key"), parent)
            btn.clicked.connect(self._enroll_key)
        elif item.fix == "ask_ai":
            btn = QPushButton(tr("Ask the assistant"), parent)
            title, body = _health_texts(item)
            btn.clicked.connect(lambda: self.ai_help_requested.emit(title, body))
        else:
            return None
        btn.setProperty("primary", True)
        return btn

    def _restart(self) -> None:
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            tr("Restart now"),
            tr("Save your work first. Restart the computer now?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            QProcess.startDetached("systemctl", ["reboot"])

    def _rebuild_modules(self, headers: str) -> None:
        steps: list[TaskStep] = []
        if headers:
            steps.append(
                TaskStep(
                    op_id="package.install",
                    label=tr("Install {pkg}").format(pkg=headers),
                    params={"name": headers},
                )
            )
        steps.append(
            TaskStep(
                op_id="driver.rebuild_modules",
                label=tr("Prepare drivers for the running kernel"),
                params={},
            )
        )
        self.task_run_now.emit(Task(label=tr("Prepare drivers again"), steps=steps))

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
