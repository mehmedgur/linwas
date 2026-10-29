# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Ağ önerileri ve gölge kipi: kanıta dayalı, geri alınabilir, ölçülmüş. Qt'ye bağımlı değildir.

Öneri bir işlem yapmaz; ilgili ayar penceresini açar, değişiklik orada kullanıcının onayıyla yapılır
ve orada geri alınır. Her öneri "Neden?" bölümünde kanıtını (sayılar), kuralını ve geçmiş isabetini
gösterir. Öneriler yalnızca ölçüm açıkken (`net_measure`) ve ölçüm kaydından (`netlog`) çıkar.

**Gölge kipi:** kural, öneri gösterilsin ya da gösterilmesin, günde en çok bir kez sessizce "bu
ağ/cihaz yarın da kopacak" diye *tahmin* yazar; 24 saat sonra gerçek ölçümle karşılaştırılır
(tuttu / tutmadı / izlenemedi). İsabet oranı önerinin "Neden?" bölümünde görünür; böylece kuralın
bu kullanıcının ağında işe yarayıp yaramadığı varsayılmaz, ölçülür.

Dosya: ~/.local/share/linwas/net_advice.jsonl — her satır bir kayıt: tahmin ("predict"), sonuç
("outcome") ya da "Şimdi değil" ("dismiss"). Ölçüm kaydıyla aynı süre (7 gün), aynı rıza ve silme.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from linwas.core import app_settings, netlog, user_data
from linwas.core.netlog import KIND_BT, KIND_WIFI, Sample

FILE_NAME = "net_advice.jsonl"

RULE_WIFI = "wifi_unstable"  # kayıtlı bir ağ sık kopuyor
RULE_BT = "bt_unstable"  # bir Bluetooth cihazı sık kopuyor

MIN_DROPS = 3  # son 7 günde bu kadar kopma → öneri
MIN_SAMPLES = 30  # bundan az ölçümle öneri yok (veri yetersiz)
HORIZON = 24 * 3600  # tahmin ufku: bir sonraki gün
MIN_FOLLOWUP = 10  # tahmini değerlendirmek için ufukta en az bu kadar ölçüm
HIT_DROPS = 1  # ufukta en az bu kadar kopma → tahmin tuttu
PREDICT_EVERY = 24 * 3600  # aynı konu için günde en çok bir tahmin
DISMISS_SECONDS = netlog.RETENTION_DAYS * 86400  # "Şimdi değil" bir hafta susturur
MIN_TRACK = 3  # isabet oranını göstermek için en az değerlendirilmiş tahmin
MAX_SHOWN = 2  # kartta en çok bu kadar öneri (süzülmüş görünüm)

# Boştayken kendiliğinden uyuyan/kopan cihazlar: kopma bir arıza değildir, öneri çıkmaz
SLEEPY_ICONS = ("input-mouse", "input-keyboard", "input-tablet", "input-gaming")


def default_path() -> Path:
    return user_data.data_dir() / FILE_NAME


@dataclass(frozen=True)
class Advice:
    rule: str  # RULE_WIFI | RULE_BT
    subject: str  # Wi-Fi: ağ adı; Bluetooth: cihaz adresi (MAC)
    name: str  # gösterilecek ad
    drops: int  # son 7 günde kopma sayısı
    samples: int  # bu konuda kaç ölçüm var
    avg_signal: int | None = None  # Wi-Fi: ortalama sinyal (%)
    avg_rtt_ms: float | None = None  # Wi-Fi: ağ geçidine ortalama gecikme


@dataclass(frozen=True)
class TrackRecord:
    """Bu tür önerilerin geçmiş isabeti: tahmin tuttu mu (ertesi gün sorun sürdü mü)."""

    hits: int = 0
    total: int = 0

    @property
    def known(self) -> bool:
        return self.total >= MIN_TRACK


