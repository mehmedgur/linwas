# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Güncelleme merkezi › Firmware: fwupd güncellemeleri (sürüm notlarıyla), aygıtlar, geçmiş ve
işlemci mikrokodu."""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import firmware
from linwas.backend.drivers import DriverCandidate, available_in_repo, microcode_candidates
from linwas.core.autoupdate import on_battery
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("FirmwareView", text)


def _error_text(error: str) -> str:
    """fwupd'nin sık hata nedenleri (İngilizce) → sade Türkçe; bilinmeyen olduğu gibi."""
    known = {
        "Device requires AC power to be connected": tr(
            "The computer must be plugged in to update this device."
        ),
        "System requires external power source": tr(
            "The computer must be plugged in to update this device."
        ),
        "Device battery power is too low": tr("The device battery is too low."),
    }
    return known.get(error, error)


@dataclass
class _Data:
    available: bool = False
    updates: list[firmware.FirmwareDevice] = field(default_factory=list)
    devices: list[firmware.FirmwareDevice] = field(default_factory=list)
    history: list[firmware.FirmwareDevice] = field(default_factory=list)
    microcode: list[DriverCandidate] = field(default_factory=list)
    battery: bool = False


class _Worker(QThread):
    done = Signal(object)  # _Data

    def run(self) -> None:
        data = _Data(available=firmware.available(), battery=on_battery())
        try:
            micro = microcode_candidates()
            names = available_in_repo([c.package for c in micro])
            data.microcode = [c for c in micro if c.package in names]
            if data.available:
                data.updates = firmware.list_updates()
                data.devices = firmware.list_devices()
                data.history = firmware.list_history()
        except Exception:
            pass
        self.done.emit(data)


def _clear(layout) -> None:  # noqa: ANN001 - QLayout
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


