"""Wi-Fi sekmesinin "Bağlantı kalitesi" kartı: son 24 saatin çizelgesi ve bağlantı testi.

Ölçüm yalnızca açık rıza ile çalışır (varsayılan kapalı); kayıtlar bu bilgisayarda kalır
(`core/netlog.py`, `backend/netquality.py`).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from linwas.backend import netquality
from linwas.core import app_settings, netlog
from linwas.core.netlog import Bucket, WifiSummary
from linwas.ui import icons
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.jobs import Jobs
from linwas.ui.widgets.quality_chart import QualityChart

BUCKET_SECONDS = 900  # 15 dakika → 96 çubuk
HISTORY_SECONDS = 24 * 3600
MIN_SAMPLES = 5  # bundan azıyla çizelge gösterilmez
REFRESH_SECONDS = 60


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkPage", text)


# --- Metinler (arayüzden bağımsız, test edilebilir) ---


def history_for_chart(now: int | None = None) -> tuple[list[Bucket], WifiSummary]:
    """Son 24 saatin dilimleri ve özeti (disk okur; arka plan işinde çağrılır)."""
    ts = int(time.time()) if now is None else now
    end = (ts // BUCKET_SECONDS + 1) * BUCKET_SECONDS
    start = end - HISTORY_SECONDS
    samples = netlog.load(since=start, kind=netlog.KIND_WIFI)
    offset = time.localtime(ts).tm_gmtoff or 0
    return (
        netlog.bucketize(samples, start, end, BUCKET_SECONDS),
        netlog.summarize_wifi(samples, utc_offset=offset),
    )


def summary_text(summary: WifiSummary) -> str:
    parts = [tr("Disconnections: {n}").format(n=summary.disconnects)]
    if summary.stalls:
        parts.append(tr("Router stopped answering: {n}").format(n=summary.stalls))
    if summary.avg_rtt_ms is not None:
        parts.append(tr("Average delay: {ms} ms").format(ms=round(summary.avg_rtt_ms)))
    if summary.worst_hour is not None:
        parts.append(tr("Slowest around {hour}:00").format(hour=f"{summary.worst_hour:02d}"))
    return " · ".join(parts)


def report_rows(report: netquality.ConnectivityReport) -> list[tuple[bool | None, str]]:
    """Test adımları: (başarılı mı — None: atlandı, metin)."""
    rows: list[tuple[bool | None, str]] = []
    gw = report.gateway_ping
    if not report.gateway:
        rows.append((False, tr("No router address was assigned")))
    elif gw is None or not gw.available:
        rows.append((None, tr("Router check skipped (the ping tool is not available)")))
    elif gw.received == 0:
        rows.append(
            (False, tr("The router ({gateway}) does not answer").format(gateway=report.gateway))
        )
    elif (gw.loss or 0.0) >= netquality.LOSSY_THRESHOLD:
        rows.append(
            (
                False,
                tr("The router ({gateway}) answers, but {percent}% of the tests were lost").format(
                    gateway=report.gateway, percent=round((gw.loss or 0.0) * 100)
                ),
            )
        )
    else:
        rows.append(
            (
                True,
                tr("The router ({gateway}) answers in {ms} ms").format(
                    gateway=report.gateway, ms=round(gw.avg_ms or 0)
                ),
            )
        )
    if report.nm_state == "portal":
        rows.append((False, tr("The network asks you to sign in first")))
    if report.dns_ok:
        rows.append((True, tr("Name lookup works ({ms} ms)").format(ms=round(report.dns_ms or 0))))
    elif report.dns_ok is False:
        rows.append((False, tr("Name lookup failed (DNS)")))
    if report.internet_ok:
        rows.append(
            (
                True,
                tr("The internet is reachable ({ms} ms)").format(ms=round(report.internet_ms or 0)),
            )
        )
    elif report.internet_ok is False:
        rows.append((False, tr("The internet could not be reached")))
    return rows


def diagnosis_text(code: str) -> str:
    return {
        "ok": tr("Everything looks fine: your connection works."),
        "no_address": tr(
            "You are connected, but no network address was assigned. Disconnect and connect "
            "again; if it keeps happening, restart the router."
        ),
        "gateway_down": tr(
            "Your computer cannot reach the router. Move closer to it or restart the router."
        ),
        "gateway_lossy": tr(
            "The connection to the router is unstable. Move closer to the router, or use its "
            "5 GHz network if it has one."
        ),
        "portal": tr("The network wants you to sign in first. Open a web browser to sign in."),
        "dns_failed": tr(
            "The router answers, but names cannot be looked up (a DNS problem). Wait a minute "
            "and try again, or restart the router."
        ),
        "internet_down": tr(
            "The router answers, but the internet cannot be reached. The problem is probably "
            "with the internet provider or the router's own connection."
        ),
        "slow": tr(
            "The connection works, but the router answers slowly. Move closer to the router."
        ),
    }.get(code, "")


# --- Kart ---


class QualityCard(Card):
    """Çizelge + özet + ölçüm anahtarı + "Bağlantıyı test et"."""

    ai_help_requested = Signal(str, str)  # (başlık, ayrıntı) → asistana sor

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._jobs = Jobs()
        self._gateway = ""
        self._connected = False
        self._last_refresh = 0.0
        self._loading = False
        self._testing = False
        self._report: netquality.ConnectivityReport | None = None

        header = QHBoxLayout()
        heading = QLabel(tr("Connection quality"), self)
        heading.setObjectName("H2")
        header.addWidget(heading)
        header.addStretch(1)
        self._test_btn = QPushButton(tr("Test connection"), self)
        self._test_btn.clicked.connect(self._run_test)
        header.addWidget(self._test_btn)
        self.layout.addLayout(header)

        # Test sonucu (başta gizli)
        self._result = QWidget(self)
        self._result.setObjectName("QualityResult")
        # Genel "QWidget" zemini kartın içinde şeritler gibi görünmesin
        self._result.setStyleSheet("QWidget#QualityResult { background: transparent; }")
        self._result_layout = QVBoxLayout(self._result)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(6)
        self._result.setVisible(False)
        self.layout.addWidget(self._result)

        self._summary = QLabel("", self)
        self._summary.setObjectName("Secondary")
        self._summary.setWordWrap(True)
        self._chart = QualityChart(self)
        self._hint = QLabel("", self)
        self._hint.setObjectName("Secondary")
        self._hint.setWordWrap(True)
        self.layout.addWidget(self._chart)
        self.layout.addWidget(self._summary)
        self.layout.addWidget(self._hint)

        self._measure = QCheckBox(tr("Measure my connection quality"), self)
        self._measure.toggled.connect(self._on_measure_toggled)
        self.layout.addWidget(self._measure)
        note = QLabel(
            tr(
                "While Linwas is running, it notes your signal strength and the delay to your "
                "router once a minute. Nothing leaves this computer, and the notes are deleted "
                "after 7 days."
            ),
            self,
        )
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        self.layout.addWidget(note)
        self._chart.setVisible(False)
        self._summary.setVisible(False)
        self._update_test_button()

    # --- Dışarıdan ---

    def set_connection(self, connected: bool, gateway: str) -> None:
        """Wi-Fi sekmesi her yüklemede çağırır; bağlantı kalktıysa eski test sonucu silinir."""
        was = self._connected
        self._connected, self._gateway = connected, gateway
        if was and not connected:
            self._clear_result()
        self._update_test_button()
        self.refresh()

    def refresh(self, force: bool = False) -> None:
        """Geçmişi diskten yükler (en çok dakikada bir)."""
        if self._loading or (not force and time.monotonic() - self._last_refresh < REFRESH_SECONDS):
            return
        self._loading = True
        self._jobs.run(history_for_chart, self._on_history)

    # --- Geçmiş ---

    def _on_history(self, result: object) -> None:
        self._loading = False
        self._last_refresh = time.monotonic()
        if not isinstance(result, tuple):
            return
        buckets, summary = result
        measuring = app_settings.load().net_measure
        self._measure.blockSignals(True)
        self._measure.setChecked(measuring)
        self._measure.blockSignals(False)
        enough = summary.samples >= MIN_SAMPLES
        self._chart.setVisible(enough)
        self._summary.setVisible(enough)
        if enough:
            text = summary_text(summary)
            self._chart.set_buckets(buckets, BUCKET_SECONDS, text)
            self._summary.setText(tr("Last 24 hours") + " — " + text)
            self._hint.setVisible(not measuring)
            self._hint.setText(tr("Measuring is off, so no new notes are added."))
        else:
            self._hint.setVisible(True)
            self._hint.setText(
                tr("The chart appears after a few minutes of measuring.")
                if measuring
                else tr("Turn on measuring to see how your connection did over the last 24 hours.")
            )

    def _on_measure_toggled(self, on: bool) -> None:
        settings = app_settings.load()
        settings.net_measure = on
        app_settings.save(settings)
        netquality.SAMPLER.set_enabled(on)
        self.refresh(force=True)

    # --- Bağlantı testi ---

    def _update_test_button(self) -> None:
        can = self._connected and not self._testing
        self._test_btn.setEnabled(can)
        self._test_btn.setToolTip(
            "" if self._connected else tr("Connect to a Wi-Fi network first.")
        )
        self._test_btn.setText(tr("Testing…") if self._testing else tr("Test connection"))

    def _run_test(self) -> None:
        if self._testing or not self._connected:
            return
        self._testing = True
        self._update_test_button()
        gateway = self._gateway
        self._jobs.run(lambda: netquality.run_connectivity_test(gateway), self._on_report)

    def _on_report(self, result: object) -> None:
        self._testing = False
        self._update_test_button()
        if isinstance(result, netquality.ConnectivityReport):
            self._report = result
            self._show_report(result)

    def _clear_result(self) -> None:
        self._report = None
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    inner = item.layout().takeAt(0).widget()
                    if inner is not None:
                        inner.deleteLater()
        self._result.setVisible(False)

    def _show_report(self, report: netquality.ConnectivityReport) -> None:
        self._clear_result()
        self._report = report
        for ok, text in report_rows(report):
            row = QHBoxLayout()
            row.setSpacing(8)
            mark = QLabel(self._result)
            mark.setFixedSize(16, 16)
            if ok is None:
                mark.setText("–")
                mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                icons.bind(mark, "check" if ok else "close", "success" if ok else "danger", 14)
            label = QLabel(text, self._result)
            label.setWordWrap(True)
            row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label, 1)
            self._result_layout.addLayout(row)
        verdict = QLabel(diagnosis_text(report.diagnosis), self._result)
        verdict.setWordWrap(True)
        font = verdict.font()
        font.setBold(True)
        verdict.setFont(font)
        self._result_layout.addWidget(verdict)
        if report.diagnosis != "ok":
            ask = QPushButton(tr("Ask the assistant"), self._result)
            ask.clicked.connect(
                lambda: self.ai_help_requested.emit(tr("Connection test"), report.as_text())
            )
            wrap = QHBoxLayout()
            wrap.addWidget(ask)
            wrap.addStretch(1)
            self._result_layout.addLayout(wrap)
        self._result.setVisible(True)
