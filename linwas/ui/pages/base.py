"""Sayfa temel sınıfı: görev kuyruğu ve gezinme sinyalleri."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from linwas.core.tasks import Task


class BasePage(QWidget):
    """Tüm içerik sayfaları bu sınıfı devralır."""

    task_requested = Signal(Task)  # kuyruğa ekle (kullanıcı Uygula'ya basar)
    task_run_now = Signal(Task)  # kuyruğa ekle + hemen onay penceresini aç
    page_requested = Signal(str)  # sayfa ID'siyle gezinme
