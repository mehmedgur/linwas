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
    ai_help_requested = Signal(str, str)  # (görev adı, hata çıktısı) → AI asistanına sorulur

    def on_tasks_finished(self) -> None:
        """Görevler bittiğinde ana pencere çağırır; sayfa durumunu yenileyebilir."""