# --- Kural ---


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def find_advice(samples: list[Sample], interval: int = netlog.DEFAULT_INTERVAL) -> list[Advice]:
    """Ölçümlerden öneriler; çok kopandan aza. Yeterince veri ve en az `MIN_DROPS` kopma gerekir."""
    found: list[Advice] = []
    wifi = [s for s in samples if s.kind == KIND_WIFI]
    drops = Counter(name for name, _kind in netlog.wifi_drops(wifi, interval) if name)
    for name, count in drops.items():
        group = [s for s in wifi if s.name == name]
        if count < MIN_DROPS or len(group) < MIN_SAMPLES:
            continue
        signal = _mean([s.signal for s in group if s.connected and s.signal is not None])
        rtt = _mean([s.rtt_ms for s in group if s.connected and s.rtt_ms is not None])
        found.append(
            Advice(
                RULE_WIFI,
                name,
                name,
                count,
                len(group),
                avg_signal=None if signal is None else round(signal),
                avg_rtt_ms=rtt,
            )
        )
    devices: dict[str, list[Sample]] = {}
    for s in samples:
        if s.kind == KIND_BT and s.ident:
            devices.setdefault(s.ident, []).append(s)
    for ident, group in devices.items():
        if any(s.icon in SLEEPY_ICONS for s in group):
            continue
        summary = netlog.summarize_bluetooth(group, ident, interval)
        if summary.disconnects >= MIN_DROPS and summary.samples >= MIN_SAMPLES:
            name = next((s.name for s in reversed(group) if s.name), ident)
            found.append(Advice(RULE_BT, ident, name, summary.disconnects, summary.samples))
    return sorted(found, key=lambda a: (-a.drops, a.subject))


# --- Kayıt (tahmin, sonuç, "Şimdi değil") ---


