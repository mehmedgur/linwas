"""Düzen yardımcıları."""

from __future__ import annotations

from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    """Düzendeki bileşenleri güvenle kaldırır.

    `deleteLater()` yerine bileşen önce üst parçadan ayrılır; Python referansı bırakılınca hemen
    silinir. Böylece sahibi (kart/sayfa) hemen ardından yok edilse bile bekleyen bir `deleteLater`
    olayı kalmaz (PySide'da çift silme ve çökme riski).
    """
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)  # type: ignore[arg-type]
