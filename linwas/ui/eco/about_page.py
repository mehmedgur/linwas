"""Hakkında sayfası: sistem bilgisi ve donanım özeti (salt okunur)."""

from __future__ import annotations

import os

from PySide6.QtCore import QCoreApplication

from linwas import __version__
from linwas.backend.desktop import Desktop, detect_desktop, detect_session_type
from linwas.backend.distro import detect_distro
from linwas.backend.sysinfo import SystemInfo, read_system_info
from linwas.ui.eco.widgets import InfoCard, Page


def tr(text: str) -> str:
    return QCoreApplication.translate("EcoAboutPage", text)


def format_uptime(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return tr("{days} days {hours} hours").format(days=days, hours=hours)
    if hours:
        return tr("{hours} hours {minutes} minutes").format(hours=hours, minutes=minutes)
    return tr("{minutes} minutes").format(minutes=minutes)


def _desktop_name(desktop: Desktop) -> str:
    names = {
        Desktop.GNOME: "GNOME",
        Desktop.CINNAMON: "Cinnamon",
        Desktop.XFCE: "XFCE",
        Desktop.KDE: "KDE Plasma",
        Desktop.OTHER: tr("Other"),
        Desktop.UNKNOWN: tr("Unknown"),
    }
    return names[desktop]


def _graphics_server(session: str) -> str:
    return {"wayland": "Wayland", "x11": "X11"}.get(session, tr("Unknown"))


def system_rows(info: SystemInfo) -> list[tuple[str, str]]:
    distro = detect_distro()
    rows = [
        (tr("Operating system"), distro.display_name or tr("Unknown")),
        (tr("Kernel"), info.kernel),
        (tr("Desktop shell"), _desktop_name(detect_desktop(os.environ))),
        (tr("Graphics server"), _graphics_server(detect_session_type(os.environ))),
        (tr("Architecture"), info.architecture),
        (tr("Uptime"), format_uptime(info.uptime_seconds) if info.uptime_seconds else ""),
    ]
    return [(label, value) for label, value in rows if value]


def hardware_rows(info: SystemInfo) -> list[tuple[str, str]]:
    cores = ""
    if info.cpu_cores and info.cpu_threads:
        cores = tr("{cores} cores / {threads} threads").format(
            cores=info.cpu_cores, threads=info.cpu_threads
        )
    elif info.cpu_threads:
        cores = tr("{threads} threads").format(threads=info.cpu_threads)
    ram = f"{round(info.ram_bytes / 1024**3)} GB" if info.ram_bytes else ""
    rows = [
        (tr("Processor"), info.cpu_model),
        (tr("Cores / threads"), cores),
        (tr("Memory"), ram),
        (tr("Storage"), ", ".join(info.disks)),
        (tr("Motherboard"), info.board),
    ]
    return [(label, value) for label, value in rows if value]


class AboutPage(Page):
    def __init__(self) -> None:
        super().__init__(tr("About"), tr("System information and hardware summary"))
        info = read_system_info()
        distro = detect_distro()
        self.body.addWidget(
            InfoCard(
                distro.display_name or tr("Unknown"),
                [(tr("Settings app"), f"Linwas {__version__}")],
            )
        )
        self.body.addWidget(InfoCard(tr("System information"), system_rows(info)))
        self.body.addWidget(InfoCard(tr("Hardware summary"), hardware_rows(info)))
        self.body.addStretch(1)
