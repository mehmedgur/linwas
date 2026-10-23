"""Ağ kalitesi kaydı: saklama, dilimleme ve özetleme (Qt'siz)."""

import json

import pytest

from linwas.core import netlog
from linwas.core.netlog import KIND_BT, KIND_WIFI, Sample

T0 = 1_700_000_000  # sabit başlangıç (saniye)


def wifi(ts, rtt=10.0, loss=0.0, connected=True, user=False, name="Ev", signal=70):
    return Sample(
        ts=ts, kind=KIND_WIFI, name=name, connected=connected, signal=signal,
        rtt_ms=rtt, loss=loss, user=user,
    )  # fmt: skip


def test_sample_from_dict_rejects_bad_rows_and_fixes_types():
    assert Sample.from_dict("x") is None
    assert Sample.from_dict({"ts": True, "kind": "wifi"}) is None
    assert Sample.from_dict({"ts": 1, "kind": "ses"}) is None
    s = Sample.from_dict({"ts": 5, "kind": "wifi", "name": 7, "rtt_ms": "x", "connected": "evet"})
    assert s is not None
    assert (s.name, s.rtt_ms, s.connected) == ("", None, True)  # yanlış tipler varsayılana döner


def test_append_load_roundtrip_filters_and_skips_bad_lines(tmp_path):
    path = tmp_path / "q.jsonl"
    netlog.append(wifi(T0 + 60), path)
    netlog.append(Sample(ts=T0 + 30, kind=KIND_BT, name="Kulaklık", ident="AA", battery=80), path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write('bozuk satır\n{"ts": 1}\n')
    all_samples = netlog.load(path=path)
    assert [s.ts for s in all_samples] == [T0 + 30, T0 + 60]  # zamana göre sıralı
    assert [s.kind for s in netlog.load(kind=KIND_WIFI, path=path)] == [KIND_WIFI]
    assert [s.ts for s in netlog.load(since=T0 + 50, path=path)] == [T0 + 60]
    assert netlog.load(path=tmp_path / "yok.jsonl") == []


def test_prune_drops_old_samples(tmp_path):
    path = tmp_path / "q.jsonl"
    old = T0 - (netlog.RETENTION_DAYS + 1) * 86400
    for ts in (old, T0 - 60, T0):
        netlog.append(wifi(ts), path)
    assert netlog.prune(now=T0, path=path) == 1
    assert [s.ts for s in netlog.load(path=path)] == [T0 - 60, T0]
    assert netlog.prune(now=T0, path=path) == 0
    assert netlog.prune(now=T0, path=tmp_path / "yok.jsonl") == 0


def test_stored_line_is_compact_json(tmp_path):
    path = tmp_path / "q.jsonl"
    netlog.append(wifi(T0), path)
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["kind"] == "wifi" and row["name"] == "Ev" and "\n" not in path.read_text().strip()


@pytest.mark.parametrize(
    ("rtt", "loss", "state"),
    [
        (5.0, 0.0, "good"),
        (50.0, 0.0, "fair"),
        (200.0, 0.0, "bad"),
        (5.0, 0.05, "fair"),
        (5.0, 0.5, "bad"),
        (None, 1.0, "bad"),
        (None, None, "unknown"),
    ],
)
def test_classify(rtt, loss, state):
    assert netlog.classify(rtt, loss) == state


def test_bucketize_states_and_gaps():
    start, size = T0, 900
    samples = [
        wifi(start + 10, rtt=5),
        wifi(start + 20, rtt=300),  # aynı dilimde en kötüsü sayılır
        wifi(start + 900 + 10, connected=False, rtt=None, loss=None),
        wifi(start + 1800 + 10, connected=False, user=True, rtt=None, loss=None),
    ]
    b = netlog.bucketize(samples, start, start + 4 * size, size)
    assert [x.state for x in b] == ["bad", "offline", "nodata", "nodata"]
    assert b[0].rtt_ms == 300 or b[0].rtt_ms == 5  # ortanca (iki örnek)
    assert b[0].signal == 70
    assert netlog.bucketize(samples, start, start, size) == []
    assert netlog.bucketize(samples, start, start + 10, 0) == []


def test_summarize_wifi_counts_disconnects_stalls_and_ignores_gaps_and_user_actions():
    s = [
        wifi(T0, rtt=10),
        wifi(T0 + 60, connected=False, rtt=None, loss=None),  # kopma 1
        wifi(T0 + 120, rtt=12),
        wifi(T0 + 180, rtt=None, loss=1.0),  # takılma 1
        wifi(T0 + 240, rtt=None, loss=1.0),  # aynı takılma
        wifi(T0 + 300, rtt=20),
        wifi(T0 + 360, connected=False, user=True, rtt=None, loss=None),  # kullanıcı kesti
        wifi(T0 + 5000, rtt=15),  # büyük boşluk: kopma sayılmaz
        wifi(T0 + 5060, connected=False, rtt=None, loss=None),  # kopma 2
    ]
    sm = netlog.summarize_wifi(s)
    assert (sm.disconnects, sm.stalls) == (2, 1)
    assert sm.samples == 9 and sm.networks == ("Ev",)
    assert sm.avg_rtt_ms == pytest.approx((10 + 12 + 20 + 15) / 4)
    assert sm.p95_rtt_ms == 20
    empty = netlog.summarize_wifi([])
    assert (empty.samples, empty.avg_rtt_ms, empty.p95_rtt_ms, empty.worst_hour) == (
        0,
        None,
        None,
        None,
    )


def test_summarize_wifi_worst_hour_needs_two_hours():
    one_hour = [wifi(T0 + i * 60, rtt=10) for i in range(5)]
    assert netlog.summarize_wifi(one_hour).worst_hour is None
    two = [wifi(T0, rtt=10), wifi(T0 + 7200, rtt=90)]
    hour = netlog.summarize_wifi(two, utc_offset=0).worst_hour
    assert hour == ((T0 + 7200) // 3600) % 24
    shifted = netlog.summarize_wifi(two, utc_offset=3 * 3600).worst_hour
    assert shifted == ((T0 + 7200 + 3 * 3600) // 3600) % 24


def bt(ts, connected=True, battery=None, user=False, ident="AA"):
    return Sample(
        ts=ts, kind=KIND_BT, name="Kulaklık", ident=ident, connected=connected,
        battery=battery, user=user,
    )  # fmt: skip


def test_summarize_bluetooth():
    s = [
        bt(T0, battery=90),
        bt(T0 + 60, connected=False),  # kopma
        bt(T0 + 120, battery=80),
        bt(T0 + 180, connected=False, user=True),  # kullanıcı kesti
        bt(T0 + 240, battery=70, ident="BB"),  # başka cihaz
    ]
    sm = netlog.summarize_bluetooth(s, "AA")
    assert (sm.samples, sm.disconnects, sm.last_battery, sm.battery_drop) == (4, 1, 80, 10)
    none = netlog.summarize_bluetooth([], "AA")
    assert (none.samples, none.last_battery, none.battery_drop) == (0, None, None)
