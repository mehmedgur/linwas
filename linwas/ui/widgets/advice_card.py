"""Öneri kartı: tek cümlelik öneri, "Neden?" kanıtı ve "Şimdi değil" (süzülmüş görünüm).

Kart yalnızca öneri varsa görünür, en çok iki öneri taşır. Öneri bir şey değiştirmez: "Ayarlara bak"
ilgili ayar penceresini açar. Kanıt ve geçmiş isabet "Neden?" arkasındadır (`core/netadvice.py`).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from linwas.core import netadvice
from linwas.core.netadvice import Advice, TrackRecord
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.details_toggle import DetailsToggle
from linwas.ui.widgets.layout_utils import clear_layout


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkAdvice", text)


def title_text(advice: Advice) -> str:
    return tr("“{name}” keeps dropping").format(name=advice.name)


def summary_text(advice: Advice) -> str:
    return tr("The connection dropped {n} times in the last 7 days.").format(n=advice.drops)


def reason_lines(advice: Advice, record: TrackRecord) -> list[str]:
    """ "Neden?" bölümü: ölçülen kanıt, kural, geçmiş isabet ve hiçbir şeyin değişmediği notu."""
    lines = [
        tr("Measured: {drops} drops in {samples} readings over the last 7 days.").format(
            drops=advice.drops, samples=advice.samples
        )
    ]
    if advice.avg_signal is not None:
        lines.append(tr("Average signal: {percent}%.").format(percent=advice.avg_signal))
    if advice.avg_rtt_ms is not None:
        lines.append(
            tr("Average delay to the router: {ms} ms.").format(ms=round(advice.avg_rtt_ms))
        )
    lines.append(
        tr("Rule: shown when a connection drops {n} or more times in a week.").format(
            n=netadvice.MIN_DROPS
        )
    )
    if record.known:
        lines.append(
            tr(
                "Track record: with this kind of prediction, the problem continued the next day "
                "{hits}/{total} times."
            ).format(hits=record.hits, total=record.total)
        )
    else:
        lines.append(tr("Not enough history yet to say how reliable this kind of suggestion is."))
    lines.append(
        tr(
            "Nothing is changed for you: “Review settings” only opens the settings, where you "
            "can undo anything."
        )
    )
    return lines


class _AdviceRow(QWidget):
    review = Signal()
    dismiss = Signal()

    def __init__(
        self, advice: Advice, record: TrackRecord, can_review: bool, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AdviceRow")
        self.setStyleSheet("QWidget#AdviceRow { background: transparent; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        title = QLabel(title_text(advice), self)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        title.setWordWrap(True)
        layout.addWidget(title)
        summary = QLabel(summary_text(advice), self)
        summary.setObjectName("Secondary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.review_button = QPushButton(tr("Review settings"), self)
        self.review_button.setVisible(can_review)
        self.review_button.clicked.connect(self.review)
        buttons.addWidget(self.review_button)
        self.dismiss_button = QPushButton(tr("Not now"), self)
        self.dismiss_button.clicked.connect(self.dismiss)
        buttons.addWidget(self.dismiss_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.why = DetailsToggle(tr("Why?"), self)
        layout.addWidget(self.why, 0, Qt.AlignmentFlag.AlignLeft)
        self.reasons = QWidget(self)
        self.reasons.setObjectName("AdviceReasons")
        self.reasons.setStyleSheet("QWidget#AdviceReasons { background: transparent; }")
        box = QVBoxLayout(self.reasons)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        for line in reason_lines(advice, record):
            label = QLabel(line, self.reasons)
            label.setObjectName("Secondary")
            label.setWordWrap(True)
            box.addWidget(label)
        layout.addWidget(self.reasons)
        self.why.add_target(self.reasons)


class AdviceCard(Card):
    """Öneri yoksa gizli; satırlar yalnızca öneriler değişince yeniden kurulur (titreme olmasın)."""

    review_requested = Signal(str, str)  # kural, konu
    dismissed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        heading = QLabel(tr("Suggestions"), self)
        heading.setObjectName("H2")
        self.layout.addWidget(heading)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(6)
        self.layout.addLayout(self._rows)
        self._key: object = None
        self.setVisible(False)

    def set_items(
        self,
        items: list[tuple[Advice, TrackRecord]],
        can_review: Callable[[Advice], bool] = lambda advice: True,
    ) -> None:
        key = [(a.rule, a.subject, a.drops, r.hits, r.total, can_review(a)) for a, r in items]
        if key == self._key:
            return
        self._key = key
        clear_layout(self._rows)
        for i, (advice, record) in enumerate(items):
            if i:
                sep = QFrame(self)
                sep.setObjectName("Separator")
                sep.setFixedHeight(1)
                self._rows.addWidget(sep)
            row = _AdviceRow(advice, record, can_review(advice), self)
            row.review.connect(lambda a=advice: self.review_requested.emit(a.rule, a.subject))
            row.dismiss.connect(lambda a=advice: self.dismissed.emit(a.rule, a.subject))
            self._rows.addWidget(row)
        self.setVisible(bool(items))