def _append(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _parse(line: str) -> dict[str, Any] | None:
    """Geçerli kayıt ya da None (bozuk JSON, bilinmeyen tür, eksik/yanlış tipli alan)."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if (
        isinstance(data, dict)
        and data.get("type") in ("predict", "outcome", "dismiss")
        and isinstance(data.get("ts"), int)
        and not isinstance(data.get("ts"), bool)
        and isinstance(data.get("rule"), str)
        and isinstance(data.get("subject"), str)
    ):
        return data
    return None


def _load(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or default_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [record for record in map(_parse, lines) if record is not None]


def prune(now: int | None = None, path: Path | None = None) -> int:
    """Saklama süresinden eski (ve bozuk) satırları siler; silinen satır sayısını döndürür."""
    target = path or default_path()
    cutoff = (int(time.time()) if now is None else now) - netlog.RETENTION_DAYS * 86400
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    kept = [
        line for line in lines if (record := _parse(line)) is not None and record["ts"] >= cutoff
    ]
    removed = len(lines) - len(kept)
    if removed:
        try:
            tmp = target.with_suffix(".tmp")
            tmp.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            return 0
    return removed


def judge(
    prediction: dict[str, Any], samples: list[Sample], interval: int = netlog.DEFAULT_INTERVAL
) -> str:
    """Tahmini ertesi günün ölçümleriyle karşılaştırır: "hit" | "miss" | "skip".

    "skip": kullanıcı o ağı/cihazı kullanmadı ya da ölçüm yetersiz; isabet oranına girmez.
    """
    t0 = int(prediction["ts"])
    subject = str(prediction["subject"])
    window = [s for s in samples if t0 < s.ts <= t0 + HORIZON]
    if prediction["rule"] == RULE_WIFI:
        wifi = [s for s in window if s.kind == KIND_WIFI]
        followed = sum(1 for s in wifi if s.name == subject and s.connected)
        drops = sum(1 for name, _k in netlog.wifi_drops(wifi, interval) if name == subject)
    else:
        device = [s for s in window if s.kind == KIND_BT and s.ident == subject]
        followed = len(device)
        drops = netlog.summarize_bluetooth(device, subject, interval).disconnects
    if followed < MIN_FOLLOWUP:
        return "skip"
    return "hit" if drops >= HIT_DROPS else "miss"


def predict(advice: list[Advice], now: int, path: Path | None = None) -> int:
    """Her öneri için günde en çok bir tahmin yazar; yazılan tahmin sayısını döndürür."""
    records = _load(path)
    written = 0
    for item in advice:
        recent = any(
            r["type"] == "predict"
            and r["rule"] == item.rule
            and r["subject"] == item.subject
            and int(r["ts"]) > now - PREDICT_EVERY
            for r in records
        )
        if not recent:
            _append(
                {
                    "type": "predict",
                    "ts": now,
                    "rule": item.rule,
                    "subject": item.subject,
                    "drops": item.drops,
                },
                path,
            )
            written += 1
    return written


def settle(samples: list[Sample], now: int, path: Path | None = None) -> int:
    """Ufku dolan ve henüz sonuçlanmamış tahminleri gerçekle karşılaştırır; sonuç sayısı döner."""
    records = _load(path)
    settled = {
        (r["rule"], r["subject"], r.get("predicted_at")) for r in records if r["type"] == "outcome"
    }
    written = 0
    for r in records:
        if r["type"] != "predict" or int(r["ts"]) + HORIZON > now:
            continue
        if (r["rule"], r["subject"], r["ts"]) in settled:
            continue
        _append(
            {
                "type": "outcome",
                "ts": now,
                "rule": r["rule"],
                "subject": r["subject"],
                "predicted_at": r["ts"],
                "result": judge(r, samples),
            },
            path,
        )
        written += 1
    return written


def track_record(rule: str, path: Path | None = None) -> TrackRecord:
    """Bu kuralın sonuçlanmış tahminleri (izlenemeyenler sayılmaz)."""
    results = [r.get("result") for r in _load(path) if r["type"] == "outcome" and r["rule"] == rule]
    hits = results.count("hit")
    return TrackRecord(hits=hits, total=hits + results.count("miss"))


def dismiss(rule: str, subject: str, now: int | None = None, path: Path | None = None) -> None:
    """ "Şimdi değil": bu öneri bir hafta gösterilmez."""
    ts = int(time.time()) if now is None else now
    _append({"type": "dismiss", "ts": ts, "rule": rule, "subject": subject}, path)


def is_dismissed(rule: str, subject: str, now: int | None = None, path: Path | None = None) -> bool:
    ts = int(time.time()) if now is None else now
    return any(
        r["type"] == "dismiss"
        and r["rule"] == rule
        and r["subject"] == subject
        and int(r["ts"]) > ts - DISMISS_SECONDS
        for r in _load(path)
    )


# --- Uygulamanın kullandığı giriş noktaları ---


def run_shadow(
    now: int | None = None,
    path: Path | None = None,
    load_samples: Callable[..., list[Sample]] = netlog.load,
) -> None:
    """Örnekleyici saatte bir çağırır: eski tahminleri sonuçlandırır, yenilerini sessizce yazar."""
    ts = int(time.time()) if now is None else now
    samples = load_samples(since=ts - netlog.RETENTION_DAYS * 86400)
    settle(samples, ts, path)
    predict(find_advice(samples), ts, path)
    prune(ts, path)


def current(
    rule: str,
    now: int | None = None,
    path: Path | None = None,
    load_samples: Callable[..., list[Sample]] = netlog.load,
) -> list[tuple[Advice, TrackRecord]]:
    """Gösterilecek öneriler ("Şimdi değil" denmemiş) ve kuralın isabeti; ölçüm kapalıysa boş."""
    if not app_settings.load().net_measure:
        return []
    ts = int(time.time()) if now is None else now
    samples = load_samples(since=ts - netlog.RETENTION_DAYS * 86400)
    record = track_record(rule, path)
    return [
        (item, record)
        for item in find_advice(samples)
        if item.rule == rule and not is_dismissed(item.rule, item.subject, ts, path)
    ][:MAX_SHOWN]
