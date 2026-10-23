"""Ağ önerileri ve gölge kipi: kural, tahmin, sonuçlandırma, isabet oranı (Qt'siz)."""

import pytest

from linwas.core import app_settings, netadvice
from linwas.core.netadvice import RULE_BT, RULE_WIFI, Advice
from linwas.core.netlog import KIND_BT, KIND_WIFI, Sample

T0 = 1_700_000_000
DAY = 86400


def wifi_series(name, start, count, drops=(), signal=40, rtt=50.0, step=60):
    """`count` dakikalık bağlı Wi-Fi ölçümü; `drops` sıra numaralarında bağlantı kopar."""
    out = []
    for i in range(count):
        ts = start + i * step
        if i in drops:
            out.append(Sample(ts=ts, kind=KIND_WIFI, name="", connected=False))
        else:
            out.append(
                Sample(ts=ts, kind=KIND_WIFI, name=name, connected=True, signal=signal, rtt_ms=rtt)
            )
    return out


def bt_series(mac, name, start, count, drops=(), icon="audio-headset", user_drops=(), step=60):
    out = []
    for i in range(count):
        ts = start + i * step
        connected = i not in drops and i not in user_drops
        out.append(
            Sample(
                ts=ts, kind=KIND_BT, name=name, ident=mac, connected=connected, icon=icon,
                user=i in user_drops,
            )
        )  # fmt: skip
    return out


# --- Kural ---


def test_wifi_advice_needs_enough_drops_and_data():
    unstable = wifi_series("Kafe", T0, 40, drops={5, 12, 20, 30}, signal=30, rtt=80.0)
    (advice,) = netadvice.find_advice(unstable)
    assert (advice.rule, advice.subject, advice.name) == (RULE_WIFI, "Kafe", "Kafe")
    assert advice.drops == 4 and advice.samples == 36  # kopuk örnekler ağa yazılmaz
    assert advice.avg_signal == 30 and advice.avg_rtt_ms == pytest.approx(80.0)
    # az kopma
    assert netadvice.find_advice(wifi_series("Kafe", T0, 40, drops={5, 12})) == []
    # yeterli kopma ama veri az
    assert netadvice.find_advice(wifi_series("Kafe", T0, 20, drops={3, 6, 9, 12})) == []


def test_user_disconnects_and_gaps_do_not_count():
    series = wifi_series("Ev", T0, 40, drops={5, 12})
    series[20] = Sample(ts=series[20].ts, kind=KIND_WIFI, name="", connected=False, user=True)
    series[30] = Sample(ts=series[30].ts, kind=KIND_WIFI, name="", connected=False, user=True)
    assert netadvice.find_advice(series) == []  # 2 gerçek kopma + 2 kullanıcı kesmesi
    # her blok: 10 bağlı ölçüm, 6 saat sessizlik, sonra "bağlı değil": uzun boşlukta kopma sayılmaz
    gappy = []
    for day in range(4):
        start = T0 + day * DAY
        gappy += wifi_series("Ev", start, 10)
        gappy.append(Sample(ts=start + 6 * 3600, kind=KIND_WIFI, name="", connected=False))
    assert len(gappy) >= netadvice.MIN_SAMPLES and netadvice.find_advice(gappy) == []


def test_networks_are_judged_separately_and_sorted_by_drops():
    ev = wifi_series("Ev", T0, 60, drops={5, 15, 25, 35, 45})
    kafe = wifi_series("Kafe", T0 + 2 * DAY, 40, drops={5, 15, 25})
    sakin = wifi_series("Okul", T0 + 4 * DAY, 60, drops={10})
    found = netadvice.find_advice(ev + kafe + sakin)
    assert [(a.name, a.drops) for a in found] == [("Ev", 5), ("Kafe", 3)]


def test_bluetooth_advice_skips_sleepy_devices_and_user_disconnects():
    headset = bt_series("AA", "Kulaklık", T0, 40, drops={5, 15, 25})
    mouse = bt_series("BB", "Fare", T0, 40, drops={5, 15, 25}, icon="input-mouse")
    calm = bt_series("CC", "Hoparlör", T0, 40, user_drops={5, 15, 25})  # hep kendisi kesti
    (advice,) = netadvice.find_advice(headset + mouse + calm)
    assert (advice.rule, advice.subject, advice.name, advice.drops) == (
        RULE_BT, "AA", "Kulaklık", 3,
    )  # fmt: skip
    assert advice.avg_signal is None
    assert (
        netadvice.find_advice(bt_series("AA", "Kulaklık", T0, 20, drops={3, 6, 9})) == []
    )  # az veri


# --- Kayıt ve tahmin ---