class FirmwareView(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _Worker | None = None
        self._loaded = False
        self._data = _Data()

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel(tr("Firmware"), content)
        title.setObjectName("H1")
        head.addWidget(title)
        head.addStretch(1)
        self._refresh_btn = QPushButton(tr("Download latest information"), content)
        self._refresh_btn.setToolTip(
            tr("Downloads the list of firmware updates from LVFS (asks for your password).")
        )
        self._refresh_btn.clicked.connect(self._refresh_metadata)
        head.addWidget(self._refresh_btn)
        outer.addLayout(head)
        intro = QLabel(
            tr(
                "Firmware is the built-in software of devices such as the BIOS, SSD, docks and "
                "the processor. Updates come from the device makers through LVFS."
            ),
            content,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        outer.addWidget(intro)
        self._body = QVBoxLayout()
        self._body.setSpacing(12)
        outer.addLayout(self._body)
        outer.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if not self._loaded:
            self.reload()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            self.reload()

    def reload(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._loaded = True
        _clear(self._body)
        loading = QLabel(tr("Reading firmware information…"), self)
        loading.setObjectName("Secondary")
        self._body.addWidget(loading)
        self._worker = _Worker(self)
        self._worker.done.connect(self._on_data)
        self._worker.start()

    # --- Çizim ---

    def _on_data(self, data: _Data) -> None:
        self._data = data
        _clear(self._body)
        self._refresh_btn.setEnabled(data.available)
        if not data.available:
            card = Card(self)
            text = QLabel(tr("The firmware update tool (fwupd) is not installed."), card)
            text.setWordWrap(True)
            card.layout.addWidget(text)
            btn = QPushButton(tr("Install fwupd"), card)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda: self._install_package("fwupd"))
            card.layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
            self._body.addWidget(card)
        else:
            self._body.addWidget(self._updates_card(data))
        for micro in data.microcode:
            self._body.addWidget(self._microcode_card(micro))
        if data.available:
            self._body.addWidget(self._devices_card(data.devices))
            if data.history:
                self._body.addWidget(self._history_card(data.history))

    def _updates_card(self, data: _Data) -> Card:
        card = Card(self)
        h = QLabel(tr("Available firmware updates"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        if not data.updates:
            none = QLabel(tr("No firmware updates. Your devices are up to date."), card)
            none.setObjectName("Secondary")
            card.layout.addWidget(none)
            return card
        warn = QLabel(
            tr(
                "Do not turn off the computer while firmware is updating. Some updates "
                "finish during the next restart."
            ),
            card,
        )
        warn.setObjectName("Warning")
        warn.setWordWrap(True)
        card.layout.addWidget(warn)
        for dev in data.updates:
            card.layout.addWidget(self._update_row(dev, data.battery))
        return card

    def _update_row(self, dev: firmware.FirmwareDevice, battery: bool) -> QWidget:
        box = QFrame(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        release = dev.releases[0]
        top = QHBoxLayout()
        name = QLabel(f"<b>{html.escape(dev.name)}</b>", box)
        top.addWidget(name)
        if release.urgency in ("high", "critical"):
            pill = QLabel(tr("Important"), box)
            pill.setObjectName("Pill")
            top.addWidget(pill)
        top.addStretch(1)
        btn = QPushButton(tr("Update"), box)
        btn.setProperty("primary", True)
        blocked = dev.requires_ac and battery
        btn.setEnabled(not blocked)
        if blocked:
            btn.setToolTip(tr("Plug in the computer to update this device."))
        btn.clicked.connect(lambda: self._update_device(dev))
        top.addWidget(btn)
        layout.addLayout(top)
        ver = QLabel(
            tr("{vendor} · version {old} → {new}").format(
                vendor=dev.vendor or "—", old=dev.version or "?", new=release.version
            ),
            box,
        )
        ver.setObjectName("Secondary")
        layout.addWidget(ver)
        extra = []
        if dev.needs_reboot:
            extra.append(tr("Finishes during the next restart."))
        if dev.requires_ac:
            extra.append(tr("The computer must be plugged in."))
        if release.summary:
            extra.insert(0, release.summary)
        if extra:
            info = QLabel(" ".join(extra), box)
            info.setWordWrap(True)
            layout.addWidget(info)
        if release.notes:
            notes = QLabel(release.notes, box)
            notes.setObjectName("Caption")
            notes.setWordWrap(True)
            notes.hide()
            more = QPushButton(tr("Release notes"), box)
            more.setFlat(True)
            more.clicked.connect(lambda: notes.setVisible(not notes.isVisible()))
            layout.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(notes)
        return box

    def _microcode_card(self, micro: DriverCandidate) -> Card:
        card = Card(self)
        h = QLabel(tr("Processor microcode"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        text = QLabel(
            tr(
                "Security and stability fixes from the processor maker, loaded at every start "
                "({pkg})."
            ).format(pkg=micro.package),
            card,
        )
        text.setWordWrap(True)
        card.layout.addWidget(text)
        if micro.installed:
            ok = QLabel("✓ " + tr("Installed; updated together with system updates."), card)
            ok.setObjectName("Success")
            card.layout.addWidget(ok)
        else:
            btn = QPushButton(tr("Install"), card)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda: self._install_package(micro.package))
            card.layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _devices_card(self, devices: list[firmware.FirmwareDevice]) -> Card:
        card = Card(self)
        h = QLabel(tr("Devices"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        for dev in devices:
            state = tr("can be updated") if dev.updatable else tr("updates not supported")
            line = f"<b>{html.escape(dev.name)}</b> · {html.escape(dev.version)} · {state}"
            if dev.update_error:
                line += (
                    "<br><span style='font-size: 13px'>"
                    + html.escape(_error_text(dev.update_error))
                    + "</span>"
                )
            lbl = QLabel(line, card)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            card.layout.addWidget(lbl)
        return card

    def _history_card(self, history: list[firmware.FirmwareDevice]) -> Card:
        card = Card(self)
        h = QLabel(tr("Firmware update history"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        for dev in history:
            version = dev.releases[0].version if dev.releases else dev.version
            lbl = QLabel(
                tr("{name}: version {version}").format(name=dev.name, version=version), card
            )
            lbl.setWordWrap(True)
            card.layout.addWidget(lbl)
        return card

    # --- İşlemler ---

    def _refresh_metadata(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Download latest firmware information"),
                steps=[TaskStep(op_id="firmware.refresh", params={})],
            )
        )

    def _update_device(self, dev: firmware.FirmwareDevice) -> None:
        answer = QMessageBox.question(
            self,
            tr("Update firmware"),
            tr(
                "Update the firmware of {name}? Keep the computer plugged in and do not turn "
                "it off until it finishes."
            ).format(name=dev.name),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.task_run_now.emit(
            Task(
                label=tr("Update firmware: {name}").format(name=dev.name),
                steps=[
                    TaskStep(op_id="firmware.update_device", params={"device_id": dev.device_id})
                ],
            )
        )

    def _install_package(self, pkg: str) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install {pkg}").format(pkg=pkg),
                steps=[TaskStep(op_id="package.install", params={"name": pkg})],
            )
        )
