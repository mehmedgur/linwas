"""Bağlantı kalitesi kartı, çizelgesi ve metinleri (PySide6 gerektirir; yoksa atlanır)."""

import os

import pytest

from linwas.backend import netquality
from linwas.core import app_settings, netlog
from linwas.core.netlog import Bucket, Sample


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Ayar ve ölçüm dosyaları geçici klasörde; örnekleyici sahte."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    class FakeSampler:
        def __init__(self):
            self.calls = []

        def set_enabled(self, enabled):
            self.calls.append(enabled)

        def stop(self):
            self.calls.append("stop")

    fake = FakeSampler()
    monkeypatch.setattr(netquality, "SAMPLER", fake)
    return fake


def wait_until(condition, timeout=3.0):
    from PySide6.QtTest import QTest

    waited = 0
    while not condition() and waited < timeout * 1000:
        QTest.qWait(20)
        waited += 20
    return condition()


def test_every_diagnosis_code_has_text(qapp):
    from linwas.ui.pages.network_quality import diagnosis_text

    codes = ["ok", "no_address", "gateway_down", "gateway_lossy", "portal"]
    codes += ["dns_failed", "internet_down", "slow"]
    for code in codes:
        assert diagnosis_text(code), code
    assert diagnosis_text("bilinmeyen") == ""


def test_summary_text_pieces(qapp):
    from linwas.ui.pages.network_quality import summary_text

    full = netlog.WifiSummary(100, 2, 1, 18.4, 40.0, 0.01, 21, ("Ev",))
    text = summary_text(full)
    assert "Disconnections: 2" in text and "Router stopped answering: 1" in text
    assert "Average delay: 18 ms" in text and "Slowest around 21:00" in text
    bare = summary_text(netlog.WifiSummary(10, 0, 0, None, None, None, None, ()))
    assert bare == "Disconnections: 0"


def test_report_rows_cover_outcomes(qapp):
    from linwas.ui.pages.network_quality import report_rows

    ok = netquality.ConnectivityReport(
        gateway="192.168.1.1",
        gateway_ping=netquality.PingResult(True, 3, 3, [2.0, 3.0, 4.0]),
        nm_state="full",
        dns_ok=True,
        dns_ms=11.6,
        dns_addr="1.2.3.4",
        internet_ok=True,
        internet_ms=31.2,
    )
    rows = report_rows(ok)
    assert [r[0] for r in rows] == [True, True, True]
    assert "answers in 3 ms" in rows[0][1] and "(12 ms)" in rows[1][1]

    down = netquality.ConnectivityReport(
        gateway="192.168.1.1",
        gateway_ping=netquality.PingResult(True, 3, 0, []),
        dns_ok=False,
        diagnosis="gateway_down",
    )
    assert [r[0] for r in report_rows(down)] == [False, False]
    skipped = netquality.ConnectivityReport(
        gateway="10.0.0.1", gateway_ping=netquality.PingResult(False)
    )
    assert report_rows(skipped)[0][0] is None
    portal = netquality.ConnectivityReport(
        gateway="10.0.0.1", gateway_ping=netquality.PingResult(True, 3, 3, [1.0]), nm_state="portal"
    )
    assert any("sign in" in text for _, text in report_rows(portal))
    assert report_rows(netquality.ConnectivityReport(gateway=""))[0][0] is False


def test_history_for_chart_reads_last_24_hours(qapp, isolated):
    from linwas.ui.pages.network_quality import BUCKET_SECONDS, HISTORY_SECONDS, history_for_chart

    now = 1_700_000_000
    for i in range(10):
        netlog.append(Sample(ts=now - 600 + i * 60, kind="wifi", name="Ev", rtt_ms=5.0, loss=0.0))
    netlog.append(Sample(ts=now - HISTORY_SECONDS - 3600, kind="wifi", name="Eski"))  # kapsam dışı
    buckets, summary = history_for_chart(now)
    assert len(buckets) == HISTORY_SECONDS // BUCKET_SECONDS
    assert summary.samples == 10 and summary.networks == ("Ev",)
    assert buckets[-1].start + BUCKET_SECONDS > now  # son dilim şu anı kapsar


