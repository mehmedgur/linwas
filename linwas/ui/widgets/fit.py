"""Düğme genişliği: alabileceği bütün yazılar sığsın (sabit genişlik Türkçede kesiliyordu)."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

# stylesheet.py › QPushButton: padding 7px 18px + 1px kenarlık
_H_PADDING = 2 * 18 + 2 + 6


def fit_width(button: QPushButton, *texts: str) -> None:
    """En uzun yazıya göre en az genişlik verir; yazı değişince düğme zıplamaz."""
    button.ensurePolished()
    metrics = button.fontMetrics()
    widest = max(metrics.horizontalAdvance(t) for t in (*texts, button.text()))
    icon = button.iconSize().width() + 8 if not button.icon().isNull() else 0
    button.setMinimumWidth(widest + _H_PADDING + icon)