def test_predict_writes_one_prediction_per_subject_per_day(tmp_path):
    path = tmp_path / "advice.jsonl"
    a = Advice(RULE_WIFI, "Kafe", "Kafe", 4, 40)
    b = Advice(RULE_BT, "AA", "Kulaklık", 3, 40)
    assert netadvice.predict([a, b], T0, path) == 2
    assert netadvice.predict([a, b], T0 + 3600, path) == 0  # aynı gün tekrar yazılmaz
    assert netadvice.predict([a], T0 + DAY + 60, path) == 1  # ertesi gün yeniden
    kinds = [(r["type"], r["rule"], r["subject"]) for r in netadvice._load(path)]
    assert kinds.count(("predict", RULE_WIFI, "Kafe")) == 2 and len(kinds) == 3


def test_load_tolerates_garbage_and_wrong_types(tmp_path):
    path = tmp_path / "advice.jsonl"
    path.write_text(
        '{"type":"predict","ts":5,"rule":"r","subject":"s"}\n'
        "bozuk\n"
        '{"type":"predict","ts":"5","rule":"r","subject":"s"}\n'  # ts dize
        '{"type":"predict","ts":true,"rule":"r","subject":"s"}\n'  # ts mantıksal
        '{"type":"yabanci","ts":5,"rule":"r","subject":"s"}\n'
        '{"type":"dismiss","ts":6,"rule":"r"}\n'  # subject yok
        "[1,2]\n",
        encoding="utf-8",
    )
    assert [r["ts"] for r in netadvice._load(path)] == [5]
    assert netadvice._load(tmp_path / "yok.jsonl") == []


def test_prune_removes_old_and_broken_lines(tmp_path):
    path = tmp_path / "advice.jsonl"
    old = T0 - 8 * DAY
    path.write_text(
        f'{{"type":"predict","ts":{old},"rule":"r","subject":"eski"}}\n'
        f'{{"type":"predict","ts":{T0},"rule":"r","subject":"yeni"}}\n'
        "bozuk\n",
        encoding="utf-8",
    )
    assert netadvice.prune(T0, path) == 2
    assert [r["subject"] for r in netadvice._load(path)] == ["yeni"]
    assert netadvice.prune(T0, path) == 0
    assert netadvice.prune(T0, tmp_path / "yok.jsonl") == 0


# --- Gölge kipi: değerlendirme ---


def prediction(rule, subject, ts):
    return {"type": "predict", "ts": ts, "rule": rule, "subject": subject}


def test_judge_wifi_hit_miss_and_skip():
    p = prediction(RULE_WIFI, "Kafe", T0)
    after = T0 + 600
    assert netadvice.judge(p, wifi_series("Kafe", after, 30, drops={10})) == "hit"
    assert netadvice.judge(p, wifi_series("Kafe", after, 30)) == "miss"
    assert netadvice.judge(p, wifi_series("Kafe", after, 5, drops={2})) == "skip"  # az veri
    # kullanıcı başka ağdaydı: o ağın kopması bu tahmini etkilemez, izlenemedi sayılır
    assert netadvice.judge(p, wifi_series("Ev", after, 30, drops={10})) == "skip"
    # ufuğun dışındaki ölçümler sayılmaz
    outside = wifi_series("Kafe", T0 + DAY + 60, 30, drops={10})
    assert netadvice.judge(p, outside) == "skip"


def test_judge_bluetooth():
    p = prediction(RULE_BT, "AA", T0)
    after = T0 + 600
    assert netadvice.judge(p, bt_series("AA", "K", after, 30, drops={10})) == "hit"
    assert netadvice.judge(p, bt_series("AA", "K", after, 30)) == "miss"
    assert netadvice.judge(p, bt_series("BB", "K", after, 30, drops={10})) == "skip"
    assert netadvice.judge(p, bt_series("AA", "K", after, 30, user_drops={10})) == "miss"


def test_settle_waits_for_the_horizon_and_is_idempotent(tmp_path):
    path = tmp_path / "advice.jsonl"
    netadvice.predict([Advice(RULE_WIFI, "Kafe", "Kafe", 4, 40)], T0, path)
    samples = wifi_series("Kafe", T0 + 600, 40, drops={10})
    assert netadvice.settle(samples, T0 + DAY - 1, path) == 0  # ufuk dolmadı
    assert netadvice.settle(samples, T0 + DAY + 1, path) == 1
    assert netadvice.settle(samples, T0 + DAY + 2, path) == 0  # yeniden sonuçlanmaz
    outcomes = [r for r in netadvice._load(path) if r["type"] == "outcome"]
    assert [(r["result"], r["predicted_at"]) for r in outcomes] == [("hit", T0)]