def test_chart_geometry_tooltip_and_render(qapp):
    from linwas.ui.widgets.quality_chart import QualityChart, bucket_tooltip

    chart = QualityChart()
    chart.resize(400, 80)
    start = 1_700_000_000 // 900 * 900
    states = ["good", "fair", "bad", "offline", "unknown", "nodata"]
    buckets = [Bucket(start + i * 900, st, rtt_ms=12.0, signal=70) for i, st in enumerate(states)]
    chart.set_buckets(buckets, 900, "özet")
    assert "özet" in chart.accessibleName()
    assert chart.bucket_at(0) == 0 and chart.bucket_at(399) == 5 and chart.bucket_at(500) is None
    tip = bucket_tooltip(buckets[1], 900)
    assert "Slow" in tip and "12 ms" in tip and "signal 70%" in tip
    assert not chart.grab().isNull()  # her durum çizilebiliyor
    empty = QualityChart()
    empty.set_buckets([], 900)
    assert empty.bucket_at(5) is None and not empty.grab().isNull()


def test_card_measure_toggle_persists_and_controls_sampler(qapp, isolated):
    from linwas.ui.pages.network_quality import QualityCard

    card = QualityCard()
    assert card._measure.isChecked() is False
    card._measure.setChecked(True)
    assert app_settings.load().net_measure is True and isolated.calls[-1] is True
    card._measure.setChecked(False)
    assert app_settings.load().net_measure is False and isolated.calls[-1] is False


def test_card_hint_and_chart_follow_data(qapp, isolated, monkeypatch):
    from linwas.ui.pages import network_quality

    card = network_quality.QualityCard()
    card.refresh(force=True)
    assert wait_until(lambda: card._hint.text() != "")
    assert card._chart.isHidden() and "Turn on measuring" in card._hint.text()

    now = 1_700_000_000
    for i in range(8):
        netlog.append(Sample(ts=now - i * 60, kind="wifi", name="Ev", rtt_ms=5.0, loss=0.0))
    real_history = network_quality.history_for_chart
    monkeypatch.setattr(network_quality, "history_for_chart", lambda: real_history(now))
    card.refresh(force=True)
    assert wait_until(lambda: not card._chart.isHidden())
    assert "Last 24 hours" in card._summary.text()
    assert "Measuring is off" in card._hint.text()  # veri var ama ölçüm kapalı


def test_card_connection_test_flow(qapp, isolated, monkeypatch):
    from linwas.ui.pages.network_quality import QualityCard

    card = QualityCard()
    assert not card._test_btn.isEnabled() and card._test_btn.toolTip()
    card.set_connection(True, "192.168.1.1")
    assert card._test_btn.isEnabled()

    report = netquality.ConnectivityReport(
        gateway="192.168.1.1",
        gateway_ping=netquality.PingResult(True, 3, 0, []),
        dns_ok=False,
        diagnosis="gateway_down",
    )
    seen = []
    monkeypatch.setattr(
        netquality, "run_connectivity_test", lambda gateway: seen.append(gateway) or report
    )
    asked = []
    card.ai_help_requested.connect(lambda title, text: asked.append((title, text)))
    card._test_btn.click()
    assert card._test_btn.text() == "Testing…" and not card._test_btn.isEnabled()
    assert wait_until(lambda: not card._result.isHidden())
    assert seen == ["192.168.1.1"] and card._test_btn.isEnabled()
    # Sonuçta "Asistana sor" düğmesi var ve ayrıntıyı iletir
    from PySide6.QtWidgets import QPushButton

    buttons = [b for b in card._result.findChildren(QPushButton) if b.text() == "Ask the assistant"]
    assert len(buttons) == 1
    buttons[0].click()
    assert asked and asked[0][0] == "Connection test" and "Diagnosis: gateway_down" in asked[0][1]
    # Bağlantı kopunca eski sonuç silinir
    card.set_connection(False, "")
    assert card._result.isHidden() and not card._test_btn.isEnabled()