def test_track_record_ignores_skips_and_needs_a_minimum(tmp_path):
    path = tmp_path / "advice.jsonl"
    assert netadvice.track_record(RULE_WIFI, path) == netadvice.TrackRecord(0, 0)
    for i, result in enumerate(["hit", "hit", "miss", "skip"]):
        netadvice._append(
            {
                "type": "outcome", "ts": T0 + i, "rule": RULE_WIFI, "subject": f"n{i}",
                "predicted_at": T0, "result": result,
            },
            path,
        )  # fmt: skip
    netadvice._append(
        {"type": "outcome", "ts": T0, "rule": RULE_BT, "subject": "AA", "result": "hit"}, path
    )
    record = netadvice.track_record(RULE_WIFI, path)
    assert (record.hits, record.total, record.known) == (2, 3, True)
    bt = netadvice.track_record(RULE_BT, path)
    assert (bt.hits, bt.total, bt.known) == (1, 1, False)  # 3'ten az: oran gösterilmez


# --- "Şimdi değil" ---


def test_dismiss_silences_one_subject_for_a_week(tmp_path):
    path = tmp_path / "advice.jsonl"
    netadvice.dismiss(RULE_WIFI, "Kafe", T0, path)
    assert netadvice.is_dismissed(RULE_WIFI, "Kafe", T0 + 3600, path)
    assert not netadvice.is_dismissed(RULE_WIFI, "Ev", T0 + 3600, path)  # başka ağ
    assert not netadvice.is_dismissed(RULE_BT, "Kafe", T0 + 3600, path)  # başka kural
    assert not netadvice.is_dismissed(RULE_WIFI, "Kafe", T0 + 7 * DAY + 1, path)  # süre doldu


# --- Uçtan uca ---


def test_run_shadow_predicts_then_settles_and_a_hit_builds_the_track_record(tmp_path):
    path = tmp_path / "advice.jsonl"
    day1 = wifi_series("Kafe", T0, 40, drops={5, 12, 20})
    netadvice.run_shadow(T0 + 3000, path, load_samples=lambda since=None: day1)
    assert [r["type"] for r in netadvice._load(path)] == ["predict"]  # sessizce tahmin

    # ertesi gün: kullanıcı aynı ağda, yine kopma var
    day2 = day1 + wifi_series("Kafe", T0 + DAY, 40, drops={7, 14, 21})
    netadvice.run_shadow(T0 + DAY + 4000, path, load_samples=lambda since=None: day2)
    records = netadvice._load(path)
    types = [r["type"] for r in records]
    assert types.count("outcome") == 1 and types.count("predict") == 2
    assert [r["result"] for r in records if r["type"] == "outcome"] == ["hit"]
    assert netadvice.track_record(RULE_WIFI, path).hits == 1


def test_run_shadow_without_advice_writes_nothing(tmp_path):
    path = tmp_path / "advice.jsonl"
    calm = wifi_series("Ev", T0, 60)
    netadvice.run_shadow(T0 + 4000, path, load_samples=lambda since=None: calm)
    assert not path.exists()


@pytest.fixture
def consent(monkeypatch):
    state = {"on": True}
    monkeypatch.setattr(
        app_settings, "load", lambda path=None: app_settings.AppSettings(net_measure=state["on"])
    )
    return state


def test_current_requires_consent_and_hides_dismissed(tmp_path, consent):
    path = tmp_path / "advice.jsonl"
    samples = (
        wifi_series("Kafe", T0, 40, drops={5, 12, 20, 30})
        + wifi_series("Ev", T0 + 2 * DAY, 40, drops={5, 12, 20})
        + bt_series("AA", "Kulaklık", T0 + 4 * DAY, 40, drops={5, 12, 20})
    )

    def load(since=None):
        return samples

    now = T0 + 5 * DAY
    wifi = netadvice.current(RULE_WIFI, now, path, load)
    assert [a.name for a, _record in wifi] == ["Kafe", "Ev"]  # çok kopandan aza
    assert [a.name for a, _record in netadvice.current(RULE_BT, now, path, load)] == ["Kulaklık"]

    netadvice.dismiss(RULE_WIFI, "Kafe", now, path)
    assert [a.name for a, _r in netadvice.current(RULE_WIFI, now, path, load)] == ["Ev"]

    consent["on"] = False  # ölçüm kapalı: eski notlardan öneri gösterilmez
    assert netadvice.current(RULE_WIFI, now, path, load) == []


def test_current_attaches_the_track_record_and_limits_the_count(tmp_path, consent):
    path = tmp_path / "advice.jsonl"
    samples = []
    for i, name in enumerate(["A", "B", "C"]):
        samples += wifi_series(name, T0 + i * 2 * DAY, 40, drops={5, 12, 20})
    for i in range(3):
        netadvice._append(
            {
                "type": "outcome", "ts": T0, "rule": RULE_WIFI, "subject": f"x{i}",
                "predicted_at": T0, "result": "hit" if i < 2 else "miss",
            },
            path,
        )  # fmt: skip
    shown = netadvice.current(RULE_WIFI, T0 + 7 * DAY, path, lambda since=None: samples)
    assert len(shown) == netadvice.MAX_SHOWN  # süzülmüş: en çok iki öneri
    assert all((r.hits, r.total) == (2, 3) for _a, r in shown)
